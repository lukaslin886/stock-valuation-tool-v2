"""FinMind 資料來源模組。

透過 FinMind API 取得台股股價、財報與公司基本資訊。
整合 Rate Limiter 控制請求頻率、Circuit Breaker 保護失敗隔離，
並處理 HTTP 402（配額耗盡）自動切換備援來源的邏輯。

外部相依套件（FinMind DataLoader）採用懶載入（lazy import），
使本模組可在未安裝 finmind 時仍能被 import（不會在模組載入時報錯）。

Usage::

    from app.infra.sources.finmind_source import FinMindSource
    from app.infra.resilience.circuit_breaker import CircuitBreaker
    from app.infra.resilience.rate_limiter import FinMindRateLimiter

    cb = CircuitBreaker(source_name="finmind")
    rl = FinMindRateLimiter(circuit_breaker=cb)
    source = FinMindSource(token="your_api_token", rate_limiter=rl, circuit_breaker=cb)

    df = source.get_stock_price("2330", start_date, end_date)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd

from app.core.errors import DataSourceError, RateLimitError
from app.infra.logging import get_logger
from app.infra.resilience.circuit_breaker import CircuitBreaker
from app.infra.resilience.rate_limiter import FinMindRateLimiter
from app.infra.sources.base import BaseDataSource

logger = get_logger(__name__)


class FinMindSource(BaseDataSource):
    """FinMind 資料來源實作。

    使用 FinMind DataLoader API 取得台股相關資料，搭配速率限制器與
    斷路器實現韌性存取。當 HTTP 402 發生時，自動觸發斷路器並通知
    呼叫方切換至備援來源。

    Attributes:
        _token: FinMind API 存取 token。
        _rate_limiter: FinMind 專用速率限制器實例。

    Example::

        source = FinMindSource(
            token="my_token",
            rate_limiter=fm_rate_limiter,
            circuit_breaker=fm_circuit_breaker,
        )
        prices = source.get_stock_price("2330", start, end)
    """

    def __init__(
        self,
        token: str,
        rate_limiter: FinMindRateLimiter,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """初始化 FinMind 資料來源。

        Args:
            token: FinMind API token 字串。
            rate_limiter: FinMind 專用速率限制器（含配額預檢與降速邏輯）。
            circuit_breaker: 對應 FinMind 的斷路器實例。
        """
        super().__init__(circuit_breaker=circuit_breaker)
        self._token: str = token
        self._rate_limiter: FinMindRateLimiter = rate_limiter

    @property
    def source_name(self) -> str:
        """資料來源名稱。

        Returns:
            固定回傳 "finmind"。
        """
        return "finmind"

    def _acquire_rate_limit(self) -> None:
        """在發送請求前取得速率限制 token。

        使用阻塞式等待，確保不超過配置的請求頻率。

        Raises:
            RateLimitError: 當速率限制器無法取得 token 時。
        """
        if not self._rate_limiter.acquire():
            self._rate_limiter.wait_and_acquire()

    def _handle_http_402(self, stock_code: Optional[str] = None) -> None:
        """處理 FinMind HTTP 402 回應。

        觸發速率限制器的 HTTP 402 處理邏輯（記錄事件 + 觸發斷路器），
        並拋出 RateLimitError 通知呼叫方切換備援。

        Args:
            stock_code: 正在處理的股票代碼。

        Raises:
            RateLimitError: 永遠拋出，通知呼叫方配額耗盡。
        """
        status = self._rate_limiter.handle_http_402()
        logger.error(
            "FinMind HTTP 402 配額耗盡，建議切換備援來源",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        raise RateLimitError(
            message="FinMind API 配額耗盡 (HTTP 402)，請切換備援來源",
            retry_after=300.0,
            stock_code=stock_code,
        )

    def _get_data_loader(self) -> Any:
        """懶載入 FinMind DataLoader 並登入。

        Returns:
            已登入的 FinMind DataLoader 實例。

        Raises:
            DataSourceError: FinMind 套件未安裝或登入失敗。
        """
        try:
            from FinMind.data import DataLoader  # type: ignore[import-untyped]
        except ImportError as exc:
            raise DataSourceError(
                message="FinMind 套件未安裝，請執行 uv add FinMind",
                source_name=self.source_name,
            ) from exc

        try:
            dl = DataLoader()
            dl.login_by_token(api_token=self._token)
            return dl
        except Exception as exc:
            error_msg = str(exc)
            # 偵測 HTTP 402
            if "402" in error_msg:
                self._handle_http_402()
            raise DataSourceError(
                message=f"FinMind DataLoader 登入失敗: {exc}",
                source_name=self.source_name,
            ) from exc

    def _fetch_stock_price(
        self, stock_code: str, start_date: datetime, end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """取得台股每日股價資料。

        使用 FinMind ``taiwan_stock_daily`` API 取得 OHLCV 資料。

        Args:
            stock_code: 台股代碼（例如 "2330"）。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            包含 date, open, high, low, close, volume 欄位的 DataFrame。
            若無資料則回傳 None。

        Raises:
            DataSourceError: API 呼叫失敗或回應格式異常。
        """
        self._acquire_rate_limit()

        try:
            dl = self._get_data_loader()
            df = dl.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
        except (RateLimitError, DataSourceError):
            raise
        except Exception as exc:
            error_msg = str(exc)
            if "402" in error_msg:
                self._handle_http_402(stock_code)
            raise DataSourceError(
                message=f"FinMind 取得股價資料失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        if df is None or df.empty:
            logger.debug(
                "FinMind 無股價資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 統一欄位名稱
        column_mapping = {
            "date": "date",
            "open": "open",
            "max": "high",
            "min": "low",
            "close": "close",
            "Trading_Volume": "volume",
        }
        df = df.rename(columns=column_mapping)

        # 僅保留需要的欄位
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        available_cols = [c for c in required_cols if c in df.columns]
        df = df[available_cols]

        logger.debug(
            f"FinMind 取得 {len(df)} 筆股價資料",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return df

    def _fetch_financial_data(
        self, stock_code: str, years: int = 5
    ) -> Optional[pd.DataFrame]:
        """取得台股財務報表資料。

        使用 FinMind 財報相關端點取得 EPS、營收、ROE 等資料。

        Args:
            stock_code: 台股代碼。
            years: 回溯年數，預設 5 年。

        Returns:
            包含 period, revenue, eps, roe 等欄位的 DataFrame。
            若無資料則回傳 None。

        Raises:
            DataSourceError: API 呼叫失敗。
        """
        self._acquire_rate_limit()

        try:
            dl = self._get_data_loader()

            # 計算起始日期
            start_date = (
                datetime.now() - timedelta(days=years * 365)
            ).strftime("%Y-%m-%d")

            # 使用綜合損益表取得財報資料
            df = dl.taiwan_stock_financial_statement(
                stock_id=stock_code,
                start_date=start_date,
            )
        except (RateLimitError, DataSourceError):
            raise
        except Exception as exc:
            error_msg = str(exc)
            if "402" in error_msg:
                self._handle_http_402(stock_code)
            raise DataSourceError(
                message=f"FinMind 取得財報資料失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        if df is None or df.empty:
            logger.debug(
                "FinMind 無財報資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 嘗試轉換為標準化格式
        result = self._normalize_financial_data(df, stock_code)

        logger.debug(
            f"FinMind 取得 {len(result)} 筆財報資料",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return result

    def _normalize_financial_data(
        self, df: pd.DataFrame, stock_code: str
    ) -> pd.DataFrame:
        """將 FinMind 財報原始資料轉換為標準化格式。

        FinMind 財報資料為長表格式（每列為一個指標），
        本方法將其轉換為每列為一個期間的寬表格式。

        Args:
            df: FinMind 原始財報 DataFrame。
            stock_code: 股票代碼。

        Returns:
            標準化後的 DataFrame，包含 period, revenue, eps 等欄位。
        """
        # FinMind 財報資料可能有 date, type, value 等欄位
        # 視實際 API 回傳格式做適當轉換
        if "date" in df.columns and "type" in df.columns and "value" in df.columns:
            # 長表轉寬表
            pivot_df = df.pivot_table(
                index="date", columns="type", values="value", aggfunc="first"
            ).reset_index()
            pivot_df = pivot_df.rename(columns={"date": "period"})
            pivot_df.insert(0, "stock_code", stock_code)
            return pivot_df

        # 如果已經是可用格式，直接加上 stock_code
        if "stock_code" not in df.columns:
            df = df.copy()
            df.insert(0, "stock_code", stock_code)
        return df

    def _fetch_stock_info(
        self, stock_code: str
    ) -> Optional[Dict[str, Any]]:
        """取得股票基本資訊。

        使用 FinMind 公司基本資訊端點。

        Args:
            stock_code: 台股代碼。

        Returns:
            包含 stock_name, industry, market 等資訊的字典。
            若查詢失敗則回傳 None。

        Raises:
            DataSourceError: API 呼叫失敗。
        """
        self._acquire_rate_limit()

        try:
            dl = self._get_data_loader()
            df = dl.taiwan_stock_info()
        except (RateLimitError, DataSourceError):
            raise
        except Exception as exc:
            error_msg = str(exc)
            if "402" in error_msg:
                self._handle_http_402(stock_code)
            raise DataSourceError(
                message=f"FinMind 取得公司資訊失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        if df is None or df.empty:
            logger.debug(
                "FinMind 無公司資訊資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 篩選指定股票代碼
        stock_df = df[df["stock_id"] == stock_code]
        if stock_df.empty:
            logger.debug(
                f"FinMind 未找到股票 {stock_code} 的公司資訊",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        row = stock_df.iloc[0]
        info: Dict[str, Any] = {
            "stock_code": stock_code,
            "stock_name": row.get("stock_name", ""),
            "industry": row.get("industry_category", ""),
            "market": row.get("type", "twse"),
        }

        logger.debug(
            "FinMind 取得公司資訊成功",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return info
