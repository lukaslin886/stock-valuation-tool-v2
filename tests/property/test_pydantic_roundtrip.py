# Feature: stock-valuation-optimization, Property 1
"""Pydantic 模型 JSON 往返屬性測試。

驗證所有 6 個核心 Pydantic 模型（StockInfo, PriceData, FinancialData,
DCFResult, ScanResult, TradeSignal）的 JSON 序列化/反序列化往返特性：
對任意有效模型實例，Model.from_json(instance.to_json()) 產生等價實例。

**Validates: Requirements 14.5, 14.6, 18.2**
"""

from datetime import date, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.models import (
    DCFResult,
    FinancialData,
    Market,
    PriceData,
    ScanResult,
    SignalType,
    StockInfo,
    TradeSignal,
)

# --- Hypothesis Strategies ---

non_empty_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")

stock_code_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() != "")

market_strategy = st.sampled_from([Market.TW, Market.TWO, Market.US])

date_strategy = st.dates(
    min_value=date(1990, 1, 1),
    max_value=date(2030, 12, 31),
)

datetime_strategy = st.datetimes(
    min_value=datetime(1990, 1, 1),
    max_value=datetime(2030, 12, 31),
)

signal_type_strategy = st.sampled_from([SignalType.BUY, SignalType.SELL, SignalType.HOLD])


@st.composite
def stock_info_strategy(draw: st.DrawFn) -> StockInfo:
    """產生有效的 StockInfo 實例。

    約束：stock_code 非空，shares_outstanding >= 0。
    """
    stock_code = draw(stock_code_strategy)
    stock_name = draw(st.text(max_size=20))
    market = draw(market_strategy)
    industry = draw(st.text(max_size=20))
    listed_date = draw(st.one_of(st.none(), date_strategy))
    shares_outstanding = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000_000)))

    return StockInfo(
        stock_code=stock_code,
        stock_name=stock_name,
        market=market,
        industry=industry,
        listed_date=listed_date,
        shares_outstanding=shares_outstanding,
    )


@st.composite
def price_data_strategy(draw: st.DrawFn) -> PriceData:
    """產生有效的 PriceData 實例。

    約束：all prices > 0, high >= low, close between high and low, volume >= 0。
    """
    stock_code = draw(stock_code_strategy)
    trade_date = draw(date_strategy)

    # 產生符合 high >= low 且 close 在 [low, high] 之間的價格
    low_price = draw(st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False))
    high_price = draw(
        st.floats(min_value=low_price, max_value=max(low_price * 2, low_price + 1000.0),
                  allow_nan=False, allow_infinity=False)
    )
    close_price = draw(
        st.floats(min_value=low_price, max_value=high_price,
                  allow_nan=False, allow_infinity=False)
    )
    open_price = draw(st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False))
    volume = draw(st.integers(min_value=0, max_value=1_000_000_000))

    return PriceData(
        stock_code=stock_code,
        date=trade_date,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )


@st.composite
def financial_data_strategy(draw: st.DrawFn) -> FinancialData:
    """產生有效的 FinancialData 實例。

    約束：revenue >= 0, eps in [-1000, 10000], roe in [-100, 200],
    pe_ratio in [-100, 10000]。
    注意：roe 需要避開 (-1.0, 1.0) 的歧義區間（normalize_percentage 會轉換）。
    """
    stock_code = draw(stock_code_strategy)
    period = draw(st.from_regex(r"20[12]\d[Q][1-4]", fullmatch=True))
    revenue = draw(st.floats(min_value=0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False))
    eps = draw(st.floats(min_value=-1000, max_value=10000, allow_nan=False, allow_infinity=False))

    # roe: 避開 (-1.0, 1.0) 因為 normalize_percentage 會乘以 100
    # 直接產生已經是百分比形式的值
    roe = draw(st.one_of(
        st.just(0.0),
        st.floats(min_value=-100, max_value=-1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.0, max_value=200, allow_nan=False, allow_infinity=False),
    ))

    pe_ratio = draw(st.one_of(
        st.none(),
        st.floats(min_value=-100, max_value=10000, allow_nan=False, allow_infinity=False),
    ))

    # dividend_yield: 同樣避開 (-1.0, 1.0) 歧義區間；ge=0 所以只需避開 (0, 1.0)
    dividend_yield = draw(st.one_of(
        st.none(),
        st.just(0.0),
        st.floats(min_value=1.0, max_value=100, allow_nan=False, allow_infinity=False),
    ))

    operating_margin = draw(st.one_of(
        st.none(),
        st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
    ))

    return FinancialData(
        stock_code=stock_code,
        period=period,
        revenue=revenue,
        eps=eps,
        roe=roe,
        pe_ratio=pe_ratio,
        dividend_yield=dividend_yield,
        operating_margin=operating_margin,
    )


@st.composite
def dcf_result_strategy(draw: st.DrawFn) -> DCFResult:
    """產生有效的 DCFResult 實例。

    約束：current_price > 0, discount_rate in (0, 1], upside_potential in [-1, 100]。
    """
    stock_code = draw(stock_code_strategy)
    stock_name = draw(st.text(max_size=20))
    current_price = draw(st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False))
    intrinsic_value = draw(st.floats(min_value=-100000, max_value=1_000_000, allow_nan=False, allow_infinity=False))
    upside_potential = draw(st.floats(min_value=-1.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    discount_rate = draw(st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False))
    growth_rates = draw(st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=5,
    ))
    terminal_value = draw(st.floats(min_value=-1_000_000, max_value=10_000_000, allow_nan=False, allow_infinity=False))
    recommendation = draw(st.text(max_size=50))
    calculated_at = draw(datetime_strategy)
    data_source = draw(st.text(max_size=30))

    return DCFResult(
        stock_code=stock_code,
        stock_name=stock_name,
        current_price=current_price,
        intrinsic_value=intrinsic_value,
        upside_potential=upside_potential,
        discount_rate=discount_rate,
        growth_rates=growth_rates,
        terminal_value=terminal_value,
        recommendation=recommendation,
        calculated_at=calculated_at,
        data_source=data_source,
    )


@st.composite
def scan_result_strategy(draw: st.DrawFn) -> ScanResult:
    """產生有效的 ScanResult 實例。

    約束：current_price >= 0, pe_ratio in [-100, 10000], roe in [-100, 200],
    price_position in [0, 1]。
    注意：roe 和 dividend_yield 需避開 normalize_percentage 歧義區間。
    """
    stock_code = draw(stock_code_strategy)
    stock_name = draw(st.text(max_size=20))
    current_price = draw(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False))
    pe_ratio = draw(st.floats(min_value=-100, max_value=10000, allow_nan=False, allow_infinity=False))

    # roe: 避開 (-1.0, 1.0) 歧義
    roe = draw(st.one_of(
        st.just(0.0),
        st.floats(min_value=-100, max_value=-1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.0, max_value=200, allow_nan=False, allow_infinity=False),
    ))

    # dividend_yield: 避開 (0, 1.0) 歧義
    dividend_yield = draw(st.one_of(
        st.just(0.0),
        st.floats(min_value=1.0, max_value=100, allow_nan=False, allow_infinity=False),
    ))

    market_cap = draw(st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False))
    price_position = draw(st.floats(min_value=0, max_value=1.0, allow_nan=False, allow_infinity=False))
    fundamental_score = draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    fundamental_grade = draw(st.text(max_size=5))
    chip_data_available = draw(st.booleans())
    foreign_consecutive_buy = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=365)))
    trust_consecutive_buy = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=365)))

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
        fundamental_grade=fundamental_grade,
        chip_data_available=chip_data_available,
        foreign_consecutive_buy=foreign_consecutive_buy,
        trust_consecutive_buy=trust_consecutive_buy,
    )


@st.composite
def trade_signal_strategy(draw: st.DrawFn) -> TradeSignal:
    """產生有效的 TradeSignal 實例。

    約束：confidence in [0, 100], suggested_price_low > 0,
    suggested_price_high >= suggested_price_low。
    """
    stock_code = draw(stock_code_strategy)
    signal_type = draw(signal_type_strategy)
    confidence = draw(st.integers(min_value=0, max_value=100))
    trigger_description = draw(non_empty_text)
    suggested_price_low = draw(
        st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False)
    )
    suggested_price_high = draw(
        st.floats(min_value=suggested_price_low, max_value=max(suggested_price_low * 2, suggested_price_low + 1000.0),
                  allow_nan=False, allow_infinity=False)
    )
    generated_at = draw(datetime_strategy)

    return TradeSignal(
        stock_code=stock_code,
        signal_type=signal_type,
        confidence=confidence,
        trigger_description=trigger_description,
        suggested_price_low=suggested_price_low,
        suggested_price_high=suggested_price_high,
        generated_at=generated_at,
    )


# --- Property Tests ---


@pytest.mark.property
class TestPydanticJsonRoundtrip:
    """Property 1: Pydantic 模型 JSON 往返特性。

    For any 有效的 Pydantic 模型實例，將其序列化為 JSON 再反序列化
    SHALL 產生與原始實例欄位值完全相等的物件。

    **Validates: Requirements 14.5, 14.6, 18.2**
    """

    @given(instance=stock_info_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_stock_info_roundtrip(self, instance: StockInfo) -> None:
        """StockInfo JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = StockInfo.from_json(json_str)
        assert restored == instance

    @given(instance=price_data_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_price_data_roundtrip(self, instance: PriceData) -> None:
        """PriceData JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = PriceData.from_json(json_str)
        assert restored == instance

    @given(instance=financial_data_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_financial_data_roundtrip(self, instance: FinancialData) -> None:
        """FinancialData JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = FinancialData.from_json(json_str)
        assert restored == instance

    @given(instance=dcf_result_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_dcf_result_roundtrip(self, instance: DCFResult) -> None:
        """DCFResult JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = DCFResult.from_json(json_str)
        assert restored == instance

    @given(instance=scan_result_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_scan_result_roundtrip(self, instance: ScanResult) -> None:
        """ScanResult JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = ScanResult.from_json(json_str)
        assert restored == instance

    @given(instance=trade_signal_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_trade_signal_roundtrip(self, instance: TradeSignal) -> None:
        """TradeSignal JSON 往返：序列化再反序列化產生等價物件。"""
        json_str = instance.to_json()
        restored = TradeSignal.from_json(json_str)
        assert restored == instance
