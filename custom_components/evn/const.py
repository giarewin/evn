# =========================
# DJ Billing — constants (ok2)
# =========================
DOMAIN = "evn"
NAME = "Mua Bán Điện"

# --------------------------
# Config keys
# --------------------------
CONF_FORWARD = "forward_entity_id"
CONF_REVERSE = "reverse_entity_id"
CONF_INTERVAL_MIN = "interval_minutes"
CONF_DIR = "directory_path"

DEFAULT_FORWARD = "sensor.evn_total_forward_energy"
DEFAULT_REVERSE = "sensor.evn_total_reverse_energy"
DEFAULT_INTERVAL_MIN = 1

# Thư mục mặc định mới: /config/custom_components/{DOMAIN}
DEFAULT_DIR = f"/config/custom_components/{DOMAIN}/data"

# --------------------------
# Storage/CSV
# --------------------------
STORAGE_VERSION = 1
STORAGE_KEY_FMT = "evn_billing_{entry_id}"

# CẤU TRÚC CSV MỚI:
# date|hour|min_sec|total_buy|buy_day|buy_month|buy_year|total_sell|sell_day|sell_month|sell_year
CSV_HEADER = (
    "date|hour|min_sec|total_buy|buy_day|buy_month|buy_year|"
    "total_sell|sell_day|sell_month|sell_year"
)

# --------------------------
# EVN 2025 tiers + VAT
# --------------------------
EVN_TIERS = [
    (50.0, 1984.0),
    (50.0, 2050.0),
    (100.0, 2380.0),
    (100.0, 2998.0),
    (100.0, 3350.0),
    (None, 3460.0),
]
EVN_VAT = 0.08
EVN_SELL_PRICE = 2275.0  # đ/kWh, không VAT

# --------------------------
# Options one-shot nhập kWh
# --------------------------
OPT_BUY_DAY = "buy_day_kwh"
OPT_BUY_MONTH = "buy_month_kwh"
OPT_BUY_YEAR = "buy_year_kwh"
OPT_SELL_DAY = "sell_day_kwh"
OPT_SELL_MONTH = "sell_month_kwh"
OPT_SELL_YEAR = "sell_year_kwh"

# Prefix cho tên sensor
CONF_PREFIX = "prefix"
DEFAULT_PREFIX = "evn"
