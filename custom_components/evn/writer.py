from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Tuple

from homeassistant.core import HomeAssistant

class CsvDailyYearWriter:
    """Ghi file theo năm. Mỗi dòng là một ngày, mới nhất ở trên cùng.

    CSV line (đÃ bổ sung cột thời gian cuối):
      YYYY-MM-DD,total_buy,buy_day,buy_month,total_sell,sell_day,sell_month,HH:MM:SS
    """

    def __init__(self, hass: HomeAssistant, output_dir: str, round_decimals: int = 3) -> None:
        self.hass = hass
        self.base_dir = hass.config.path(output_dir)  # chấp nhận "www/energy"
        self.round = round_decimals
        self._lock = asyncio.Lock()

    def _year_path(self, dt: datetime) -> str:
        year = dt.strftime("%Y")
        # Tên file chỉ là năm: 2025.csv, 2026.csv, ...
        return os.path.join(self.base_dir, f"{year}.csv")

    async def upsert_today(
        self,
        dt: datetime,
        total_buy: Optional[float],
        buy_day: Optional[float],
        buy_month: Optional[float],
        total_sell: Optional[float],
        sell_day: Optional[float],
        sell_month: Optional[float],
    ) -> None:
        """Ghi/cập nhật dòng của ngày dt. Bỏ qua nếu thiếu dữ liệu."""
        vals = [total_buy, buy_day, buy_month, total_sell, sell_day, sell_month]
        if any(v is None for v in vals):
            return

        # làm tròn theo cấu hình
        rb  = round(total_buy,  self.round)
        rd  = round(buy_day,    self.round)
        rm  = round(buy_month,  self.round)
        rsb = round(total_sell, self.round)
        rsd = round(sell_day,   self.round)
        rsm = round(sell_month, self.round)

        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")
        path = self._year_path(dt)

        async with self._lock:
            # Tạo thư mục nếu chưa có
            await self.hass.async_add_executor_job(os.makedirs, self.base_dir, True)

            # Đọc file cũ vào bộ nhớ
            rows: Dict[str, Tuple[float, float, float, float, float, float, str]] = {}
            if os.path.isfile(path):
                def _read():
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = [p.strip() for p in line.split(",")]
                            if len(parts) < 7:
                                continue
                            d = parts[0]
                            try:
                                t_b = float(parts[1]); b_d = float(parts[2]); b_m = float(parts[3])
                                t_s = float(parts[4]); s_d = float(parts[5]); s_m = float(parts[6])
                            except Exception:
                                continue
                            # cột 8 (time) có thể chưa có ở file cũ
                            tm = parts[7] if len(parts) >= 8 else ""
                            rows[d] = (t_b, b_d, b_m, t_s, s_d, s_m, tm)
                await self.hass.async_add_executor_job(_read)

            # Upsert ngày hiện tại (ghi đè nếu đã có); set time hiện tại
            rows[date_str] = (rb, rd, rm, rsb, rsd, rsm, time_str)

            # Sắp xếp ngày giảm dần (mới nhất ở trên cùng)
            ordered_desc = sorted(rows.items(), key=lambda kv: kv[0], reverse=True)

            # Ghi lại (atomic)
            def _write():
                tmp = f"{path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for d, (t_b, b_d, b_m, t_s, s_d, s_m, tm) in ordered_desc:
                        # Nếu dòng cũ chưa có time, giữ rỗng; riêng dòng hôm nay dùng time hiện tại
                        tm_out = tm if tm else (time_str if d == date_str else "")
                        f.write(f"{d},{t_b},{b_d},{b_m},{t_s},{s_d},{s_m},{tm_out}\n")
                os.replace(tmp, path)

            await self.hass.async_add_executor_job(_write)
