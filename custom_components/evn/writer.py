from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Tuple

from homeassistant.core import HomeAssistant

class CsvDailyYearWriter:
    """Ghi file theo năm. Mỗi dòng là một ngày, mới nhất ở trên cùng.

    CSV line:
      YYYY-MM-DD,total_buy,buy_day,buy_month,total_sell,sell_day,sell_month
    """

    def __init__(self, hass: HomeAssistant, output_dir: str, round_decimals: int = 3) -> None:
        self.hass = hass
        self.base_dir = hass.config.path(output_dir)  # chấp nhận "www/energy"
        self.round = round_decimals
        self._lock = asyncio.Lock()

    def _year_path(self, dt: datetime) -> str:
        year = dt.strftime("%Y")
        # TÊN FILE CHỈ LÀ NĂM: 2025.csv, 2026.csv, ...
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

        # round
        rb  = round(total_buy,  self.round)
        rd  = round(buy_day,    self.round)
        rm  = round(buy_month,  self.round)
        rsb = round(total_sell, self.round)
        rsd = round(sell_day,   self.round)
        rsm = round(sell_month, self.round)

        date_str = dt.strftime("%Y-%m-%d")
        path = self._year_path(dt)

        async with self._lock:
            await self.hass.async_add_executor_job(os.makedirs, self.base_dir, True)

            rows: Dict[str, Tuple[float, float, float, float, float, float]] = {}
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
                            rows[d] = (t_b, b_d, b_m, t_s, s_d, s_m)
                await self.hass.async_add_executor_job(_read)

            rows[date_str] = (rb, rd, rm, rsb, rsd, rsm)

            ordered_desc = sorted(rows.items(), key=lambda kv: kv[0], reverse=True)

            def _write():
                tmp = f"{path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for d, (t_b, b_d, b_m, t_s, s_d, s_m) in ordered_desc:
                        f.write(f"{d},{t_b},{b_d},{b_m},{t_s},{s_d},{s_m}\n")
                os.replace(tmp, path)

            await self.hass.async_add_executor_job(_write)
