"""篩選器屬性基測試。

使用 Hypothesis 驗證篩選器的核心正確性屬性：
- Property 3: 冪等性 -- filter.apply(filter.apply(data)) == filter.apply(data)
- Property 4: 資料縮減性 -- len(filter.apply(data)) <= len(data)
- compose_filters 組合一致性

**Validates: Requirements 18.3, 18.4**
"""

from __future__ import annotations

from typing import List, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.models.scan import ScanResult
from app.services.filters import (
    ChipFilter,
    FundamentalFilter,
    TechnicalFilter,
    compose_filters,
)


# ============================================================================
# Hypothesis Strategies
# ============================================================================


@st.composite
def scan_result_strategy(draw: st.DrawFn) -> ScanResult:
    """產生隨機有效的 ScanResult 實例。

    確保所有欄位值在 ScanResult 模型定義的合理範圍內，
    避免 Pydantic 驗證失敗。

    Args:
        draw: Hypothesis 的 draw 函式。

    Returns:
        隨機有效的 ScanResult 實例。
    """
    stock_code = draw(
        st.from_regex(r"[0-9]{4,6}", fullmatch=True)
    )
    stock_name = draw(st.text(min_size=1, max_size=10))
    current_price = draw(st.floats(min_value=0, max_value=50000, allow_nan=False))
    # pe_ratio: ge=-100, le=10000
    pe_ratio = draw(st.floats(min_value=-100, max_value=10000, allow_nan=False))
    # roe: ge=-100, le=200 (百分比形式，避免觸發歸一化轉換)
    roe = draw(
        st.one_of(
            st.just(0.0),
            st.floats(min_value=-100, max_value=-1.0, allow_nan=False),
            st.floats(min_value=1.0, max_value=200, allow_nan=False),
        )
    )
    # dividend_yield: ge=0, le=100 (百分比形式，避免觸發歸一化轉換)
    dividend_yield = draw(
        st.one_of(
            st.just(0.0),
            st.floats(min_value=1.0, max_value=100, allow_nan=False),
        )
    )
    market_cap = draw(st.floats(min_value=0, max_value=100000, allow_nan=False))
    price_position = draw(st.floats(min_value=0, max_value=1.0, allow_nan=False))
    fundamental_score = draw(st.floats(min_value=0, max_value=100, allow_nan=False))
    chip_data_available = draw(st.booleans())
    foreign_consecutive_buy: Optional[int] = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=100))
    )
    trust_consecutive_buy: Optional[int] = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=100))
    )

    return ScanResult(
        stock_code=stock_code,
        stock_name=stock_name,
        current_price=current_price,
        pe_ratio=pe_ratio,
        roe=roe,
        dividend_yield=dividend_yield,
        market_cap=market_cap,
        price_position=price_position,
        fundamental_score=fundamental_score,
        chip_data_available=chip_data_available,
        foreign_consecutive_buy=foreign_consecutive_buy,
        trust_consecutive_buy=trust_consecutive_buy,
    )


scan_result_list_strategy = st.lists(scan_result_strategy(), min_size=0, max_size=30)


@st.composite
def fundamental_filter_strategy(draw: st.DrawFn) -> FundamentalFilter:
    """產生隨機的 FundamentalFilter 參數組合。

    Args:
        draw: Hypothesis 的 draw 函式。

    Returns:
        隨機配置的 FundamentalFilter 實例。
    """
    pe_min = draw(st.one_of(st.none(), st.floats(min_value=-100, max_value=5000, allow_nan=False)))
    pe_max = draw(st.one_of(st.none(), st.floats(min_value=-100, max_value=10000, allow_nan=False)))
    roe_min = draw(st.one_of(st.none(), st.floats(min_value=-100, max_value=200, allow_nan=False)))
    dividend_yield_min = draw(
        st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False))
    )
    market_cap_min = draw(
        st.one_of(st.none(), st.floats(min_value=0, max_value=100000, allow_nan=False))
    )
    return FundamentalFilter(
        pe_min=pe_min,
        pe_max=pe_max,
        roe_min=roe_min,
        dividend_yield_min=dividend_yield_min,
        market_cap_min=market_cap_min,
    )


@st.composite
def technical_filter_strategy(draw: st.DrawFn) -> TechnicalFilter:
    """產生隨機的 TechnicalFilter 參數組合。

    Args:
        draw: Hypothesis 的 draw 函式。

    Returns:
        隨機配置的 TechnicalFilter 實例。
    """
    price_position_max = draw(
        st.one_of(st.none(), st.floats(min_value=0, max_value=1.0, allow_nan=False))
    )
    price_position_min = draw(
        st.one_of(st.none(), st.floats(min_value=0, max_value=1.0, allow_nan=False))
    )
    return TechnicalFilter(
        price_position_max=price_position_max,
        price_position_min=price_position_min,
    )


@st.composite
def chip_filter_strategy(draw: st.DrawFn) -> ChipFilter:
    """產生隨機的 ChipFilter 參數組合。

    Args:
        draw: Hypothesis 的 draw 函式。

    Returns:
        隨機配置的 ChipFilter 實例。
    """
    foreign_consecutive_buy_min = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=50))
    )
    trust_consecutive_buy_min = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=50))
    )
    total_institutional_buy_min = draw(
        st.one_of(st.none(), st.integers(min_value=0, max_value=200))
    )
    return ChipFilter(
        foreign_consecutive_buy_min=foreign_consecutive_buy_min,
        trust_consecutive_buy_min=trust_consecutive_buy_min,
        total_institutional_buy_min=total_institutional_buy_min,
    )


# ============================================================================
# Property 3: 篩選器冪等性
# Feature: stock-valuation-optimization, Property 3: 篩選器冪等性
# **Validates: Requirements 18.3**
# ============================================================================


class TestFundamentalFilterIdempotency:
    """FundamentalFilter 冪等性測試。

    驗證對同一資料集連續套用相同篩選條件兩次的結果
    與套用一次完全相同。
    """

    @given(data=scan_result_list_strategy, f=fundamental_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_idempotency(self, data: List[ScanResult], f: FundamentalFilter) -> None:
        """FundamentalFilter 套用兩次結果應與一次相同。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 FundamentalFilter。
        """
        once = f.apply(data)
        twice = f.apply(once)
        assert once == twice


class TestTechnicalFilterIdempotency:
    """TechnicalFilter 冪等性測試。

    驗證對同一資料集連續套用相同篩選條件兩次的結果
    與套用一次完全相同。
    """

    @given(data=scan_result_list_strategy, f=technical_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_idempotency(self, data: List[ScanResult], f: TechnicalFilter) -> None:
        """TechnicalFilter 套用兩次結果應與一次相同。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 TechnicalFilter。
        """
        once = f.apply(data)
        twice = f.apply(once)
        assert once == twice


class TestChipFilterIdempotency:
    """ChipFilter 冪等性測試。

    驗證對同一資料集連續套用相同篩選條件兩次的結果
    與套用一次完全相同。
    """

    @given(data=scan_result_list_strategy, f=chip_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_idempotency(self, data: List[ScanResult], f: ChipFilter) -> None:
        """ChipFilter 套用兩次結果應與一次相同。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 ChipFilter。
        """
        once = f.apply(data)
        twice = f.apply(once)
        assert once == twice


# ============================================================================
# Property 4: 篩選器資料縮減性（變形屬性）
# Feature: stock-valuation-optimization, Property 4: 篩選器資料縮減性
# **Validates: Requirements 18.4**
# ============================================================================


class TestFundamentalFilterSubset:
    """FundamentalFilter 資料縮減性測試。

    驗證篩選後的資料筆數小於等於篩選前的資料筆數。
    """

    @given(data=scan_result_list_strategy, f=fundamental_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_subset(self, data: List[ScanResult], f: FundamentalFilter) -> None:
        """FundamentalFilter 篩選後筆數應 <= 篩選前筆數。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 FundamentalFilter。
        """
        result = f.apply(data)
        assert len(result) <= len(data)


class TestTechnicalFilterSubset:
    """TechnicalFilter 資料縮減性測試。

    驗證篩選後的資料筆數小於等於篩選前的資料筆數。
    """

    @given(data=scan_result_list_strategy, f=technical_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_subset(self, data: List[ScanResult], f: TechnicalFilter) -> None:
        """TechnicalFilter 篩選後筆數應 <= 篩選前筆數。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 TechnicalFilter。
        """
        result = f.apply(data)
        assert len(result) <= len(data)


class TestChipFilterSubset:
    """ChipFilter 資料縮減性測試。

    驗證篩選後的資料筆數小於等於篩選前的資料筆數。
    """

    @given(data=scan_result_list_strategy, f=chip_filter_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_subset(self, data: List[ScanResult], f: ChipFilter) -> None:
        """ChipFilter 篩選後筆數應 <= 篩選前筆數。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f: 隨機配置的 ChipFilter。
        """
        result = f.apply(data)
        assert len(result) <= len(data)


# ============================================================================
# compose_filters 組合一致性
# 驗證 compose_filters([f1, f2])(data) == f2.apply(f1.apply(data))
# ============================================================================


class TestComposeFiltersConsistency:
    """compose_filters 組合一致性測試。

    驗證組合後的篩選器函式與依序手動呼叫的結果相同。
    同時驗證組合後的函式仍滿足冪等性與資料縮減性。
    """

    @given(
        data=scan_result_list_strategy,
        f1=fundamental_filter_strategy(),
        f2=technical_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_fundamental_technical(
        self,
        data: List[ScanResult],
        f1: FundamentalFilter,
        f2: TechnicalFilter,
    ) -> None:
        """compose_filters([fundamental, technical]) 應等同依序手動套用。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 FundamentalFilter。
            f2: 隨機配置的 TechnicalFilter。
        """
        composed = compose_filters([f1, f2])
        composed_result = composed(data)
        manual_result = f2.apply(f1.apply(data))
        assert composed_result == manual_result

    @given(
        data=scan_result_list_strategy,
        f1=fundamental_filter_strategy(),
        f2=chip_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_fundamental_chip(
        self,
        data: List[ScanResult],
        f1: FundamentalFilter,
        f2: ChipFilter,
    ) -> None:
        """compose_filters([fundamental, chip]) 應等同依序手動套用。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 FundamentalFilter。
            f2: 隨機配置的 ChipFilter。
        """
        composed = compose_filters([f1, f2])
        composed_result = composed(data)
        manual_result = f2.apply(f1.apply(data))
        assert composed_result == manual_result

    @given(
        data=scan_result_list_strategy,
        f1=technical_filter_strategy(),
        f2=chip_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_technical_chip(
        self,
        data: List[ScanResult],
        f1: TechnicalFilter,
        f2: ChipFilter,
    ) -> None:
        """compose_filters([technical, chip]) 應等同依序手動套用。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 TechnicalFilter。
            f2: 隨機配置的 ChipFilter。
        """
        composed = compose_filters([f1, f2])
        composed_result = composed(data)
        manual_result = f2.apply(f1.apply(data))
        assert composed_result == manual_result

    @given(
        data=scan_result_list_strategy,
        f1=fundamental_filter_strategy(),
        f2=technical_filter_strategy(),
        f3=chip_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_three_filters(
        self,
        data: List[ScanResult],
        f1: FundamentalFilter,
        f2: TechnicalFilter,
        f3: ChipFilter,
    ) -> None:
        """compose_filters([f1, f2, f3]) 應等同依序手動套用三個篩選器。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 FundamentalFilter。
            f2: 隨機配置的 TechnicalFilter。
            f3: 隨機配置的 ChipFilter。
        """
        composed = compose_filters([f1, f2, f3])
        composed_result = composed(data)
        manual_result = f3.apply(f2.apply(f1.apply(data)))
        assert composed_result == manual_result

    @given(
        data=scan_result_list_strategy,
        f1=fundamental_filter_strategy(),
        f2=technical_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_idempotency(
        self,
        data: List[ScanResult],
        f1: FundamentalFilter,
        f2: TechnicalFilter,
    ) -> None:
        """組合後的篩選器仍滿足冪等性。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 FundamentalFilter。
            f2: 隨機配置的 TechnicalFilter。
        """
        composed = compose_filters([f1, f2])
        once = composed(data)
        twice = composed(once)
        assert once == twice

    @given(
        data=scan_result_list_strategy,
        f1=fundamental_filter_strategy(),
        f2=technical_filter_strategy(),
    )
    @settings(max_examples=200, deadline=30000)
    def test_compose_subset(
        self,
        data: List[ScanResult],
        f1: FundamentalFilter,
        f2: TechnicalFilter,
    ) -> None:
        """組合後的篩選器仍滿足資料縮減性。

        Args:
            data: 隨機產生的 ScanResult 列表。
            f1: 隨機配置的 FundamentalFilter。
            f2: 隨機配置的 TechnicalFilter。
        """
        composed = compose_filters([f1, f2])
        result = composed(data)
        assert len(result) <= len(data)
