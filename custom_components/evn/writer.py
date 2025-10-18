from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Tuple

from homeassistant.core import HomeAssistant

class CsvDailyYearWriter:
    """Ghi file theo năm. Mỗi dòng là một ngày, mới nhất ở trên cùng.

    CSV line:
      YYYY-MM-DD,total_buy,buy_day,buy_month,total_sell,sell_day,sell_month,HH:MM:SS
    """

    def __init__(self, hass: HomeAssistant, output_dir: str, round_decimals: int = 3) -> None:
        self.hass = hass
        self.base_dir = hass.config.path(output_dir)
        self.round = round_decimals
        self._lock = asyncio.Lock()

    def _year_path(self, dt: datetime) -> str:
        return os.path.join(self.base_dir, f"{dt:%Y}.csv")

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
        """LUÔN ghi/cập nhật dòng ngày dt (kể cả khi không đổi).
        Trường None giữ giá trị cũ (nếu có) hoặc 0.0.
        Cột thời gian luôn = thời điểm sửa file (mtime) và được đồng bộ cho khớp.
        """
        date_str = dt.strftime("%Y-%m-%d")
        placeholder_time = "00:00:00"
        path = self._year_path(dt)

        async with self._lock:
            await self.hass.async_add_executor_job(os.makedirs, self.base_dir, True)

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
                            tm = parts[7] if len(parts) >= 8 else ""
                            rows[d] = (t_b, b_d, b_m, t_s, s_d, s_m, tm)
                await self.hass.async_add_executor_job(_read)

            prev = rows.get(date_str)
            prev_t_b, prev_b_d, prev_b_m, prev_t_s, prev_s_d, prev_s_m, _prev_tm = prev if prev else (None,)*7

            def choose(new_val: Optional[float], old_val: Optional[float]) -> float:
                if new_val is not None:
                    return round(new_val, self.round)
                if old_val is not None:
                    return round(old_val, self.round)
                return round(0.0, self.round)

            new_t_b = choose(total_buy,  prev_t_b)
            new_b_d = choose(buy_day,    prev_b_d)
            new_b_m = choose(buy_month,  prev_b_m)
            new_t_s = choose(total_sell, prev_t_s)
            new_s_d = choose(sell_day,   prev_s_d)
            new_s_m = choose(sell_month, prev_s_m)

            rows[date_str] = (new_t_b, new_b_d, new_b_m, new_t_s, new_s_d, new_s_m, placeholder_time)

            ordered_desc = sorted(rows.items(), key=lambda kv: kv[0], reverse=True)

            def _write_and_sync_mtime():
                tmp = f"{path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for d, (t_b, b_d, b_m, t_s, s_d, s_m, tm) in ordered_desc:
                        tm_out = placeholder_time if d == date_str else tm
                        f.write(f"{d},{t_b},{b_d},{b_m},{t_s},{s_d},{s_m},{tm_out}\n")
                os.replace(tmp, path)

                mtime_ts = os.path.getmtime(path)
                mtime_dt = datetime.fromtimestamp(mtime_ts)
                time_str = mtime_dt.strftime("%H:%M:%S")

                tmp2 = f"{path}.tmp"
                with open(path, "r", encoding="utf-8") as fin, open(tmp2, "w", encoding="utf-8") as fout:
                    for line in fin:
                        parts = [p.strip() for p in line.rstrip("\n").split(",")]
                        if parts and parts[0] == date_str and len(parts) >= 8:
                            parts[7] = time_str
                            line = ",".join(parts) + "\n"
                        fout.write(line)
                os.replace(tmp2, path)

                target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                try:
                    atime = os.path.getatime(path)
                    os.utime(path, (atime, target_dt.timestamp()))
                except Exception:
                    pass

            await self.hass.async_add_executor_job(_write_and_sync_mtime)
