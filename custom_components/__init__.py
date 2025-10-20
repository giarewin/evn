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

PLATFORMS = ["sensor"]


# -------------------- Setup entry --------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = dict(entry.data)
    forward = data[CONF_FORWARD]
    reverse  = data[CONF_REVERSE]
    interval_min = int(data[CONF_INTERVAL_MIN])

    base_dir = data[CONF_DIR]

    # ==== FIX: makedirs với exist_ok=True trong executor ====
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
        if updated_entry.entry_id != entry.entry_id:
            return
        opts = dict(updated_entry.options or {})

        # 1) đổi interval (KHÔNG await – đây không phải coroutine)
        if CONF_INTERVAL_MIN in opts and opts[CONF_INTERVAL_MIN] is not None:
            try:
                new_min = max(1, int(opts.get(CONF_INTERVAL_MIN)))
            except Exception:
                new_min = None
            if new_min:
                new_data = dict(updated_entry.data)
                new_data[CONF_INTERVAL_MIN] = new_min
                hass.config_entries.async_update_entry(updated_entry, data=new_data)
                await _start_interval(new_min)

        # 2) áp các ô one-shot vào baseline
        await _apply_one_shot(opts)

        # 3) xoá options để tránh lặp áp dụng (KHÔNG await)
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

        desired_csv = os.path.join(os.path.dirname(self.csv_path), f"{year_str}.csv")
        if os.path.normpath(desired_csv) != os.path.normpath(self.csv_path):
            self.csv_path = desired_csv
            await self.hass.async_add_executor_job(self._ensure_csv_sync, self.csv_path)

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
        await self._async_write_csv_row(dt_util.now())
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

    def _ensure_csv_sync(self, path: str):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(CSV_HEADER + "\n")

    async def _async_write_csv_row(self, now_dt):
        await self.hass.async_add_executor_job(self._write_csv_row_sync, now_dt)

    def _write_csv_row_sync(self, now_dt):
        min_sec = now_dt.strftime("%M:%S")
        row = (
            f"{now_dt.date().isoformat()}|{now_dt.strftime('%H')}|{min_sec}"
            f"|{self.state['total_buy']:.3f}|{self.state['buy_day']:.3f}|{self.state['buy_month']:.3f}|{self.state['buy_year']:.3f}"
            f"|{self.state['total_sell']:.3f}|{self.state['sell_day']:.3f}|{self.state['sell_month']:.3f}|{self.state['sell_year']:.3f}"
        )

        if not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0:
            with open(self.csv_path, "w", encoding="utf-8") as f:
                f.write(CSV_HEADER + "\n")

        with open(self.csv_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            if len(lines) <= 1:
                f.seek(0, os.SEEK_END); f.write(row + "\n"); return

            idx = len(lines) - 1
            while idx >= 0 and (not lines[idx].strip() or lines[idx].strip() == CSV_HEADER):
                idx -= 1
            if idx < 1:
                f.seek(0, os.SEEK_END); f.write(row + "\n"); return

            last = lines[idx].strip()
            def _key(s: str):
                p = s.split("|")
                return (p[0], p[1]) if len(p) >= 2 else ("","")

            if _key(last) == _key(row) and _key(row) != ("",""):
                lines[idx] = row + "\n"
                f.seek(0); f.truncate(0); f.writelines(lines)
            else:
                f.seek(0, os.SEEK_END); f.write(row + "\n")
