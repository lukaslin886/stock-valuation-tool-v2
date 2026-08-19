"""FinLab 資料來源模組。

透過 FinLab API 取得台股股價、財報與公司基本資訊。
整合 Circuit Breaker 保護，確保外部服務異常時系統可快速回應。

外部相依套件（finlab）採用懶載入（lazy import），
使本模組可在未安裝 finlab 時仍能被 import（不會在模組載入時報錯）。

Usage::

    from app.infra.sources.finlab_source import FinLabSource
    from app.infra.resilience.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(source_name="finlab")
    source = FinLabSource(token="your_api_token", circuit_breaker=cb)

    df = source.get_stock_price("2330", start_date, end_date)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from app.core.errors import DataSourceError
from app.infra.logging import get_logger
from app.infra.resilience.circuit_breaker import CircuitBreaker
from app.infra.sources.base import BaseDataSource

logger = get_logger(__name__)


class FinLabSource(BaseDataSource):
    """FinLab 資料來源實作。

    使用 FinLab 資料 API 取得台股股價、財報與公司基本資訊。
    所有 API 呼叫受 Circuit Breaker 保護，連續失敗時自動熔斷。

    FinLab 的資料存取模式為透過 ``finlab.data.get()`` 函式取得
    整張資料表（DataFrame），再依股票代碼篩選。

    Attributes:
        _token: FinLab API 存取 token。

    Example::

        source = FinLabSource(
            token="my_token",
            circuit_breaker=finlab_circuit_breaker,
        )
        prices = source.get_stock_price("2330", start, end)
    """

    def __init__(
        self,
        token: str,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """初始化 FinLab 資料來源。

        Args:
            token: FinLab API token 字串。
            circuit_breaker: 對應 FinLab 的斷路器實例。
        """
        super().__init__(circuit_breaker=circuit_breaker)
        self._token: str = token
        self._initialized: bool = False

    @property
    def source_name(self) -> str:
        """資料來源名稱。

        Returns:
            固定回傳 "finlab"。
        """
        return "finlab"

    def _ensure_initialized(self) -> None:
        """確保 FinLab 已完成初始化（懶載入 + 登入）。

        首次呼叫時執行 finlab.login()，後續呼叫直接返回。

        Raises:
            DataSourceError: finlab 套件未安裝或登入失敗。
        """
        if self._initialized:
            return

        try:
            import finlab  # type: ignore[import-untyped]

            finlab.login(api_token=self._token)
            self._initialized = True
        except ImportError as exc:
            raise DataSourceError(
                message="finlab 套件未安裝，請執行 uv add finlab",
                source_name=self.source_name,
            ) from exc
        except Exception as exc:
            raise DataSourceError(
                message=f"FinLab 登入失敗: {exc}",
                source_name=self.source_name,
            ) from exc

    def _fetch_stock_price(
        self, stock_code: str, start_date: datetime, end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """取得台股每日收盤價資料。

        使用 FinLab ``data.get('price:收盤價')`` 等介面取得
        OHLCV 資料。FinLab 回傳的 DataFrame 為寬表格式
        （columns=股票代碼，index=日期），需轉換為長表格式。

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
        self._ensure_initialized()

        try:
            from finlab import data  # type: ignore[import-untyped]

            # FinLab 回傳寬表：index=date, columns=stock_codes
            close_df = data.get("price:收盤價")
            open_df = data.get("price:開盤價")
            high_df = data.get("price:最高價")
            low_df = data.get("price:最低價")
            volume_df = data.get("price:成交股數")
        except Exception as exc:
            raise DataSourceError(
                message=f"FinLab 取得股價資料失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        # 檢查股票代碼是否存在於資料中
        if close_df is None or stock_code not in close_df.columns:
            logger.debug(
                f"FinLab 未找到股票 {stock_code} 的價格資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 篩選日期範圍
        mask = (close_df.index >= start_date.strftime("%Y-%m-%d")) & (
            close_df.index <= end_date.strftime("%Y-%m-%d")
        )

        result = pd.DataFrame(
            {
                "date": close_df.index[mask],
                "close": close_df.loc[mask, stock_code].values,
            }
        )

        # 安全地加入其他欄位（可能某些欄位不存在）
        if open_df is not None and stock_code in open_df.columns:
            result["open"] = open_df.loc[mask, stock_code].values
        if high_df is not None and stock_code in high_df.columns:
            result["high"] = high_df.loc[mask, stock_code].values
        if low_df is not None and stock_code in low_df.columns:
            result["low"] = low_df.loc[mask, stock_code].values
        if volume_df is not None and stock_code in volume_df.columns:
            result["volume"] = volume_df.loc[mask, stock_code].values

        if result.empty:
            logger.debug(
                "FinLab 指定日期範圍無股價資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        logger.debug(
            f"FinLab 取得 {len(result)} 筆股價資料",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return result

    def _fetch_financial_data(
        self, stock_code: str, years: int = 5
    ) -> Optional[pd.DataFrame]:
        """取得台股財報資料。

        使用 FinLab 財報相關資料表（如 EPS、營收、ROE）。

        Args:
            stock_code: 台股代碼。
            years: 回溯年數，預設 5 年。

        Returns:
            包含 period, eps, revenue, roe 等欄位的 DataFrame。
            若無資料則回傳 None。

        Raises:
            DataSourceError: API 呼叫失敗。
        """
        self._ensure_initialized()

        try:
            from finlab import data  # type: ignore[import-untyped]

            # 取得 EPS 資料（季度）
            eps_df = data.get("fundamental_features:每股盈餘")
            # 取得營收
            revenue_df = data.get("monthly_revenue:當月營收")
            # 取得 ROE
            roe_df = data.get("fundamental_features:股東權益報酬率")
        except Exception as exc:
            raise DataSourceError(
                message=f"FinLab 取得財報資料失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        if eps_df is None or stock_code not in eps_df.columns:
            logger.debug(
                f"FinLab 未找到股票 {stock_code} 的財報資料",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 篩選近 N 年資料
        cutoff_date = (
            datetime.now() - pd.Timedelta(days=years * 365)
        ).strftime("%Y-%m-%d")

        eps_series = eps_df[stock_code].dropna()
        eps_series = eps_series[eps_series.index >= cutoff_date]

        if eps_series.empty:
            return None

        # 組合結果 DataFrame
        result = pd.DataFrame(
            {
                "period": eps_series.index,
                "stock_code": stock_code,
                "eps": eps_series.values,
            }
        )

        # 安全合併其他欄位
        if revenue_df is not None and stock_code in revenue_df.columns:
            rev_series = revenue_df[stock_code]
            result["revenue"] = result["period"].map(
                lambda d: rev_series.get(d)
            )

        if roe_df is not None and stock_code in roe_df.columns:
            roe_series = roe_df[stock_code]
            result["roe"] = result["period"].map(
                lambda d: roe_series.get(d)
            )

        logger.debug(
            f"FinLab 取得 {len(result)} 筆財報資料",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return result

    def _fetch_stock_info(
        self, stock_code: str
    ) -> Optional[Dict[str, Any]]:
        """取得股票基本資訊。

        使用 FinLab 公司基本資訊資料表。

        Args:
            stock_code: 台股代碼。

        Returns:
            包含 stock_name, industry, market 等資訊的字典。
            若查詢失敗則回傳 None。

        Raises:
            DataSourceError: API 呼叫失敗。
        """
        self._ensure_initialized()

        try:
            from finlab import data  # type: ignore[import-untyped]

            # 取得公司基本資訊
            company_df = data.get("company_basic_info")
        except Exception as exc:
            raise DataSourceError(
                message=f"FinLab 取得公司資訊失敗: {exc}",
                source_name=self.source_name,
                stock_code=stock_code,
            ) from exc

        if company_df is None:
            logger.debug(
                "FinLab 無公司基本資訊資料表",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 嘗試依股票代碼篩選
        # FinLab company_basic_info 格式可能以 stock_id 為 index 或欄位
        stock_row = None
        if stock_code in company_df.index:
            stock_row = company_df.loc[stock_code]
        elif "stock_id" in company_df.columns:
            filtered = company_df[company_df["stock_id"] == stock_code]
            if not filtered.empty:
                stock_row = filtered.iloc[0]

        if stock_row is None:
            logger.debug(
                f"FinLab 未找到股票 {stock_code} 的公司資訊",
                extra={"stock_code": stock_code, "source": self.source_name},
            )
            return None

        # 組裝結果字典
        info: Dict[str, Any] = {
            "stock_code": stock_code,
            "stock_name": _safe_get(stock_row, "公司簡稱", ""),
            "industry": _safe_get(stock_row, "產業類別", ""),
            "market": _safe_get(stock_row, "市場別", "twse"),
        }

        logger.debug(
            "FinLab 取得公司資訊成功",
            extra={"stock_code": stock_code, "source": self.source_name},
        )
        return info


def _safe_get(row: Any, key: str, default: Any = None) -> Any:
    """安全取得 Series/dict 的值。

    Args:
        row: pandas Series 或字典。
        key: 欲取得的鍵值。
        default: 鍵值不存在時的預設回傳值。

    Returns:
        對應的值，或 default。
    """
    try:
        if hasattr(row, "get"):
            return row.get(key, default)
        if hasattr(row, "__getitem__"):
            val = row[key]
            if pd.isna(val):
                return default
            return val
    except (KeyError, IndexError, TypeError):
        pass
    return default
