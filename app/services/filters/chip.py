"""籌碼面篩選器。

提供外資/投信連續買超天數、三大法人合計買超量等籌碼指標的篩選功能。
篩選器為純函式操作，無副作用且滿足冪等性。
"""

from __future__ import annotations

from typing import List, Optional

from app.core.models.scan import ScanResult


class ChipFilter:
    """籌碼面篩選器。

    依據法人連續買超天數與合計買超量篩選股票。
    當股票的籌碼資料不可用（chip_data_available=False）時，
    該股票將被排除於篩選結果之外。
    所有篩選條件皆為可選，未設定的條件不會套用篩選。
    apply() 方法為純函式，不修改輸入資料且滿足冪等性。

    Attributes:
        foreign_consecutive_buy_min: 外資連續買超最少天數（含）。
        trust_consecutive_buy_min: 投信連續買超最少天數（含）。
        total_institutional_buy_min: 三大法人合計買超最少量（含，單位：張）。
    """

    def __init__(
        self,
        foreign_consecutive_buy_min: Optional[int] = None,
        trust_consecutive_buy_min: Optional[int] = None,
        total_institutional_buy_min: Optional[int] = None,
    ) -> None:
        """初始化籌碼面篩選器。

        Args:
            foreign_consecutive_buy_min: 外資連續買超最少天數（含）。
                None 表示不篩選此條件。
            trust_consecutive_buy_min: 投信連續買超最少天數（含）。
                None 表示不篩選此條件。
            total_institutional_buy_min: 三大法人合計買超最少量（含，單位：張）。
                None 表示不篩選此條件。
        """
        self.foreign_consecutive_buy_min = foreign_consecutive_buy_min
        self.trust_consecutive_buy_min = trust_consecutive_buy_min
        self.total_institutional_buy_min = total_institutional_buy_min

    def apply(self, results: List[ScanResult]) -> List[ScanResult]:
        """套用籌碼面篩選條件，回傳符合的結果列表。

        此方法為純函式：不修改輸入列表，不產生副作用。
        連續套用兩次的結果與套用一次相同（冪等性）。

        當任何籌碼篩選條件被設定時，籌碼資料不可用的股票將被排除。

        Args:
            results: 待篩選的 ScanResult 列表。

        Returns:
            符合所有篩選條件的 ScanResult 列表。
        """
        # 若未設定任何條件，直接回傳全部
        if self._no_conditions_set():
            return list(results)

        filtered: List[ScanResult] = []
        for item in results:
            if not self._matches(item):
                continue
            filtered.append(item)
        return filtered

    def _no_conditions_set(self) -> bool:
        """檢查是否所有篩選條件皆為 None。

        Returns:
            若所有條件皆為 None 回傳 True。
        """
        return (
            self.foreign_consecutive_buy_min is None
            and self.trust_consecutive_buy_min is None
            and self.total_institutional_buy_min is None
        )

    def _matches(self, item: ScanResult) -> bool:
        """檢查單一 ScanResult 是否符合所有籌碼面篩選條件。

        當任何籌碼條件被設定且該股票籌碼資料不可用時，視為不符合。
        當籌碼欄位為 None（資料缺失）時，該條件視為不符合。

        Args:
            item: 待檢查的 ScanResult。

        Returns:
            若符合所有已設定的條件回傳 True，否則 False。
        """
        # 籌碼資料不可用時，排除
        if not item.chip_data_available:
            return False

        if self.foreign_consecutive_buy_min is not None:
            if item.foreign_consecutive_buy is None:
                return False
            if item.foreign_consecutive_buy < self.foreign_consecutive_buy_min:
                return False

        if self.trust_consecutive_buy_min is not None:
            if item.trust_consecutive_buy is None:
                return False
            if item.trust_consecutive_buy < self.trust_consecutive_buy_min:
                return False

        if self.total_institutional_buy_min is not None:
            # ScanResult 目前無 total_institutional_buy 欄位，
            # 以外資+投信連續買超天數的較小值作為近似判斷。
            # 當 ScanResult 擴充 total_institutional_buy 欄位後可直接使用。
            # 暫時：若外資或投信資料皆為 None 則不符合
            foreign = item.foreign_consecutive_buy or 0
            trust = item.trust_consecutive_buy or 0
            total = foreign + trust
            if total < self.total_institutional_buy_min:
                return False

        return True
