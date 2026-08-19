"""Yahoo Finance 資料來源模組。

透過 yfinance 套件取得台股與美股的股價、財報與基本資訊資料。
整合 Circuit Breaker 保護，支援台股（.TW/.TWO 後綴）與美股（無後綴）。

市場辨識邏輯：
- 純英文 1-5 字元 -> 美股（如 AAPL、MSFT）
- 純數字 4-6 位 -> 台股（上市 .TW / 上櫃 .TWO）
- 帶後綴格式 -> 直接使用

Usage::

    from app.infra.resilience.circuit_breaker import CircuitBreaker
    from app.infra.sources.yfinance_source import YFinanceSource

    cb = CircuitBreaker(source_name="yahoo_finance")
    source = YFinanceSource(circuit_breaker=cb)
    df = source.get_stock_price("2330", start, end)
"""

from __future__ import annotations

import re
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from app.core.errors import DataSourceError
from app.core.errors import TimeoutError as StockToolTimeoutError
from app.core.models.stock import Market
from app.infra.logging import get_logger
from app.infra.resilience.circuit_breaker import CircuitBreaker
from app.infra.sources.base import BaseDataSource

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 市場辨識
# ---------------------------------------------------------------------------


def detect_market(stock_input: str) -> Market:
    """辨識股票代碼對應的市場別。

    辨識規則：
    1. 純英文字母 1-5 字元 -> Market.US
    2. 純數字 4-6 位 -> Market.TW（代碼 < 6000）或 Market.TWO（>= 6000）
    3. 帶 .TW 後綴 -> Market.TW
    4. 帶 .TWO 後綴 -> Market.TWO
    5. 預設 -> Market.TW

    Args:
        stock_input: 使用者輸入的股票代碼字串。

    Returns:
        對應的 Market 列舉值。

    Examples:
        >>> detect_market("AAPL")
        <Market.US: 'US'>
        >>> detect_market("2330")
        <Market.TW: 'TW'>
        >>> detect_market("6510")
        <Market.TWO: 'TWO'>
    """
    stock_input = stock_input.strip().upper()

    # 純英文字母 1-5 字元 -> 美股
    if re.match(r"^[A-Z]{1,5}$", stock_input):
        return Market.US

    # 純數字 4-6 位 -> 台股
    if re.match(r"^\d{4,6}$", stock_input):
        code = int(stock_input)
        if code >= 6000:
            return Market.TWO
        return Market.TW

    # 帶後綴的格式
    if stock_input.endswith(".TW"):
        return Market.TW
    if stock_input.endswith(".TWO"):
        return Market.TWO

    # 預設台股
    return Market.TW


def _to_yfinance_ticker(stock_code: str) -> str:
    """將股票代碼轉為 yfinance 可辨識的 ticker 格式。

    Args:
        stock_code: 原始股票代碼。

    Returns:
        yfinance 格式 ticker（台股加後綴、美股保持原樣）。

    Examples:
        >>> _to_yfinance_ticker("2330")
        '2330.TW'
        >>> _to_yfinance_ticker("6510")
        '6510.TWO'
        >>> _to_yfinance_ticker("AAPL")
        'AAPL'
    """
    # 若已含後綴，直接回傳
    upper = stock_code.strip().upper()
    if upper.endswith(".TW") or upper.endswith(".TWO"):
        return upper

    market = detect_market(stock_code)
    if market == Market.US:
        return upper
    elif market == Market.TWO:
        # 取出數字部分
        numeric = re.sub(r"[^0-9]", "", stock_code)
        return f"{numeric}.TWO"
    else:
        numeric = re.sub(r"[^0-9]", "", stock_code)
        return f"{numeric}.TW"


# ---------------------------------------------------------------------------
# YFinanceSource
# ---------------------------------------------------------------------------


class YFinanceSource(BaseDataSource):
    """Yahoo Finance 資料來源實作。

    透過 yfinance 套件取得股價、財報與公司資訊。
    支援台股（自動加上 .TW / .TWO 後綴）與美股（直接使用 ticker）。

    繼承 BaseDataSource 以整合 Circuit Breaker 保護、錯誤包裝與結構化日誌。

    Attributes:
        _timeout: 單次 API 呼叫逾時秒數。

    Example::

        from app.infra.resilience.circuit_breaker import CircuitBreaker
        from app.infra.sources.yfinance_source import YFinanceSource

        cb = CircuitBreaker(source_name="yahoo_finance")
        source = YFinanceSource(circuit_breaker=cb, timeout=30.0)

        if source.is_available:
            df = source.get_stock_price("2330", start_date, end_date)
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        timeout: float = 30.0,
    ) -> None:
        """初始化 Yahoo Finance 資料來源。

        Args:
            circuit_breaker: Yahoo Finance 對應的 CircuitBreaker 實例。
            timeout: 單次 API 呼叫逾時秒數，預設 30.0。
        """
        super().__init__(
            circuit_breaker=circuit_breaker,
            default_timeout=timeout,
        )
        self._timeout = timeout

    @property
    def source_name(self) -> str:
        """資料來源名稱。

        Returns:
            固定回傳 "yahoo_finance"。
        """
        return "yahoo_finance"

    # ------------------------------------------------------------------
    # 底層 API 呼叫實作
    # ------------------------------------------------------------------

    def _fetch_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        """透過 yfinance 取得股價資料。

        使用 yf.download() 取得 OHLCV 資料。
        自動根據市場辨識結果加上對應後綴。

        Args:
            stock_code: 原始股票代碼。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            包含 date, open, high, low, close, volume 欄位的 DataFrame，
            若無資料則回傳 None。

        Raises:
            StockToolTimeoutError: 當 API 呼叫逾時時。
            DataSourceError: 當 API 發生錯誤時。
        """
        import yfinance as yf

        ticker = _to_yfinance_ticker(stock_code)

        def _download() -> pd.DataFrame:
            df = yf.download(
                ticker,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            return df

        df = self._run_with_timeout(_download, stock_code)

        if df is None or df.empty:
            logger.info(
                "yfinance 回傳空資料: ticker=%s, period=%s~%s",
                ticker,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )
            return None

        # 標準化欄位名稱
        result = self._normalize_price_dataframe(df, stock_code)
        return result

    def _fetch_financial_data(
        self,
        stock_code: str,
        years: int,
    ) -> Optional[pd.DataFrame]:
        """透過 yfinance 取得財報資料。

        使用 yf.Ticker().financials 取得年度損益表資料，
        並計算 EPS、營收等衍生欄位。

        Args:
            stock_code: 原始股票代碼。
            years: 回溯年數。

        Returns:
            包含 period, revenue, eps 等欄位的 DataFrame，
            若無資料則回傳 None。

        Raises:
            StockToolTimeoutError: 當 API 呼叫逾時時。
            DataSourceError: 當 API 發生錯誤時。
        """
        import yfinance as yf

        ticker_str = _to_yfinance_ticker(stock_code)

        def _fetch() -> Dict[str, Any]:
            ticker = yf.Ticker(ticker_str)
            financials = ticker.financials
            info = ticker.info
            return {"financials": financials, "info": info}

        data = self._run_with_timeout(_fetch, stock_code)
        if data is None:
            return None

        financials = data.get("financials")
        info = data.get("info", {})

        if financials is None or financials.empty:
            logger.info("yfinance 財報資料為空: ticker=%s", ticker_str)
            return None

        # 限制年數
        financials = financials.iloc[:, :years] if financials.shape[1] > years else financials

        result = self._normalize_financial_dataframe(
            financials, info, stock_code
        )
        return result

    def _fetch_stock_info(
        self,
        stock_code: str,
    ) -> Optional[Dict[str, Any]]:
        """透過 yfinance 取得股票基本資訊。

        使用 yf.Ticker().info 取得公司基本資料。

        Args:
            stock_code: 原始股票代碼。

        Returns:
            包含公司基本資訊的字典，若查詢失敗則回傳 None。

        Raises:
            StockToolTimeoutError: 當 API 呼叫逾時時。
            DataSourceError: 當 API 發生錯誤時。
        """
        import yfinance as yf

        ticker_str = _to_yfinance_ticker(stock_code)

        def _fetch() -> Dict[str, Any]:
            ticker = yf.Ticker(ticker_str)
            return dict(ticker.info)

        raw_info = self._run_with_timeout(_fetch, stock_code)
        if raw_info is None or not raw_info:
            logger.info("yfinance 基本資訊為空: ticker=%s", ticker_str)
            return None

        # 標準化為統一格式
        market = detect_market(stock_code)
        result: Dict[str, Any] = {
            "stock_code": stock_code.strip(),
            "stock_name": raw_info.get("shortName", raw_info.get("longName", "")),
            "market": market.value,
            "industry": raw_info.get("industry", ""),
            "sector": raw_info.get("sector", ""),
            "shares_outstanding": raw_info.get("sharesOutstanding"),
            "market_cap": raw_info.get("marketCap"),
            "currency": raw_info.get("currency", ""),
            "current_price": raw_info.get(
                "currentPrice", raw_info.get("regularMarketPrice")
            ),
            "pe_ratio": raw_info.get("trailingPE"),
            "forward_pe": raw_info.get("forwardPE"),
            "dividend_yield": raw_info.get("dividendYield"),
            "book_value": raw_info.get("bookValue"),
        }
        return result

    # ------------------------------------------------------------------
    # 逾時處理
    # ------------------------------------------------------------------

    def _run_with_timeout(
        self,
        func: Any,
        stock_code: str,
    ) -> Any:
        """以逾時保護執行函式。

        使用 ThreadPoolExecutor 包裹同步呼叫，
        在 timeout 秒後若未完成則拋出 TimeoutError。

        Args:
            func: 要執行的無參數可呼叫物件。
            stock_code: 股票代碼（用於錯誤訊息）。

        Returns:
            func 的回傳值。

        Raises:
            StockToolTimeoutError: 當執行超過 timeout 秒時。
            DataSourceError: 當 func 內部發生例外時。
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=self._timeout)
            except FuturesTimeoutError:
                raise StockToolTimeoutError(
                    message=(
                        f"Yahoo Finance API 呼叫逾時 "
                        f"(>{self._timeout:.0f}s): {stock_code}"
                    ),
                    timeout_seconds=self._timeout,
                    stock_code=stock_code,
                )
            except (DataSourceError, StockToolTimeoutError):
                raise
            except Exception as exc:
                raise DataSourceError(
                    message=f"Yahoo Finance API 錯誤: {exc}",
                    source_name="yahoo_finance",
                    stock_code=stock_code,
                ) from exc

    # ------------------------------------------------------------------
    # DataFrame 標準化
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_price_dataframe(
        df: pd.DataFrame,
        stock_code: str,
    ) -> pd.DataFrame:
        """標準化 yfinance 股價 DataFrame 欄位名稱。

        將 yfinance 回傳的欄位名稱映射為統一格式：
        Open -> open, High -> high, Low -> low, Close -> close, Volume -> volume

        Args:
            df: yfinance 回傳的原始 DataFrame。
            stock_code: 股票代碼。

        Returns:
            標準化後的 DataFrame，包含 stock_code, date, open, high, low,
            close, volume 欄位。
        """
        result = df.copy()

        # yfinance 多層欄位處理（下載多檔時可能有 MultiIndex）
        if isinstance(result.columns, pd.MultiIndex):
            result.columns = result.columns.get_level_values(0)

        # 欄位名稱映射
        column_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Adj Close": "adj_close",
        }
        result = result.rename(columns=column_map)

        # 若欄位已是小寫形式（某些 yfinance 版本），保持不變
        expected_cols = ["open", "high", "low", "close", "volume"]
        for col in expected_cols:
            if col not in result.columns:
                lower_cols = {c.lower(): c for c in result.columns}
                if col in lower_cols:
                    result = result.rename(columns={lower_cols[col]: col})

        # 添加 stock_code 欄位
        result["stock_code"] = stock_code.strip()

        # index 轉為 date 欄位
        if result.index.name == "Date" or result.index.name == "date":
            result = result.reset_index()
            result = result.rename(columns={"Date": "date", "date": "date"})
        elif "Date" not in result.columns and "date" not in result.columns:
            result = result.reset_index()
            if "index" in result.columns:
                result = result.rename(columns={"index": "date"})

        # 篩選最終欄位
        final_cols = ["stock_code", "date", "open", "high", "low", "close", "volume"]
        available_cols = [c for c in final_cols if c in result.columns]
        result = result[available_cols]

        return result

    @staticmethod
    def _normalize_financial_dataframe(
        financials: pd.DataFrame,
        info: Dict[str, Any],
        stock_code: str,
    ) -> pd.DataFrame:
        """標準化 yfinance 財報 DataFrame。

        將 yfinance Ticker.financials 的轉置格式（列為科目、欄為期間）
        轉換為標準的每期一列格式。

        Args:
            financials: yfinance Ticker.financials 原始 DataFrame。
            info: yfinance Ticker.info 字典（用於取得 EPS 等資訊）。
            stock_code: 股票代碼。

        Returns:
            包含 stock_code, period, revenue, eps 等欄位的 DataFrame。
        """
        records = []

        # financials 的欄位是日期（期間），列是科目名稱
        for col_date in financials.columns:
            period_str = col_date.strftime("%YQ4") if hasattr(col_date, "strftime") else str(col_date)

            record: Dict[str, Any] = {
                "stock_code": stock_code.strip(),
                "period": period_str,
            }

            # 嘗試取得營收（Total Revenue）
            revenue_keys = ["Total Revenue", "Revenue", "Operating Revenue"]
            for key in revenue_keys:
                if key in financials.index:
                    val = financials.loc[key, col_date]
                    if pd.notna(val):
                        # 轉為百萬單位
                        record["revenue"] = float(val) / 1_000_000
                        break

            # 嘗試取得淨利（Net Income）
            income_keys = ["Net Income", "Net Income Common Stockholders"]
            for key in income_keys:
                if key in financials.index:
                    val = financials.loc[key, col_date]
                    if pd.notna(val):
                        record["net_income"] = float(val)
                        break

            # EPS（從 info 取得，為最新值）
            eps = info.get("trailingEps")
            if eps is not None:
                record["eps"] = float(eps)

            records.append(record)

        if not records:
            return pd.DataFrame()

        result = pd.DataFrame(records)
        return result
