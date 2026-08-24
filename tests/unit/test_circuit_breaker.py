"""Circuit Breaker 單元測試。

驗證斷路器狀態機的所有轉換路徑、滑動時間視窗行為、
以及每個資料來源獨立實例的正確性。
"""

import threading
from unittest.mock import patch

import pytest

from app.infra.resilience.circuit_breaker import (
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreaker,
)


class TestCircuitBreakerInitialization:
    """初始化與預設值測試。"""

    def test_initial_state_is_closed(self) -> None:
        """斷路器初始狀態為 closed。"""
        cb = CircuitBreaker(source_name="test_source")
        assert cb.state == STATE_CLOSED

    def test_default_parameters(self) -> None:
        """預設參數值正確。"""
        cb = CircuitBreaker(source_name="test")
        assert cb.failure_threshold == 5
        assert cb.window_seconds == 60.0
        assert cb.recovery_timeout == 300.0

    def test_custom_parameters(self) -> None:
        """自訂參數可正常設定。"""
        cb = CircuitBreaker(
            source_name="custom",
            failure_threshold=3,
            window_seconds=30.0,
            recovery_timeout=120.0,
        )
        assert cb.failure_threshold == 3
        assert cb.window_seconds == 30.0
        assert cb.recovery_timeout == 120.0

    def test_allow_request_when_closed(self) -> None:
        """closed 狀態下允許所有請求。"""
        cb = CircuitBreaker(source_name="test")
        assert cb.allow_request() is True


class TestClosedToOpen:
    """CLOSED -> OPEN 狀態轉換測試。"""

    def test_open_after_threshold_failures_within_window(self) -> None:
        """60 秒內 5 次失敗觸發 open。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        for _ in range(5):
            cb.record_failure()

        assert cb.state == STATE_OPEN

    def test_stays_closed_below_threshold(self) -> None:
        """失敗次數未達閾值時維持 closed。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        for _ in range(4):
            cb.record_failure()

        assert cb.state == STATE_CLOSED

    def test_old_failures_expire_outside_window(self) -> None:
        """超出視窗的舊失敗記錄會被剔除，不計入閾值。"""
        times = [0.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            window_seconds=60.0,
        )

        # 在 t=0 記錄 3 次失敗
        for _ in range(3):
            cb.record_failure()

        # 跳到 t=61（超出視窗）
        times[0] = 61.0

        # 再記錄 2 次失敗（視窗內只有 2 次）
        for _ in range(2):
            cb.record_failure()

        # 視窗內總共只有 2 次，不應觸發 open
        assert cb.state == STATE_CLOSED

    def test_failures_at_window_boundary(self) -> None:
        """恰好在視窗邊界的失敗仍計入。"""
        times = [0.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            window_seconds=60.0,
        )

        # 在 t=0 記錄 3 次
        for _ in range(3):
            cb.record_failure()

        # 在 t=59.9（仍在視窗內）記錄 2 次
        times[0] = 59.9
        for _ in range(2):
            cb.record_failure()

        # 視窗內共 5 次，應觸發 open
        assert cb.state == STATE_OPEN

    def test_allow_request_returns_false_when_open(self) -> None:
        """open 狀態下拒絕請求。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        for _ in range(5):
            cb.record_failure()

        assert cb.allow_request() is False


class TestOpenToHalfOpen:
    """OPEN -> HALF_OPEN 狀態轉換測試。"""

    def test_transitions_to_half_open_after_recovery_timeout(self) -> None:
        """超過冷卻時間後轉為 half_open。"""
        times = [1000.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            recovery_timeout=300.0,
        )

        # 觸發 open
        for _ in range(5):
            cb.record_failure()
        assert cb.state == STATE_OPEN

        # 前進 300 秒
        times[0] = 1300.0
        assert cb.state == STATE_HALF_OPEN

    def test_stays_open_before_recovery_timeout(self) -> None:
        """冷卻時間未到前維持 open。"""
        times = [1000.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            recovery_timeout=300.0,
        )

        for _ in range(5):
            cb.record_failure()

        # 前進 299 秒（不夠）
        times[0] = 1299.0
        assert cb.state == STATE_OPEN

    def test_allow_request_permits_one_probe_in_half_open(self) -> None:
        """half_open 狀態允許恰好一次探測性請求。"""
        times = [1000.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            recovery_timeout=300.0,
        )

        for _ in range(5):
            cb.record_failure()

        times[0] = 1300.0  # 進入 half_open

        # 第一次應允許
        assert cb.allow_request() is True
        # 第二次應拒絕
        assert cb.allow_request() is False


class TestHalfOpenTransitions:
    """HALF_OPEN 的兩種轉換路徑測試。"""

    def _create_half_open_breaker(self) -> tuple:
        """建立已進入 half_open 狀態的斷路器，回傳 (cb, times)。"""
        times = [1000.0]

        def mock_time() -> float:
            return times[0]

        cb = CircuitBreaker(
            source_name="test",
            time_func=mock_time,
            recovery_timeout=300.0,
        )

        for _ in range(5):
            cb.record_failure()

        times[0] = 1300.0  # 進入 half_open
        # 觸發狀態轉換
        _ = cb.state
        return cb, times

    def test_half_open_to_closed_on_success(self) -> None:
        """half_open 探測成功後恢復為 closed。"""
        cb, _ = self._create_half_open_breaker()

        cb.record_success()
        assert cb.state == STATE_CLOSED

    def test_half_open_to_open_on_failure(self) -> None:
        """half_open 探測失敗後回到 open。"""
        cb, _ = self._create_half_open_breaker()

        cb.record_failure()
        assert cb.state == STATE_OPEN

    def test_closed_after_recovery_allows_all_requests(self) -> None:
        """從 half_open 恢復 closed 後應允許所有請求。"""
        cb, _ = self._create_half_open_breaker()

        cb.record_success()
        assert cb.allow_request() is True
        assert cb.allow_request() is True


class TestReset:
    """reset() 方法測試。"""

    def test_reset_from_open(self) -> None:
        """open 狀態下 reset 恢復為 closed。"""
        cb = CircuitBreaker(source_name="test", time_func=lambda: 1000.0)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == STATE_OPEN

        cb.reset()
        assert cb.state == STATE_CLOSED
        assert cb.allow_request() is True

    def test_reset_clears_failure_history(self) -> None:
        """reset 後舊的失敗記錄不再影響。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        # 記錄 4 次失敗
        for _ in range(4):
            cb.record_failure()

        cb.reset()

        # 再記錄 4 次，因為 deque 被清空，不應觸發 open
        for _ in range(4):
            cb.record_failure()

        assert cb.state == STATE_CLOSED


class TestIndependentInstances:
    """每個資料來源獨立實例測試。"""

    def test_separate_sources_independent(self) -> None:
        """不同來源的斷路器互不影響。"""
        current_time = 1000.0
        cb_yahoo = CircuitBreaker(
            source_name="yahoo_finance",
            time_func=lambda: current_time,
        )
        cb_finmind = CircuitBreaker(
            source_name="finmind",
            time_func=lambda: current_time,
        )

        # Yahoo 觸發 open
        for _ in range(5):
            cb_yahoo.record_failure()

        assert cb_yahoo.state == STATE_OPEN
        # FinMind 不受影響
        assert cb_finmind.state == STATE_CLOSED
        assert cb_finmind.allow_request() is True


class TestRecordSuccessInClosed:
    """closed 狀態下 record_success 行為測試。"""

    def test_success_in_closed_does_not_clear_failures(self) -> None:
        """closed 狀態下 record_success 不清除失敗記錄（由時間視窗自然過期）。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        # 記錄 4 次失敗
        for _ in range(4):
            cb.record_failure()

        # 成功不清除計數
        cb.record_success()

        # 再失敗 1 次（視窗內共 5 次）→ open
        cb.record_failure()
        assert cb.state == STATE_OPEN


class TestThreadSafety:
    """執行緒安全測試。"""

    def test_concurrent_failures_do_not_corrupt_state(self) -> None:
        """多執行緒同時記錄失敗不會造成狀態損壞。"""
        current_time = 1000.0
        cb = CircuitBreaker(
            source_name="test",
            time_func=lambda: current_time,
        )

        def record_many_failures() -> None:
            for _ in range(3):
                cb.record_failure()

        threads = [threading.Thread(target=record_many_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 12 次失敗（遠超 5），狀態應為 open
        assert cb.state == STATE_OPEN


class TestProtocolConformance:
    """驗證 CircuitBreaker 實作符合 CircuitBreakerProtocol。"""

    def test_conforms_to_protocol(self) -> None:
        """CircuitBreaker 實例通過 isinstance 檢查。"""
        from app.core.protocols import CircuitBreakerProtocol

        cb = CircuitBreaker(source_name="test")
        assert isinstance(cb, CircuitBreakerProtocol)
