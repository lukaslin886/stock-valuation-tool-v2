"""Rate Limiter 單元測試。

驗證 Token Bucket 演算法、FinMind 配額預檢、HTTP 402 處理、
以及指數退避重試策略的正確性。
"""

import time

import pytest

from app.infra.resilience.rate_limiter import (
    ExponentialBackoff,
    FinMindRateLimiter,
    QuotaStatus,
    RateLimiter,
    retry_with_backoff,
)
from app.core.errors import RateLimitError


# ---------------------------------------------------------------------------
# ExponentialBackoff 測試
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    """指數退避重試策略測試。"""

    def test_default_wait_times(self) -> None:
        """預設配置：1s -> 2s -> 4s。"""
        backoff = ExponentialBackoff()
        assert backoff.get_wait_time(0) == 1.0
        assert backoff.get_wait_time(1) == 2.0
        assert backoff.get_wait_time(2) == 4.0

    def test_max_retries_default(self) -> None:
        """預設最大重試次數為 3。"""
        backoff = ExponentialBackoff()
        assert backoff.max_retries == 3

    def test_cap_at_max_wait(self) -> None:
        """超過 max_wait_seconds 時應被截斷。"""
        backoff = ExponentialBackoff(max_wait_seconds=60.0)
        # 2^10 = 1024 > 60
        assert backoff.get_wait_time(10) == 60.0

    def test_custom_initial_wait(self) -> None:
        """自訂初始等待時間。"""
        backoff = ExponentialBackoff(initial_wait=0.5, multiplier=3.0)
        assert backoff.get_wait_time(0) == 0.5
        assert backoff.get_wait_time(1) == 1.5
        assert backoff.get_wait_time(2) == 4.5

    def test_get_all_wait_times(self) -> None:
        """取得全部重試等待時間清單。"""
        backoff = ExponentialBackoff()
        times = backoff.get_all_wait_times()
        assert times == [1.0, 2.0, 4.0]

    def test_negative_attempt_raises(self) -> None:
        """負數 attempt 應拋出 ValueError。"""
        backoff = ExponentialBackoff()
        with pytest.raises(ValueError, match="不得為負數"):
            backoff.get_wait_time(-1)


# ---------------------------------------------------------------------------
# RateLimiter 測試
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Token Bucket 速率限制器測試。"""

    def _make_limiter(
        self,
        max_tokens: int = 5,
        refill_rate: float = 1.0,
    ) -> tuple:
        """建立帶有假時間的 limiter。"""
        current_time = [0.0]

        def fake_time() -> float:
            return current_time[0]

        limiter = RateLimiter(
            max_tokens=max_tokens,
            refill_rate=refill_rate,
            time_func=fake_time,
        )
        return limiter, current_time

    def test_initial_tokens_full(self) -> None:
        """初始化時 token 桶應為滿的。"""
        limiter, _ = self._make_limiter(max_tokens=10)
        assert limiter.available_tokens == 10.0

    def test_acquire_success(self) -> None:
        """有足夠 token 時 acquire 應回傳 True。"""
        limiter, _ = self._make_limiter(max_tokens=5)
        assert limiter.acquire(1) is True
        assert limiter.acquire(4) is True

    def test_acquire_failure(self) -> None:
        """Token 不足時 acquire 應回傳 False。"""
        limiter, _ = self._make_limiter(max_tokens=5)
        limiter.acquire(5)
        assert limiter.acquire(1) is False

    def test_token_refill(self) -> None:
        """經過時間後 token 應自動補充。"""
        limiter, current_time = self._make_limiter(max_tokens=5, refill_rate=1.0)
        limiter.acquire(5)  # drain all
        current_time[0] = 3.0  # 3 seconds pass -> 3 tokens
        assert limiter.acquire(3) is True
        assert limiter.acquire(1) is False

    def test_token_refill_cap(self) -> None:
        """Token 補充不會超過 max_tokens。"""
        limiter, current_time = self._make_limiter(max_tokens=5, refill_rate=1.0)
        limiter.acquire(2)  # 3 tokens left
        current_time[0] = 100.0  # long time
        assert limiter.available_tokens == 5.0

    def test_invalid_max_tokens(self) -> None:
        """max_tokens <= 0 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="max_tokens"):
            RateLimiter(max_tokens=0)

    def test_invalid_refill_rate(self) -> None:
        """refill_rate <= 0 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="refill_rate"):
            RateLimiter(max_tokens=5, refill_rate=0)

    def test_acquire_invalid_tokens(self) -> None:
        """acquire(0) 或 acquire(-1) 應拋出 ValueError。"""
        limiter, _ = self._make_limiter()
        with pytest.raises(ValueError, match="tokens"):
            limiter.acquire(0)
        with pytest.raises(ValueError, match="tokens"):
            limiter.acquire(-1)

    def test_wait_and_acquire_fast_refill(self) -> None:
        """wait_and_acquire 應阻塞等待直到 token 可用。"""
        # 使用真實時間但超快補充速率
        limiter = RateLimiter(max_tokens=2, refill_rate=100.0)
        limiter.acquire(2)  # drain
        start = time.time()
        limiter.wait_and_acquire(1)
        elapsed = time.time() - start
        assert elapsed < 1.0

    def test_wait_and_acquire_exceeds_max(self) -> None:
        """要求超過 max_tokens 的 wait_and_acquire 應拋出 ValueError。"""
        limiter, _ = self._make_limiter(max_tokens=5)
        with pytest.raises(ValueError, match="不得超過 max_tokens"):
            limiter.wait_and_acquire(6)

    def test_set_rate(self) -> None:
        """動態調整 refill_rate。"""
        limiter, current_time = self._make_limiter(max_tokens=10, refill_rate=1.0)
        limiter.acquire(10)  # drain
        limiter.set_rate(5.0)
        current_time[0] = 2.0  # 2s * 5 tokens/s = 10 tokens
        assert limiter.available_tokens == 10.0

    def test_set_rate_invalid(self) -> None:
        """set_rate(0) 應拋出 ValueError。"""
        limiter, _ = self._make_limiter()
        with pytest.raises(ValueError, match="refill_rate"):
            limiter.set_rate(0)


# ---------------------------------------------------------------------------
# FinMindRateLimiter 測試
# ---------------------------------------------------------------------------


class FakeCircuitBreaker:
    """測試用假斷路器。"""

    def __init__(self) -> None:
        self.failures: int = 0
        self.successes: int = 0
        self._state: str = "closed"

    @property
    def state(self) -> str:
        return self._state

    def record_success(self) -> None:
        self.successes += 1

    def record_failure(self) -> None:
        self.failures += 1

    def allow_request(self) -> bool:
        return self._state != "open"

    def reset(self) -> None:
        self._state = "closed"
        self.failures = 0


class TestFinMindRateLimiter:
    """FinMind 專用速率限制器測試。"""

    def test_quota_check_sufficient(self) -> None:
        """配額充足時回傳 sufficient=True, throttled=False。"""
        def quota_checker(estimated: int) -> int:
            return 500  # plenty

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            quota_checker=quota_checker,
        )
        status = limiter.check_quota(estimated_requests=10)
        assert status.sufficient is True
        assert status.throttled is False
        assert status.remaining == 500

    def test_quota_check_throttled(self) -> None:
        """配額 < 120% 預計請求量但仍足夠時應降速。"""
        def quota_checker(estimated: int) -> int:
            return 11  # 11 < 10*1.2=12 -> throttled, but 11 >= 10 -> sufficient

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=5.0,
            quota_checker=quota_checker,
        )
        status = limiter.check_quota(estimated_requests=10)
        assert status.sufficient is True
        assert status.throttled is True
        assert limiter.is_throttled is True
        assert limiter.refill_rate == 1.0  # throttled to 1 req/s

    def test_quota_check_insufficient(self) -> None:
        """配額不足時回傳 sufficient=False。"""
        def quota_checker(estimated: int) -> int:
            return 5

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            quota_checker=quota_checker,
        )
        status = limiter.check_quota(estimated_requests=100)
        assert status.sufficient is False
        assert status.throttled is True

    def test_quota_check_release_throttle(self) -> None:
        """配額回復充足後應解除降速。"""
        remaining = [11]

        def quota_checker(estimated: int) -> int:
            return remaining[0]

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=5.0,
            quota_checker=quota_checker,
        )
        # 先觸發降速
        limiter.check_quota(estimated_requests=10)
        assert limiter.is_throttled is True
        assert limiter.refill_rate == 1.0

        # 配額回復
        remaining[0] = 500
        limiter.check_quota(estimated_requests=10)
        assert limiter.is_throttled is False
        assert limiter.refill_rate == 5.0

    def test_quota_checker_none(self) -> None:
        """未設定 quota_checker 時視為配額充足。"""
        limiter = FinMindRateLimiter(max_tokens=10, refill_rate=2.0)
        status = limiter.check_quota(estimated_requests=100)
        assert status.sufficient is True
        assert status.remaining == 999999

    def test_quota_checker_exception(self) -> None:
        """quota_checker 拋出例外時採寬鬆策略。"""
        def broken_checker(estimated: int) -> int:
            raise ConnectionError("network error")

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            quota_checker=broken_checker,
        )
        status = limiter.check_quota(estimated_requests=10)
        assert status.sufficient is True  # lenient
        assert status.error_message is not None

    def test_handle_http_402(self) -> None:
        """HTTP 402 應觸發 Circuit Breaker 並回傳 exhausted 狀態。"""
        cb = FakeCircuitBreaker()
        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            circuit_breaker=cb,
        )
        status = limiter.handle_http_402()
        assert status.quota_exhausted is True
        assert status.sufficient is False
        assert cb.failures == 1

    def test_handle_http_402_no_cb(self) -> None:
        """無 Circuit Breaker 時 HTTP 402 仍正常回傳。"""
        limiter = FinMindRateLimiter(max_tokens=10, refill_rate=2.0)
        status = limiter.handle_http_402()
        assert status.quota_exhausted is True

    def test_reset_throttle(self) -> None:
        """手動重置降速狀態。"""
        def quota_checker(estimated: int) -> int:
            return 5

        limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=5.0,
            quota_checker=quota_checker,
        )
        limiter.check_quota(estimated_requests=10)  # trigger throttle
        assert limiter.is_throttled is True

        limiter.reset_throttle()
        assert limiter.is_throttled is False
        assert limiter.refill_rate == 5.0


# ---------------------------------------------------------------------------
# retry_with_backoff 測試
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """指數退避重試輔助函式測試。"""

    def test_success_first_try(self) -> None:
        """第一次就成功不需重試。"""
        result = retry_with_backoff(
            lambda: "ok",
            backoff=ExponentialBackoff(initial_wait=0.01),
        )
        assert result == "ok"

    def test_success_after_retries(self) -> None:
        """失敗後成功應回傳結果。"""
        call_count = [0]

        def flaky() -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("fail")
            return "ok"

        fast_backoff = ExponentialBackoff(
            initial_wait=0.01,
            max_wait_seconds=0.05,
            max_retries=3,
        )
        result = retry_with_backoff(flaky, backoff=fast_backoff)
        assert result == "ok"
        assert call_count[0] == 3

    def test_all_retries_exhausted(self) -> None:
        """所有重試耗盡後應拋出 RateLimitError。"""
        def always_fail() -> None:
            raise RuntimeError("always fails")

        fast_backoff = ExponentialBackoff(
            initial_wait=0.01,
            max_wait_seconds=0.05,
            max_retries=3,
        )
        with pytest.raises(RateLimitError, match="重試 3 次後仍然失敗"):
            retry_with_backoff(always_fail, backoff=fast_backoff)

    def test_on_retry_callback(self) -> None:
        """on_retry 回呼應在每次重試時被呼叫。"""
        retries: list = []

        def on_retry(attempt: int, wait: float, exc: Exception) -> None:
            retries.append((attempt, wait))

        call_count = [0]

        def flaky() -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("fail")
            return "ok"

        fast_backoff = ExponentialBackoff(
            initial_wait=0.01,
            multiplier=2.0,
            max_wait_seconds=1.0,
            max_retries=3,
        )
        retry_with_backoff(flaky, backoff=fast_backoff, on_retry=on_retry)
        assert len(retries) == 2
        assert retries[0][0] == 0  # first retry attempt=0
        assert retries[1][0] == 1  # second retry attempt=1
