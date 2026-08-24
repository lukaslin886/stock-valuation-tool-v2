"""美股支援整合模組的單元測試。

驗證 MarketContext 建立、幣別標示、價格格式化、以及
美股專屬錯誤訊息等功能的正確性。同時驗證端對端整合流程：
使用者輸入美股代碼 -> detect_market -> DCFCalculator 使用美股參數。
"""

import pytest

from app.core.models.stock import Market, detect_market
from app.services.us_stock_support import (
    MarketContext,
    format_market_info,
    format_price,
    get_market_context,
    get_us_stock_error_message,
)


# ---------------------------------------------------------------------------
# get_market_context 測試
# ---------------------------------------------------------------------------


class TestGetMarketContext:
    """測試 get_market_context 市場上下文建立。"""

    def test_us_stock_aapl(self) -> None:
        """美股代碼 AAPL 應回傳 US 市場上下文。"""
        ctx = get_market_context("AAPL")
        assert ctx.market == Market.US
        assert ctx.currency == "USD"
        assert ctx.currency_symbol == "$"
        assert ctx.market_label == "美股"
        assert ctx.is_us_stock is True

    def test_us_stock_msft(self) -> None:
        """美股代碼 MSFT 應回傳 US 市場上下文。"""
        ctx = get_market_context("MSFT")
        assert ctx.is_us_stock is True
        assert ctx.currency == "USD"

    def test_us_stock_lowercase(self) -> None:
        """小寫美股代碼應被正確辨識。"""
        ctx = get_market_context("tsla")
        assert ctx.market == Market.US
        assert ctx.is_us_stock is True

    def test_tw_stock_2330(self) -> None:
        """台股代碼 2330 應回傳 TW 市場上下文。"""
        ctx = get_market_context("2330")
        assert ctx.market == Market.TW
        assert ctx.currency == "TWD"
        assert ctx.currency_symbol == "NT$"
        assert ctx.market_label == "台股（上市）"
        assert ctx.is_us_stock is False

    def test_two_stock_6510(self) -> None:
        """上櫃代碼 6510 應回傳 TWO 市場上下文。"""
        ctx = get_market_context("6510")
        assert ctx.market == Market.TWO
        assert ctx.currency == "TWD"
        assert ctx.market_label == "台股（上櫃）"
        assert ctx.is_us_stock is False

    def test_tw_stock_with_suffix(self) -> None:
        """帶 .TW 後綴的台股代碼應回傳 TW 市場上下文。"""
        ctx = get_market_context("2330.TW")
        assert ctx.market == Market.TW
        assert ctx.is_us_stock is False

    def test_market_context_is_frozen(self) -> None:
        """MarketContext 為不可變資料類別。"""
        ctx = get_market_context("AAPL")
        with pytest.raises(Exception):
            ctx.currency = "EUR"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# format_price 測試
# ---------------------------------------------------------------------------


class TestFormatPrice:
    """測試 format_price 價格格式化。"""

    def test_us_stock_price_two_decimals(self) -> None:
        """美股價格應保留兩位小數。"""
        result = format_price(175.50, Market.US)
        assert result == "$175.50"

    def test_us_stock_price_large(self) -> None:
        """美股大額價格應有千分位逗號。"""
        result = format_price(3450.00, Market.US)
        assert result == "$3,450.00"

    def test_tw_stock_price_integer(self) -> None:
        """台股整數價格不顯示小數。"""
        result = format_price(973.0, Market.TW)
        assert result == "NT$973"

    def test_tw_stock_price_with_decimal(self) -> None:
        """台股非整數價格應保留兩位小數。"""
        result = format_price(59.55, Market.TW)
        assert result == "NT$59.55"

    def test_two_stock_price(self) -> None:
        """上櫃股價使用 NT$ 符號。"""
        result = format_price(150.0, Market.TWO)
        assert result == "NT$150"

    def test_us_stock_price_penny(self) -> None:
        """美股小額價格正確格式化。"""
        result = format_price(0.75, Market.US)
        assert result == "$0.75"


# ---------------------------------------------------------------------------
# get_us_stock_error_message 測試
# ---------------------------------------------------------------------------


class TestGetUsStockErrorMessage:
    """測試美股專屬錯誤訊息。"""

    def test_returns_correct_message(self) -> None:
        """應回傳符合需求 11.5 的錯誤訊息。"""
        msg = get_us_stock_error_message()
        assert msg == "美股資料暫時無法取得，請確認網路連線"

    def test_message_not_empty(self) -> None:
        """錯誤訊息不得為空。"""
        msg = get_us_stock_error_message()
        assert len(msg) > 0


# ---------------------------------------------------------------------------
# format_market_info 測試
# ---------------------------------------------------------------------------


class TestFormatMarketInfo:
    """測試 format_market_info 市場資訊摘要。"""

    def test_us_stock_info(self) -> None:
        """美股資訊摘要格式正確。"""
        result = format_market_info("aapl")
        assert result == "AAPL (美股 / USD)"

    def test_tw_stock_info(self) -> None:
        """台股資訊摘要格式正確。"""
        result = format_market_info("2330")
        assert "台股" in result
        assert "TWD" in result


# ---------------------------------------------------------------------------
# 端對端整合驗證
# ---------------------------------------------------------------------------


class TestEndToEndIntegration:
    """驗證美股支援的端對端整合流程。

    流程：使用者輸入 "AAPL"
    -> detect_market -> Market.US
    -> DCFCalculator 使用 US params (4.5%, 5%, 2.5%, 2.5%)
    -> YFinanceSource 使用 "AAPL"（無後綴）
    -> UI 顯示 "美股" 標籤和 "USD" 幣別
    """

    def test_detect_market_us_stock(self) -> None:
        """detect_market 對美股代碼回傳 Market.US。"""
        assert detect_market("AAPL") == Market.US
        assert detect_market("MSFT") == Market.US
        assert detect_market("GOOG") == Market.US
        assert detect_market("NVDA") == Market.US

    def test_detect_market_tw_stock(self) -> None:
        """detect_market 對台股代碼回傳 Market.TW。"""
        assert detect_market("2330") == Market.TW
        assert detect_market("2317") == Market.TW

    def test_dcf_calculator_uses_us_params(self) -> None:
        """DCFCalculator 在美股模式使用正確的預設參數。"""
        from app.services.dcf_calculator import DCFCalculator, _get_market_params

        # 驗證美股參數
        us_params = _get_market_params(Market.US)
        assert us_params["risk_free_rate"] == 0.045
        assert us_params["risk_premium"] == 0.05
        assert us_params["inflation_rate"] == 0.025
        assert us_params["perpetual_growth"] == 0.025

        # 驗證台股參數（對照）
        tw_params = _get_market_params(Market.TW)
        assert tw_params["risk_free_rate"] == 0.04
        assert tw_params["risk_premium"] == 0.04
        assert tw_params["inflation_rate"] == 0.03
        assert tw_params["perpetual_growth"] == 0.02

    def test_dcf_calculator_auto_detect_market(self) -> None:
        """DCFCalculator 能自動偵測 stock_code 的市場別並切換參數。"""
        from app.services.dcf_calculator import DCFCalculator

        calc = DCFCalculator()
        result = calc.calculate_dcf_value(
            current_price=175.0,
            current_eps=6.5,
            growth_rates=[0.15, 0.08],
            stock_code="AAPL",
        )
        # 結果應為有效的正數內在價值
        assert result.intrinsic_value > 0
        assert result.stock_code == "AAPL"

    def test_yfinance_ticker_format_us(self) -> None:
        """YFinanceSource 的 ticker 轉換對美股代碼不加後綴。"""
        from app.infra.sources.yfinance_source import _to_yfinance_ticker

        ticker = _to_yfinance_ticker("AAPL")
        # 美股不應有 .TW 或 .TWO 後綴
        assert ticker == "AAPL"

    def test_yfinance_ticker_format_tw(self) -> None:
        """YFinanceSource 的 ticker 轉換對台股代碼加 .TW 後綴。"""
        from app.infra.sources.yfinance_source import _to_yfinance_ticker

        ticker = _to_yfinance_ticker("2330")
        assert ticker == "2330.TW"

    def test_ui_context_matches_market(self) -> None:
        """UI 上下文應與 detect_market 結果一致。"""
        # 美股
        us_ctx = get_market_context("AAPL")
        assert us_ctx.market == detect_market("AAPL")
        assert us_ctx.market_label == "美股"
        assert us_ctx.currency == "USD"

        # 台股
        tw_ctx = get_market_context("2330")
        assert tw_ctx.market == detect_market("2330")
        assert tw_ctx.market_label == "台股（上市）"
        assert tw_ctx.currency == "TWD"
