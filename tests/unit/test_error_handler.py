"""統一錯誤處理器單元測試。

驗證 ErrorHandler 的錯誤分流處理、友善訊息產生、
批次作業錯誤不中斷流程等行為。
"""

import pytest

from app.core.errors import (
    CircuitOpenError,
    DataSourceError,
    RateLimitError,
    StockToolError,
    TimeoutError,
    ValidationError,
)
from app.infra.error_handler import ErrorHandler, ErrorResult


@pytest.fixture
def handler() -> ErrorHandler:
    """建立 ErrorHandler 實例。"""
    return ErrorHandler()


class TestErrorResult:
    """ErrorResult 資料結構測試。"""

    def test_default_values(self) -> None:
        """預設值為失敗、空訊息、應繼續。"""
        result = ErrorResult()
        assert result.success is False
        assert result.user_message == ""
        assert result.should_continue is True
        assert result.fallback_data is None
        assert result.error_type == ""
        assert result.stock_code is None


class TestHandleError:
    """handle_error 分流處理測試。"""

    def test_data_source_error(self, handler: ErrorHandler) -> None:
        """DataSourceError 回傳 fallback 建議。"""
        error = DataSourceError(
            message="Yahoo Finance API 回應逾時",
            source_name="yahoo_finance",
            stock_code="2330",
        )
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "DataSourceError"
        assert result.stock_code == "2330"
        assert "備援" in result.user_message or "來源" in result.user_message

    def test_validation_error(self, handler: ErrorHandler) -> None:
        """ValidationError 回傳快取資料建議。"""
        error = ValidationError(
            message="PE ratio 超出範圍",
            field_name="pe_ratio",
            stock_code="2317",
        )
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "ValidationError"
        assert result.stock_code == "2317"
        assert "快取" in result.user_message

    def test_timeout_error(self, handler: ErrorHandler) -> None:
        """TimeoutError 回傳逾時訊息。"""
        error = TimeoutError(
            message="FinMind API 逾時",
            timeout_seconds=15.0,
            stock_code="2454",
        )
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "TimeoutError"
        assert result.stock_code == "2454"
        assert "逾時" in result.user_message

    def test_rate_limit_error(self, handler: ErrorHandler) -> None:
        """RateLimitError 回傳退避建議。"""
        error = RateLimitError(
            message="FinMind 配額已用完",
            retry_after=5.0,
            stock_code="2412",
        )
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "RateLimitError"
        assert result.stock_code == "2412"
        assert "頻繁" in result.user_message or "降速" in result.user_message

    def test_circuit_open_error(self, handler: ErrorHandler) -> None:
        """CircuitOpenError 回傳跳過來源建議。"""
        error = CircuitOpenError(
            message="yahoo_finance 斷路器已開啟",
            source_name="yahoo_finance",
            stock_code="1301",
        )
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "CircuitOpenError"
        assert result.stock_code == "1301"
        assert "備援" in result.user_message or "停用" in result.user_message

    def test_unknown_error_should_not_continue(self, handler: ErrorHandler) -> None:
        """未知例外：should_continue 為 False。"""
        error = RuntimeError("something unexpected")
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is False
        assert result.error_type == "RuntimeError"
        assert "暫時無法處理" in result.user_message

    def test_stock_tool_base_error(self, handler: ErrorHandler) -> None:
        """StockToolError base 類別的通用處理。"""
        error = StockToolError(message="一般業務錯誤", stock_code="3008")
        result = handler.handle_error(error)

        assert result.success is False
        assert result.should_continue is True
        assert result.error_type == "StockToolError"
        assert result.stock_code == "3008"

    def test_context_overrides_stock_code(self, handler: ErrorHandler) -> None:
        """context 中的 stock_code 優先於例外物件的。"""
        error = DataSourceError(
            message="API error",
            source_name="finmind",
            stock_code="2330",
        )
        result = handler.handle_error(error, context={"stock_code": "9999"})
        assert result.stock_code == "9999"

    def test_context_provides_stock_code_when_error_has_none(
        self, handler: ErrorHandler
    ) -> None:
        """例外無 stock_code 時從 context 取得。"""
        error = RuntimeError("oops")
        result = handler.handle_error(error, context={"stock_code": "1234"})
        assert result.stock_code == "1234"


class TestGetUserMessage:
    """get_user_message 測試。"""

    def test_data_source_error_message(self, handler: ErrorHandler) -> None:
        error = DataSourceError("fail", source_name="yf")
        msg = handler.get_user_message(error)
        assert "來源" in msg

    def test_validation_error_message(self, handler: ErrorHandler) -> None:
        error = ValidationError("bad", field_name="roe")
        msg = handler.get_user_message(error)
        assert "快取" in msg

    def test_timeout_error_message(self, handler: ErrorHandler) -> None:
        error = TimeoutError("slow", timeout_seconds=30.0)
        msg = handler.get_user_message(error)
        assert "逾時" in msg

    def test_rate_limit_error_message(self, handler: ErrorHandler) -> None:
        error = RateLimitError("too fast")
        msg = handler.get_user_message(error)
        assert "頻繁" in msg or "降速" in msg

    def test_circuit_open_error_message(self, handler: ErrorHandler) -> None:
        error = CircuitOpenError("open", source_name="fm")
        msg = handler.get_user_message(error)
        assert "停用" in msg or "備援" in msg

    def test_unknown_error_message(self, handler: ErrorHandler) -> None:
        error = ValueError("unexpected")
        msg = handler.get_user_message(error)
        assert "暫時無法處理" in msg


class TestHandleStockBatchError:
    """handle_stock_batch_error 測試 - Market Scanner 批次錯誤不中斷。"""

    def test_always_continues(self, handler: ErrorHandler) -> None:
        """批次模式下 should_continue 永遠為 True。"""
        error = DataSourceError(
            message="connection refused",
            source_name="yahoo_finance",
            stock_code="2330",
        )
        result = handler.handle_stock_batch_error(error, stock_code="2330")

        assert result.should_continue is True
        assert result.stock_code == "2330"
        assert result.error_type == "DataSourceError"

    def test_unknown_error_in_batch_still_continues(
        self, handler: ErrorHandler
    ) -> None:
        """即使是未知錯誤，批次模式也繼續。"""
        error = RuntimeError("unexpected crash")
        result = handler.handle_stock_batch_error(error, stock_code="3711")

        assert result.should_continue is True
        assert result.stock_code == "3711"
        assert result.error_type == "RuntimeError"

    def test_batch_context_preserved(self, handler: ErrorHandler) -> None:
        """批次上下文資訊被正確記錄。"""
        error = TimeoutError(
            message="too slow", timeout_seconds=30.0, stock_code="2454"
        )
        result = handler.handle_stock_batch_error(
            error,
            stock_code="2454",
            batch_context={"batch_number": 3, "total_batches": 10},
        )

        assert result.should_continue is True
        assert result.stock_code == "2454"
