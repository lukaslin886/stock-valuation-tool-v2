"""基本面篩選器。

提供本益比、ROE、殖利率、市值等基本面指標的篩選功能。
篩選器為純函式操作，無副作用且滿足冪等性。
"""

from __future__ import annotations

from typing import List, Optional

from app.core.models.scan import ScanResult


class FundamentalFilter:
    """基本面篩選器。

    依據本益比、ROE、殖利率、市值等基本面指標篩選股票。
    所有篩選條件皆為可選，未設定的條件不會套用篩選。
    apply() 方法為純函式，不修改輸入資料且滿足冪等性。

    Attributes:
        pe_min: 本益比下限（含）。
        pe_max: 本益比上限（含）。
        roe_min: ROE 下限（含，百分比形式）。
        roe_max: ROE 上限（含，百分比形式）。
        dividend_yield_min: 殖利率下限（含，百分比形式）。
        market_cap_min: 市值下限（含，單位：億）。
    """

    def __init__(
        self,
        pe_min: Optional[float] = None,
        pe_max: Optional[float] = None,
        roe_min: Optional[float] = None,
        roe_max: Optional[float] = None,
        dividend_yield_min: Optional[float] = None,
        market_cap_min: Optional[float] = None,
    ) -> None:
        """初始化基本面篩選器。

        Args:
            pe_min: 本益比下限（含）。None 表示不設下限。
            pe_max: 本益比上限（含）。None 表示不設上限。
            roe_min: ROE 下限（含，百分比形式）。None 表示不設下限。
            roe_max: ROE 上限（含，百分比形式）。None 表示不設上限。
            dividend_yield_min: 殖利率下限（含，百分比形式）。None 表示不設下限。
            market_cap_min: 市值下限（含，單位：億）。None 表示不設下限。
        """
        self.pe_min = pe_min
        self.pe_max = pe_max
        self.roe_min = roe_min
        self.roe_max = roe_max
        self.dividend_yield_min = dividend_yield_min
        self.market_cap_min = market_cap_min

    def apply(self, results: List[ScanResult]) -> List[ScanResult]:
        """套用基本面篩選條件，回傳符合的結果列表。

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
        """檢查單一 ScanResult 是否符合所有篩選條件。

        Args:
            item: 待檢查的 ScanResult。

        Returns:
            若符合所有已設定的條件回傳 True，否則 False。
        """
        if self.pe_min is not None and item.pe_ratio < self.pe_min:
            return False
        if self.pe_max is not None and item.pe_ratio > self.pe_max:
            return False
        if self.roe_min is not None and item.roe < self.roe_min:
            return False
        if self.roe_max is not None and item.roe > self.roe_max:
            return False
        if self.dividend_yield_min is not None and item.dividend_yield < self.dividend_yield_min:
            return False
        if self.market_cap_min is not None and item.market_cap < self.market_cap_min:
            return False
        return True
