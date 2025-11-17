from __future__ import annotations
import os
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
from .function.copy_html import copy_evn_static_files
from .function.write_csv import ensure_evn_csv_header, write_evn_csv_row

PLATFORMS = ["sensor"]


# -------------------- Setup entry --------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # Dùng data ban đầu (entry.data) để lấy config cơ bản
    data = dict(entry.data)
    forward = data[CONF_FORWARD]
    reverse  = data[CONF_REVERSE]
    interval_min = int(data[CONF_INTERVAL_MIN])

    base_dir = data[CONF_DIR]

    # ==== Tạo thư mục CSV ban đầu ====
    def _makedirs_sync(path: str):
        os.makedirs(path, exist_ok=True)
    await hass.async_add_executor_job(_makedirs_sync, base_dir)

    # Copy file HTML/JS phục vụ biểu đồ
    await hass.async_add_executor_job(copy_evn_static_files, hass)

    # CSV theo năm trong đúng thư mục đã cấu hình
    year = dt_util.now().strftime("%Y")
    csv_path = os.path.join(base_dir, f"{year}.csv")

    # Đảm bảo file CSV tồn tại + có header
    await hass.async_add_executor_job(ensure_evn_csv_header, csv_path)

    store  = Store(hass, STORAGE_VERSION, STORAGE_KEY_FMT.format(entry_id=entry.entry_id))
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

        b_day = base_from(acc_f, values.get(OPT_BUY_DAY))
        s_day = base_from(acc_r, values.get(OPT_SELL_DAY))
        if b_day is not None: dj.data["day"]["f_base"] = b_day
        if s_day is not None: dj.data["day"]["r_base"] = s_day

        b_mon = base_from(acc_f, values.get(OPT_BUY_MONTH))
        s_mon = base_from(acc_r, values.get(OPT_SELL_MONTH))
        if b_mon is not None: dj.data["month"]["f_base"] = b_mon
        if s_mon is not None: dj.data["month"]["r_base"] = s_mon

        b_year = base_from(acc_f, values.get(OPT_BUY_YEAR))
        s_year = base_from(acc_r, values.get(OPT_SELL_YEAR))
        if b_year is not None: dj.data["year"]["f_base"] = b_year
        if s_year is not None: dj.data["year"]["r_base"] = s_year

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
                if dj_runtime is not None:
                    # Tạo thư mục mới
                    def _mk():
                        os.makedirs(new_dir, exist_ok=True)
                    await hass.async_add_executor_job(_mk)

                    # Đổi đường dẫn csv sang thư mục mới + năm hiện tại
                    year_str = dt_util.now().strftime("%Y")
                    new_csv_path = os.path.join(new_dir, f"{year_str}.csv")
                    dj_runtime.csv_path = new_csv_path
                    # Đảm bảo file có header
                    await hass.async_add_executor_job(ensure_evn_csv_header, new_csv_path)

        # 1) Đổi interval (phút)
        if CONF_INTERVAL_MIN in opts and opts[CONF_INTERVAL_MIN] is not None:
            try:
                new_min = max(1, int(opts.get(CONF_INTERVAL_MIN)))
            except Exception:
                new_min = None
            if new_min:
                if new_min != new_data.get(CONF_INTERVAL_MIN):
                    new_data[CONF_INTERVAL_MIN] = new_min
                    data_changed = True
                # Đổi lịch tick runtime
                await _start_interval(new_min)

        # Nếu có thay đổi ở data (dir / interval) thì ghi lại vào config_entry.data
        if data_changed:
            hass.config_entries.async_update_entry(updated_entry, data=new_data)

        # 2) Áp các ô one-shot vào baseline (buy/sell day|month|year)
        await _apply_one_shot(opts)

        # 3) Xoá options để tránh lặp áp dụng one-shot lần sau
        # (dir + interval đã được chuyển sang entry.data ở trên)
        if updated_entry.options:
            hass.config_entries.async_update_entry(updated_entry, options={})

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    dj: DJRuntime | None = hass.data[DOMAIN].pop(entry.entry_id, None)
    if dj and dj.unsub:
        dj.unsub()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# -------------------- Dispatcher helpers --------------------

def _sig(entry_id: str) -> str:
    return f"{DOMAIN}_update_{entry_id}"

def async_dispatch_update(hass: HomeAssistant, entry_id: str):
    async_dispatcher_send(hass, _sig(entry_id))

def async_listen_update(hass: HomeAssistant, entry_id: str, update_cb):
    return async_dispatcher_connect(hass, _sig(entry_id), update_cb)


# -------------------- Runtime --------------------

class DJRuntime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 forward_entity: str, reverse_entity: str,
                 csv_path: str, store: Store, stored: Dict[str, Any]):
        self.hass = hass
        self.entry = entry
        self.forward_entity = forward_entity
        self.reverse_entity  = reverse_entity
        self.csv_path = csv_path
        self.store = store
        self.data = stored
        self.unsub = None

        self.state: Dict[str, Any] = {
            "total_buy": 0.0, "buy_day": 0.0, "buy_month": 0.0, "buy_year": 0.0,
            "total_sell": 0.0, "sell_day": 0.0, "sell_month": 0.0, "sell_year": 0.0,
            "buy_cost_day": 0.0, "buy_cost_month": 0.0, "buy_cost_year": 0.0,
            "sell_revenue_day": 0.0, "sell_revenue_month": 0.0, "sell_revenue_year": 0.0,
            "last_updated": None,
        }

        self.data.setdefault("accepted", {"forward": None, "reverse": None})
        self.data.setdefault("day",   {"date": None,  "f_base": None, "r_base": None})
        self.data.setdefault("month", {"month": None, "f_base": None, "r_base": None})
        self.data.setdefault("year",  {"year": None,  "f_base": None, "r_base": None, "months": {}})

    async def async_update(self, now):
        acc_f, acc_r = self._refresh_accepted()

        now_dt   = dt_util.now()
        date_str = now_dt.date().isoformat()
        month_str = now_dt.strftime("%Y-%m")
        year_str  = now_dt.strftime("%Y")

        # Nếu năm đổi (2025 -> 2026) thì tự động chuyển csv_path sang file năm mới
        desired_csv = os.path.join(os.path.dirname(self.csv_path), f"{year_str}.csv")
        if os.path.normpath(desired_csv) != os.path.normpath(self.csv_path):
            self.csv_path = desired_csv
            await self.hass.async_add_executor_job(ensure_evn_csv_header, self.csv_path)

        if self.data["day"]["date"] != date_str or self.data["day"]["f_base"] is None:
            self.data["day"]["date"]  = date_str
            self.data["day"]["f_base"] = acc_f if self.data["day"]["f_base"] is None else self.data["day"]["f_base"]
            self.data["day"]["r_base"] = acc_r if self.data["day"]["r_base"] is None else self.data["day"]["r_base"]

        if self.data["month"]["month"] != month_str or self.data["month"]["f_base"] is None:
            self.data["month"]["month"] = month_str
            self.data["month"]["f_base"] = acc_f if self.data["month"]["f_base"] is None else self.data["month"]["f_base"]
            self.data["month"]["r_base"] = acc_r if self.data["month"]["r_base"] is None else self.data["month"]["r_base"]

        if self.data["year"]["year"] != year_str or self.data["year"]["f_base"] is None:
            self.data["year"] = {
                "year": year_str,
                "f_base": acc_f if self.data["year"]["f_base"] is None else self.data["year"]["f_base"],
                "r_base": acc_r if self.data["year"]["r_base"] is None else self.data["year"]["r_base"],
                "months": self.data["year"].get("months") or {},
            }

        buy_day   = max(acc_f - (self.data["day"]["f_base"]   or 0.0), 0.0)
        buy_month = max(acc_f - (self.data["month"]["f_base"] or 0.0), 0.0)
        buy_year  = max(acc_f - (self.data["year"]["f_base"]  or 0.0), 0.0)

        sell_day   = max(acc_r - (self.data["day"]["r_base"]   or 0.0), 0.0)
        sell_month = max(acc_r - (self.data["month"]["r_base"] or 0.0), 0.0)
        sell_year  = max(acc_r - (self.data["year"]["r_base"]  or 0.0), 0.0)

        buy_cost_month_K = self._cost_K(buy_month)
        mtd_at_midnight = max((self.data["day"]["f_base"] or 0.0) - (self.data["month"]["f_base"] or 0.0), 0.0)
        buy_cost_day_K = max(buy_cost_month_K - self._cost_K(mtd_at_midnight), 0.0)

        months_map = self.data["year"].get("months") or {}
        sum_past_months_K = sum(self._cost_K(kwh_m) for kwh_m in months_map.values())
        buy_cost_year_K = sum_past_months_K + buy_cost_month_K

        sell_rev_day_K   = (sell_day   * EVN_SELL_PRICE) / 1000.0
        sell_rev_month_K = (sell_month * EVN_SELL_PRICE) / 1000.0
        sell_rev_year_K  = (sell_year  * EVN_SELL_PRICE) / 1000.0

        self.state.update({
            "total_buy": acc_f, "buy_day": buy_day, "buy_month": buy_month, "buy_year": buy_year,
            "total_sell": acc_r, "sell_day": sell_day, "sell_month": sell_month, "sell_year": sell_year,
            "buy_cost_day": round(buy_cost_day_K, 1),
            "buy_cost_month": round(buy_cost_month_K, 1),
            "buy_cost_year": round(buy_cost_year_K, 1),
            "sell_revenue_day": round(sell_rev_day_K, 1),
            "sell_revenue_month": round(sell_rev_month_K, 1),
            "sell_revenue_year": round(sell_rev_year_K, 1),
            "last_updated": dt_util.now(),
        })

        await self.store.async_save(self.data)

        # Ghi CSV (chạy trong executor, giống logic cũ)
        await self.hass.async_add_executor_job(
            write_evn_csv_row,
            self.csv_path,
            dt_util.now(),
            self.state,
        )

        async_dispatch_update(self.hass, self.entry.entry_id)

    # ---- helpers ----
    def _refresh_accepted(self) -> Tuple[float, float]:
        def _val(entity_id: str) -> float:
            st = self.hass.states.get(entity_id)
            try:
                return float(st.state) if st and st.state not in ("unknown","unavailable","none","") else 0.0
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
        remain = max(float(kwh), 0.0)
        cost = 0.0
        for block_kwh, price in EVN_TIERS:
            take = remain if block_kwh is None else min(remain, block_kwh)
            cost += take * price
            remain -= take
            if remain <= 0:
                break
        cost *= 1.08
        return cost / 1000.0
