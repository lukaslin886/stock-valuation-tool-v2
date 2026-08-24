"""
分頁工具（純函式，與 UI 解耦，可獨立測試）

對應 TODO.md「搜尋結果分頁處理 (若股票數 > 500)」。
"""

import math
from typing import Tuple


def slice_page(n_total: int, page: int, page_size: int) -> Tuple[int, int, int, int]:
    """
    計算分頁切片範圍。

    Args:
        n_total: 資料總筆數。
        page: 目前頁碼（1-based）；超界會被夾回合法範圍。
        page_size: 每頁筆數；<=0 視為單頁全部。

    Returns:
        (start, end, n_pages, page)
        - start/end：可直接用於 df.iloc[start:end]（半開區間）。
        - n_pages：總頁數（至少 1）。
        - page：夾回合法範圍後的實際頁碼。
    """
    n_total = max(0, int(n_total))
    if page_size is None or page_size <= 0:
        page_size = n_total if n_total > 0 else 1

    n_pages = max(1, math.ceil(n_total / page_size)) if n_total > 0 else 1
    page = min(max(1, int(page)), n_pages)

    start = (page - 1) * page_size
    end = min(start + page_size, n_total)
    return start, end, n_pages, page
