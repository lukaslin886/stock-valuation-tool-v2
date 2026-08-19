"""批次下載器模組。

提供分批下載大量股票資料的能力，具備逾時保護、子批次拆分重試、
連續失敗中止、以及進度回呼等韌性功能。

設計決策：
    - 使用 ThreadPoolExecutor（max_workers=5）而非 asyncio。
      原因：yfinance 為同步 API，ThreadPool 可直接包裹現有呼叫。
    - download_func 為呼叫方注入的下載邏輯，BatchDownloader 不依賴 yfinance。
    - time_func 與 sleep_func 可注入以利測試。

核心行為：
    - 每批次上限 50 檔，批次間等待 1 秒
    - 單批逾時 30 秒 -> 拆為兩個子批次重試
    - 連續 3 批失敗 -> 中止並回傳部分資料
    - 進度回呼（已完成/總批次數）

Usage::

    from app.infra.resilience.batch_downloader import BatchDownloader

    downloader = BatchDownloader()
    result = downloader.download(
        stock_codes=["2330", "2317", "2454", ...],
        download_func=my_yfinance_download,
        progress_callback=lambda done, total, msg: print(f"{done}/{total}"),
    )
    print(f"成功: {len(result.successful_data)} 檔")
    print(f"失敗: {len(result.failed_stocks)} 檔")
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 型別別名
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str], None]
"""進度回呼函式簽名：(completed_batches, total_batches, message)。"""

DownloadFunc = Callable[[List[str]], Dict[str, Any]]
"""下載函式簽名：接收股票代碼清單，回傳 {stock_code: data} 字典。"""


# ---------------------------------------------------------------------------
# BatchResult 資料結構
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    """批次下載結果。

    彙整整個下載流程的成功/失敗資料與統計資訊。

    Attributes:
        successful_data: 成功下載的資料，以股票代碼為 key。
        failed_stocks: 下載失敗的股票代碼清單。
        total_batches: 原始分割的批次總數。
        completed_batches: 成功完成的批次數。
        aborted: 是否因連續失敗而中止。
        abort_reason: 中止原因描述。
    """

    successful_data: Dict[str, Any] = field(default_factory=dict)
    failed_stocks: List[str] = field(default_factory=list)
    total_batches: int = 0
    completed_batches: int = 0
    aborted: bool = False
    abort_reason: str = ""


# ---------------------------------------------------------------------------
# BatchDownloader
# ---------------------------------------------------------------------------


class BatchDownloader:
    """批次下載器。

    將大量股票代碼分批處理，透過 ThreadPoolExecutor 並行下載。
    具備逾時拆分、連續失敗中止、進度回呼等韌性特性。

    執行緒安全：結果累積使用內部鎖保護。

    Attributes:
        batch_size: 每批次最大股票數量（預設 50）。
        batch_delay: 批次間等待秒數（預設 1.0）。
        timeout_seconds: 單批逾時上限秒數（預設 30.0）。
        max_workers: ThreadPoolExecutor 最大工作執行緒數（預設 5）。
        max_consecutive_failures: 連續失敗中止閾值（預設 3）。

    Example::

        downloader = BatchDownloader(batch_size=50, max_workers=5)
        result = downloader.download(
            stock_codes=all_stocks,
            download_func=yf_download_batch,
            progress_callback=on_progress,
        )
    """

    def __init__(
        self,
        batch_size: int = 50,
        batch_delay: float = 1.0,
        timeout_seconds: float = 30.0,
        max_workers: int = 5,
        max_consecutive_failures: int = 3,
        time_func: Callable[[], float] = time.time,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        """初始化批次下載器。

        Args:
            batch_size: 每批次上限股票數量，預設 50。
            batch_delay: 批次間等待秒數，預設 1.0。
            timeout_seconds: 單批逾時上限秒數，預設 30.0。
            max_workers: 並行工作執行緒數上限，預設 5。
            max_consecutive_failures: 連續失敗達此數量時中止下載，預設 3。
            time_func: 時間取得函式，可注入以利測試。
            sleep_func: 休眠函式，可注入以利測試。

        Raises:
            ValueError: 若 batch_size、max_workers 或
                       max_consecutive_failures 不為正整數。
        """
        if batch_size <= 0:
            raise ValueError(f"batch_size 必須為正整數，收到: {batch_size}")
        if max_workers <= 0:
            raise ValueError(f"max_workers 必須為正整數，收到: {max_workers}")
        if max_consecutive_failures <= 0:
            raise ValueError(
                f"max_consecutive_failures 必須為正整數，收到: "
                f"{max_consecutive_failures}"
            )

        self.batch_size: int = batch_size
        self.batch_delay: float = batch_delay
        self.timeout_seconds: float = timeout_seconds
        self.max_workers: int = max_workers
        self.max_consecutive_failures: int = max_consecutive_failures
        self._time_func: Callable[[], float] = time_func
        self._sleep_func: Callable[[float], None] = sleep_func

    def download(
        self,
        stock_codes: List[str],
        download_func: DownloadFunc,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> BatchResult:
        """執行批次下載。

        將 stock_codes 依 batch_size 分批，逐批送入 ThreadPoolExecutor
        並行下載。支援逾時拆分重試與連續失敗中止。

        Args:
            stock_codes: 待下載的股票代碼清單。
            download_func: 下載函式，接收 List[str] 回傳 Dict[str, Any]。
                          呼叫方自行決定如何從外部 API 取得資料。
            progress_callback: 進度回呼函式，接收
                              (completed, total, message)。可為 None。

        Returns:
            BatchResult 包含成功資料、失敗清單與統計資訊。
        """
        if not stock_codes:
            return BatchResult(
                total_batches=0,
                completed_batches=0,
            )

        # 分批
        batches = self._split_into_batches(stock_codes)
        total_batches = len(batches)

        logger.info(
            f"[OK] BatchDownloader: 開始下載 {len(stock_codes)} 檔 "
            f"(分 {total_batches} 批, 每批上限 {self.batch_size})"
        )

        result = BatchResult(total_batches=total_batches)
        consecutive_failures = 0
        result_lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for batch_idx, batch in enumerate(batches):
                # 檢查是否應中止
                if consecutive_failures >= self.max_consecutive_failures:
                    result.aborted = True
                    result.abort_reason = (
                        f"連續 {consecutive_failures} 批失敗，中止下載"
                    )
                    # 將剩餘批次的股票加入失敗清單
                    for remaining_batch in batches[batch_idx:]:
                        result.failed_stocks.extend(remaining_batch)
                    logger.warning(
                        f"[FAIL] BatchDownloader: {result.abort_reason}"
                    )
                    break

                # 批次間等待（第一批不等待）
                if batch_idx > 0:
                    self._sleep_func(self.batch_delay)

                # 執行單批下載
                batch_success = self._execute_batch(
                    batch=batch,
                    download_func=download_func,
                    executor=executor,
                    result=result,
                    result_lock=result_lock,
                )

                if batch_success:
                    consecutive_failures = 0
                    result.completed_batches += 1
                else:
                    consecutive_failures += 1

                # 進度回呼
                if progress_callback is not None:
                    progress_callback(
                        result.completed_batches,
                        total_batches,
                        f"批次 {batch_idx + 1}/{total_batches} 完成"
                        if batch_success
                        else f"批次 {batch_idx + 1}/{total_batches} 失敗",
                    )

        logger.info(
            f"[OK] BatchDownloader: 下載完成 - "
            f"成功 {len(result.successful_data)} 檔, "
            f"失敗 {len(result.failed_stocks)} 檔, "
            f"中止={result.aborted}"
        )
        return result

    def _split_into_batches(self, stock_codes: List[str]) -> List[List[str]]:
        """將股票代碼清單分割為固定大小的批次。

        Args:
            stock_codes: 完整股票代碼清單。

        Returns:
            分批後的二維清單，每個子清單長度不超過 batch_size。
        """
        batches: List[List[str]] = []
        for i in range(0, len(stock_codes), self.batch_size):
            batches.append(stock_codes[i : i + self.batch_size])
        return batches

    def _execute_batch(
        self,
        batch: List[str],
        download_func: DownloadFunc,
        executor: ThreadPoolExecutor,
        result: BatchResult,
        result_lock: threading.Lock,
    ) -> bool:
        """執行單一批次下載，含逾時拆分重試邏輯。

        Args:
            batch: 本批次的股票代碼清單。
            download_func: 下載函式。
            executor: ThreadPoolExecutor 實例。
            result: 結果累積物件。
            result_lock: 結果寫入鎖。

        Returns:
            True 表示至少有部分資料成功取得（非全批失敗），
            False 表示全批失敗。
        """
        future: Future = executor.submit(download_func, batch)

        try:
            batch_data = future.result(timeout=self.timeout_seconds)
        except (FuturesTimeoutError, TimeoutError):
            # 逾時：取消任務並拆分重試
            future.cancel()
            logger.warning(
                f"[FAIL] BatchDownloader: 批次逾時 "
                f"({len(batch)} 檔, >{self.timeout_seconds}s)，"
                f"拆分為子批次重試"
            )
            return self._retry_split_batch(
                batch=batch,
                download_func=download_func,
                executor=executor,
                result=result,
                result_lock=result_lock,
            )
        except Exception as exc:
            # 其他錯誤：整批記為失敗
            logger.error(
                f"[FAIL] BatchDownloader: 批次下載例外 - {exc}",
                exc_info=True,
            )
            with result_lock:
                result.failed_stocks.extend(batch)
            return False

        # 成功：累積結果
        if batch_data:
            with result_lock:
                result.successful_data.update(batch_data)
            # 檢查是否有未回傳資料的股票（部分失敗）
            returned_codes = set(batch_data.keys())
            missed = [code for code in batch if code not in returned_codes]
            if missed:
                with result_lock:
                    result.failed_stocks.extend(missed)
            return True
        else:
            # download_func 回傳空字典：全批失敗
            with result_lock:
                result.failed_stocks.extend(batch)
            return False

    def _retry_split_batch(
        self,
        batch: List[str],
        download_func: DownloadFunc,
        executor: ThreadPoolExecutor,
        result: BatchResult,
        result_lock: threading.Lock,
    ) -> bool:
        """逾時後拆分為兩個子批次重試。

        將原批次對半分割，各自以獨立 future 執行。
        子批次使用相同的 timeout_seconds 逾時限制。

        Args:
            batch: 原始批次股票代碼清單。
            download_func: 下載函式。
            executor: ThreadPoolExecutor 實例。
            result: 結果累積物件。
            result_lock: 結果寫入鎖。

        Returns:
            True 若至少一個子批次成功，False 若全部子批次皆失敗。
        """
        if len(batch) <= 1:
            # 單一股票仍逾時，無法再拆分
            with result_lock:
                result.failed_stocks.extend(batch)
            return False

        mid = len(batch) // 2
        sub_batch_a = batch[:mid]
        sub_batch_b = batch[mid:]

        any_success = False

        for sub_idx, sub_batch in enumerate([sub_batch_a, sub_batch_b]):
            sub_future: Future = executor.submit(download_func, sub_batch)
            try:
                sub_data = sub_future.result(timeout=self.timeout_seconds)
            except (FuturesTimeoutError, TimeoutError):
                sub_future.cancel()
                logger.warning(
                    f"[FAIL] BatchDownloader: 子批次 {sub_idx + 1}/2 "
                    f"仍逾時 ({len(sub_batch)} 檔)"
                )
                with result_lock:
                    result.failed_stocks.extend(sub_batch)
                continue
            except Exception as exc:
                logger.error(
                    f"[FAIL] BatchDownloader: 子批次 {sub_idx + 1}/2 "
                    f"例外 - {exc}",
                    exc_info=True,
                )
                with result_lock:
                    result.failed_stocks.extend(sub_batch)
                continue

            # 子批次成功
            if sub_data:
                with result_lock:
                    result.successful_data.update(sub_data)
                # 檢查部分失敗
                returned_codes = set(sub_data.keys())
                missed = [
                    code for code in sub_batch if code not in returned_codes
                ]
                if missed:
                    with result_lock:
                        result.failed_stocks.extend(missed)
                any_success = True
            else:
                with result_lock:
                    result.failed_stocks.extend(sub_batch)

        return any_success
