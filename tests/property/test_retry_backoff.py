"""指數退避重試間隔正確性屬性測試。

Feature: stock-valuation-optimization, Property 18: Exponential backoff retry interval correctness

使用 Hypothesis 驗證指數退避策略的不變式：
- 對任意第 N 次重試（N = 0, 1, 2），等待時間 = min(initial_wait * multiplier^N, max_wait_seconds)
- 重試次數不超過 max_retries（預設 3）

**Validates: Requirements 7.4**
"""

from typing import List

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.infra.resilience.rate_limiter import ExponentialBackoff


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 產生合理的 initial_wait（0.1 ~ 10.0 秒）
initial_wait_st = st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)

# 產生合理的 multiplier（1.1 ~ 5.0）
multiplier_st = st.floats(min_value=1.1, max_value=5.0, allow_nan=False, allow_infinity=False)

# 產生合理的 max_wait_seconds（1.0 ~ 120.0 秒）
max_wait_st = st.floats(min_value=1.0, max_value=120.0, allow_nan=False, allow_infinity=False)

# 產生合理的 max_retries（1 ~ 10）
max_retries_st = st.integers(min_value=1, max_value=10)

# 產生隨機 ExponentialBackoff 配置
backoff_config_st = st.builds(
    ExponentialBackoff,
    initial_wait=initial_wait_st,
    multiplier=multiplier_st,
    max_wait_seconds=max_wait_st,
    max_retries=max_retries_st,
)

# attempt index（0-indexed）
attempt_st = st.integers(min_value=0, max_value=9)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestExponentialBackoffProperties:
    """Property 18: Exponential backoff retry interval correctness."""

    @given(config=backoff_config_st, attempt=attempt_st)
    @settings(max_examples=200, deadline=30000)
    def test_wait_time_formula(self, config: ExponentialBackoff, attempt: int) -> None:
        """等待時間遵循公式 min(initial_wait * multiplier^N, max_wait_seconds)。

        對任意有效的 ExponentialBackoff 配置與任意 attempt N，
        get_wait_time(N) 必須等於 min(initial_wait * multiplier^N, max_wait_seconds)。

        **Validates: Requirements 7.4**
        """
        assume(attempt < config.max_retries)

        actual = config.get_wait_time(attempt)
        expected = min(
            config.initial_wait * (config.multiplier ** attempt),
            config.max_wait_seconds,
        )

        assert abs(actual - expected) < 1e-9, (
            f"attempt={attempt}, expected={expected}, actual={actual}"
        )

    @given(config=backoff_config_st)
    @settings(max_examples=200, deadline=30000)
    def test_wait_time_never_exceeds_max(self, config: ExponentialBackoff) -> None:
        """任何重試的等待時間不超過 max_wait_seconds。

        對任意 ExponentialBackoff 配置，所有 attempt 的等待時間
        都不得超過 max_wait_seconds。

        **Validates: Requirements 7.4**
        """
        for attempt in range(config.max_retries):
            wait = config.get_wait_time(attempt)
            assert wait <= config.max_wait_seconds + 1e-9, (
                f"attempt={attempt}, wait={wait}, max={config.max_wait_seconds}"
            )

    @given(config=backoff_config_st)
    @settings(max_examples=200, deadline=30000)
    def test_wait_time_non_decreasing(self, config: ExponentialBackoff) -> None:
        """等待時間為非遞減序列（因 multiplier >= 1）。

        由於 multiplier >= 1.1，每次重試的等待時間不會低於前一次
        （在未達上限前嚴格遞增，達上限後持平）。

        **Validates: Requirements 7.4**
        """
        wait_times = config.get_all_wait_times()
        for i in range(1, len(wait_times)):
            assert wait_times[i] >= wait_times[i - 1] - 1e-9, (
                f"等待時間非遞減違規: wait_times[{i-1}]={wait_times[i-1]}, "
                f"wait_times[{i}]={wait_times[i]}"
            )

    @given(config=backoff_config_st)
    @settings(max_examples=200, deadline=30000)
    def test_max_retries_bounds_wait_list(self, config: ExponentialBackoff) -> None:
        """get_all_wait_times 回傳長度恰好等於 max_retries。

        重試次數不超過配置的 max_retries。

        **Validates: Requirements 7.4**
        """
        wait_times = config.get_all_wait_times()
        assert len(wait_times) == config.max_retries

    @given(config=backoff_config_st)
    @settings(max_examples=200, deadline=30000)
    def test_first_wait_equals_initial_wait_or_capped(
        self, config: ExponentialBackoff
    ) -> None:
        """第一次重試（attempt=0）等待時間 = min(initial_wait, max_wait_seconds)。

        因為 multiplier^0 = 1，第一次等待就是 initial_wait 本身，
        若 initial_wait > max_wait_seconds 則被截斷。

        **Validates: Requirements 7.4**
        """
        first_wait = config.get_wait_time(0)
        expected = min(config.initial_wait, config.max_wait_seconds)
        assert abs(first_wait - expected) < 1e-9, (
            f"first_wait={first_wait}, expected={expected}"
        )

    @given(config=backoff_config_st)
    @settings(max_examples=200, deadline=30000)
    def test_wait_time_always_positive(self, config: ExponentialBackoff) -> None:
        """所有等待時間為正數。

        由於 initial_wait > 0 且 multiplier > 1，所有等待時間必定 > 0。

        **Validates: Requirements 7.4**
        """
        for attempt in range(config.max_retries):
            wait = config.get_wait_time(attempt)
            assert wait > 0, f"attempt={attempt}, wait={wait}"

    @given(attempt=st.integers(min_value=-10, max_value=-1))
    @settings(max_examples=200, deadline=30000)
    def test_negative_attempt_raises_error(self, attempt: int) -> None:
        """負數 attempt 應拋出 ValueError。

        **Validates: Requirements 7.4**
        """
        backoff = ExponentialBackoff()
        with pytest.raises(ValueError):
            backoff.get_wait_time(attempt)

    @settings(max_examples=200, deadline=30000)
    @given(data=st.data())
    def test_default_config_produces_expected_sequence(self, data: st.DataObject) -> None:
        """預設配置（initial=1, multiplier=2, max=60, retries=3）產生 1, 2, 4 序列。

        驗證需求 7.4 明確的 1s -> 2s -> 4s 重試序列。

        **Validates: Requirements 7.4**
        """
        backoff = ExponentialBackoff(
            initial_wait=1.0,
            multiplier=2.0,
            max_wait_seconds=60.0,
            max_retries=3,
        )

        expected_times = [1.0, 2.0, 4.0]
        actual_times = backoff.get_all_wait_times()

        assert len(actual_times) == 3
        for i, (actual, expected) in enumerate(zip(actual_times, expected_times)):
            assert abs(actual - expected) < 1e-9, (
                f"attempt={i}, actual={actual}, expected={expected}"
            )
