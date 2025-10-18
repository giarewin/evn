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
    CONF_SEED_BUY_DAY, CONF_SEED_BUY_MONTH, CONF_SEED_BUY_YEAR,
    CONF_SEED_SELL_DAY, CONF_SEED_SELL_MONTH, CONF_SEED_SELL_YEAR,
    CONF_SEED_BUY_DAY_ENTITY, CONF_SEED_BUY_MONTH_ENTITY, CONF_SEED_BUY_YEAR_ENTITY,
    CONF_SEED_SELL_DAY_ENTITY, CONF_SEED_SELL_MONTH_ENTITY, CONF_SEED_SELL_YEAR_ENTITY,
    DEFAULT_OUTPUT_DIR, DEFAULT_INTERVAL, DEFAULT_ROUND,
    STORAGE_KEY, STORAGE_VERSION,
)
from .writer import CsvDailyYearWriter

PLATFORMS = [Platform.SENSOR]
UNKNOWN_STATES = {"unknown", "unavailable", None, ""}

def _to_float(hass: HomeAssistant, entity_id: Optional[str]) -> Optional[float]:
    if not entity_id:
        return None
    st = hass.states.get(entity_id)
    if not st or st.state in UNKNOWN_STATES:
        return None
    try:
        return float(st.state)
    except Exception:
        return None

class Runtime:
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
        def _remove(): self._listeners.remove(cb)
        return _remove
    @callback
    def _notify(self):
        for cb in list(self._listeners):
            self.hass.async_create_task(cb())

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = {**entry.data, **entry.options}

    f_total = data[CONF_FORWARD_TOTAL]
    r_total = data[CONF_REVERSE_TOTAL]

    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}.json")
    stored: Dict[str, Any] | None = await store.async_load() or {}

    init = {
        "buy":  {"day": {"base": None, "date": None},
                 "month":{"base": None, "ym":   None},
                 "year": {"base": None, "y":    None}},
        "sell": {"day": {"base": None, "date": None},
                 "month":{"base": None, "ym":   None},
                 "year": {"base": None, "y":    None}},
    }
    baseline: Dict[str, Any] = stored.get("baseline", init)

    runtime = Runtime(hass, int(data.get(CONF_ROUND, DEFAULT_ROUND)))

    # share cho sensor.py
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"runtime": runtime, "prefix": data[CONF_PREFIX]}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    def _ensure_period_keys(now: datetime, kind: str):
        d  = now.strftime("%Y-%m-%d")
        ym = now.strftime("%Y-%m")
        y  = now.strftime("%Y")
        baseline[kind]["day"]["date"]  = d
        baseline[kind]["month"]["ym"]  = ym
        baseline[kind]["year"]["y"]    = y

    def _ensure_baseline_rollover(now: datetime, kind: str, total: Optional[float]):
        if total is None:
            return
        d  = now.strftime("%Y-%m-%d")
        ym = now.strftime("%Y-%m")
        y  = now.strftime("%Y")
        if baseline[kind]["day"]["date"] != d or baseline[kind]["day"]["base"] is None:
            baseline[kind]["day"]["date"] = d
            baseline[kind]["day"]["base"] = total
        if baseline[kind]["month"]["ym"] != ym or baseline[kind]["month"]["base"] is None:
            baseline[kind]["month"]["ym"] = ym
            baseline[kind]["month"]["base"] = total
        if baseline[kind]["year"]["y"] != y or baseline[kind]["year"]["base"] is None:
            baseline[kind]["year"]["y"] = y
            baseline[kind]["year"]["base"] = total

    def _diff(total, base):
        if total is None or base is None:
            return None
        v = total - base
        return v if v > 0 else 0.0

    def _pick_seed(hass: HomeAssistant, ent_id: Optional[str], num: Optional[float]) -> Optional[float]:
        val = _to_float(hass, ent_id)
        if val is not None:
            return val
        try:
            return float(num) if num is not None else None
        except Exception:
            return None

    async def _save():
        await Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORAGE_KEY}.json").async_save({"baseline": baseline})

    async def _job(now):
        opts = {**entry.data, **entry.options}
        output_dir  = opts.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)
        round_dec   = int(opts.get(CONF_ROUND, DEFAULT_ROUND))
        runtime.round_dec = round_dec

        tb = _to_float(hass, f_total)
        ts = _to_float(hass, r_total)
        nowdt = datetime.now()

        _ensure_baseline_rollover(nowdt, "buy",  tb)
        _ensure_baseline_rollover(nowdt, "sell", ts)

        sb_d = _pick_seed(hass, opts.get(CONF_SEED_BUY_DAY_ENTITY),   opts.get(CONF_SEED_BUY_DAY))
        sb_m = _pick_seed(hass, opts.get(CONF_SEED_BUY_MONTH_ENTITY), opts.get(CONF_SEED_BUY_MONTH))
        sb_y = _pick_seed(hass, opts.get(CONF_SEED_BUY_YEAR_ENTITY),  opts.get(CONF_SEED_BUY_YEAR))

        ss_d = _pick_seed(hass, opts.get(CONF_SEED_SELL_DAY_ENTITY),   opts.get(CONF_SEED_SELL_DAY))
        ss_m = _pick_seed(hass, opts.get(CONF_SEED_SELL_MONTH_ENTITY), opts.get(CONF_SEED_SELL_MONTH))
        ss_y = _pick_seed(hass, opts.get(CONF_SEED_SELL_YEAR_ENTITY),  opts.get(CONF_SEED_SELL_YEAR))

        def _apply_seed(kind: str, period: str, total: Optional[float], seed: Optional[float]):
            if total is None or seed is None:
                return
            _ensure_period_keys(nowdt, kind)
            baseline[kind][period]["base"] = total - seed

        _apply_seed("buy",  "day",   tb, sb_d)
        _apply_seed("buy",  "month", tb, sb_m)
        _apply_seed("buy",  "year",  tb, sb_y)
        _apply_seed("sell", "day",   ts, ss_d)
        _apply_seed("sell", "month", ts, ss_m)
        _apply_seed("sell", "year",  ts, ss_y)

        await _save()

        buy_vals  = {
            "day":   _diff(tb, baseline["buy"]["day"]["base"]),
            "month": _diff(tb, baseline["buy"]["month"]["base"]),
            "year":  _diff(tb, baseline["buy"]["year"]["base"]),
        }
        sell_vals = {
            "day":   _diff(ts, baseline["sell"]["day"]["base"]),
            "month": _diff(ts, baseline["sell"]["month"]["base"]),
            "year":  _diff(ts, baseline["sell"]["year"]["base"]),
        }

        runtime.values["buy"].update(buy_vals)
        runtime.values["sell"].update(sell_vals)
        runtime._notify()

        writer = CsvDailyYearWriter(hass, output_dir, round_dec)
        await writer.upsert_today(
            nowdt,
            total_buy = tb,
            buy_day   = buy_vals["day"],
            buy_month = buy_vals["month"],
            total_sell= ts,
            sell_day  = sell_vals["day"],
            sell_month= sell_vals["month"],
        )

    await _job(None)
    cancel = async_track_time_interval(hass, _job, timedelta(minutes=int(data.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL))))
    hass.data[DOMAIN][entry.entry_id]["cancel"] = cancel

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry):
        await hass.config_entries.async_reload(updated_entry.entry_id)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if data and "cancel" in data and data["cancel"]:
            data["cancel"]()
    return unload_ok
