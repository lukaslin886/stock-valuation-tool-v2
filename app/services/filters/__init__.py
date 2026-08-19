"""篩選引擎模組。

提供基本面、技術面、籌碼面三種篩選器，以及 compose_filters 工具
函式用於組合多個篩選器為單一可呼叫物件。

所有篩選器滿足以下特性：
- 冪等性：套用兩次的結果與套用一次相同
- 資料縮減性：篩選後筆數 <= 篩選前筆數
- 純函式：不修改輸入資料，無副作用
"""

from __future__ import annotations

from typing import Any, Callable, List

from app.core.models.scan import ScanResult
from app.services.filters.chip import ChipFilter
from app.services.filters.fundamental import FundamentalFilter
from app.services.filters.technical import TechnicalFilter

__all__ = [
    "ChipFilter",
    "FundamentalFilter",
    "TechnicalFilter",
    "compose_filters",
]


def compose_filters(
    filters: List[Any],
) -> Callable[[List[ScanResult]], List[ScanResult]]:
    """組合多個篩選器為單一函式。

    依序套用所有篩選器，前一個篩選器的輸出作為下一個的輸入。
    當 filters 為空列表時，回傳的函式會原樣回傳輸入資料。

    Args:
        filters: 篩選器物件列表，每個物件須具備 apply() 方法。

    Returns:
        組合後的篩選函式，接受 List[ScanResult] 並回傳 List[ScanResult]。
    """

    def composed(results: List[ScanResult]) -> List[ScanResult]:
        """套用所有篩選器。

        Args:
            results: 待篩選的 ScanResult 列表。

        Returns:
            經所有篩選器依序處理後的結果列表。
        """
        current = results
        for f in filters:
            current = f.apply(current)
        return current

    return composed
