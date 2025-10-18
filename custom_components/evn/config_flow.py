from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_FORWARD_TOTAL, CONF_REVERSE_TOTAL, CONF_PREFIX,
    CONF_OUTPUT_DIR, CONF_INTERVAL_MIN, CONF_ROUND,
    CONF_SEED_BUY_DAY, CONF_SEED_BUY_MONTH, CONF_SEED_BUY_YEAR,
    CONF_SEED_SELL_DAY, CONF_SEED_SELL_MONTH, CONF_SEED_SELL_YEAR,
    CONF_SEED_BUY_DAY_ENTITY, CONF_SEED_BUY_MONTH_ENTITY, CONF_SEED_BUY_YEAR_ENTITY,
    CONF_SEED_SELL_DAY_ENTITY, CONF_SEED_SELL_MONTH_ENTITY, CONF_SEED_SELL_YEAR_ENTITY,
    DEFAULT_OUTPUT_DIR, DEFAULT_INTERVAL, DEFAULT_ROUND,
)

def _entity_sel():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor"]))

def _num_sel(minv=0.0):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=minv, step=0.001, mode=selector.NumberSelectorMode.BOX)
    )

def _text_sel():
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )

class EVNConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Mua Bán Điện", data=user_input)

        schema = vol.Schema({
            # Mặc định theo yêu cầu
            vol.Required(CONF_FORWARD_TOTAL, default="sensor.evn_total_forward_energy"): _entity_sel(),
            vol.Required(CONF_REVERSE_TOTAL, default="sensor.evn_total_reverse_energy"): _entity_sel(),
            vol.Required(CONF_PREFIX,        default="evn"): str,

            vol.Optional(CONF_OUTPUT_DIR, default=DEFAULT_OUTPUT_DIR): _text_sel(),
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

        o = {**self._entry.data, **self._entry.options}
        schema = vol.Schema({
            # Thư mục / chu kỳ / làm tròn
            vol.Optional(CONF_OUTPUT_DIR, default=o.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)): _text_sel(),
            vol.Optional(CONF_INTERVAL_MIN, default=o.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min")
            ),
            vol.Optional(CONF_ROUND, default=o.get(CONF_ROUND, DEFAULT_ROUND)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=6, step=1)
            ),

            # ==== Seeds: nhập số HOẶC chọn sensor (có thể thay đổi bất kỳ lúc nào) ====
            # MUA
            vol.Optional(CONF_SEED_BUY_DAY,   default=o.get(CONF_SEED_BUY_DAY)):   _num_sel(),
            vol.Optional(CONF_SEED_BUY_DAY_ENTITY, default=o.get(CONF_SEED_BUY_DAY_ENTITY)): _entity_sel(),
            vol.Optional(CONF_SEED_BUY_MONTH, default=o.get(CONF_SEED_BUY_MONTH)): _num_sel(),
            vol.Optional(CONF_SEED_BUY_MONTH_ENTITY, default=o.get(CONF_SEED_BUY_MONTH_ENTITY)): _entity_sel(),
            vol.Optional(CONF_SEED_BUY_YEAR,  default=o.get(CONF_SEED_BUY_YEAR)):  _num_sel(),
            vol.Optional(CONF_SEED_BUY_YEAR_ENTITY, default=o.get(CONF_SEED_BUY_YEAR_ENTITY)): _entity_sel(),
            # BÁN
            vol.Optional(CONF_SEED_SELL_DAY,  default=o.get(CONF_SEED_SELL_DAY)):  _num_sel(),
            vol.Optional(CONF_SEED_SELL_DAY_ENTITY, default=o.get(CONF_SEED_SELL_DAY_ENTITY)): _entity_sel(),
            vol.Optional(CONF_SEED_SELL_MONTH,default=o.get(CONF_SEED_SELL_MONTH)):_num_sel(),
            vol.Optional(CONF_SEED_SELL_MONTH_ENTITY, default=o.get(CONF_SEED_SELL_MONTH_ENTITY)): _entity_sel(),
            vol.Optional(CONF_SEED_SELL_YEAR, default=o.get(CONF_SEED_SELL_YEAR)): _num_sel(),
            vol.Optional(CONF_SEED_SELL_YEAR_ENTITY, default=o.get(CONF_SEED_SELL_YEAR_ENTITY)): _entity_sel(),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
