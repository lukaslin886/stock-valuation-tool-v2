"""Batch Downloader 屬性測試。

Feature: stock-valuation-optimization, Property 10: Batch splitting correctness
Feature: stock-valuation-optimization, Property 11: Concurrency limit invariant

使用 Hypothesis 驗證批次下載器的不變式：
- Property 10: 批次分割正確性
  對任意長度 N (N > 0) 的股票清單與 batch_size (1-100)：
  批次總數 = ceil(N/batch_size)、每批 <= batch_size、
  聯集 = 原始清單（無遺漏、無重複）
- Property 11: 並行度上限不變式
  活躍的同時請求數量永不超過 max_workers

**Validates: Requirements 3.1, 6.1, 6.3, 6.4**
"""

import math
import threading
import time
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.infra.resilience.batch_downloader import BatchDownloader


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 產生隨機股票代碼清單（長度 1~500）
stock_list_strategy = st.lists(
    st.text(
        alphabet=st.sampled_from("0123456789"),
        min_size=4,
        max_size=6,
    ),
    min_size=1,
    max_size=500,
).map(lambda codes: list(dict.fromkeys(codes))).filter(lambda x: len(x) > 0)
# 使用 dict.fromkeys 去重後再過濾確保非空

# 批次大小 1~100
batch_size_strategy = st.integers(min_value=1, max_value=100)

# max_workers 1~10
max_workers_strategy = st.integers(min_value=1, max_value=10)


# ---------------------------------------------------------------------------
# Property 10: Batch splitting correctness
# ---------------------------------------------------------------------------


class TestBatchSplittingCorrectness:
    """Property 10: 批次分割正確性。

    **Validates: Requirements 3.1**
    """

    @given(
        stock_codes=stock_list_strategy,
        batch_size=batch_size_strategy,
    )
    @settings(max_examples=200, deadline=30000)
    def test_batch_count_equals_ceil_n_over_batch_size(
        self, stock_codes: List[str], batch_size: int
    ) -> None:
        """批次總數等於 ceil(N / batch_size)。

        **Validates: Requirements 3.1**
        """
        downloader = BatchDownloader(
            batch_size=batch_size,
            max_workers=5,
            batch_delay=0.0,
            sleep_func=lambda _: None,
        )

        batches = downloader._split_into_batches(stock_codes)
        n = len(stock_codes)
        expected_count = math.ceil(n / batch_size)

        assert len(batches) == expected_count

    @given(
        stock_codes=stock_list_strategy,
        batch_size=batch_size_strategy,
    )
    @settings(max_examples=200, deadline=30000)
    def test_each_batch_size_within_limit(
        self, stock_codes: List[str], batch_size: int
    ) -> None:
        """每個批次元素數量不超過 batch_size。

        **Validates: Requirements 3.1**
        """
        downloader = BatchDownloader(
            batch_size=batch_size,
            max_workers=5,
            batch_delay=0.0,
            sleep_func=lambda _: None,
        )

        batches = downloader._split_into_batches(stock_codes)

        for batch in batches:
            assert len(batch) <= batch_size

    @given(
        stock_codes=stock_list_strategy,
        batch_size=batch_size_strategy,
    )
    @settings(max_examples=200, deadline=30000)
    def test_union_of_batches_equals_original(
        self, stock_codes: List[str], batch_size: int
    ) -> None:
        """所有批次的聯集等於原始清單（無遺漏、無重複、順序保持）。

        **Validates: Requirements 3.1**
        """
        downloader = BatchDownloader(
            batch_size=batch_size,
            max_workers=5,
            batch_delay=0.0,
            sleep_func=lambda _: None,
        )

        batches = downloader._split_into_batches(stock_codes)

        # 展平所有批次
        flattened: List[str] = []
        for batch in batches:
            flattened.extend(batch)

        # 無遺漏：元素數量相同
        assert len(flattened) == len(stock_codes)

        # 無重複且順序保持：逐一比對
        assert flattened == stock_codes

    @given(
        stock_codes=stock_list_strategy,
        batch_size=batch_size_strategy,
    )
    @settings(max_examples=200, deadline=30000)
    def test_all_batches_except_last_are_full(
        self, stock_codes: List[str], batch_size: int
    ) -> None:
        """除最後一批外，所有批次元素數量恰為 batch_size。

        **Validates: Requirements 3.1**
        """
        downloader = BatchDownloader(
            batch_size=batch_size,
            max_workers=5,
            batch_delay=0.0,
            sleep_func=lambda _: None,
        )

        batches = downloader._split_into_batches(stock_codes)

        if len(batches) > 1:
            for batch in batches[:-1]:
                assert len(batch) == batch_size

        # 最後一批 <= batch_size 且 > 0
        assert 0 < len(batches[-1]) <= batch_size


# ---------------------------------------------------------------------------
# Property 11: Concurrency limit invariant
# ---------------------------------------------------------------------------


class TestConcurrencyLimitInvariant:
    """Property 11: 並行度上限不變式。

    驗證活躍並行請求數永不超過 max_workers。
    由於 Hypothesis 難以直接測試並行行為，採用 unit test 風格搭配
    threading 計數器驗證。

    **Validates: Requirements 6.1, 6.3, 6.4**
    """

    @given(
        n_stocks=st.integers(min_value=5, max_value=100),
        max_workers=st.integers(min_value=1, max_value=8),
        batch_size=st.integers(min_value=2, max_value=20),
    )
    @settings(max_examples=200, deadline=30000)
    def test_active_requests_never_exceed_max_workers(
        self, n_stocks: int, max_workers: int, batch_size: int
    ) -> None:
        """活躍的同時請求數量永不超過 max_workers。

        使用 threading 原子計數器追蹤同時活躍的下載呼叫數。

        **Validates: Requirements 6.1, 6.3, 6.4**
        """
        # 追蹤並行度
        concurrency_counter = threading.Semaphore(value=0)
        max_observed = [0]
        lock = threading.Lock()
        active_count = [0]

        def tracked_download(codes: List[str]) -> Dict[str, Any]:
            """追蹤並行度的 mock 下載函式。"""
            with lock:
                active_count[0] += 1
                if active_count[0] > max_observed[0]:
                    max_observed[0] = active_count[0]

            # 模擬短暫工作
            time.sleep(0.01)

            with lock:
                active_count[0] -= 1

            return {code: {"price": 100.0} for code in codes}

        # 產生股票代碼
        stock_codes = [f"{i:04d}" for i in range(n_stocks)]

        downloader = BatchDownloader(
            batch_size=batch_size,
            max_workers=max_workers,
            batch_delay=0.0,
            timeout_seconds=10.0,
            sleep_func=lambda _: None,
        )

        result = downloader.download(
            stock_codes=stock_codes,
            download_func=tracked_download,
        )

        # 驗證並行度上限
        assert max_observed[0] <= max_workers

    @given(
        n_stocks=st.integers(min_value=10, max_value=80),
        max_workers=st.integers(min_value=2, max_value=6),
    )
    @settings(max_examples=200, deadline=30000)
    def test_partial_failure_returns_correct_counts(
        self, n_stocks: int, max_workers: int
    ) -> None:
        """N 個請求中有 K 個失敗時，回傳 N-K 筆成功資料。

        同時驗證所有失敗的股票代碼被記錄。

        **Validates: Requirements 6.3, 6.4**
        """
        # 決定哪些股票會失敗（前 30% 失敗）
        stock_codes = [f"{i:04d}" for i in range(n_stocks)]
        fail_count = max(1, n_stocks // 3)
        fail_set = set(stock_codes[:fail_count])

        def partial_fail_download(codes: List[str]) -> Dict[str, Any]:
            """部分失敗的 mock 下載函式：只回傳不在 fail_set 中的股票。"""
            return {
                code: {"price": 100.0}
                for code in codes
                if code not in fail_set
            }

        downloader = BatchDownloader(
            batch_size=10,
            max_workers=max_workers,
            batch_delay=0.0,
            timeout_seconds=10.0,
            sleep_func=lambda _: None,
        )

        result = downloader.download(
            stock_codes=stock_codes,
            download_func=partial_fail_download,
        )

        # 成功資料數 = 非失敗的股票數
        expected_success = n_stocks - fail_count
        assert len(result.successful_data) == expected_success

        # 所有失敗的股票代碼都被記錄
        assert set(result.failed_stocks) == fail_set
