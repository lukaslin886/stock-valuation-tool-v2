"""自訂例外類別階層。

定義台股估值工具的統一錯誤分類體系，提供結構化的錯誤上下文資訊，
以利日誌記錄、錯誤分流與使用者友善訊息產生。

Typical usage::

    from app.core.errors import DataSourceError, ValidationError

    raise DataSourceError(
        message="Yahoo Finance API 回應逾時",
        source_name="yahoo_finance",
        stock_code="2330",
    )
"""

from __future__ import annotations

from typing import Optional


class StockToolError(Exception):
    """台股估值工具基礎例外類別。

    所有業務相關例外的共同父類別，提供 ``stock_code`` 上下文欄位，
    方便日誌記錄與錯誤追蹤時快速定位受影響的股票。

    Attributes:
        stock_code: 發生錯誤時正在處理的股票代碼，可為 None。
        message: 人類可讀的錯誤描述。
    """

    def __init__(
        self,
        message: str,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化基礎例外。

        Args:
            message: 人類可讀的錯誤描述。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.stock_code: Optional[str] = stock_code
        self.message: str = message
        super().__init__(message)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [f"message={self.message!r}"]
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class DataSourceError(StockToolError):
    """資料來源錯誤。

    當外部資料來源（如 Yahoo Finance、FinMind、FinLab）不可達、
    回應格式異常、或回傳非預期狀態碼時拋出。

    Attributes:
        source_name: 發生錯誤的資料來源名稱（例如 "yahoo_finance"、"finmind"）。
    """

    def __init__(
        self,
        message: str,
        source_name: str,
        *,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化資料來源錯誤。

        Args:
            message: 人類可讀的錯誤描述。
            source_name: 發生錯誤的資料來源名稱。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.source_name: str = source_name
        super().__init__(message, stock_code=stock_code)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [
            f"message={self.message!r}",
            f"source_name={self.source_name!r}",
        ]
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class ValidationError(StockToolError):
    """資料驗證失敗。

    當 API 回應缺少必要欄位、數值超出合理範圍（例如 PE ratio 超出
    [-100, 10000]）、或資料格式不符預期時拋出。

    Attributes:
        field_name: 驗證失敗的欄位名稱。
    """

    def __init__(
        self,
        message: str,
        field_name: str,
        *,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化資料驗證錯誤。

        Args:
            message: 人類可讀的錯誤描述。
            field_name: 驗證失敗的欄位名稱。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.field_name: str = field_name
        super().__init__(message, stock_code=stock_code)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [
            f"message={self.message!r}",
            f"field_name={self.field_name!r}",
        ]
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class TimeoutError(StockToolError):
    """請求逾時。

    當對外部 API 的請求超過允許的時間上限時拋出。
    記錄逾時秒數以利診斷與調整逾時設定。

    Attributes:
        timeout_seconds: 觸發逾時的秒數閾值。
    """

    def __init__(
        self,
        message: str,
        timeout_seconds: float,
        *,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化逾時錯誤。

        Args:
            message: 人類可讀的錯誤描述。
            timeout_seconds: 觸發逾時的秒數閾值。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.timeout_seconds: float = timeout_seconds
        super().__init__(message, stock_code=stock_code)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [
            f"message={self.message!r}",
            f"timeout_seconds={self.timeout_seconds!r}",
        ]
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class RateLimitError(StockToolError):
    """速率限制觸發。

    當外部 API（如 FinMind）回傳 HTTP 402 或其他速率限制回應時拋出。
    若 API 提供重試等待時間，記錄於 ``retry_after`` 欄位。

    Attributes:
        retry_after: API 建議的重試等待秒數，可為 None（未提供時）。
    """

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        *,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化速率限制錯誤。

        Args:
            message: 人類可讀的錯誤描述。
            retry_after: API 建議的重試等待秒數。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.retry_after: Optional[float] = retry_after
        super().__init__(message, stock_code=stock_code)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [f"message={self.message!r}"]
        if self.retry_after is not None:
            parts.append(f"retry_after={self.retry_after!r}")
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class CircuitOpenError(StockToolError):
    """斷路器已開啟。

    當某個資料來源的斷路器（Circuit Breaker）處於開啟狀態，
    請求被立即拒絕而不實際發送時拋出。系統應自動略過該來源並
    使用下一優先順序的備援來源。

    Attributes:
        source_name: 斷路器已開啟的資料來源名稱。
    """

    def __init__(
        self,
        message: str,
        source_name: str,
        *,
        stock_code: Optional[str] = None,
    ) -> None:
        """初始化斷路器開啟錯誤。

        Args:
            message: 人類可讀的錯誤描述。
            source_name: 斷路器已開啟的資料來源名稱。
            stock_code: 發生錯誤時正在處理的股票代碼。
        """
        self.source_name: str = source_name
        super().__init__(message, stock_code=stock_code)

    def __repr__(self) -> str:
        """回傳含上下文的表示字串。"""
        parts: list[str] = [
            f"message={self.message!r}",
            f"source_name={self.source_name!r}",
        ]
        if self.stock_code is not None:
            parts.append(f"stock_code={self.stock_code!r}")
        return f"{type(self).__name__}({', '.join(parts)})"
