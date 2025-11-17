from __future__ import annotations

import os
import shutil
from homeassistant.core import HomeAssistant


def copy_evn_static_files(hass: HomeAssistant) -> None:
    """Copy 2 file evn_chart.* từ thư mục html của integration sang www/evn."""
    # Thư mục gốc integration: custom_components/evn
    base_dir = os.path.dirname(os.path.dirname(__file__))
    # Thư mục nguồn: custom_components/evn/html
    src_dir = os.path.join(base_dir, "html")
    if not os.path.isdir(src_dir):
        return

    # Thư mục đích: <config>/www/evn
    dst_dir = hass.config.path("www", "evn")
    os.makedirs(dst_dir, exist_ok=True)

    for filename in ("evn_chart.html", "evn_chart.js"):
        src = os.path.join(src_dir, filename)
        if os.path.isfile(src):
            dst = os.path.join(dst_dir, filename)
            try:
                shutil.copy2(src, dst)
            except Exception:
                # Không để lỗi copy làm hỏng việc load tích hợp
                pass
