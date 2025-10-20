from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, List

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAME, CONF_PREFIX, DEFAULT_PREFIX
from . import async_listen_update


def _object_id(prefix: str, key: str) -> str:
    return f"{prefix}_{key}"


# === Khai báo mô tả sensor với translation_key ===
DESCRIPTIONS: List[SensorEntityDescription] = [
    # Energy (kWh)
    SensorEntityDescription(key="total_buy", translation_key="total_buy", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="buy_day", translation_key="buy_day", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="buy_month", translation_key="buy_month", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="buy_year", translation_key="buy_year", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="total_sell", translation_key="total_sell", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="sell_day", translation_key="sell_day", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="sell_month", translation_key="sell_month", native_unit_of_measurement="kWh"),
    SensorEntityDescription(key="sell_year", translation_key="sell_year", native_unit_of_measurement="kWh"),

    # Money (K = nghìn đồng)
    SensorEntityDescription(key="buy_cost_day", translation_key="buy_cost_day", native_unit_of_measurement="K"),
    SensorEntityDescription(key="buy_cost_month", translation_key="buy_cost_month", native_unit_of_measurement="K"),
    SensorEntityDescription(key="buy_cost_year", translation_key="buy_cost_year", native_unit_of_measurement="K"),
    SensorEntityDescription(key="sell_revenue_day", translation_key="sell_revenue_day", native_unit_of_measurement="K"),
    SensorEntityDescription(key="sell_revenue_month", translation_key="sell_revenue_month", native_unit_of_measurement="K"),
    SensorEntityDescription(key="sell_revenue_year", translation_key="sell_revenue_year", native_unit_of_measurement="K"),

    # Meta
    SensorEntityDescription(key="last_updated", translation_key="last_updated"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    dj = hass.data[DOMAIN][entry.entry_id]
    prefix: str = entry.data.get(CONF_PREFIX, DEFAULT_PREFIX)

    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"{NAME} ({prefix})",
        manufacturer="Mua Bán Điện",
    )

    entities: list[DJSensor] = [DJSensor(hass, entry, dj, device, prefix, d) for d in DESCRIPTIONS]
    async_add_entities(entities, update_before_add=True)


class DJSensor(SensorEntity):
    """Một sensor của DJ Billing."""
    _attr_should_poll = False
    _attr_has_entity_name = True  # cho phép ghép với tên dịch từ translations

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        dj_runtime,
        device: DeviceInfo,
        prefix: str,
        desc: SensorEntityDescription,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.dj = dj_runtime
        self.entity_description = desc  # <- rất quan trọng để HA lấy translation_key
        self.key = desc.key

        # Giữ entity_id ổn định theo yêu cầu
        self.entity_id = f"sensor.{_object_id(prefix, self.key)}"

        self._attr_unique_id = f"{entry.entry_id}:{self.key}"
        self._attr_device_info = device
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _update():
            self.async_write_ha_state()

        self._unsub = async_listen_update(self.hass, self.entry.entry_id, _update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def native_value(self) -> Any:
        val = self.dj.state.get(self.key)
        if self.key == "last_updated" and val is not None:
            return dt_util.as_local(val).isoformat(timespec="seconds")
        if isinstance(val, (int, float)):
            return round(val, 2)
        return val
