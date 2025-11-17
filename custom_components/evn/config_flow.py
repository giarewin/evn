# ============================================
# DJ Billing — config_flow.py
# - Config Flow: forward/reverse, dir, interval
# - Options Flow:
#     * interval 1–60 phút
#     * 6 ô one-shot nhập kWh (buy/sell day|month|year)
#   Khi mở Options, các ô sẽ được điền sẵn từ dj.state (nếu có).
#   BỔ SUNG: cho phép đổi thư mục lưu (CONF_DIR) trong Options.
# ============================================

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from typing import Any, Dict

from .const import (
    DOMAIN, NAME,
    # Keys
    CONF_FORWARD, CONF_REVERSE, CONF_DIR, CONF_INTERVAL_MIN,
    DEFAULT_FORWARD, DEFAULT_REVERSE, DEFAULT_DIR, DEFAULT_INTERVAL_MIN,
    # One-shot keys (Options)
    OPT_BUY_DAY, OPT_BUY_MONTH, OPT_BUY_YEAR,
    OPT_SELL_DAY, OPT_SELL_MONTH, OPT_SELL_YEAR,
)

# ---------- Schemas ----------


def _schema_user(defaults: Dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_FORWARD,
                default=defaults.get(CONF_FORWARD, DEFAULT_FORWARD),
            ): str,
            vol.Optional(
                CONF_REVERSE,
                default=defaults.get(CONF_REVERSE, DEFAULT_REVERSE),
            ): str,
            vol.Optional(
                CONF_DIR,
                default=defaults.get(CONF_DIR, DEFAULT_DIR),
            ): str,
            vol.Optional(
                CONF_INTERVAL_MIN,
                default=defaults.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL_MIN),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        }
    )


def _schema_options(
    entry_data: Dict[str, Any],
    defaults_from_state: Dict[str, Any] | None,
) -> vol.Schema:
    """Schema cho Options:
    - Cho phép đổi lại CONF_DIR
    - Đổi CONF_INTERVAL_MIN
    - Nhập 6 giá trị one-shot kWh.
    """

    def _d(key: str):
        return None if not defaults_from_state else defaults_from_state.get(key)

    return vol.Schema(
        {
            # ✅ BỔ SUNG: cho phép chỉnh lại thư mục lưu trong Options
            vol.Optional(
                CONF_DIR,
                default=entry_data.get(CONF_DIR, DEFAULT_DIR),
            ): str,

            vol.Optional(
                CONF_INTERVAL_MIN,
                default=entry_data.get(CONF_INTERVAL_MIN, DEFAULT_INTERVAL_MIN),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),

            # 6 trường one-shot (có thể bỏ trống):
            vol.Optional(OPT_BUY_DAY, default=_d("buy_day")): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(OPT_BUY_MONTH, default=_d("buy_month")): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(OPT_BUY_YEAR, default=_d("buy_year")): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(OPT_SELL_DAY, default=_d("sell_day")): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(OPT_SELL_MONTH, default=_d("sell_month")): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(OPT_SELL_YEAR, default=_d("sell_year")): vol.Any(
                None, vol.Coerce(float)
            ),
        }
    )


# ---------- Config Flow ----------


class DJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        defaults = {
            CONF_FORWARD: DEFAULT_FORWARD,
            CONF_REVERSE: DEFAULT_REVERSE,
            CONF_DIR: DEFAULT_DIR,
            CONF_INTERVAL_MIN: DEFAULT_INTERVAL_MIN,
        }

        if user_input is not None:
            if not user_input.get(CONF_FORWARD) or not user_input.get(CONF_REVERSE):
                errors["base"] = "invalid_entities"
            else:
                return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema_user(defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DJOptionsFlowHandler(config_entry)


# ---------- Options Flow ----------


class DJOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}

        if user_input is not None:
            # __init__.py sẽ đọc options này, áp dụng one-shot (và thư mục/interval),
            # rồi xóa options hoặc giữ lại tùy logic implement.
            return self.async_create_entry(title="Options", data=user_input)

        # Lấy giá trị hiện thời từ runtime để prefill 6 ô one-shot
        defaults_from_state = None
        try:
            dj = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
            if dj and getattr(dj, "state", None):
                defaults_from_state = {
                    "buy_day": float(dj.state.get("buy_day", 0.0)),
                    "buy_month": float(dj.state.get("buy_month", 0.0)),
                    "buy_year": float(dj.state.get("buy_year", 0.0)),
                    "sell_day": float(dj.state.get("sell_day", 0.0)),
                    "sell_month": float(dj.state.get("sell_month", 0.0)),
                    "sell_year": float(dj.state.get("sell_year", 0.0)),
                }
        except Exception:
            defaults_from_state = None

        # ✅ Gộp data + options để default của CONF_DIR / CONF_INTERVAL_MIN
        # luôn lấy giá trị mới nhất (nếu đã từng lưu trong options).
        merged_entry_data: Dict[str, Any] = dict(self._entry.data)
        merged_entry_data.update(self._entry.options or {})

        return self.async_show_form(
            step_id="init",
            data_schema=_schema_options(merged_entry_data, defaults_from_state),
            errors=errors,
        )
