"""市場掃描器服務模組（重構版）。

透過依賴注入整合 BatchDownloader、DataPipeline、SQLiteCache、ErrorHandler，
支援增量更新、個別股票錯誤不中斷、篩選邏輯委派至 filters/ 子模組，
輸出 ScanResult / MarketSnapshot Pydantic 模型。

核心特性：
    - 依賴注入：所有外部依賴透過建構函式注入
    - 增量更新：僅下載超過 4 小時未更新的股票
    - 容錯：個別股票錯誤記錄後繼續處理（不中斷）
    - 篩選委派：篩選邏輯拆至 app/services/filters/
    - 結構化輸出：ScanResult / MarketSnapshot Pydantic 模型
    - 執行緒安全：結果累積使用內部鎖保護

Usage::

    from app.services.market_scanner import MarketScannerService

    scanner = MarketScannerService(
        data_pipeline=pipeline,
        batch_downloader=downloader,
        sqlite_cache=cache,
        error_handler=handler,
    )
    snapshot = scanner.scan_market(stock_codes=["2330", "2317"])
    filtered = scanner.filter_results(snapshot, {"roe_min": 10})
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.core.models.scan import MarketSnapshot, ScanResult
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.data_pipeline import DataPipeline
from app.infra.error_handler import ErrorHandler
from app.infra.logging import get_logger
from app.infra.resilience.batch_downloader import (
    BatchDownloader,
    DownloadFunc,
    ProgressCallback,
)
from app.services.filters import (
    ChipFilter,
    FundamentalFilter,
    TechnicalFilter,
    compose_filters,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

_INCREMENTAL_THRESHOLD_HOURS: float = 4.0
"""增量更新門檻：超過此時數未更新的股票才會重新下載。"""

_ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
"""SQLite 中 last_updated 欄位的格式。"""


# ---------------------------------------------------------------------------
# 型別別名
# ---------------------------------------------------------------------------

ScanProgressCallback = Callable[[int, int, str], None]
"""掃描進度回呼函式簽名：(completed, total, message)。"""


# ---------------------------------------------------------------------------
# MarketScannerService
# ---------------------------------------------------------------------------


class MarketScannerService:
    """市場掃描器服務（重構版）。

    整合 DataPipeline、BatchDownloader、SQLiteCache 與 ErrorHandler，
    提供市場全景掃描與篩選功能。所有依賴透過建構函式注入（DI）。

    Args:
        data_pipeline: 資料管線協調器，負責從外部 API 取得資料。
        batch_downloader: 批次下載器，負責分批並行下載大量股票。
        sqlite_cache: SQLite 持久化快取，儲存 market_snapshot 記錄。
        error_handler: 統一錯誤處理器，負責記錄與分流錯誤。
        time_func: 取得目前時間的函式，可注入以利測試。

    Example::

        scanner = MarketScannerService(
            data_pipeline=pipeline,
            batch_downloader=downloader,
            sqlite_cache=cache,
            error_handler=handler,
        )
        snapshot = scanner.scan_market(["2330", "2317", "2454"])
        filtered = scanner.filter_results(snapshot, {"roe_min": 15})
    """

    def __init__(
        self,
        data_pipeline: DataPipeline,
        batch_downloader: BatchDownloader,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化市場掃描器服務。

        Args:
            data_pipeline: 資料管線協調器。
            batch_downloader: 批次下載器。
            sqlite_cache: SQLite 持久化快取。
            error_handler: 統一錯誤處理器。
            time_func: 時間取得函式，預設 time.time。可注入以利測試。
        """
        self._data_pipeline = data_pipeline
        self._batch_downloader = batch_downloader
        self._sqlite_cache = sqlite_cache
        self._error_handler = error_handler
        self._time_func = time_func
        self._lock = threading.Lock()

        logger.info("MarketScannerService initialized")

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def scan_market(
        self,
        stock_codes: Optional[List[str]] = None,
        incremental: bool = True,
        progress_callback: Optional[ScanProgressCallback] = None,
    ) -> MarketSnapshot:
        """執行市場掃描。

        根據 stock_codes 掃描市場，支援增量更新模式（僅下載超過 4 小時
        未更新的股票）。個別股票發生錯誤時記錄後繼續，不中斷整體流程。

        Args:
            stock_codes: 待掃描的股票代碼清單。若為 None 或空清單，
                        則從 SQLite 快取取得所有已知股票代碼。
            incremental: 是否啟用增量更新模式。預設 True。
                        啟用時僅重新下載超過 4 小時未更新的股票。
            progress_callback: 掃描進度回呼函式。接收
                              (completed, total, message)。可為 None。

        Returns:
            MarketSnapshot 包含所有掃描結果。
        """
        logger.info(
            "scan_market: codes=%d, incremental=%s",
            len(stock_codes) if stock_codes else 0,
            incremental,
        )

        # 如果沒有指定股票代碼，從快取取得所有已知代碼
        if not stock_codes:
            stock_codes = self._get_cached_stock_codes()

        if not stock_codes:
            logger.warning("scan_market: 無股票代碼可掃描")
            return MarketSnapshot(
                total_stocks=0,
                results=[],
            )

        # 增量更新：分離需要重新下載 vs 可直接使用快取的股票
        codes_to_download: List[str]
        codes_from_cache: List[str]

        if incremental:
            codes_to_download, codes_from_cache = (
                self._partition_by_freshness(stock_codes)
            )
            logger.info(
                "incremental partition: download=%d, cache=%d",
                len(codes_to_download),
                len(codes_from_cache),
            )
        else:
            codes_to_download = list(stock_codes)
            codes_from_cache = []

        # 收集結果
        results: List[ScanResult] = []

        # 步驟 1：從快取載入仍新鮮的股票資料
        if codes_from_cache:
            cached_results = self._load_from_cache(codes_from_cache)
            results.extend(cached_results)
            if progress_callback:
                progress_callback(
                    len(cached_results),
                    len(stock_codes),
                    f"從快取載入 {len(cached_results)} 檔",
                )

        # 步驟 2：透過 BatchDownloader 下載需要更新的股票
        if codes_to_download:
            downloaded_results = self._download_and_process(
                codes_to_download,
                progress_callback=progress_callback,
                total_stocks=len(stock_codes),
                already_done=len(results),
            )
            results.extend(downloaded_results)

        # 建構 MarketSnapshot
        snapshot = MarketSnapshot(
            snapshot_time=datetime.now(timezone.utc),
            total_stocks=len(results),
            results=results,
        )

        logger.info(
            "scan_market complete: %d stocks in snapshot",
            snapshot.total_stocks,
        )
        return snapshot

    def filter_results(
        self,
        snapshot: MarketSnapshot,
        filters: Dict[str, Any],
    ) -> MarketSnapshot:
        """篩選市場快照。

        將篩選邏輯委派至 app/services/filters/ 模組。支援的篩選條件
        由 filters 引擎決定。篩選為冪等操作（同條件套用兩次結果不變）。

        Args:
            snapshot: 待篩選的市場快照。
            filters: 篩選條件字典。支援的鍵值包含：
                - pe_max: 本益比上限
                - pe_min: 本益比下限
                - roe_min: ROE 下限
                - roe_max: ROE 上限
                - dividend_yield_min: 殖利率下限
                - market_cap_min: 市值下限（億）
                - price_position_max: 價格位階上限
                - price_position_min: 價格位階下限
                - foreign_consecutive_buy_min: 外資連續買超天數下限
                - trust_consecutive_buy_min: 投信連續買超天數下限
                - total_institutional_buy_min: 三大法人合計買超量下限

        Returns:
            篩選後的 MarketSnapshot，僅包含符合條件的股票。
        """
        if not snapshot.results or not filters:
            return snapshot

        # 建構篩選器清單
        filter_chain: List[Any] = []

        # 基本面篩選器
        fundamental_kwargs = {}
        for key in ("pe_min", "pe_max", "roe_min", "roe_max",
                    "dividend_yield_min", "market_cap_min"):
            if key in filters:
                fundamental_kwargs[key] = filters[key]
        if fundamental_kwargs:
            filter_chain.append(FundamentalFilter(**fundamental_kwargs))

        # 技術面篩選器
        technical_kwargs = {}
        for key in ("price_position_max", "price_position_min"):
            if key in filters:
                technical_kwargs[key] = filters[key]
        if technical_kwargs:
            filter_chain.append(TechnicalFilter(**technical_kwargs))

        # 籌碼面篩選器
        chip_kwargs = {}
        for key in ("foreign_consecutive_buy_min",
                    "trust_consecutive_buy_min",
                    "total_institutional_buy_min"):
            if key in filters:
                chip_kwargs[key] = filters[key]
        if chip_kwargs:
            filter_chain.append(ChipFilter(**chip_kwargs))

        if not filter_chain:
            return snapshot

        # 組合並執行篩選
        composed = compose_filters(filter_chain)
        filtered_results = composed(snapshot.results)

        return MarketSnapshot(
            snapshot_time=snapshot.snapshot_time,
            total_stocks=len(filtered_results),
            results=filtered_results,
        )

    def get_cached_snapshot(self) -> MarketSnapshot:
        """取得目前 SQLite 快取中的完整市場快照。

        直接從快取讀取所有 market_snapshot 記錄，不觸發下載。

        Returns:
            快取中的 MarketSnapshot。
        """
        stock_codes = self._get_cached_stock_codes()
        if not stock_codes:
            return MarketSnapshot(total_stocks=0, results=[])

        results = self._load_from_cache(stock_codes)
        return MarketSnapshot(
            total_stocks=len(results),
            results=results,
        )

    # ------------------------------------------------------------------
    # 增量更新邏輯
    # ------------------------------------------------------------------

    def _partition_by_freshness(
        self,
        stock_codes: List[str],
    ) -> tuple[List[str], List[str]]:
        """依資料新鮮度分割股票代碼。

        檢查 SQLiteCache 中每支股票的 last_updated 時間戳記。
        若 now() - last_updated >= 4 小時：需重新下載。
        若 now() - last_updated < 4 小時：可使用快取。

        Args:
            stock_codes: 完整的股票代碼清單。

        Returns:
            元組 (codes_to_download, codes_from_cache)。
        """
        threshold_seconds = _INCREMENTAL_THRESHOLD_HOURS * 3600
        current_time = self._time_func()

        codes_to_download: List[str] = []
        codes_from_cache: List[str] = []

        for code in stock_codes:
            try:
                snapshot = self._sqlite_cache.get_snapshot(code)
                if snapshot is None:
                    # 快取中不存在 -> 需下載
                    codes_to_download.append(code)
                    continue

                last_updated_str = snapshot.get("last_updated", "")
                if not last_updated_str:
                    codes_to_download.append(code)
                    continue

                # 解析 last_updated 時間戳記
                try:
                    last_dt = datetime.strptime(
                        last_updated_str, _ISO_FORMAT
                    )
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                    elapsed = current_time - last_dt.timestamp()
                except (ValueError, TypeError):
                    # 無法解析 -> 需下載
                    codes_to_download.append(code)
                    continue

                if elapsed >= threshold_seconds:
                    codes_to_download.append(code)
                else:
                    codes_from_cache.append(code)

            except Exception as exc:
                # 查詢快取失敗 -> 保守起見標為需下載
                logger.debug(
                    "freshness check failed for %s: %s", code, exc
                )
                codes_to_download.append(code)

        return codes_to_download, codes_from_cache

    # ------------------------------------------------------------------
    # 下載與處理
    # ------------------------------------------------------------------

    def _download_and_process(
        self,
        stock_codes: List[str],
        progress_callback: Optional[ScanProgressCallback],
        total_stocks: int,
        already_done: int,
    ) -> List[ScanResult]:
        """透過 BatchDownloader 下載並處理股票資料。

        使用 BatchDownloader 的 download() 方法批次下載，
        下載完成後逐一處理每支股票的資料、計算評分並寫入快取。
        個別股票處理失敗時使用 ErrorHandler 記錄錯誤並繼續。

        Args:
            stock_codes: 需要下載的股票代碼清單。
            progress_callback: 掃描進度回呼。
            total_stocks: 整體掃描的總股票數（含快取）。
            already_done: 已完成的股票數（來自快取）。

        Returns:
            成功處理的 ScanResult 列表。
        """
        results: List[ScanResult] = []

        # 建立下載函式，包裝 DataPipeline 的多股擷取
        def download_func(codes: List[str]) -> Dict[str, Any]:
            """透過 DataPipeline 擷取多支股票資訊。"""
            fetch_results = self._data_pipeline.get_multiple_info(codes)
            data_dict: Dict[str, Any] = {}
            for fr in fetch_results:
                if fr.success and fr.data is not None:
                    data_dict[fr.stock_code] = fr.data
            return data_dict

        # 包裝進度回呼以配合整體進度
        batch_progress: Optional[ProgressCallback] = None
        if progress_callback:
            def batch_progress(
                completed: int, total: int, msg: str
            ) -> None:
                overall_done = already_done + int(
                    completed / max(total, 1) * len(stock_codes)
                )
                progress_callback(
                    overall_done,
                    total_stocks,
                    f"下載中: {msg}",
                )

        # 執行批次下載
        batch_result = self._batch_downloader.download(
            stock_codes=stock_codes,
            download_func=download_func,
            progress_callback=batch_progress,
        )

        # 處理成功下載的資料
        for code, data in batch_result.successful_data.items():
            try:
                scan_result = self._process_stock_data(code, data)
                if scan_result is not None:
                    results.append(scan_result)
                    # 寫入快取
                    self._save_to_cache(scan_result)
            except Exception as exc:
                # 個別股票錯誤不中斷：使用 ErrorHandler 記錄後繼續
                self._error_handler.handle_stock_batch_error(
                    error=exc,
                    stock_code=code,
                    batch_context={"phase": "process_stock_data"},
                )

        # 記錄失敗的股票
        if batch_result.failed_stocks:
            for code in batch_result.failed_stocks:
                logger.warning(
                    "scan_market: stock %s download failed", code
                )

        if batch_result.aborted:
            logger.warning(
                "scan_market: batch download aborted - %s",
                batch_result.abort_reason,
            )

        # 最終進度
        if progress_callback:
            progress_callback(
                already_done + len(results),
                total_stocks,
                f"下載完成: 成功 {len(results)} 檔",
            )

        return results

    def _process_stock_data(
        self,
        stock_code: str,
        data: Any,
    ) -> Optional[ScanResult]:
        """處理單支股票的原始資料並產生 ScanResult。

        將 DataPipeline 回傳的原始資料轉換為標準化的 ScanResult
        Pydantic 模型，包含基本面評分計算。

        Args:
            stock_code: 股票代碼。
            data: DataPipeline 回傳的原始資料（dict 或 DataFrame）。

        Returns:
            ScanResult 實例，若資料不足回傳 None。
        """
        if data is None:
            return None

        # 確保 data 是 dict
        if not isinstance(data, dict):
            logger.debug(
                "process_stock_data: unexpected data type for %s: %s",
                stock_code,
                type(data).__name__,
            )
            return None

        # 擷取欄位
        current_price = float(data.get("current_price", 0) or 0)
        pe_ratio = float(data.get("pe_ratio", 0) or 0)
        roe = float(data.get("roe", 0) or 0)
        dividend_yield = float(data.get("dividend_yield", 0) or 0)
        market_cap = float(data.get("market_cap", 0) or 0)

        # 市值正規化：若 > 1e8 視為「元」-> 轉為「億」
        if market_cap > 1e8:
            market_cap = market_cap / 1e8

        # 價格位階計算
        high_52w = float(data.get("high_52w", 0) or 0)
        low_52w = float(data.get("low_52w", 0) or 0)
        price_position = 0.5
        if high_52w > low_52w and current_price > 0:
            price_position = (current_price - low_52w) / (high_52w - low_52w)
            price_position = max(0.0, min(1.0, price_position))

        # 基本面評分
        score, grade = self._calculate_fundamental_score(
            roe=roe,
            pe_ratio=pe_ratio,
            dividend_yield=dividend_yield,
        )

        # 建構 ScanResult
        try:
            return ScanResult(
                stock_code=stock_code,
                stock_name=str(data.get("stock_name", "") or ""),
                current_price=max(current_price, 0),
                pe_ratio=pe_ratio,
                roe=roe,
                dividend_yield=max(dividend_yield, 0),
                market_cap=max(market_cap, 0),
                price_position=price_position,
                fundamental_score=score,
                fundamental_grade=grade,
                chip_data_available=True,
                foreign_consecutive_buy=data.get("foreign_consecutive_buy"),
                trust_consecutive_buy=data.get("trust_consecutive_buy"),
            )
        except Exception as exc:
            logger.warning(
                "ScanResult validation failed for %s: %s",
                stock_code, exc,
            )
            return None

    def _calculate_fundamental_score(
        self,
        roe: float,
        pe_ratio: float,
        dividend_yield: float,
    ) -> tuple[float, str]:
        """計算基本面綜合評分與等級。

        依據 ROE、本益比、殖利率計算綜合評分（0~100）並給予等級。

        Args:
            roe: 股東權益報酬率（%）。
            pe_ratio: 本益比。
            dividend_yield: 殖利率（%）。

        Returns:
            元組 (score, grade)，score 為 0~100 的分數，
            grade 為 "A+"/"A"/"B"/"C" 其中之一。
        """
        score = 70.0

        # ROE 加分
        if roe > 15:
            score += 15
        elif roe > 10:
            score += 10
        elif roe > 5:
            score += 5

        # PE ratio 加分（低 PE 較好）
        if 0 < pe_ratio < 10:
            score += 15
        elif 0 < pe_ratio < 15:
            score += 10
        elif 0 < pe_ratio < 20:
            score += 5

        # 殖利率加分
        if dividend_yield > 7:
            score += 10
        elif dividend_yield > 5:
            score += 7
        elif dividend_yield > 3:
            score += 3

        score = min(score, 100.0)

        # 等級判定
        if score >= 90:
            grade = "A+"
        elif score >= 80:
            grade = "A"
        elif score >= 70:
            grade = "B"
        else:
            grade = "C"

        return score, grade

    # ------------------------------------------------------------------
    # 快取操作
    # ------------------------------------------------------------------

    def _get_cached_stock_codes(self) -> List[str]:
        """從 SQLite 快取取得所有已知的股票代碼。

        Returns:
            股票代碼列表。若快取為空回傳空清單。
        """
        try:
            result = self._sqlite_cache.filter_stocks(limit=10000)
            return [row["stock_code"] for row in result.rows]
        except Exception as exc:
            logger.warning(
                "Failed to get cached stock codes: %s", exc
            )
            return []

    def _load_from_cache(
        self,
        stock_codes: List[str],
    ) -> List[ScanResult]:
        """從快取載入股票資料並轉換為 ScanResult。

        Args:
            stock_codes: 需從快取載入的股票代碼清單。

        Returns:
            成功載入的 ScanResult 列表。
        """
        results: List[ScanResult] = []

        for code in stock_codes:
            try:
                snapshot = self._sqlite_cache.get_snapshot(code)
                if snapshot is None:
                    continue

                scan_result = ScanResult(
                    stock_code=snapshot.get("stock_code", code),
                    stock_name=str(snapshot.get("stock_name", "") or ""),
                    current_price=float(
                        snapshot.get("current_price", 0) or 0
                    ),
                    pe_ratio=float(snapshot.get("pe_ratio", 0) or 0),
                    roe=float(snapshot.get("roe", 0) or 0),
                    dividend_yield=float(
                        snapshot.get("dividend_yield", 0) or 0
                    ),
                    market_cap=float(snapshot.get("market_cap", 0) or 0),
                    price_position=float(
                        snapshot.get("price_position", 0) or 0
                    ),
                    fundamental_score=float(
                        snapshot.get("fundamental_score", 0) or 0
                    ),
                    fundamental_grade=str(
                        snapshot.get("fundamental_grade", "") or ""
                    ),
                    chip_data_available=True,
                )
                results.append(scan_result)
            except Exception as exc:
                # 個別股票快取載入失敗：記錄後繼續
                self._error_handler.handle_stock_batch_error(
                    error=exc,
                    stock_code=code,
                    batch_context={"phase": "load_from_cache"},
                )

        return results

    def _save_to_cache(self, scan_result: ScanResult) -> None:
        """將 ScanResult 寫入 SQLite 快取。

        Args:
            scan_result: 已處理完成的掃描結果。
        """
        try:
            record = {
                "stock_code": scan_result.stock_code,
                "stock_name": scan_result.stock_name,
                "current_price": scan_result.current_price,
                "pe_ratio": scan_result.pe_ratio,
                "roe": scan_result.roe,
                "dividend_yield": scan_result.dividend_yield,
                "market_cap": scan_result.market_cap,
                "price_position": scan_result.price_position,
                "fundamental_score": scan_result.fundamental_score,
                "fundamental_grade": scan_result.fundamental_grade,
            }
            self._sqlite_cache.upsert_snapshot(record)
        except Exception as exc:
            logger.warning(
                "Failed to save scan result for %s: %s",
                scan_result.stock_code,
                exc,
            )
