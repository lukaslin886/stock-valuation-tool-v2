"""資料來源基礎類別模組。

提供 DataSourceProtocol 的共用實作邏輯，包含：
- Circuit Breaker 整合（請求前檢查 allow_request，成功/失敗後記錄）
- 錯誤包裝（將底層例外統一轉為 DataSourceError）
- 結構化日誌記錄（所有 API 呼叫前後記錄狀態）

所有具體資料來源（YFinance、FinMind、FinLab）應繼承此基礎類別，
僅需實作底層 API 呼叫邏輯，共用的保護與日誌機制由基礎類別處理。

Usage::

    from app.infra.sources.base import BaseDataSource

    class MySource(BaseDataSource):
        @property
        def source_name(self) -> str:
            return "my_source"

        def _fetch_stock_price(self, stock_code, start_date, end_date):
            ...
"""

from __future__ import annotations

import functools
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, Optional, TypeVar

import pandas as pd

from app.core.errors import CircuitOpenError, DataSourceError, TimeoutError
from app.infra.logging import get_logger, get_stock_logger
from app.infra.resilience.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

T = TypeVar("T")


class BaseDataSource(ABC):
    """資料來源抽象基礎類別。

    整合 Circuit Breaker 保護、錯誤包裝與結構化日誌，
    提供給具體資料來源實作繼承。

    子類別須實作以下方法：
    - source_name（property）
    - _fetch_stock_price
    - _fetch_financial_data
    - _fetch_stock_info

    Attributes:
        _circuit_breaker: 該來源對應的斷路器實例。
        _default_timeout: 單次 API 呼叫的預設逾時秒數。
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        default_timeout: float = 30.0,
    ) -> None:
        """初始化資料來源基礎類別。

        Args:
            circuit_breaker: 該來源對應的 CircuitBreaker 實例。
            default_timeout: 單次 API 呼叫的預設逾時秒數，預設 30.0。
        """
        self._circuit_breaker = circuit_breaker
        self._default_timeout = default_timeout

    @property
    @abstractmethod
    def source_name(self) -> str:
        """資料來源名稱。

        Returns:
            資料來源的唯一標識符字串。
        """
        ...

    @property
    def is_available(self) -> bool:
        """資料來源目前是否可用（斷路器未開啟）。

        注意：此屬性使用 state 檢查而非 allow_request()，
        避免在 half_open 狀態下消耗唯一的探測配額。

        Returns:
            True 表示來源可用（closed 或 half_open），
            False 表示斷路器已開啟（open）。
        """
        return self._circuit_breaker.state != "open"

    def is_ready(self) -> bool:
        """檢查資料來源是否已就緒可供查詢。

        預設實作檢查斷路器狀態。子類別可覆寫以加入更深入的健康檢查。

        Returns:
            True 表示已就緒，False 表示尚未就緒。
        """
        return self._circuit_breaker.state != "open"

    def get_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        """取得指定期間的股價資料。

        整合 Circuit Breaker 保護與錯誤包裝。

        Args:
            stock_code: 股票代碼（如 "2330"、"AAPL"）。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            包含 OHLCV 欄位的 DataFrame，若查詢失敗則回傳 None。

        Raises:
            CircuitOpenError: 當斷路器處於開啟狀態時。
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        return self._execute_with_protection(
            operation_name="get_stock_price",
            stock_code=stock_code,
            fetch_func=functools.partial(
                self._fetch_stock_price, stock_code, start_date, end_date
            ),
        )

    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5,
    ) -> Optional[pd.DataFrame]:
        """取得指定年數的財報資料。

        整合 Circuit Breaker 保護與錯誤包裝。

        Args:
            stock_code: 股票代碼。
            years: 回溯年數，預設為 5 年。

        Returns:
            包含財報欄位的 DataFrame，若查詢失敗則回傳 None。

        Raises:
            CircuitOpenError: 當斷路器處於開啟狀態時。
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        return self._execute_with_protection(
            operation_name="get_financial_data",
            stock_code=stock_code,
            fetch_func=functools.partial(
                self._fetch_financial_data, stock_code, years
            ),
        )

    def get_stock_info(
        self,
        stock_code: str,
    ) -> Optional[Dict[str, Any]]:
        """取得股票基本資訊。

        整合 Circuit Breaker 保護與錯誤包裝。

        Args:
            stock_code: 股票代碼。

        Returns:
            包含公司基本資訊的字典，若查詢失敗則回傳 None。

        Raises:
            CircuitOpenError: 當斷路器處於開啟狀態時。
            DataSourceError: 當資料來源發生不可恢復的錯誤時。
        """
        return self._execute_with_protection(
            operation_name="get_stock_info",
            stock_code=stock_code,
            fetch_func=functools.partial(self._fetch_stock_info, stock_code),
        )

    # ------------------------------------------------------------------
    # 子類別須實作的抽象方法
    # ------------------------------------------------------------------

    @abstractmethod
    def _fetch_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        """底層股價資料取得邏輯（由子類別實作）。

        Args:
            stock_code: 股票代碼。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            包含 OHLCV 欄位的 DataFrame，或 None。
        """
        ...

    @abstractmethod
    def _fetch_financial_data(
        self,
        stock_code: str,
        years: int,
    ) -> Optional[pd.DataFrame]:
        """底層財報資料取得邏輯（由子類別實作）。

        Args:
            stock_code: 股票代碼。
            years: 回溯年數。

        Returns:
            包含財報欄位的 DataFrame，或 None。
        """
        ...

    @abstractmethod
    def _fetch_stock_info(
        self,
        stock_code: str,
    ) -> Optional[Dict[str, Any]]:
        """底層股票基本資訊取得邏輯（由子類別實作）。

        Args:
            stock_code: 股票代碼。

        Returns:
            包含公司基本資訊的字典，或 None。
        """
        ...

    # ------------------------------------------------------------------
    # 保護機制：Circuit Breaker + 錯誤包裝 + 日誌
    # ------------------------------------------------------------------

    def _execute_with_protection(
        self,
        operation_name: str,
        stock_code: str,
        fetch_func: Callable[[], T],
    ) -> Optional[T]:
        """以 Circuit Breaker 保護執行 API 呼叫。

        流程：
        1. 檢查斷路器是否允許請求
        2. 執行 fetch_func
        3. 成功 -> record_success，回傳結果
        4. 失敗 -> record_failure，包裝為 DataSourceError

        Args:
            operation_name: 操作名稱（用於日誌），如 "get_stock_price"。
            stock_code: 股票代碼（用於日誌上下文）。
            fetch_func: 實際執行 API 呼叫的無參數可呼叫物件。

        Returns:
            API 呼叫結果，或 None（當呼叫失敗時）。

        Raises:
            CircuitOpenError: 當斷路器不允許請求時。
        """
        stock_logger = get_stock_logger(
            __name__, stock_code, source=self.source_name
        )

        # 檢查斷路器
        if not self._circuit_breaker.allow_request():
            stock_logger.warning(
                "斷路器已開啟，略過 %s.%s",
                self.source_name,
                operation_name,
            )
            raise CircuitOpenError(
                message=f"斷路器已開啟，{self.source_name} 暫時不可用",
                source_name=self.source_name,
                stock_code=stock_code,
            )

        stock_logger.debug(
            "呼叫 %s.%s 開始",
            self.source_name,
            operation_name,
        )
        start_time = time.time()

        try:
            result = fetch_func()
            elapsed = time.time() - start_time

            self._circuit_breaker.record_success()
            stock_logger.info(
                "%s.%s 成功 (%.2f 秒)",
                self.source_name,
                operation_name,
                elapsed,
            )
            return result

        except TimeoutError:
            elapsed = time.time() - start_time
            self._circuit_breaker.record_failure()
            stock_logger.warning(
                "%s.%s 逾時 (%.2f 秒)",
                self.source_name,
                operation_name,
                elapsed,
            )
            raise

        except DataSourceError:
            elapsed = time.time() - start_time
            self._circuit_breaker.record_failure()
            stock_logger.error(
                "%s.%s 失敗 (%.2f 秒)",
                self.source_name,
                operation_name,
                elapsed,
                exc_info=True,
            )
            raise

        except Exception as exc:
            elapsed = time.time() - start_time
            self._circuit_breaker.record_failure()
            stock_logger.error(
                "%s.%s 未預期錯誤 (%.2f 秒): %s",
                self.source_name,
                operation_name,
                elapsed,
                str(exc),
                exc_info=True,
            )
            raise DataSourceError(
                message=f"{self.source_name}.{operation_name} 失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc
