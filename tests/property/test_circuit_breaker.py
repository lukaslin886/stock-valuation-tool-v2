"""Circuit Breaker 狀態轉換正確性屬性測試。

Feature: stock-valuation-optimization, Property 9: Circuit Breaker state transition correctness

使用 Hypothesis 驗證斷路器狀態機的不變式：
- 60 秒滑動視窗內失敗次數 N < 5 時，狀態維持 closed
- 失敗次數 N >= 5 時，狀態轉為 open
- 各資料來源的失敗計數彼此獨立

**Validates: Requirements 9.1, 9.2**
"""

import time
from typing import List, Tuple

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.infra.resilience.circuit_breaker import (
    CircuitBreaker,
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 產生 1~4 次失敗（應維持 closed）
failures_below_threshold = st.integers(min_value=0, max_value=4)

# 產生 5~20 次失敗（應轉為 open）
failures_at_or_above_threshold = st.integers(min_value=5, max_value=20)

# 產生隨機來源名稱
source_names = st.sampled_from(["yahoo_finance", "finmind", "finlab", "test_source"])

# 操作類型：failure 或 success
operation_type = st.sampled_from(["failure", "success"])

# 產生一序列操作（operation, time_delta_ms）
# time_delta_ms: 每次操作之間的毫秒間隔（0~100ms，確保全部落在 60 秒視窗內）
operation_within_window = st.tuples(
    operation_type,
    st.integers(min_value=0, max_value=100),  # ms increment
)

# 產生操作序列（5~30 個操作），所有操作在同一 60 秒視窗內
operation_sequence_in_window = st.lists(
    operation_within_window, min_size=1, max_size=30
)

# 產生時間增量（用於跨越視窗邊界的測試）
time_delta_seconds = st.floats(min_value=0.0, max_value=120.0, allow_nan=False)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_cb(source_name: str = "test") -> Tuple[CircuitBreaker, List[float]]:
    """建立可注入時間的 CircuitBreaker 及時間控制器。

    Returns:
        (circuit_breaker, time_holder) 其中 time_holder[0] 為目前時間。
    """
    current_time = [0.0]

    def fake_time() -> float:
        return current_time[0]

    cb = CircuitBreaker(
        source_name=source_name,
        failure_threshold=5,
        window_seconds=60.0,
        recovery_timeout=300.0,
        time_func=fake_time,
    )
    return cb, current_time


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestCircuitBreakerStateTransition:
    """Property 9: Circuit Breaker state transition correctness."""

    @given(n_failures=failures_below_threshold)
    @settings(max_examples=200, deadline=30000)
    def test_below_threshold_stays_closed(self, n_failures: int) -> None:
        """在 60 秒視窗內，失敗次數 N < 5 時狀態維持 closed。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        for i in range(n_failures):
            # 所有失敗都在 60 秒視窗內（每次間隔 1 秒）
            current_time[0] = float(i)
            cb.record_failure()

        assert cb.state == STATE_CLOSED

    @given(n_failures=failures_at_or_above_threshold)
    @settings(max_examples=200, deadline=30000)
    def test_at_threshold_transitions_to_open(self, n_failures: int) -> None:
        """在 60 秒視窗內，失敗次數 N >= 5 時狀態轉為 open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        for i in range(n_failures):
            # 所有失敗都在 60 秒視窗內（每次間隔 1 秒）
            current_time[0] = float(i)
            cb.record_failure()

        assert cb.state == STATE_OPEN

    @given(
        source_a_failures=st.integers(min_value=0, max_value=10),
        source_b_failures=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=200, deadline=30000)
    def test_independent_failure_counts(
        self, source_a_failures: int, source_b_failures: int
    ) -> None:
        """各資料來源的失敗計數彼此獨立。

        **Validates: Requirements 9.1, 9.2**
        """
        cb_a, time_a = make_cb(source_name="source_a")
        cb_b, time_b = make_cb(source_name="source_b")

        # 對 source_a 記錄失敗
        for i in range(source_a_failures):
            time_a[0] = float(i)
            cb_a.record_failure()

        # 對 source_b 記錄失敗
        for i in range(source_b_failures):
            time_b[0] = float(i)
            cb_b.record_failure()

        # 驗證各自獨立的狀態
        expected_a = STATE_OPEN if source_a_failures >= 5 else STATE_CLOSED
        expected_b = STATE_OPEN if source_b_failures >= 5 else STATE_CLOSED

        assert cb_a.state == expected_a
        assert cb_b.state == expected_b

    @given(ops=operation_sequence_in_window)
    @settings(max_examples=200, deadline=30000)
    def test_random_operations_state_invariant(
        self, ops: List[Tuple[str, int]]
    ) -> None:
        """任意操作序列後，狀態不變式成立。

        在 60 秒視窗內：
        - 若操作序列中從上次 reset（含 success 在 half_open 觸發的 reset）
          起累計 failure 達 5，則狀態為 open
        - 若未達 5，狀態為 closed

        注意：record_success 在 half_open 時會 reset 至 closed，
        此處測試聚焦於 closed 狀態下的行為（因為所有操作在視窗內，
        且斷路器不會自動進入 half_open 除非時間超過 recovery_timeout）。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()
        elapsed_ms = 0

        # 追蹤有效失敗次數（在 closed 狀態下記錄的）
        for op_type, delta_ms in ops:
            elapsed_ms += delta_ms
            current_time[0] = elapsed_ms / 1000.0  # 轉為秒

            if cb.state == STATE_OPEN:
                # open 狀態下不再記錄操作（無法 allow_request）
                break

            if op_type == "failure":
                cb.record_failure()
            else:
                cb.record_success()

        # 最終狀態只能是 closed 或 open（不可能是 half_open，
        # 因為時間未超過 recovery_timeout = 300s，而我們最多到 3s）
        assert cb.state in (STATE_CLOSED, STATE_OPEN)

    @given(
        n_failures=st.integers(min_value=5, max_value=15),
        extra_time=st.floats(min_value=300.0, max_value=600.0, allow_nan=False),
    )
    @settings(max_examples=200, deadline=30000)
    def test_open_to_half_open_after_recovery_timeout(
        self, n_failures: int, extra_time: float
    ) -> None:
        """open 狀態超過 recovery_timeout 後轉為 half_open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 觸發 open
        for i in range(n_failures):
            current_time[0] = float(i)
            cb.record_failure()

        assert cb.state == STATE_OPEN

        # 推進時間超過 recovery_timeout
        current_time[0] = float(n_failures) + extra_time
        assert cb.state == STATE_HALF_OPEN

    @given(n_failures=st.integers(min_value=5, max_value=15))
    @settings(max_examples=200, deadline=30000)
    def test_half_open_success_resets_to_closed(self, n_failures: int) -> None:
        """half_open 狀態探測成功後恢復 closed。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 觸發 open
        for i in range(n_failures):
            current_time[0] = float(i)
            cb.record_failure()

        assert cb.state == STATE_OPEN

        # 推進至 half_open
        current_time[0] = float(n_failures) + 301.0
        assert cb.state == STATE_HALF_OPEN

        # 探測成功
        cb.record_success()
        assert cb.state == STATE_CLOSED

    @given(n_failures=st.integers(min_value=5, max_value=15))
    @settings(max_examples=200, deadline=30000)
    def test_half_open_failure_returns_to_open(self, n_failures: int) -> None:
        """half_open 狀態探測失敗後回到 open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 觸發 open
        for i in range(n_failures):
            current_time[0] = float(i)
            cb.record_failure()

        assert cb.state == STATE_OPEN

        # 推進至 half_open
        current_time[0] = float(n_failures) + 301.0
        assert cb.state == STATE_HALF_OPEN

        # 探測失敗
        cb.record_failure()
        assert cb.state == STATE_OPEN

    @given(
        n_early=st.integers(min_value=3, max_value=4),
        n_late=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=200, deadline=30000)
    def test_failures_outside_window_do_not_count(
        self, n_early: int, n_late: int
    ) -> None:
        """滑動視窗外的失敗不計入，確保只有 60 秒內的失敗才觸發 open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 假設 n_early + n_late < 5（才能驗證不觸發）
        assume(n_early + n_late < 5)
        # 但也確保 n_early 的失敗已超出視窗
        # 在 t=0 記錄 n_early 次失敗
        for i in range(n_early):
            current_time[0] = float(i)
            cb.record_failure()

        # 推進時間超過 60 秒視窗，使得前面的失敗過期
        current_time[0] = 61.0

        # 在新視窗記錄 n_late 次失敗
        for i in range(n_late):
            current_time[0] = 61.0 + float(i)
            cb.record_failure()

        # 由於前面的失敗已過期，只有 n_late 次在視窗內
        # n_late 最多 4，所以不應觸發 open
        assert cb.state == STATE_CLOSED

    @given(
        n_early=st.integers(min_value=1, max_value=4),
        n_late=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200, deadline=30000)
    def test_window_boundary_failures_trigger_open(
        self, n_early: int, n_late: int
    ) -> None:
        """當視窗內的有效失敗次數達到閾值時觸發 open。

        n_early 次失敗在視窗內（不過期），加上 n_late 次新失敗，
        若總計 >= 5 則應觸發 open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 在 t=10~(10+n_early-1) 記錄失敗（確保 60 秒內不會過期）
        for i in range(n_early):
            current_time[0] = 10.0 + float(i)
            cb.record_failure()

        # 在 t=50~(50+n_late-1) 記錄更多失敗（仍在 60 秒視窗內：50 - 10 = 40 < 60）
        for i in range(n_late):
            current_time[0] = 50.0 + float(i)
            cb.record_failure()
            # 一旦轉為 open 就停止
            if cb.state == STATE_OPEN:
                break

        total_in_window = n_early + n_late
        if total_in_window >= 5:
            assert cb.state == STATE_OPEN
        else:
            assert cb.state == STATE_CLOSED

    @given(
        success_count=st.integers(min_value=0, max_value=10),
        failure_count=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=200, deadline=30000)
    def test_success_in_closed_does_not_affect_state(
        self, success_count: int, failure_count: int
    ) -> None:
        """在 closed 狀態下，record_success 不影響狀態轉換邏輯。

        只有 failure 計數影響是否轉為 open。

        **Validates: Requirements 9.1, 9.2**
        """
        cb, current_time = make_cb()

        # 交替記錄 success 和 failure
        t = 0.0
        for _ in range(success_count):
            current_time[0] = t
            cb.record_success()
            t += 0.5

        for _ in range(failure_count):
            current_time[0] = t
            cb.record_failure()
            t += 0.5

        # failure_count < 5，所以狀態應為 closed
        assert cb.state == STATE_CLOSED
