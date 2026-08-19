"""統一錯誤處理器模組。

根據錯誤類型分流處理，記錄完整堆疊追蹤至日誌，
並向使用者顯示友善錯誤訊息。Market Scanner 個別股票錯誤
不中斷整體流程，記錄後繼續。

Usage::

    from app.infra.error_handler import ErrorHandler, ErrorResult

    handler = ErrorHandler()
    result = handler.handle_error(error, context={"stock_code": "2330"})
    if result.should_continue:
        # 繼續處理下一支股票
        ...
    else:
        # 向使用者顯示錯誤訊息
        print(result.user_message)
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.errors import (
    CircuitOpenError,
    DataSourceError,
    RateLimitError,
    StockToolError,
    TimeoutError,
    ValidationError,
)
from app.infra.logging import get_logger


# ---------------------------------------------------------------------------
# ErrorResult 資料結構
# ---------------------------------------------------------------------------


@dataclass
class ErrorResult:
    """錯誤處理結果。

    統一封裝錯誤處理後的資訊，供呼叫端決定後續行為。

    Attributes:
        success: 操作是否仍算成功（例如有 fallback 資料可用）。
        user_message: 顯示給使用者的友善訊息。
        should_continue: 是否應繼續處理後續項目（用於批次作業）。
        fallback_data: 降級回傳的替代資料，可為 None。
        error_type: 錯誤分類名稱（如 "DataSourceError"）。
        stock_code: 發生錯誤的股票代碼，可為 None。
    """

    success: bool = False
    user_message: str = ""
    should_continue: bool = True
    fallback_data: Optional[Any] = None
    error_type: str = ""
    stock_code: Optional[str] = None


# ---------------------------------------------------------------------------
# 使用者友善訊息對照表
# ---------------------------------------------------------------------------

_USER_MESSAGES: Dict[type, str] = {
    DataSourceError: "資料來源暫時無法連線，系統正在嘗試備援來源。",
    ValidationError: "資料格式異常，已回傳快取資料供參考。",
    TimeoutError: "資料取得逾時，請稍後再試。",
    RateLimitError: "API 請求過於頻繁，系統將自動降速並重試。",
    CircuitOpenError: "該資料來源暫時停用，系統已自動切換備援。",
}

_DEFAULT_USER_MESSAGE = "系統暫時無法處理您的請求，請稍後再試。"


# ---------------------------------------------------------------------------
# ErrorHandler 類別
# ---------------------------------------------------------------------------


class ErrorHandler:
    """統一錯誤處理器。

    根據錯誤類型進行分流處理：
    - DataSourceError: 記錄 + 建議 fallback
    - ValidationError: 記錄 + 建議使用快取資料
    - TimeoutError: 記錄 + circuit breaker 紀錄
    - RateLimitError: 記錄 + backoff 建議
    - CircuitOpenError: 記錄 + 跳過該來源
    - 未知例外: 記錄完整堆疊追蹤 + 通用友善訊息

    Attributes:
        logger: 結構化日誌記錄器。
    """

    def __init__(self) -> None:
        """初始化錯誤處理器。"""
        self._logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorResult:
        """處理錯誤並回傳結構化結果。

        根據錯誤類型分流至對應處理器，記錄完整堆疊追蹤，
        並產生使用者友善訊息。

        Args:
            error: 捕獲到的例外物件。
            context: 額外上下文資訊（如 stock_code、source 等）。

        Returns:
            ErrorResult 包含處理結果與後續行為建議。
        """
        ctx = context or {}
        stock_code = ctx.get("stock_code") or getattr(error, "stock_code", None)

        # 依錯誤類型分流處理
        if isinstance(error, DataSourceError):
            return self._handle_data_source_error(error, stock_code, ctx)
        elif isinstance(error, ValidationError):
            return self._handle_validation_error(error, stock_code, ctx)
        elif isinstance(error, TimeoutError):
            return self._handle_timeout_error(error, stock_code, ctx)
        elif isinstance(error, RateLimitError):
            return self._handle_rate_limit_error(error, stock_code, ctx)
        elif isinstance(error, CircuitOpenError):
            return self._handle_circuit_open_error(error, stock_code, ctx)
        elif isinstance(error, StockToolError):
            return self._handle_stock_tool_error(error, stock_code, ctx)
        else:
            return self._handle_unknown_error(error, stock_code, ctx)

    def get_user_message(self, error: Exception) -> str:
        """取得使用者友善錯誤訊息。

        根據錯誤類型回傳預定義的友善訊息，
        未知錯誤回傳通用訊息。

        Args:
            error: 例外物件。

        Returns:
            使用者可讀的錯誤訊息字串。
        """
        for error_type, message in _USER_MESSAGES.items():
            if isinstance(error, error_type):
                return message
        return _DEFAULT_USER_MESSAGE

    def handle_stock_batch_error(
        self,
        error: Exception,
        stock_code: str,
        batch_context: Optional[Dict[str, Any]] = None,
    ) -> ErrorResult:
        """處理 Market Scanner 批次作業中個別股票的錯誤。

        個別股票錯誤不中斷整體流程，記錄後繼續處理下一支。
        此方法確保 should_continue 永遠為 True。

        Args:
            error: 捕獲到的例外物件。
            stock_code: 發生錯誤的股票代碼。
            batch_context: 批次作業的額外上下文（如批次編號）。

        Returns:
            ErrorResult，should_continue 固定為 True。
        """
        ctx = batch_context or {}
        ctx["stock_code"] = stock_code
        ctx["batch_mode"] = True

        # 記錄錯誤（含完整堆疊）
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context=ctx,
            level="warning",
        )

        return ErrorResult(
            success=False,
            user_message=self.get_user_message(error),
            should_continue=True,
            fallback_data=None,
            error_type=type(error).__name__,
            stock_code=stock_code,
        )

    # ------------------------------------------------------------------
    # 私有分流處理器
    # ------------------------------------------------------------------

    def _handle_data_source_error(
        self,
        error: DataSourceError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理資料來源錯誤：記錄 + 建議 fallback。

        Args:
            error: DataSourceError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，建議使用 fallback 來源。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context={
                "source_name": error.source_name,
                "action": "fallback_to_next_source",
                **ctx,
            },
            level="warning",
        )

        return ErrorResult(
            success=False,
            user_message=_USER_MESSAGES[DataSourceError],
            should_continue=True,
            fallback_data=None,
            error_type="DataSourceError",
            stock_code=stock_code,
        )

    def _handle_validation_error(
        self,
        error: ValidationError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理驗證錯誤：記錄 + 建議使用快取資料。

        Args:
            error: ValidationError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，建議使用快取資料。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context={
                "field_name": error.field_name,
                "action": "use_cached_data",
                **ctx,
            },
            level="warning",
        )

        return ErrorResult(
            success=False,
            user_message=_USER_MESSAGES[ValidationError],
            should_continue=True,
            fallback_data=None,
            error_type="ValidationError",
            stock_code=stock_code,
        )

    def _handle_timeout_error(
        self,
        error: TimeoutError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理逾時錯誤：記錄 + circuit breaker 紀錄。

        Args:
            error: TimeoutError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，標記 circuit breaker 應記錄失敗。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context={
                "timeout_seconds": error.timeout_seconds,
                "action": "record_circuit_breaker_failure",
                **ctx,
            },
            level="error",
        )

        return ErrorResult(
            success=False,
            user_message=_USER_MESSAGES[TimeoutError],
            should_continue=True,
            fallback_data=None,
            error_type="TimeoutError",
            stock_code=stock_code,
        )

    def _handle_rate_limit_error(
        self,
        error: RateLimitError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理速率限制錯誤：記錄 + backoff 建議。

        Args:
            error: RateLimitError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，包含建議退避時間。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context={
                "retry_after": error.retry_after,
                "action": "exponential_backoff",
                **ctx,
            },
            level="warning",
        )

        return ErrorResult(
            success=False,
            user_message=_USER_MESSAGES[RateLimitError],
            should_continue=True,
            fallback_data=None,
            error_type="RateLimitError",
            stock_code=stock_code,
        )

    def _handle_circuit_open_error(
        self,
        error: CircuitOpenError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理斷路器開啟錯誤：記錄 + 跳過該來源。

        Args:
            error: CircuitOpenError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，建議跳過該來源。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context={
                "source_name": error.source_name,
                "action": "skip_source",
                **ctx,
            },
            level="warning",
        )

        return ErrorResult(
            success=False,
            user_message=_USER_MESSAGES[CircuitOpenError],
            should_continue=True,
            fallback_data=None,
            error_type="CircuitOpenError",
            stock_code=stock_code,
        )

    def _handle_stock_tool_error(
        self,
        error: StockToolError,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理其他 StockToolError 子類別。

        Args:
            error: StockToolError 例外。
            stock_code: 股票代碼。
            ctx: 上下文字典。

        Returns:
            ErrorResult，通用處理。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context=ctx,
            level="error",
        )

        return ErrorResult(
            success=False,
            user_message=_DEFAULT_USER_MESSAGE,
            should_continue=True,
            fallback_data=None,
            error_type=type(error).__name__,
            stock_code=stock_code,
        )

    def _handle_unknown_error(
        self,
        error: Exception,
        stock_code: Optional[str],
        ctx: Dict[str, Any],
    ) -> ErrorResult:
        """處理未知例外：記錄完整堆疊追蹤 + 通用友善訊息。

        Args:
            error: 任意例外物件。
            stock_code: 股票代碼（可能為 None）。
            ctx: 上下文字典。

        Returns:
            ErrorResult，通用錯誤訊息。
        """
        self._log_error(
            error,
            stock_code=stock_code,
            extra_context=ctx,
            level="error",
        )

        return ErrorResult(
            success=False,
            user_message=_DEFAULT_USER_MESSAGE,
            should_continue=False,
            fallback_data=None,
            error_type=type(error).__name__,
            stock_code=stock_code,
        )

    # ------------------------------------------------------------------
    # 日誌輔助
    # ------------------------------------------------------------------

    def _log_error(
        self,
        error: Exception,
        stock_code: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        level: str = "error",
    ) -> None:
        """記錄錯誤至結構化日誌，包含完整堆疊追蹤。

        Args:
            error: 例外物件。
            stock_code: 股票代碼。
            extra_context: 額外上下文欄位。
            level: 日誌等級（"warning"、"error"、"critical"）。
        """
        extra: Dict[str, Any] = {
            "stock_code": stock_code,
            "error_type": type(error).__name__,
        }
        if extra_context:
            extra.update(extra_context)

        # 構建包含堆疊追蹤的訊息
        tb_str = traceback.format_exception(type(error), error, error.__traceback__)
        full_traceback = "".join(tb_str)

        log_message = (
            f"[{type(error).__name__}] {error}"
        )

        log_func = getattr(self._logger, level, self._logger.error)
        log_func(
            log_message,
            extra=extra,
            exc_info=(type(error), error, error.__traceback__),
        )
