from __future__ import annotations

import os
from typing import Any, Dict

from ..const import CSV_HEADER


def ensure_evn_csv_header(path: str) -> None:
    """Đảm bảo file CSV tồn tại và có dòng header."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # Ghi header mới
        with open(path, "w", encoding="utf-8") as f:
            f.write(CSV_HEADER + "\n")


def write_evn_csv_row(csv_path: str, now_dt, state: Dict[str, Any]) -> None:
    """Ghi / cập nhật một dòng CSV, giữ nguyên logic như trước."""
    # Dùng dấu phẩy làm dấu phân cách cột CSV
    sep = ","

    date_str = now_dt.date().isoformat()
    hour_str = now_dt.strftime("%H")
    min_sec = now_dt.strftime("%M:%S")

    # Giá trị điện năng (kWh)
    total_buy = float(state["total_buy"])
    buy_day = float(state["buy_day"])
    buy_month = float(state["buy_month"])
    buy_year = float(state["buy_year"])
    total_sell = float(state["total_sell"])
    sell_day = float(state["sell_day"])
    sell_month = float(state["sell_month"])
    sell_year = float(state["sell_year"])

    # Giá trị tiền (K) đã được tính sẵn trong state
    buy_cost_day = float(state.get("buy_cost_day", 0.0))
    buy_cost_month = float(state.get("buy_cost_month", 0.0))
    buy_cost_year = float(state.get("buy_cost_year", 0.0))
    sell_rev_day = float(state.get("sell_revenue_day", 0.0))
    sell_rev_month = float(state.get("sell_revenue_month", 0.0))
    sell_rev_year = float(state.get("sell_revenue_year", 0.0))

    # Tạm thời, giá trị giờ lấy giống như giá trị ngày (tổng tích luỹ tới thời điểm đó)
    buy_hour = buy_day
    buy_hour_cost = buy_cost_day
    sell_hour = sell_day
    sell_hour_cost = sell_rev_day

    row = sep.join([
        date_str,                               # date
        hour_str,                               # hour
        min_sec,                                # min_sec
        f"{total_buy:.3f}",                     # total_buy
        f"{buy_hour:.3f}",                      # buy_hour
        f"{buy_hour_cost:.3f}",                 # buy_hour_cost
        f"{buy_day:.3f}",                       # buy_day
        f"{buy_cost_day:.3f}",                  # buy_day_cost
        f"{buy_month:.3f}",                     # buy_month
        f"{buy_cost_month:.3f}",                # buy_month_cost
        f"{buy_year:.3f}",                      # buy_year
        f"{buy_cost_year:.3f}",                 # buy_year_cost
        f"{total_sell:.3f}",                    # total_sell
        f"{sell_hour:.3f}",                     # sell_hour
        f"{sell_hour_cost:.3f}",                # sell_hour_cost
        f"{sell_day:.3f}",                      # sell_day
        f"{sell_rev_day:.3f}",                  # sell_day_cost
        f"{sell_month:.3f}",                    # sell_month
        f"{sell_rev_month:.3f}",                # sell_month_cost
        f"{sell_year:.3f}",                     # sell_year
        f"{sell_rev_year:.3f}",                 # sell_year_cost
    ])

    # Đảm bảo có header nếu file chưa tồn tại / rỗng
    ensure_evn_csv_header(csv_path)

    # Ghi / cập nhật dòng theo key (date + hour)
    with open(csv_path, "r+", encoding="utf-8") as f:
        lines = f.readlines()
        if len(lines) <= 1:
            f.seek(0, os.SEEK_END)
            f.write(row + "\n")
            return

        idx = len(lines) - 1
        # Bỏ qua các dòng rỗng / header ở cuối
        while idx >= 0 and (not lines[idx].strip() or lines[idx].strip() == CSV_HEADER):
            idx -= 1
        if idx < 1:
            f.seek(0, os.SEEK_END)
            f.write(row + "\n")
            return

        last = lines[idx].strip()

        def _key(s: str) -> tuple[str, str]:
            p = s.split(sep)
            return (p[0], p[1]) if len(p) >= 2 else ("", "")

        if _key(last) == _key(row) and _key(row) != ("", ""):
            # Cùng date + hour → ghi đè dòng cuối
            lines[idx] = row + "\n"
            f.seek(0)
            f.truncate(0)
            f.writelines(lines)
        else:
            # Khác key → thêm dòng mới
            f.seek(0, os.SEEK_END)
            f.write(row + "\n")
