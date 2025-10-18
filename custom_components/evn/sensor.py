from __future__ import annotations

from dataclasses import dataclass
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN

@dataclass
class _Key:
    kind: str   # "buy" | "sell"
    period: str # "day" | "month" | "year"

SENSORS = [
    _Key("buy", "day"), _Key("buy", "month"), _Key("buy", "year"),
    _Key("sell", "day"), _Key("sell", "month"), _Key("sell", "year"),
]

VN_PERIOD = {"day": "Ngày", "month": "Tháng", "year": "Năm"}
VN_KIND = {"buy": "Mua", "sell": "Bán"}

def _cap_first(s: str) -> str:
    if not s: return s
    return s[0].upper() + s[1:]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback):
    runtime = hass.data[DOMAIN][entry.entry_id]["runtime"]
    prefix  = hass.data[DOMAIN][entry.entry_id]["prefix"]

    entities = []
    slug = prefix.lower().strip().replace(" ", "_")
    friendly_prefix = _cap_first(prefix.strip())

    for k in SENSORS:
        entity_slug = f"{slug}_{k.kind}_{k.period}"  # entity_id: sensor.<prefix>_<buy|sell>_<day|month|year>
        friendly = f"{friendly_prefix} {VN_KIND[k.kind]} ({VN_PERIOD[k.period]})"
        entities.append(EvnDerivedSensor(hass, entry, runtime, entity_slug, friendly, k.kind, k.period))

    add_entities(entities)

class EvnDerivedSensor(SensorEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime, entity_slug: str, friendly: str, kind: str, period: str) -> None:
        self.hass = hass
        self._entry = entry
        self._runtime = runtime
        self._kind = kind
        self._period = period

        self.entity_id = f"sensor.{entity_slug}"   # ép entity_id cố định
        self._attr_name = friendly
        self._attr_unique_id = f"{entry.entry_id}-{entity_slug}"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_icon = "mdi:transmission-tower-import" if kind == "buy" else "mdi:transmission-tower-export"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Mua Bán Điện",
            manufacturer="EVN (custom)",
            model="Derived energy (day/month/year)",
        )

    @property
    def native_value(self):
        v = self._runtime.get_value(self._kind, self._period)
        return None if v is None else round(v, self._runtime.round_dec)

    async def async_added_to_hass(self):
        self.async_on_remove(self._runtime.async_listen(self._schedule_update))

    async def _schedule_update(self):
        self.async_write_ha_state()
