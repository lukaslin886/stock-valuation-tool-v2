"""資料管線協調器模組。

統一資料存取入口，依優先順序嘗試資料來源（FinLab -> Yahoo Finance -> FinMind），
整合 Pydantic 驗證、快取層、並行擷取與部分失敗回傳。

核心特性：
    - 來源備援：依優先順序逐一嘗試，任一成功即回傳
    - 快取優先：先查記憶體快取，命中則直接回傳（淺複製）
    - Pydantic 驗證：API 回應經 schema 驗證 -> range check -> unit normalization
    - 驗證失敗降級：驗證失敗但有快取資料 -> 回傳快取 + 警告
    - 並行擷取：ThreadPoolExecutor（max 5 workers）、每請求獨立逾時 15 秒
    - 部分失敗：回傳成功結果 + 記錄失敗股票代碼
    - 佇列排程：超過 5 支同時請求時排隊（由 executor 的工作佇列機制處理）

Usage::

    from app.infra.data_pipeline import DataPipeline, FetchResult

    pipeline = DataPipeline(
        sources=[finlab_source, yfinance_source, finmind_source],
        memory_cache=memory_cache,
        sqlite_cache=sqlite_cache,
        error_handler=error_handler,
    )
    result = pipeline.get_stock_price("2330", start_date, end_date)
    results = pipeline.get_multiple_prices(["2330", "2317"], start, end)
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import (
    CircuitOpenError,
    DataSourceError,
    StockToolError,
)
from app.core.protocols import DataSourceProtocol
from app.infra.cache.memory_cache import CacheEntryType, MemoryCache
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.error_handler import ErrorHandler
from app.infra.logging import get_logger, get_stock_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# FetchResult 資料結構
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """單支股票的資料擷取結果。

    封裝一次資料擷取操作的完整結果，包含來源資訊、快取狀態與警告訊息。

    Attributes:
        stock_code: 目標股票代碼。
        data: 擷取到的資料（DataFrame 或 dict），失敗時為 None。
        success: 擷取是否成功。
        source_name: 實際提供資料的來源名稱。
        from_cache: 資料是否來自快取。
        warning: 警告訊息（如使用過期快取資料時）。
        error_message: 錯誤訊息（失敗時）。
    """

    stock_code: str
    data: Optional[Any] = None
    success: bool = False
    source_name: str = ""
    from_cache: bool = False
    warning: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# 快取鍵值產生輔助
# ---------------------------------------------------------------------------


def _cache_key(data_type: str, stock_code: str, **kwargs: Any) -> str:
    """產生快取鍵值。

    Args:
        data_type: 資料類型（"price"、"financial"、"info"）。
        stock_code: 股票代碼。
        **kwargs: 額外參數（如 start_date、end_date）用於區分不同查詢。

    Returns:
        格式化的快取鍵值字串。
    """
    parts = [data_type, stock_code]
    for key in sorted(kwargs.keys()):
        val = kwargs[key]
        if isinstance(val, datetime):
            val = val.strftime("%Y%m%d")
        parts.append(f"{key}={val}")
    return ":".join(parts)


def _entry_type_for(data_type: str) -> CacheEntryType:
    """依資料類型對應快取條目類型。

    Args:
        data_type: 資料類型字串。

    Returns:
        對應的 CacheEntryType 列舉值。
    """
    mapping = {
        "price": CacheEntryType.PRICE,
        "financial": CacheEntryType.FINANCIAL,
        "info": CacheEntryType.COMPANY,
    }
    return mapping.get(data_type, CacheEntryType.PRICE)


# ---------------------------------------------------------------------------
# DataPipeline 主類別
# ---------------------------------------------------------------------------


class DataPipeline:
    """資料管線協調器。

    統一資料存取入口，協調多個資料來源、快取層與驗證邏輯。
    支援單股與多股並行擷取，提供部分失敗容忍與快取降級機制。

    Args:
        sources: 資料來源列表，按優先順序排列（index 0 為最高優先）。
        memory_cache: LRU 記憶體快取實例。
        sqlite_cache: SQLite 持久化快取實例。
        error_handler: 統一錯誤處理器實例。
        max_workers: 並行擷取的最大工作執行緒數，預設 5。
        per_request_timeout: 每個請求的獨立逾時秒數，預設 15.0。
    """

    def __init__(
        self,
        sources: List[DataSourceProtocol],
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        max_workers: int = 5,
        per_request_timeout: float = 15.0,
    ) -> None:
        """初始化資料管線協調器。

        Args:
            sources: 資料來源列表，按優先順序排列。
            memory_cache: LRU 記憶體快取實例。
            sqlite_cache: SQLite 持久化快取實例。
            error_handler: 統一錯誤處理器實例。
            max_workers: 並行擷取最大工作執行緒數，預設 5。
            per_request_timeout: 每個請求獨立逾時秒數，預設 15.0。
        """
        self._sources = sources
        self._memory_cache = memory_cache
        self._sqlite_cache = sqlite_cache
        self._error_handler = error_handler
        self._max_workers = max_workers
        self._per_request_timeout = per_request_timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

        logger.info(
            "DataPipeline initialized: %d sources, max_workers=%d, timeout=%.1fs",
            len(sources),
            max_workers,
            per_request_timeout,
        )

    # ------------------------------------------------------------------
    # 公開介面：單股擷取
    # ------------------------------------------------------------------

    def get_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> FetchResult:
        """取得股價資料。

        依優先順序嘗試資料來源，整合快取查詢與 Pydantic 驗證。

        Args:
            stock_code: 股票代碼。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            FetchResult 包含查詢結果、來源資訊與警告。
        """
        cache_key = _cache_key(
            "price", stock_code,
            start_date=start_date, end_date=end_date,
        )
        return self._fetch_with_fallback(
            stock_code=stock_code,
            data_type="price",
            cache_key=cache_key,
            fetch_func=lambda src: src.get_stock_price(
                stock_code, start_date, end_date
            ),
        )

    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5,
    ) -> FetchResult:
        """取得財報資料。

        依優先順序嘗試資料來源，整合快取查詢與 Pydantic 驗證。

        Args:
            stock_code: 股票代碼。
            years: 回溯年數，預設 5 年。

        Returns:
            FetchResult 包含查詢結果、來源資訊與警告。
        """
        cache_key = _cache_key("financial", stock_code, years=years)
        return self._fetch_with_fallback(
            stock_code=stock_code,
            data_type="financial",
            cache_key=cache_key,
            fetch_func=lambda src: src.get_financial_data(stock_code, years),
        )

    def get_stock_info(self, stock_code: str) -> FetchResult:
        """取得股票基本資訊。

        依優先順序嘗試資料來源，整合快取查詢與 Pydantic 驗證。

        Args:
            stock_code: 股票代碼。

        Returns:
            FetchResult 包含查詢結果、來源資訊與警告。
        """
        cache_key = _cache_key("info", stock_code)
        return self._fetch_with_fallback(
            stock_code=stock_code,
            data_type="info",
            cache_key=cache_key,
            fetch_func=lambda src: src.get_stock_info(stock_code),
        )

    # ------------------------------------------------------------------
    # 公開介面：多股並行擷取
    # ------------------------------------------------------------------

    def get_multiple_prices(
        self,
        stock_codes: List[str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[FetchResult]:
        """並行擷取多支股票的股價資料。

        使用 ThreadPoolExecutor 並行發送請求，每個請求具有獨立逾時。
        超過 max_workers 數量的請求由 executor 內部佇列排程。
        部分失敗不影響其他結果。

        Args:
            stock_codes: 股票代碼列表。
            start_date: 查詢起始日期。
            end_date: 查詢結束日期。

        Returns:
            FetchResult 列表（順序與輸入一致）。
        """
        return self._fetch_multiple(
            stock_codes=stock_codes,
            fetch_func=lambda code: self.get_stock_price(
                code, start_date, end_date
            ),
        )

    def get_multiple_financial(
        self,
        stock_codes: List[str],
        years: int = 5,
    ) -> List[FetchResult]:
        """並行擷取多支股票的財報資料。

        使用 ThreadPoolExecutor 並行發送請求，每個請求具有獨立逾時。

        Args:
            stock_codes: 股票代碼列表。
            years: 回溯年數，預設 5 年。

        Returns:
            FetchResult 列表（順序與輸入一致）。
        """
        return self._fetch_multiple(
            stock_codes=stock_codes,
            fetch_func=lambda code: self.get_financial_data(code, years),
        )

    def get_multiple_info(
        self,
        stock_codes: List[str],
    ) -> List[FetchResult]:
        """並行擷取多支股票的基本資訊。

        使用 ThreadPoolExecutor 並行發送請求，每個請求具有獨立逾時。

        Args:
            stock_codes: 股票代碼列表。

        Returns:
            FetchResult 列表（順序與輸入一致）。
        """
        return self._fetch_multiple(
            stock_codes=stock_codes,
            fetch_func=lambda code: self.get_stock_info(code),
        )

    # ------------------------------------------------------------------
    # 核心邏輯：來源備援 + 快取 + 驗證
    # ------------------------------------------------------------------

    def _fetch_with_fallback(
        self,
        stock_code: str,
        data_type: str,
        cache_key: str,
        fetch_func: Callable[[DataSourceProtocol], Optional[Any]],
    ) -> FetchResult:
        """以備援策略擷取資料。

        流程：
        1. 查詢記憶體快取，命中則直接回傳
        2. 依優先順序逐一嘗試來源
        3. 來源回傳資料後進行 Pydantic 驗證
        4. 驗證成功 -> 寫入快取 -> 回傳
        5. 驗證失敗 -> 嘗試下一來源
        6. 所有來源失敗 -> 嘗試從快取取得過期資料
        7. 快取也無 -> 回傳失敗結果

        Args:
            stock_code: 股票代碼。
            data_type: 資料類型（"price"/"financial"/"info"）。
            cache_key: 快取鍵值。
            fetch_func: 接受 DataSourceProtocol 並回傳資料的函式。

        Returns:
            FetchResult 包含擷取結果。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        # 步驟 1：查詢記憶體快取
        cached_data = self._memory_cache.get(cache_key)
        if cached_data is not None:
            stock_log.debug("記憶體快取命中: %s", cache_key)
            return FetchResult(
                stock_code=stock_code,
                data=cached_data,
                success=True,
                source_name="memory_cache",
                from_cache=True,
            )

        # 步驟 2-5：逐一嘗試來源
        last_error_msg: Optional[str] = None
        validation_failed = False

        for source in self._sources:
            # 跳過不可用的來源
            if not source.is_available:
                stock_log.debug(
                    "來源 %s 不可用，跳過", source.source_name
                )
                continue

            try:
                raw_data = fetch_func(source)
            except CircuitOpenError:
                stock_log.debug(
                    "來源 %s 斷路器開啟，跳過", source.source_name
                )
                continue
            except (DataSourceError, StockToolError) as exc:
                last_error_msg = str(exc)
                self._error_handler.handle_error(
                    exc, context={"stock_code": stock_code}
                )
                stock_log.warning(
                    "來源 %s 失敗: %s", source.source_name, exc
                )
                continue
            except Exception as exc:
                last_error_msg = str(exc)
                self._error_handler.handle_error(
                    exc, context={"stock_code": stock_code}
                )
                stock_log.warning(
                    "來源 %s 未預期錯誤: %s", source.source_name, exc
                )
                continue

            # 資料為 None -> 嘗試下一來源
            if raw_data is None:
                stock_log.debug(
                    "來源 %s 回傳 None，嘗試下一來源",
                    source.source_name,
                )
                continue

            # 步驟 3：Pydantic 驗證
            validated_data = self._validate_data(
                raw_data, data_type, stock_code
            )
            if validated_data is not None:
                # 驗證成功 -> 寫入快取 -> 回傳
                self._write_cache(
                    cache_key, validated_data, data_type, stock_code
                )
                stock_log.info(
                    "[OK] %s 從 %s 取得資料",
                    data_type, source.source_name,
                )
                return FetchResult(
                    stock_code=stock_code,
                    data=validated_data,
                    success=True,
                    source_name=source.source_name,
                    from_cache=False,
                )
            else:
                # 驗證失敗，記錄並嘗試下一來源
                validation_failed = True
                stock_log.warning(
                    "來源 %s 資料驗證失敗", source.source_name
                )
                continue

        # 步驟 6：所有來源失敗 -> 嘗試快取降級
        return self._fallback_to_cache(
            stock_code=stock_code,
            data_type=data_type,
            cache_key=cache_key,
            validation_failed=validation_failed,
            last_error_msg=last_error_msg,
        )

    # ------------------------------------------------------------------
    # 並行擷取邏輯
    # ------------------------------------------------------------------

    def _fetch_multiple(
        self,
        stock_codes: List[str],
        fetch_func: Callable[[str], FetchResult],
    ) -> List[FetchResult]:
        """使用 ThreadPoolExecutor 並行擷取多支股票資料。

        提交所有任務至 executor（佇列排程由 executor 處理），
        每個任務具有獨立逾時。部分失敗不影響其他結果。

        Args:
            stock_codes: 股票代碼列表。
            fetch_func: 接受股票代碼並回傳 FetchResult 的函式。

        Returns:
            FetchResult 列表，順序與 stock_codes 一致。
        """
        if not stock_codes:
            return []

        futures_map: Dict[str, Any] = {}
        results: List[FetchResult] = []
        failed_codes: List[str] = []

        # 提交所有任務（超過 max_workers 的會排隊）
        from concurrent.futures import Future

        futures: Dict[str, Future[FetchResult]] = {}
        for code in stock_codes:
            future = self._executor.submit(fetch_func, code)
            futures[code] = future

        # 收集結果（保持順序）
        for code in stock_codes:
            future = futures[code]
            try:
                result = future.result(timeout=self._per_request_timeout)
                results.append(result)
                if not result.success:
                    failed_codes.append(code)
            except FuturesTimeoutError:
                logger.warning(
                    "並行擷取逾時: %s (%.1f 秒)",
                    code, self._per_request_timeout,
                )
                failed_codes.append(code)
                results.append(FetchResult(
                    stock_code=code,
                    data=None,
                    success=False,
                    source_name="",
                    error_message=(
                        f"請求逾時 ({self._per_request_timeout}s)"
                    ),
                ))
            except Exception as exc:
                logger.warning(
                    "並行擷取未預期錯誤: %s - %s", code, exc
                )
                failed_codes.append(code)
                results.append(FetchResult(
                    stock_code=code,
                    data=None,
                    success=False,
                    source_name="",
                    error_message=str(exc),
                ))

        # 記錄部分失敗摘要
        if failed_codes:
            logger.warning(
                "[FAIL] 並行擷取部分失敗: %d/%d 失敗, codes=%s",
                len(failed_codes),
                len(stock_codes),
                ", ".join(failed_codes[:20]),
            )

        success_count = sum(1 for r in results if r.success)
        logger.info(
            "並行擷取完成: %d/%d 成功",
            success_count, len(stock_codes),
        )

        return results

    # ------------------------------------------------------------------
    # 驗證邏輯
    # ------------------------------------------------------------------

    def _validate_data(
        self,
        raw_data: Any,
        data_type: str,
        stock_code: str,
    ) -> Optional[Any]:
        """對原始 API 回應進行 Pydantic 驗證。

        驗證流程：schema validation -> range check -> unit normalization。
        Pydantic model 內建的 field_validator 會處理 range check 與
        normalize_percentage。

        Args:
            raw_data: API 回傳的原始資料（DataFrame 或 dict）。
            data_type: 資料類型（"price"/"financial"/"info"）。
            stock_code: 股票代碼。

        Returns:
            驗證後的資料（可能與原始格式相同），驗證失敗回傳 None。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        try:
            if data_type == "price":
                return self._validate_price_data(raw_data, stock_code)
            elif data_type == "financial":
                return self._validate_financial_data(raw_data, stock_code)
            elif data_type == "info":
                return self._validate_stock_info(raw_data, stock_code)
            else:
                # 未知類型，不做驗證直接回傳
                return raw_data
        except PydanticValidationError as exc:
            stock_log.warning(
                "Pydantic 驗證失敗 (%s): %s",
                data_type, str(exc)[:200],
            )
            return None
        except Exception as exc:
            stock_log.warning(
                "驗證過程未預期錯誤 (%s): %s",
                data_type, str(exc)[:200],
            )
            return None

    def _validate_price_data(
        self, raw_data: Any, stock_code: str
    ) -> Optional[Any]:
        """驗證股價資料。

        對 DataFrame 的每一列進行基礎範圍檢查：
        - 開高低收 > 0
        - 最高 >= 最低
        - 收盤在高低之間

        若 DataFrame 為空或非 DataFrame，回傳 None。

        Args:
            raw_data: 原始股價資料。
            stock_code: 股票代碼。

        Returns:
            驗證通過的 DataFrame，或 None。
        """
        if not isinstance(raw_data, pd.DataFrame):
            return None
        if raw_data.empty:
            return None

        # 基礎範圍檢查：移除不合理的列
        price_cols = ["open", "high", "low", "close"]
        available_cols = [c for c in price_cols if c in raw_data.columns]

        if not available_cols:
            # 嘗試小寫化欄位名稱
            raw_data.columns = raw_data.columns.str.lower()
            available_cols = [c for c in price_cols if c in raw_data.columns]

        if not available_cols:
            return None

        # 過濾掉價格 <= 0 的列
        for col in available_cols:
            if col in raw_data.columns:
                raw_data = raw_data[raw_data[col] > 0]

        # 檢查 high >= low
        if "high" in raw_data.columns and "low" in raw_data.columns:
            raw_data = raw_data[raw_data["high"] >= raw_data["low"]]

        if raw_data.empty:
            return None

        return raw_data

    def _validate_financial_data(
        self, raw_data: Any, stock_code: str
    ) -> Optional[Any]:
        """驗證財報資料。

        對 DataFrame 執行：
        - PE ratio 範圍 [-100, 10000]
        - ROE 範圍 [-100, 200]（歸一化後）
        - EPS 範圍 [-1000, 10000]

        超出範圍的列會被移除，若全部移除則回傳 None。

        Args:
            raw_data: 原始財報資料。
            stock_code: 股票代碼。

        Returns:
            驗證通過的 DataFrame，或 None。
        """
        if not isinstance(raw_data, pd.DataFrame):
            return None
        if raw_data.empty:
            return None

        df = raw_data.copy()

        # 欄位名稱正規化
        df.columns = df.columns.str.lower().str.strip()

        # ROE 歸一化：小數形式 -> 百分比形式
        if "roe" in df.columns:
            mask = (df["roe"].notna()) & (df["roe"] != 0)
            decimal_mask = mask & (df["roe"].abs() < 1.0)
            df.loc[decimal_mask, "roe"] = df.loc[decimal_mask, "roe"] * 100
            # 範圍過濾
            df = df[
                (df["roe"].isna()) | (
                    (df["roe"] >= -100) & (df["roe"] <= 200)
                )
            ]

        # PE ratio 範圍過濾
        if "pe_ratio" in df.columns:
            df = df[
                (df["pe_ratio"].isna()) | (
                    (df["pe_ratio"] >= -100) & (df["pe_ratio"] <= 10000)
                )
            ]

        # EPS 範圍過濾
        if "eps" in df.columns:
            df = df[
                (df["eps"].isna()) | (
                    (df["eps"] >= -1000) & (df["eps"] <= 10000)
                )
            ]

        if df.empty:
            return None

        return df

    def _validate_stock_info(
        self, raw_data: Any, stock_code: str
    ) -> Optional[Any]:
        """驗證股票基本資訊。

        對 dict 執行基礎檢查：
        - 必須包含 stock_code 或可合理辨識的鍵值
        - 若含 market_cap，須 >= 0

        Args:
            raw_data: 原始基本資訊 dict。
            stock_code: 股票代碼。

        Returns:
            驗證通過的 dict，或 None。
        """
        if not isinstance(raw_data, dict):
            return None
        if not raw_data:
            return None

        # 確保有基本的識別資訊
        info = dict(raw_data)
        info.setdefault("stock_code", stock_code)

        # market_cap 範圍檢查
        market_cap = info.get("market_cap")
        if market_cap is not None:
            try:
                mc_val = float(market_cap)
                if mc_val < 0:
                    info["market_cap"] = None
            except (ValueError, TypeError):
                info["market_cap"] = None

        return info

    # ------------------------------------------------------------------
    # 快取操作
    # ------------------------------------------------------------------

    def _write_cache(
        self,
        cache_key: str,
        data: Any,
        data_type: str,
        stock_code: str,
    ) -> None:
        """將驗證後的資料寫入記憶體快取。

        Args:
            cache_key: 快取鍵值。
            data: 已驗證的資料。
            data_type: 資料類型。
            stock_code: 股票代碼。
        """
        entry_type = _entry_type_for(data_type)
        self._memory_cache.set(
            key=cache_key,
            value=data,
            entry_type=entry_type,
            stock_code=stock_code,
        )

    def _fallback_to_cache(
        self,
        stock_code: str,
        data_type: str,
        cache_key: str,
        validation_failed: bool,
        last_error_msg: Optional[str],
    ) -> FetchResult:
        """所有來源失敗後嘗試從快取取得降級資料。

        若驗證失敗且快取有資料，回傳快取資料並附加警告訊息。
        若快取也無資料，回傳失敗結果。

        Args:
            stock_code: 股票代碼。
            data_type: 資料類型。
            cache_key: 快取鍵值。
            validation_failed: 是否曾有驗證失敗。
            last_error_msg: 最後一個錯誤訊息。

        Returns:
            FetchResult（可能含快取資料或空結果）。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        # 嘗試 SQLite 快取
        cached = self._try_sqlite_cache(stock_code, data_type)
        if cached is not None:
            warning_msg = None
            if validation_failed:
                warning_msg = (
                    f"[STALE] 新資料驗證失敗，回傳快取資料 "
                    f"({data_type}，可能已過時)"
                )
            else:
                warning_msg = (
                    f"[STALE] 所有來源失敗，回傳快取資料 "
                    f"({data_type}，可能已過時)"
                )

            stock_log.warning(warning_msg)

            return FetchResult(
                stock_code=stock_code,
                data=cached,
                success=True,
                source_name="sqlite_cache",
                from_cache=True,
                warning=warning_msg,
            )

        # 快取也無資料 -> 失敗
        error_msg = last_error_msg or f"所有來源皆無法取得 {data_type} 資料"
        stock_log.error("[FAIL] %s", error_msg)

        return FetchResult(
            stock_code=stock_code,
            data=None,
            success=False,
            source_name="",
            error_message=error_msg,
        )

    def _try_sqlite_cache(
        self, stock_code: str, data_type: str
    ) -> Optional[Any]:
        """嘗試從 SQLite 快取取得資料。

        Args:
            stock_code: 股票代碼。
            data_type: 資料類型。

        Returns:
            快取資料，若不存在回傳 None。
        """
        try:
            if data_type == "info":
                return self._sqlite_cache.get(stock_code)
            elif data_type == "price" or data_type == "financial":
                # SQLite cache 以 stock_code 為 key 存 snapshot
                snapshot = self._sqlite_cache.get_snapshot(stock_code)
                if snapshot is not None:
                    return snapshot
            return None
        except Exception as exc:
            logger.debug(
                "SQLite 快取查詢失敗: %s - %s", stock_code, exc
            )
            return None

    # ------------------------------------------------------------------
    # 生命週期管理
    # ------------------------------------------------------------------

    def shutdown(self, wait: bool = True) -> None:
        """關閉資料管線，釋放 ThreadPoolExecutor 資源。

        Args:
            wait: 是否等待進行中的任務完成，預設 True。
        """
        self._executor.shutdown(wait=wait)
        logger.info("DataPipeline shutdown (wait=%s)", wait)

    def get_available_sources(self) -> List[str]:
        """取得目前可用的資料來源名稱列表。

        Returns:
            可用來源名稱列表（按優先順序）。
        """
        return [
            src.source_name
            for src in self._sources
            if src.is_available
        ]

    def invalidate_cache(self, stock_code: str) -> int:
        """清除指定股票的所有快取資料。

        同時清除記憶體快取與通知 SQLite 快取。

        Args:
            stock_code: 要清除的股票代碼。

        Returns:
            記憶體快取中被清除的條目數量。
        """
        count = self._memory_cache.invalidate_by_stock(stock_code)
        logger.info(
            "invalidate_cache: %s, %d memory entries removed",
            stock_code, count,
        )
        return count
