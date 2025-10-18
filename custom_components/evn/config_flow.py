from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_FORWARD_TOTAL, CONF_REVERSE_TOTAL, CONF_PREFIX,
    CONF_OUTPUT_DIR, CONF_INTERVAL_MIN, CONF_ROUND,
    DEFAULT_OUTPUT_DIR, DEFAULT_INTERVAL, DEFAULT_ROUND,
)

def _entity_sel():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor"]))

class EVNConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Mua Bán Điện", data=user_input)

        schema = vol.Schema({
            # Mặc định theo yêu cầu:
            vol.Required(CONF_FORWARD_TOTAL, default="sensor.evn_total_forward_energy"): _entity_sel(),
            vol.Required(CONF_REVERSE_TOTAL, default="sensor.evn_total_reverse_energy"): _entity_sel(),
            vol.Required(CONF_PREFIX,        default="evn"): str,

            vol.Optional(CONF_OUTPUT_DIR, default=DEFAULT_OUTPUT_DIR): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_INTERVAL_MIN, default=DEFAULT_INTERVAL): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min")
            ),
            vol.Optional(CONF_ROUND, default=DEFAULT_ROUND): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=6, step=1)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EVNOptionsFlow(config_entry)

class EVNOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = {**self._entry.data, **self._entry.options}
        schema = vol.Schema({
            vol.Optional(CONF_OUTPUT_DIR, default=data.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_INTERVAL_MIN, default=data.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min")
            ),
            vol.Optional(CONF_ROUND, default=data.get(CONF_ROUND, DEFAULT_ROUND)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=6, step=1)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
