from __future__ import annotations
import os
import shutil
import logging
from datetime import timedelta
from typing import Any, Dict, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers.dispatcher import async_dispatcher_send, async_dispatcher_connect

from .const import (
    DOMAIN, NAME,
    CONF_FORWARD, CONF_REVERSE, CONF_INTERVAL_MIN, CONF_DIR,
    STORAGE_KEY_FMT, STORAGE_VERSION,
    CSV_HEADER,
    EVN_TIERS, EVN_SELL_PRICE,
    OPT_BUY_DAY, OPT_BUY_MONTH, OPT_BUY_YEAR,
    OPT_SELL_DAY, OPT_SELL_MONTH, OPT_SELL_YEAR,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


# -------------------- Setup entry --------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # Dùng data ban đầu (entry.data) để lấy config cơ bản
    data = dict(entry.data)
    forward = data[CONF_FORWARD]
    reverse = data[CONF_REVERSE]
    interval_min = int(data[CONF_INTERVAL_MIN])

    base_dir = data[CONF_DIR]

    # ==== Copy EVN chart files to /config/www/evn ====
    # Source: custom_components/evn/html/evn_chart.html & evn_chart.js
    # Target: /config/www/evn/evn_chart.html & evn_chart.js
    integration_dir = os.path.dirname(__file__)
    src_html_dir = os.path.join(integration_dir, "html")
    target_dir = hass.config.path("www", "evn")  # => /config/www/evn

    def _copy_static_files() -> None:
        try:
            os.makedirs(target_dir, exist_ok=True)
            for fname in ("evn_chart.html", "evn_chart.js"):
                src = os.path.join(src_html_dir, fname)
                dst = os.path.join(target_dir, fname)
                if not os.path.isfile(src):
                    _LOGGER.warning("EVN: source file not found: %s", src)
                    continue
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    _LOGGER.info("EVN: copied %s -> %s", src, dst)
        except Exception as err:
            _LOGGER.error("EVN: error copying static files: %s", err)

    await hass.async_add_executor_job(_copy_static_files)

    # ==== Tạo thư mục CSV ban đầu ====
    def _makedirs_sync(path: str):
        os.makedirs(path, exist_ok=True)

    await hass.async_add_executor_job(_makedirs_sync, base_dir)

    # CSV theo năm trong đúng thư mục đã cấu hình
    year = dt_util.now().strftime("%Y")
    csv_path = os.path.join(base_dir, f"{year}.csv")

    async def _ensure_csv(path: str):
        def _sync():
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(CSV_HEADER + "\n")

        await hass.async_add_executor_job(_sync)

    await _ensure_csv(csv_path)

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY_FMT.format(entry_id=entry.entry_id))
    stored = await store.async_load() or {}

    dj = DJRuntime(hass, entry, forward, reverse, csv_path, store, stored)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = dj

    async def _start_interval(minutes: int):
        if getattr(dj, "unsub", None):
            dj.unsub()

        @callback
        async def _tick(now):
            await dj.async_update(now)

        dj.unsub = async_track_time_interval(hass, _tick, timedelta(minutes=minutes))

    # Chạy 1 lần khi khởi tạo
    await dj.async_update(now=None)
    await _start_interval(interval_min)

    async def _apply_one_shot(values: Dict[str, Any]) -> None:
        if not values:
            return
        acc_f, acc_r = dj._refresh_accepted()

        def base_from(total: float, desired: Any) -> float | None:
            if desired is None or desired == "":
                return None
            try:
                v = max(float(desired), 0.0)
            except Exception:
                return None
            return max(total - v, 0.0)

        # 6 giá trị: forward/reverse (day/month/year)
        b_day = base_from(acc_f, values.get(OPT_BUY_DAY))
        s_day = base_from(acc_r, values.get(OPT_SELL_DAY))
        if b_day is not None:
            dj.data["day"]["f_base"] = b_day
        if s_day is not None:
            dj.data["day"]["r_base"] = s_day

        b_month = base_from(acc_f, values.get(OPT_BUY_MONTH))
        s_month = base_from(acc_r, values.get(OPT_SELL_MONTH))
        if b_month is not None:
            dj.data["month"]["f_base"] = b_month
        if s_month is not None:
            dj.data["month"]["r_base"] = s_month

        b_year = base_from(acc_f, values.get(OPT_BUY_YEAR))
        s_year = base_from(acc_r, values.get(OPT_SELL_YEAR))
        if b_year is not None:
            dj.data["year"]["f_base"] = b_year
        if s_year is not None:
            dj.data["year"]["r_base"] = s_year

        await dj.store.async_save(dj.data)
        await dj.async_update(now=None)

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry):
        """Lắng nghe khi Options thay đổi:
        - Đổi interval
        - Đổi directory_path (CONF_DIR)
        - Áp 6 giá trị one-shot
        """
        if updated_entry.entry_id != entry.entry_id:
            return

        opts: Dict[str, Any] = dict(updated_entry.options or {})
        # new_data là bản copy của entry.data hiện tại, sẽ ghi lại nếu có thay đổi
        new_data: Dict[str, Any] = dict(updated_entry.data)
        data_changed = False

        # 0) Đổi thư mục lưu (CONF_DIR) nếu người dùng nhập trong Options
        if CONF_DIR in opts and opts[CONF_DIR]:
            new_dir = str(opts[CONF_DIR]).strip()
            if new_dir and new_dir != new_data.get(CONF_DIR):
                new_data[CONF_DIR] = new_dir
                data_changed = True

                # Cập nhật runtime DJ: đổi csv_path sang thư mục mới
                dj_runtime: DJRuntime | None = hass.data.get(DOMAIN, {}).get(updated_entry.entry_id)
                if dj_runtime:
                    new_year = dt_util.now().strftime("%Y")
                    dj_runtime.csv_path = os.path.join(new_dir, f"{new_year}.csv")

        # 1) Nếu CONF_INTERVAL_MIN thay đổi trong options
        if CONF_INTERVAL_MIN in opts:
            new_interval = int(opts[CONF_INTERVAL_MIN])
            if new_interval != interval_min:
                await _start_interval(new_interval)

        # 2) Áp các giá trị one-shot
        await _apply_one_shot(opts)

        # 3) Nếu data_changed (ví dụ đổi CONF_DIR), ghi lại vào entry
        if data_changed:
            hass.config_entries.async_update_entry(updated_entry, data=new_data)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_options_updated_{entry.entry_id}",
            lambda updated_entry: hass.async_create_task(_options_updated(hass, updated_entry)),
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Được gọi khi xóa config entry."""
    dj: DJRuntime | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if dj and getattr(dj, "unsub", None):
        dj.unsub()
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Migrate config entry khi tăng VERSION trong config_flow."""
    # Hiện tại chưa có logic migrate, cứ return True cho chắc.
    return True


# -------------------- Runtime class --------------------


class DJRuntime:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        forward_entity: str,
        reverse_entity: str,
        csv_path: str,
        store: Store,
        stored: Dict[str, Any],
    ):
        self.hass = hass
        self.entry = entry
        self.forward_entity = forward_entity
        self.reverse_entity = reverse_entity
        self.csv_path = csv_path
        self.store = store
        self.data = stored
        self.unsub = None

        self.state: Dict[str, Any] = {
            "total_buy": 0.0,
            "buy_day": 0.0,
            "buy_month": 0.0,
            "buy_year": 0.0,
            "total_sell": 0.0,
            "sell_day": 0.0,
            "sell_month": 0.0,
            "sell_year": 0.0,
            "buy_cost_day": 0.0,
            "buy_cost_month": 0.0,
            "buy_cost_year": 0.0,
            "sell_revenue_day": 0.0,
            "sell_revenue_month": 0.0,
            "sell_revenue_year": 0.0,
            "last_updated": None,
        }

        self.data.setdefault("accepted", {"forward": None, "reverse": None})
        self.data.setdefault("day", {"date": None, "f_base": None, "r_base": None})
        self.data.setdefault("month", {"month": None, "f_base": None, "r_base": None})
        self.data.setdefault(
            "year", {"year": None, "f_base": None, "r_base": None, "months": {}}
        )

    async def async_update(self, now):
        acc_f, acc_r = self._refresh_accepted()

        now_dt = dt_util.now()
        date_str = now_dt.date().isoformat()
        month_str = now_dt.strftime("%Y-%m")
        year_str = now_dt.strftime("%Y")

        day = self.data["day"]
        month = self.data["month"]
        year = self.data["year"]
        months_map: Dict[str, float] = year["months"]

        # Reset base khi sang ngày / tháng / năm mới
        if day["date"] != date_str:
            day["date"] = date_str
            day["f_base"] = acc_f
            day["r_base"] = acc_r

        if month["month"] != month_str:
            month["month"] = month_str
            month["f_base"] = acc_f
            month["r_base"] = acc_r

        if year["year"] != year_str:
            year["year"] = year_str
            year["f_base"] = acc_f
            year["r_base"] = acc_r
            months_map.clear()

        buy_day = max(acc_f - (day["f_base"] or 0.0), 0.0)
        buy_month = max(acc_f - (month["f_base"] or 0.0), 0.0)
        buy_year = max(acc_f - (year["f_base"] or 0.0), 0.0)

        sell_day = max(acc_r - (day["r_base"] or 0.0), 0.0)
        sell_month = max(acc_r - (month["r_base"] or 0.0), 0.0)
        sell_year = max(acc_r - (year["r_base"] or 0.0), 0.0)

        months_map[month_str] = buy_month

        # Tiền mua điện (K = nghìn đồng)
        buy_cost_day_K = self._cost_K(buy_day)
        buy_cost_month_K = self._cost_K(buy_month)
        sum_past_months_K = sum(self._cost_K(kwh_m) for kwh_m in months_map.values())
        buy_cost_year_K = sum_past_months_K + buy_cost_month_K

        # Tiền bán điện (K = nghìn đồng)
        sell_rev_day_K = (sell_day * EVN_SELL_PRICE) / 1000.0
        sell_rev_month_K = (sell_month * EVN_SELL_PRICE) / 1000.0
        sell_rev_year_K = (sell_year * EVN_SELL_PRICE) / 1000.0

        self.state.update(
            {
                "total_buy": acc_f,
                "buy_day": buy_day,
                "buy_month": buy_month,
                "buy_year": buy_year,
                "total_sell": acc_r,
                "sell_day": sell_day,
                "sell_month": sell_month,
                "sell_year": sell_year,
                "buy_cost_day": round(buy_cost_day_K, 1),
                "buy_cost_month": round(buy_cost_month_K, 1),
                "buy_cost_year": round(buy_cost_year_K, 1),
                "sell_revenue_day": round(sell_rev_day_K, 1),
                "sell_revenue_month": round(sell_rev_month_K, 1),
                "sell_revenue_year": round(sell_rev_year_K, 1),
                "last_updated": dt_util.now(),
            }
        )

        await self.store.async_save(self.data)
        await self._async_write_csv_row(dt_util.now())
        async_dispatch_update(self.hass, self.entry.entry_id)

    # ---- helpers ----
    def _refresh_accepted(self) -> Tuple[float, float]:
        def _val(entity_id: str) -> float:
            st = self.hass.states.get(entity_id)
            try:
                return (
                    float(st.state)
                    if st and st.state not in ("unknown", "unavailable", "none", "")
                    else 0.0
                )
            except Exception:
                return 0.0

        f = _val(self.forward_entity)
        r = _val(self.reverse_entity)
        acc = self.data.setdefault("accepted", {"forward": None, "reverse": None})
        if acc["forward"] is None or f > acc["forward"]:
            acc["forward"] = f
        if acc["reverse"] is None or r > acc["reverse"]:
            acc["reverse"] = r
        return float(acc["forward"] or 0.0), float(acc["reverse"] or 0.0)

    def _cost_K(self, kwh: float) -> float:
        remain = max(kwh, 0.0)
        cost = 0.0
        last_limit = 0.0

        for limit, price in EVN_TIERS:
            cap = limit - last_limit
            if remain <= 0:
                break
            chunk = min(remain, cap)
            cost += chunk * price
            remain -= chunk
            last_limit = limit

        if remain > 0:
            last_price = EVN_TIERS[-1][1]
            cost += remain * last_price

        return cost / 1000.0

    async def _async_write_csv_row(self, now: dt_util.dt) -> None:
        date_str = now.strftime("%Y-%m-%d")
        hour_str = now.strftime("%H")
        min_sec = now.strftime("%M:%S")

        total_buy = self.state["total_buy"]
        buy_day = self.state["buy_day"]
        buy_month = self.state["buy_month"]
        buy_year = self.state["buy_year"]

        total_sell = self.state["total_sell"]
        sell_day = self.state["sell_day"]
        sell_month = self.state["sell_month"]
        sell_year = self.state["sell_year"]

        buy_cost_day = self.state["buy_cost_day"]
        buy_cost_month = self.state["buy_cost_month"]
        buy_cost_year = self.state["buy_cost_year"]

        sell_rev_day = self.state["sell_revenue_day"]
        sell_rev_month = self.state["sell_revenue_month"]
        sell_rev_year = self.state["sell_revenue_year"]

        # Tính hour từ chênh lệch tổng (đơn giản: không giữ riêng từng giờ trong state)
        buy_hour = 0.0
        sell_hour = 0.0
        buy_hour_cost = 0.0
        sell_hour_cost = 0.0

        sep = "|"

        row = sep.join(
            [
                date_str,  # date
                hour_str,  # hour
                min_sec,  # min_sec
                f"{total_buy:.3f}",  # total_buy
                f"{buy_hour:.3f}",  # buy_hour
                f"{buy_hour_cost:.3f}",  # buy_hour_cost
                f"{buy_day:.3f}",  # buy_day
                f"{buy_cost_day:.3f}",  # buy_day_cost
                f"{buy_month:.3f}",  # buy_month
                f"{buy_cost_month:.3f}",  # buy_month_cost
                f"{buy_year:.3f}",  # buy_year
                f"{buy_cost_year:.3f}",  # buy_year_cost
                f"{total_sell:.3f}",  # total_sell
                f"{sell_hour:.3f}",  # sell_hour
                f"{sell_hour_cost:.3f}",  # sell_hour_cost
                f"{sell_day:.3f}",  # sell_day
                f"{sell_rev_day:.3f}",  # sell_day_cost
                f"{sell_month:.3f}",  # sell_month
                f"{sell_rev_month:.3f}",  # sell_month_cost
                f"{sell_year:.3f}",  # sell_year
                f"{sell_rev_year:.3f}",  # sell_year_cost
            ]
        )

        # Đảm bảo có header nếu file chưa tồn tại / rỗng
        if not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0:
            with open(self.csv_path, "w", encoding="utf-8") as f:
                f.write(CSV_HEADER + "\n")

        # Ghi hoặc merge dòng cuối nếu cùng date+hour
        with open(self.csv_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            if len(lines) <= 1:
                f.seek(0, os.SEEK_END)
                f.write(row + "\n")
                return

            idx = len(lines) - 1
            last = lines[idx].strip()

            def _key(s: str) -> tuple[str, str]:
                p = s.split(sep)
                return (p[0], p[1]) if len(p) >= 2 else ("", "")

            if _key(last) == _key(row) and _key(row) != ("", ""):
                lines[idx] = row + "\n"
                f.seek(0)
                f.truncate(0)
                f.writelines(lines)
            else:
                f.seek(0, os.SEEK_END)
                f.write(row + "\n")
