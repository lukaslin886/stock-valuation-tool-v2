"""Pydantic 模型驗證單元測試。

覆蓋 6 個核心模型（StockInfo, PriceData, FinancialData, DCFResult,
ScanResult, TradeSignal）的有效輸入、邊界值與無效輸入三種情境。

Requirements: 17.4
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.core.models.financial import DCFResult, FinancialData, normalize_percentage
from app.core.models.scan import ScanResult
from app.core.models.stock import Market, PriceData, StockInfo
from app.core.models.trade import SignalType, TradeSignal


# ============================================================
# StockInfo
# ============================================================


class TestStockInfoValid:
    """StockInfo 有效輸入測試。"""

    def test_minimal_valid(self) -> None:
        info = StockInfo(stock_code="2330")
        assert info.stock_code == "2330"
        assert info.stock_name == ""
        assert info.market == Market.TW

    def test_full_valid(self) -> None:
        info = StockInfo(
            stock_code="AAPL",
            stock_name="Apple Inc.",
            market=Market.US,
            industry="Technology",
            listed_date=date(1980, 12, 12),
            shares_outstanding=15_000_000_000,
        )
        assert info.stock_code == "AAPL"
        assert info.market == Market.US
        assert info.listed_date == date(1980, 12, 12)
        assert info.shares_outstanding == 15_000_000_000

    def test_whitespace_trimmed(self) -> None:
        info = StockInfo(stock_code="  2317  ")
        assert info.stock_code == "2317"


class TestStockInfoBoundary:
    """StockInfo 邊界值測試。"""

    def test_shares_outstanding_zero(self) -> None:
        info = StockInfo(stock_code="2330", shares_outstanding=0)
        assert info.shares_outstanding == 0

    def test_single_char_code(self) -> None:
        info = StockInfo(stock_code="A")
        assert info.stock_code == "A"

    def test_all_market_values(self) -> None:
        for market in Market:
            info = StockInfo(stock_code="TEST", market=market)
            assert info.market == market


class TestStockInfoInvalid:
    """StockInfo 無效輸入測試。"""

    def test_empty_stock_code(self) -> None:
        with pytest.raises(ValidationError, match="股票代碼不得為空"):
            StockInfo(stock_code="")

    def test_whitespace_only_code(self) -> None:
        with pytest.raises(ValidationError, match="股票代碼不得為空"):
            StockInfo(stock_code="   ")

    def test_invalid_market_enum(self) -> None:
        with pytest.raises(ValidationError):
            StockInfo(stock_code="2330", market="INVALID")  # type: ignore[arg-type]

    def test_negative_shares_outstanding(self) -> None:
        with pytest.raises(ValidationError):
            StockInfo(stock_code="2330", shares_outstanding=-1)


# ============================================================
# PriceData
# ============================================================


class TestPriceDataValid:
    """PriceData 有效輸入測試。"""

    def test_normal_price(self) -> None:
        p = PriceData(
            stock_code="2330",
            date=date(2024, 1, 15),
            open_price=580.0,
            high_price=590.0,
            low_price=575.0,
            close_price=585.0,
            volume=30_000_000,
        )
        assert p.close_price == 585.0
        assert p.volume == 30_000_000

    def test_close_equals_high(self) -> None:
        p = PriceData(
            stock_code="2330",
            date=date(2024, 1, 15),
            open_price=580.0,
            high_price=590.0,
            low_price=575.0,
            close_price=590.0,
            volume=1000,
        )
        assert p.close_price == p.high_price

    def test_close_equals_low(self) -> None:
        p = PriceData(
            stock_code="2330",
            date=date(2024, 1, 15),
            open_price=580.0,
            high_price=590.0,
            low_price=575.0,
            close_price=575.0,
            volume=0,
        )
        assert p.close_price == p.low_price


class TestPriceDataBoundary:
    """PriceData 邊界值測試。"""

    def test_high_equals_low(self) -> None:
        p = PriceData(
            stock_code="2330",
            date=date(2024, 1, 15),
            open_price=100.0,
            high_price=100.0,
            low_price=100.0,
            close_price=100.0,
            volume=0,
        )
        assert p.high_price == p.low_price == p.close_price

    def test_very_small_price(self) -> None:
        p = PriceData(
            stock_code="9999",
            date=date(2024, 1, 1),
            open_price=0.01,
            high_price=0.01,
            low_price=0.01,
            close_price=0.01,
            volume=100,
        )
        assert p.open_price == 0.01

    def test_zero_volume(self) -> None:
        p = PriceData(
            stock_code="2330",
            date=date(2024, 1, 1),
            open_price=100.0,
            high_price=100.0,
            low_price=100.0,
            close_price=100.0,
            volume=0,
        )
        assert p.volume == 0


class TestPriceDataInvalid:
    """PriceData 無效輸入測試。"""

    def test_price_zero(self) -> None:
        with pytest.raises(ValidationError):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=0,
                high_price=100.0,
                low_price=50.0,
                close_price=80.0,
                volume=1000,
            )

    def test_price_negative(self) -> None:
        with pytest.raises(ValidationError):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=-10.0,
                high_price=100.0,
                low_price=50.0,
                close_price=80.0,
                volume=1000,
            )

    def test_high_less_than_low(self) -> None:
        with pytest.raises(ValidationError, match="最高價不得低於最低價"):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=100.0,
                high_price=50.0,
                low_price=80.0,
                close_price=60.0,
                volume=1000,
            )

    def test_close_above_high(self) -> None:
        with pytest.raises(ValidationError, match="收盤價須在最高最低價之間"):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=100.0,
                high_price=110.0,
                low_price=90.0,
                close_price=120.0,
                volume=1000,
            )

    def test_close_below_low(self) -> None:
        with pytest.raises(ValidationError, match="收盤價須在最高最低價之間"):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=100.0,
                high_price=110.0,
                low_price=90.0,
                close_price=80.0,
                volume=1000,
            )

    def test_negative_volume(self) -> None:
        with pytest.raises(ValidationError):
            PriceData(
                stock_code="2330",
                date=date(2024, 1, 1),
                open_price=100.0,
                high_price=100.0,
                low_price=100.0,
                close_price=100.0,
                volume=-1,
            )


# ============================================================
# FinancialData
# ============================================================


class TestFinancialDataValid:
    """FinancialData 有效輸入測試。"""

    def test_normal_financials(self) -> None:
        fd = FinancialData(
            stock_code="2330",
            period="2024Q4",
            revenue=500000.0,
            eps=20.5,
            roe=25.0,
            pe_ratio=15.0,
            dividend_yield=3.5,
        )
        assert fd.roe == 25.0
        assert fd.eps == 20.5

    def test_decimal_roe_normalized(self) -> None:
        fd = FinancialData(
            stock_code="2330",
            period="2024Q3",
            revenue=100000.0,
            eps=5.0,
            roe=0.15,
        )
        assert fd.roe == 15.0

    def test_decimal_dividend_yield_normalized(self) -> None:
        fd = FinancialData(
            stock_code="2330",
            period="2024Q3",
            revenue=100000.0,
            eps=5.0,
            roe=10.0,
            dividend_yield=0.05,
        )
        assert fd.dividend_yield == 5.0


class TestFinancialDataBoundary:
    """FinancialData 邊界值測試。"""

    def test_roe_at_lower_bound(self) -> None:
        fd = FinancialData(
            stock_code="2330",
            period="2024Q1",
            revenue=0,
            eps=-1000,
            roe=-100.0,
        )
        assert fd.roe == -100.0

    def test_roe_at_upper_bound(self) -> None:
        fd = FinancialData(
            stock_code="2330",
            period="2024Q1",
            revenue=0,
            eps=10000,
            roe=200.0,
        )
        assert fd.roe == 200.0

    def test_eps_at_bounds(self) -> None:
        fd_min = FinancialData(
            stock_code="X", period="2024Q1", revenue=0, eps=-1000, roe=0
        )
        fd_max = FinancialData(
            stock_code="X", period="2024Q1", revenue=0, eps=10000, roe=0
        )
        assert fd_min.eps == -1000
        assert fd_max.eps == 10000

    def test_pe_ratio_at_bounds(self) -> None:
        fd_low = FinancialData(
            stock_code="X", period="2024Q1", revenue=0, eps=1, roe=0, pe_ratio=-100
        )
        fd_high = FinancialData(
            stock_code="X", period="2024Q1", revenue=0, eps=1, roe=0, pe_ratio=10000
        )
        assert fd_low.pe_ratio == -100
        assert fd_high.pe_ratio == 10000

    def test_zero_revenue(self) -> None:
        fd = FinancialData(
            stock_code="X", period="2024Q1", revenue=0, eps=0, roe=0
        )
        assert fd.revenue == 0


class TestFinancialDataInvalid:
    """FinancialData 無效輸入測試。"""

    def test_roe_below_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q1",
                revenue=1000,
                eps=5,
                roe=-101.0,
            )

    def test_roe_above_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q1",
                revenue=1000,
                eps=5,
                roe=201.0,
            )

    def test_negative_revenue(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q1",
                revenue=-1,
                eps=5,
                roe=10.0,
            )

    def test_eps_above_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q1",
                revenue=1000,
                eps=10001,
                roe=10.0,
            )

    def test_dividend_yield_negative(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q1",
                revenue=0,
                eps=0,
                roe=0,
                dividend_yield=-1.0,
            )

    def test_missing_required_field_period(self) -> None:
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                revenue=1000,
                eps=5,
                roe=10.0,
            )  # type: ignore[call-arg]


class TestNormalizePercentage:
    """normalize_percentage 函式單元測試。"""

    def test_none_passthrough(self) -> None:
        assert normalize_percentage(None) is None

    def test_zero_passthrough(self) -> None:
        assert normalize_percentage(0) == 0

    def test_decimal_converted(self) -> None:
        assert normalize_percentage(0.15) == 15.0

    def test_negative_decimal_converted(self) -> None:
        assert normalize_percentage(-0.10) == -10.0

    def test_already_percentage_unchanged(self) -> None:
        assert normalize_percentage(15.0) == 15.0

    def test_idempotent(self) -> None:
        val = 0.25
        first = normalize_percentage(val)
        second = normalize_percentage(first)
        assert first == second


# ============================================================
# DCFResult
# ============================================================


class TestDCFResultValid:
    """DCFResult 有效輸入測試。"""

    def test_normal_dcf(self) -> None:
        dcf = DCFResult(
            stock_code="2330",
            stock_name="TSMC",
            current_price=580.0,
            intrinsic_value=750.0,
            upside_potential=0.29,
            discount_rate=0.1,
            growth_rates=[0.15, 0.08],
            terminal_value=12000.0,
            recommendation="Buy",
        )
        assert dcf.current_price == 580.0
        assert dcf.intrinsic_value == 750.0

    def test_negative_intrinsic_value(self) -> None:
        dcf = DCFResult(
            stock_code="9999",
            current_price=10.0,
            intrinsic_value=-5.0,
            upside_potential=-1.0,
            discount_rate=0.5,
            growth_rates=[-0.5],
            terminal_value=-100.0,
        )
        assert dcf.intrinsic_value == -5.0


class TestDCFResultBoundary:
    """DCFResult 邊界值測試。"""

    def test_discount_rate_minimal(self) -> None:
        dcf = DCFResult(
            stock_code="X",
            current_price=0.01,
            intrinsic_value=1.0,
            upside_potential=0.0,
            discount_rate=0.001,
            growth_rates=[0.0],
            terminal_value=0.0,
        )
        assert dcf.discount_rate == 0.001

    def test_discount_rate_at_max(self) -> None:
        dcf = DCFResult(
            stock_code="X",
            current_price=100.0,
            intrinsic_value=50.0,
            upside_potential=-0.5,
            discount_rate=1.0,
            growth_rates=[0.0],
            terminal_value=0.0,
        )
        assert dcf.discount_rate == 1.0

    def test_upside_potential_at_bounds(self) -> None:
        dcf_low = DCFResult(
            stock_code="X",
            current_price=1.0,
            intrinsic_value=1.0,
            upside_potential=-1.0,
            discount_rate=0.1,
            growth_rates=[],
            terminal_value=0.0,
        )
        dcf_high = DCFResult(
            stock_code="X",
            current_price=1.0,
            intrinsic_value=1.0,
            upside_potential=100.0,
            discount_rate=0.1,
            growth_rates=[],
            terminal_value=0.0,
        )
        assert dcf_low.upside_potential == -1.0
        assert dcf_high.upside_potential == 100.0


class TestDCFResultInvalid:
    """DCFResult 無效輸入測試。"""

    def test_current_price_zero(self) -> None:
        with pytest.raises(ValidationError):
            DCFResult(
                stock_code="2330",
                current_price=0,
                intrinsic_value=100.0,
                upside_potential=0.5,
                discount_rate=0.1,
                growth_rates=[0.1],
                terminal_value=500.0,
            )

    def test_current_price_negative(self) -> None:
        with pytest.raises(ValidationError):
            DCFResult(
                stock_code="2330",
                current_price=-10.0,
                intrinsic_value=100.0,
                upside_potential=0.5,
                discount_rate=0.1,
                growth_rates=[0.1],
                terminal_value=500.0,
            )

    def test_discount_rate_zero(self) -> None:
        with pytest.raises(ValidationError):
            DCFResult(
                stock_code="2330",
                current_price=100.0,
                intrinsic_value=100.0,
                upside_potential=0.0,
                discount_rate=0.0,
                growth_rates=[0.1],
                terminal_value=500.0,
            )

    def test_discount_rate_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DCFResult(
                stock_code="2330",
                current_price=100.0,
                intrinsic_value=100.0,
                upside_potential=0.0,
                discount_rate=1.01,
                growth_rates=[0.1],
                terminal_value=500.0,
            )

    def test_upside_potential_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            DCFResult(
                stock_code="2330",
                current_price=100.0,
                intrinsic_value=100.0,
                upside_potential=101.0,
                discount_rate=0.1,
                growth_rates=[0.1],
                terminal_value=500.0,
            )


# ============================================================
# ScanResult
# ============================================================


class TestScanResultValid:
    """ScanResult 有效輸入測試。"""

    def test_normal_scan_result(self) -> None:
        sr = ScanResult(
            stock_code="2330",
            stock_name="TSMC",
            current_price=580.0,
            pe_ratio=18.5,
            roe=25.0,
            dividend_yield=2.5,
            market_cap=15000.0,
            price_position=0.75,
            fundamental_score=85.0,
            fundamental_grade="A",
        )
        assert sr.price_position == 0.75
        assert sr.fundamental_score == 85.0

    def test_minimal_scan_result(self) -> None:
        sr = ScanResult(stock_code="2330")
        assert sr.current_price == 0
        assert sr.pe_ratio == 0
        assert sr.chip_data_available is True

    def test_decimal_roe_normalized(self) -> None:
        sr = ScanResult(stock_code="2330", roe=0.25)
        assert sr.roe == 25.0


class TestScanResultBoundary:
    """ScanResult 邊界值測試。"""

    def test_price_position_zero(self) -> None:
        sr = ScanResult(stock_code="X", price_position=0.0)
        assert sr.price_position == 0.0

    def test_price_position_one(self) -> None:
        sr = ScanResult(stock_code="X", price_position=1.0)
        assert sr.price_position == 1.0

    def test_pe_ratio_at_bounds(self) -> None:
        sr_low = ScanResult(stock_code="X", pe_ratio=-100)
        sr_high = ScanResult(stock_code="X", pe_ratio=10000)
        assert sr_low.pe_ratio == -100
        assert sr_high.pe_ratio == 10000

    def test_fundamental_score_bounds(self) -> None:
        sr_low = ScanResult(stock_code="X", fundamental_score=0)
        sr_high = ScanResult(stock_code="X", fundamental_score=100)
        assert sr_low.fundamental_score == 0
        assert sr_high.fundamental_score == 100


class TestScanResultInvalid:
    """ScanResult 無效輸入測試。"""

    def test_price_position_above_one(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", price_position=1.1)

    def test_price_position_negative(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", price_position=-0.1)

    def test_pe_ratio_above_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", pe_ratio=10001)

    def test_pe_ratio_below_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", pe_ratio=-101)

    def test_roe_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", roe=201.0)

    def test_dividend_yield_negative(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", dividend_yield=-1.0)

    def test_fundamental_score_above_100(self) -> None:
        with pytest.raises(ValidationError):
            ScanResult(stock_code="2330", fundamental_score=101)

    def test_empty_stock_code(self) -> None:
        with pytest.raises(ValidationError, match="股票代碼不得為空"):
            ScanResult(stock_code="")


# ============================================================
# TradeSignal
# ============================================================


class TestTradeSignalValid:
    """TradeSignal 有效輸入測試。"""

    def test_buy_signal(self) -> None:
        ts = TradeSignal(
            stock_code="2330",
            signal_type=SignalType.BUY,
            confidence=85,
            trigger_description="DCF undervalued >30%, foreign buy 5 days",
            suggested_price_low=550.0,
            suggested_price_high=600.0,
        )
        assert ts.signal_type == SignalType.BUY
        assert ts.confidence == 85

    def test_sell_signal(self) -> None:
        ts = TradeSignal(
            stock_code="2317",
            signal_type=SignalType.SELL,
            confidence=60,
            trigger_description="DCF overvalued >20%",
            suggested_price_low=100.0,
            suggested_price_high=110.0,
        )
        assert ts.signal_type == SignalType.SELL

    def test_equal_price_range(self) -> None:
        ts = TradeSignal(
            stock_code="2330",
            signal_type=SignalType.HOLD,
            confidence=50,
            trigger_description="Neutral",
            suggested_price_low=100.0,
            suggested_price_high=100.0,
        )
        assert ts.suggested_price_low == ts.suggested_price_high


class TestTradeSignalBoundary:
    """TradeSignal 邊界值測試。"""

    def test_confidence_zero(self) -> None:
        ts = TradeSignal(
            stock_code="X",
            signal_type=SignalType.HOLD,
            confidence=0,
            trigger_description="Low confidence",
            suggested_price_low=10.0,
            suggested_price_high=10.0,
        )
        assert ts.confidence == 0

    def test_confidence_100(self) -> None:
        ts = TradeSignal(
            stock_code="X",
            signal_type=SignalType.BUY,
            confidence=100,
            trigger_description="Max confidence",
            suggested_price_low=10.0,
            suggested_price_high=20.0,
        )
        assert ts.confidence == 100

    def test_very_small_price(self) -> None:
        ts = TradeSignal(
            stock_code="X",
            signal_type=SignalType.BUY,
            confidence=50,
            trigger_description="Penny stock",
            suggested_price_low=0.01,
            suggested_price_high=0.02,
        )
        assert ts.suggested_price_low == 0.01


class TestTradeSignalInvalid:
    """TradeSignal 無效輸入測試。"""

    def test_confidence_above_100(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.BUY,
                confidence=101,
                trigger_description="Invalid",
                suggested_price_low=100.0,
                suggested_price_high=200.0,
            )

    def test_confidence_negative(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.SELL,
                confidence=-1,
                trigger_description="Invalid",
                suggested_price_low=100.0,
                suggested_price_high=200.0,
            )

    def test_price_high_less_than_low(self) -> None:
        with pytest.raises(ValidationError, match="價格上限不得低於下限"):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.BUY,
                confidence=50,
                trigger_description="Invalid range",
                suggested_price_low=200.0,
                suggested_price_high=100.0,
            )

    def test_price_zero(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.BUY,
                confidence=50,
                trigger_description="Zero price",
                suggested_price_low=0.0,
                suggested_price_high=100.0,
            )

    def test_price_negative(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.BUY,
                confidence=50,
                trigger_description="Negative price",
                suggested_price_low=-10.0,
                suggested_price_high=100.0,
            )

    def test_empty_stock_code(self) -> None:
        with pytest.raises(ValidationError, match="股票代碼不得為空"):
            TradeSignal(
                stock_code="",
                signal_type=SignalType.BUY,
                confidence=50,
                trigger_description="Test",
                suggested_price_low=10.0,
                suggested_price_high=20.0,
            )

    def test_invalid_signal_type(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type="invalid",  # type: ignore[arg-type]
                confidence=50,
                trigger_description="Test",
                suggested_price_low=10.0,
                suggested_price_high=20.0,
            )

    def test_missing_trigger_description(self) -> None:
        with pytest.raises(ValidationError):
            TradeSignal(
                stock_code="2330",
                signal_type=SignalType.BUY,
                confidence=50,
                suggested_price_low=10.0,
                suggested_price_high=20.0,
            )  # type: ignore[call-arg]
