from __future__ import annotations

from datetime import timedelta, datetime
from typing import Optional, Callable, Dict, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    CONF_FORWARD_TOTAL, CONF_REVERSE_TOTAL, CONF_PREFIX,
    CONF_OUTPUT_DIR, CONF_INTERVAL_MIN, CONF_ROUND,
    DEFAULT_OUTPUT_DIR, DEFAULT_INTERVAL, DEFAULT_ROUND,
    STORAGE_KEY, STORAGE_VERSION,
)
from .writer import CsvDailyYearWriter

PLATFORMS = [Platform.SENSOR]

UNKNOWN_STATES = {"unknown", "unavailable", None, ""}

def _to_float(hass: HomeAssistant, entity_id: str) -> Optional[float]:
    st = hass.states.get(entity_id)
    if not st or st.state in UNKNOWN_STATES:
        return None
    try:
        return float(st.state)
    except Exception:
        return None

class Runtime:
    """Giữ baseline & giá trị hiện tại; bắn sự kiện cho sensor.py cập nhật."""

    def __init__(self, hass: HomeAssistant, round_dec: int) -> None:
        self.hass = hass
        self.round_dec = round_dec
        self._listeners: list[Callable[[], None]] = []
        self.values: Dict[str, Dict[str, Optional[float]]] = {
            "buy":  {"day": None, "month": None, "year": None},
            "sell": {"day": None, "month": None, "year": None},
        }

    def get_value(self, kind: str, period: str) -> Optional[float]:
        return self.values.get(kind, {}).get(period)

    @callback
    def async_listen(self, cb: Callable[[], None]):
        self._listeners.append(cb)
        def _remove():
            self._listeners.remove(cb)
        return _remove

    @callback
    def _notify(self):
        for cb in list(self._listeners):
            self.hass.async_create_task(cb())

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = {**entry.data, **entry.options}

    f_total = data[CONF_FORWARD_TOTAL]
    r_total = data[CONF_REVERSE_TOTAL]
    prefix  = data[CONF_PREFIX]

    output_dir  = data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)
    interval_min = int(data.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL))
    round_dec    = int(data.get(CONF_ROUND, DEFAULT_ROUND))

    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}.json")
    stored: Dict[str, Any] | None = await store.async_load() or {}

    # cấu trúc baseline
    init = {
        "buy":  {"day": {"base": None, "date": None},
                 "month":{"base": None, "ym":   None},
                 "year": {"base": None, "y":    None}},
        "sell": {"day": {"base": None, "date": None},
                 "month":{"base": None, "ym":   None},
                 "year": {"base": None, "y":    None}},
    }
    baseline: Dict[str, Any] = stored.get("baseline", init)

    writer = CsvDailyYearWriter(hass, output_dir, round_dec)
    runtime = Runtime(hass, round_dec)

    async def _save():
        await store.async_save({"baseline": baseline})

    def _ensure_baseline(now: datetime, kind: str, total: Optional[float]):
        if total is None:
            return
        # day
        d = now.strftime("%Y-%m-%d")
        if baseline[kind]["day"]["date"] != d or baseline[kind]["day"]["base"] is None:
            baseline[kind]["day"]["date"] = d
            baseline[kind]["day"]["base"] = total
        # month
        ym = now.strftime("%Y-%m")
        if baseline[kind]["month"]["ym"] != ym or baseline[kind]["month"]["base"] is None:
            baseline[kind]["month"]["ym"] = ym
            baseline[kind]["month"]["base"] = total
        # year
        y = now.strftime("%Y")
        if baseline[kind]["year"]["y"] != y or baseline[kind]["year"]["base"] is None:
            baseline[kind]["year"]["y"] = y
            baseline[kind]["year"]["base"] = total

    def _derive(kind: str, total: Optional[float], now: datetime) -> dict[str, Optional[float]]:
        if total is None:
            return {"day": None, "month": None, "year": None}
        base_day   = baseline[kind]["day"]["base"]
        base_month = baseline[kind]["month"]["base"]
        base_year  = baseline[kind]["year"]["base"]
        def diff(a, b): return None if (a is None or b is None) else max(0.0, a - b)
        return {
            "day":   diff(total, base_day),
            "month": diff(total, base_month),
            "year":  diff(total, base_year),
        }

    async def _job(now):
        # lấy total
        tb = _to_float(hass, f_total)
        ts = _to_float(hass, r_total)
        nowdt = datetime.now()

        # thiết lập baseline khi sang ngày/tháng/năm mới
        _ensure_baseline(nowdt, "buy",  tb)
        _ensure_baseline(nowdt, "sell", ts)
        await _save()

        # tính toán
        buy_vals  = _derive("buy",  tb, nowdt)
        sell_vals = _derive("sell", ts, nowdt)

        runtime.values["buy"].update(buy_vals)
        runtime.values["sell"].update(sell_vals)
        runtime._notify()

        # ghi CSV (upsert ngày hiện tại)
        await writer.upsert_today(
            nowdt,
            total_buy = tb,
            buy_day   = buy_vals["day"],
            buy_month = buy_vals["month"],
            total_sell= ts,
            sell_day  = sell_vals["day"],
            sell_month= sell_vals["month"],
        )

    # Lưu shared data cho sensor.py
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "runtime": runtime,
        "prefix":  prefix,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # chạy ngay & lặp
    await _job(None)
    cancel = async_track_time_interval(hass, _job, timedelta(minutes=interval_min))
    hass.data[DOMAIN][entry.entry_id]["cancel"] = cancel
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if data and "cancel" in data and data["cancel"]:
            data["cancel"]()
    return unload_ok
