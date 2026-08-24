"""BatchDownloader 單元測試。

驗證批次下載器的核心行為：
- 分批策略正確性
- 逾時拆分重試
- 連續失敗中止
- 進度回呼
- 空清單處理
"""

import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.infra.resilience.batch_downloader import (
    BatchDownloader,
    BatchResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_stock_list(n: int) -> List[str]:
    """產生 n 支測試用股票代碼清單。"""
    return [f"{i:04d}" for i in range(1, n + 1)]


def success_download_func(stocks: List[str]) -> Dict[str, Any]:
    """模擬全部成功的下載函式。"""
    return {code: {"price": 100.0} for code in stocks}


def failure_download_func(stocks: List[str]) -> Dict[str, Any]:
    """模擬全批失敗（回傳空字典）的下載函式。"""
    return {}


def exception_download_func(stocks: List[str]) -> Dict[str, Any]:
    """模擬拋出例外的下載函式。"""
    raise RuntimeError("Network error")


def timeout_download_func(stocks: List[str]) -> Dict[str, Any]:
    """模擬超時的下載函式（阻塞久於 timeout）。"""
    time.sleep(60)
    return {}


# ---------------------------------------------------------------------------
# 基本功能測試
# ---------------------------------------------------------------------------


class TestBatchDownloaderBasic:
    """基本功能測試。"""

    def test_empty_stock_list(self) -> None:
        """空清單應回傳空結果。"""
        downloader = BatchDownloader()
        result = downloader.download(
            stock_codes=[],
            download_func=success_download_func,
        )
        assert result.total_batches == 0
        assert result.completed_batches == 0
        assert result.successful_data == {}
        assert result.failed_stocks == []
        assert result.aborted is False

    def test_single_stock(self) -> None:
        """單一股票應成功下載。"""
        downloader = BatchDownloader(
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=["2330"],
            download_func=success_download_func,
        )
        assert result.total_batches == 1
        assert result.completed_batches == 1
        assert "2330" in result.successful_data
        assert result.failed_stocks == []

    def test_exact_batch_size(self) -> None:
        """恰好等於 batch_size 的清單產生 1 批。"""
        stocks = make_stock_list(50)
        downloader = BatchDownloader(
            batch_size=50,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=stocks,
            download_func=success_download_func,
        )
        assert result.total_batches == 1
        assert result.completed_batches == 1
        assert len(result.successful_data) == 50

    def test_multiple_batches(self) -> None:
        """超過 batch_size 應正確分批。"""
        stocks = make_stock_list(120)
        downloader = BatchDownloader(
            batch_size=50,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=stocks,
            download_func=success_download_func,
        )
        assert result.total_batches == 3  # ceil(120/50) = 3
        assert result.completed_batches == 3
        assert len(result.successful_data) == 120
        assert result.failed_stocks == []

    def test_no_duplicates_in_result(self) -> None:
        """結果中不應有重複的股票代碼。"""
        stocks = make_stock_list(75)
        downloader = BatchDownloader(
            batch_size=50,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=stocks,
            download_func=success_download_func,
        )
        assert len(result.successful_data) == 75


# ---------------------------------------------------------------------------
# 分批策略測試
# ---------------------------------------------------------------------------


class TestBatchSplitting:
    """分批策略正確性測試。"""

    def test_split_into_batches_simple(self) -> None:
        """基本分批邏輯。"""
        downloader = BatchDownloader(batch_size=10)
        batches = downloader._split_into_batches(make_stock_list(25))
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5

    def test_split_preserves_all_elements(self) -> None:
        """分批後所有元素不遺漏。"""
        stocks = make_stock_list(73)
        downloader = BatchDownloader(batch_size=20)
        batches = downloader._split_into_batches(stocks)
        flattened = [code for batch in batches for code in batch]
        assert flattened == stocks

    def test_split_no_empty_batches(self) -> None:
        """分批結果中不應有空批次。"""
        for n in range(1, 200):
            downloader = BatchDownloader(batch_size=50)
            batches = downloader._split_into_batches(make_stock_list(n))
            for batch in batches:
                assert len(batch) > 0
            assert len(batches) == -(-n // 50)  # ceil division


# ---------------------------------------------------------------------------
# 逾時與拆分重試測試
# ---------------------------------------------------------------------------


class TestTimeoutAndSplit:
    """逾時拆分重試測試。"""

    def test_timeout_triggers_split(self) -> None:
        """逾時應觸發子批次拆分重試。"""
        call_count = 0

        def timeout_then_success(stocks: List[str]) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次（原批次）超時
                raise TimeoutError("timeout")
            # 子批次成功
            return {code: {"data": True} for code in stocks}

        downloader = BatchDownloader(
            batch_size=10,
            timeout_seconds=5.0,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(10),
            download_func=timeout_then_success,
        )
        # 子批次應成功取得資料
        assert len(result.successful_data) == 10
        assert result.failed_stocks == []

    def test_single_stock_timeout_not_splittable(self) -> None:
        """單一股票逾時無法再拆分，記為失敗。"""
        downloader = BatchDownloader(
            batch_size=50,
            timeout_seconds=0.01,
            sleep_func=lambda _: None,
        )

        def always_timeout(stocks: List[str]) -> Dict[str, Any]:
            time.sleep(0.1)
            return {}

        result = downloader.download(
            stock_codes=["2330"],
            download_func=always_timeout,
        )
        assert "2330" in result.failed_stocks

    def test_partial_sub_batch_success(self) -> None:
        """子批次之一成功、另一個失敗時，應回傳部分資料。"""
        call_count = 0

        def mixed_results(stocks: List[str]) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("original batch timeout")
            if call_count == 2:
                # 子批次 A 成功
                return {code: {"data": True} for code in stocks}
            # 子批次 B 失敗
            raise RuntimeError("sub-batch B failed")

        downloader = BatchDownloader(
            batch_size=10,
            timeout_seconds=5.0,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(10),
            download_func=mixed_results,
        )
        # 子批次 A (5 檔) 成功，子批次 B (5 檔) 失敗
        assert len(result.successful_data) == 5
        assert len(result.failed_stocks) == 5


# ---------------------------------------------------------------------------
# 連續失敗中止測試
# ---------------------------------------------------------------------------


class TestConsecutiveFailureAbort:
    """連續失敗中止測試。"""

    def test_abort_after_3_consecutive_failures(self) -> None:
        """連續 3 批失敗後應中止並回傳部分資料。"""
        downloader = BatchDownloader(
            batch_size=10,
            max_consecutive_failures=3,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(50),
            download_func=failure_download_func,
        )
        assert result.aborted is True
        assert "連續" in result.abort_reason
        # 5 批中只嘗試了 3 批（全失敗），剩餘 2 批直接加入失敗
        assert len(result.failed_stocks) == 50

    def test_consecutive_counter_resets_on_success(self) -> None:
        """成功後連續失敗計數器重置。"""
        batch_idx = 0

        def intermittent_fail(stocks: List[str]) -> Dict[str, Any]:
            nonlocal batch_idx
            batch_idx += 1
            # 批次 1 成功，2 失敗，3 成功，4 失敗，5 失敗
            if batch_idx in (1, 3):
                return {code: {"data": True} for code in stocks}
            return {}

        downloader = BatchDownloader(
            batch_size=10,
            max_consecutive_failures=3,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(50),
            download_func=intermittent_fail,
        )
        # 不應中止：最多連續 2 次失敗（批次 4, 5）
        assert result.aborted is False

    def test_exception_counts_as_failure(self) -> None:
        """下載函式拋出例外也計為失敗。"""
        downloader = BatchDownloader(
            batch_size=10,
            max_consecutive_failures=3,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(40),
            download_func=exception_download_func,
        )
        assert result.aborted is True
        assert len(result.failed_stocks) == 40


# ---------------------------------------------------------------------------
# 進度回呼測試
# ---------------------------------------------------------------------------


class TestProgressCallback:
    """進度回呼測試。"""

    def test_callback_called_for_each_batch(self) -> None:
        """每個批次完成後都應呼叫 callback。"""
        callbacks: List[tuple] = []

        def on_progress(completed: int, total: int, msg: str) -> None:
            callbacks.append((completed, total, msg))

        downloader = BatchDownloader(
            batch_size=10,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(30),
            download_func=success_download_func,
            progress_callback=on_progress,
        )
        assert len(callbacks) == 3
        assert callbacks[-1][0] == 3  # completed
        assert callbacks[-1][1] == 3  # total

    def test_callback_not_required(self) -> None:
        """不傳 callback 時不應報錯。"""
        downloader = BatchDownloader(sleep_func=lambda _: None)
        result = downloader.download(
            stock_codes=make_stock_list(10),
            download_func=success_download_func,
            progress_callback=None,
        )
        assert result.completed_batches == 1

    def test_callback_shows_failure_message(self) -> None:
        """失敗批次的 callback 訊息應包含「失敗」。"""
        callbacks: List[tuple] = []

        def on_progress(completed: int, total: int, msg: str) -> None:
            callbacks.append((completed, total, msg))

        downloader = BatchDownloader(
            batch_size=10,
            max_consecutive_failures=5,
            sleep_func=lambda _: None,
        )
        downloader.download(
            stock_codes=make_stock_list(10),
            download_func=failure_download_func,
            progress_callback=on_progress,
        )
        assert any("失敗" in cb[2] for cb in callbacks)


# ---------------------------------------------------------------------------
# 批次延遲測試
# ---------------------------------------------------------------------------


class TestBatchDelay:
    """批次間延遲測試。"""

    def test_sleep_called_between_batches(self) -> None:
        """批次間應呼叫 sleep_func。"""
        sleep_calls: List[float] = []

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        downloader = BatchDownloader(
            batch_size=10,
            batch_delay=1.5,
            sleep_func=mock_sleep,
        )
        downloader.download(
            stock_codes=make_stock_list(30),
            download_func=success_download_func,
        )
        # 3 批，批次間等待 2 次
        assert len(sleep_calls) == 2
        assert all(s == 1.5 for s in sleep_calls)

    def test_no_sleep_for_single_batch(self) -> None:
        """單一批次不應呼叫 sleep_func。"""
        sleep_calls: List[float] = []

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        downloader = BatchDownloader(
            batch_size=50,
            sleep_func=mock_sleep,
        )
        downloader.download(
            stock_codes=make_stock_list(10),
            download_func=success_download_func,
        )
        assert sleep_calls == []


# ---------------------------------------------------------------------------
# 部分成功測試
# ---------------------------------------------------------------------------


class TestPartialSuccess:
    """部分成功情境測試。"""

    def test_partial_data_in_batch(self) -> None:
        """download_func 只回傳部分股票資料時應正確標記失敗的。"""

        def partial_success(stocks: List[str]) -> Dict[str, Any]:
            # 只回傳前半
            half = stocks[: len(stocks) // 2]
            return {code: {"data": True} for code in half}

        downloader = BatchDownloader(
            batch_size=10,
            sleep_func=lambda _: None,
        )
        result = downloader.download(
            stock_codes=make_stock_list(10),
            download_func=partial_success,
        )
        assert len(result.successful_data) == 5
        assert len(result.failed_stocks) == 5


# ---------------------------------------------------------------------------
# 參數驗證測試
# ---------------------------------------------------------------------------


class TestParameterValidation:
    """初始化參數驗證測試。"""

    def test_invalid_batch_size(self) -> None:
        """batch_size <= 0 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="batch_size"):
            BatchDownloader(batch_size=0)

    def test_invalid_max_workers(self) -> None:
        """max_workers <= 0 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="max_workers"):
            BatchDownloader(max_workers=-1)

    def test_invalid_max_consecutive_failures(self) -> None:
        """max_consecutive_failures <= 0 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="max_consecutive_failures"):
            BatchDownloader(max_consecutive_failures=0)
