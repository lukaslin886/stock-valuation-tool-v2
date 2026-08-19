"""技術面篩選器。

提供價格位階等技術指標的篩選功能。
篩選器為純函式操作，無副作用且滿足冪等性。
"""

from __future__ import annotations

from typing import List, Optional

from app.core.models.scan import ScanResult


class TechnicalFilter:
    """技術面篩選器。

    依據價格位階（52 週位階）等技術指標篩選股票。
    所有篩選條件皆為可選，未設定的條件不會套用篩選。
    apply() 方法為純函式，不修改輸入資料且滿足冪等性。

    Attributes:
        price_position_max: 價格位階上限（含），用於篩選低基期股票。
        price_position_min: 價格位階下限（含）。
    """

    def __init__(
        self,
        price_position_max: Optional[float] = None,
        price_position_min: Optional[float] = None,
    ) -> None:
        """初始化技術面篩選器。

        Args:
            price_position_max: 價格位階上限（含，0~1.0）。
                設定此值可篩選低基期股票。None 表示不設上限。
            price_position_min: 價格位階下限（含，0~1.0）。
                None 表示不設下限。
        """
        self.price_position_max = price_position_max
        self.price_position_min = price_position_min

    def apply(self, results: List[ScanResult]) -> List[ScanResult]:
        """套用技術面篩選條件，回傳符合的結果列表。

        此方法為純函式：不修改輸入列表，不產生副作用。
        連續套用兩次的結果與套用一次相同（冪等性）。

        Args:
            results: 待篩選的 ScanResult 列表。

        Returns:
            符合所有篩選條件的 ScanResult 列表。
        """
        filtered: List[ScanResult] = []
        for item in results:
            if not self._matches(item):
                continue
            filtered.append(item)
        return filtered

    def _matches(self, item: ScanResult) -> bool:
        """檢查單一 ScanResult 是否符合所有技術面篩選條件。

        Args:
            item: 待檢查的 ScanResult。

        Returns:
            若符合所有已設定的條件回傳 True，否則 False。
        """
        if self.price_position_max is not None and item.price_position > self.price_position_max:
            return False
        if self.price_position_min is not None and item.price_position < self.price_position_min:
            return False
        return True
