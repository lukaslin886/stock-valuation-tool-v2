"""速率限制器模組。

提供 Token Bucket 演算法實作的速率限制器，以及 FinMind 專用的配額預檢邏輯。
支援指數退避重試策略。

核心元件：
    - RateLimiter: 通用 Token Bucket 速率限制器（執行緒安全）
    - ExponentialBackoff: 指數退避重試策略
    - FinMindRateLimiter: FinMind 專用速率限制器（含配額預檢與 HTTP 402 處理）
    - QuotaStatus: 配額狀態資料結構

Usage::

    from app.infra.resilience.rate_limiter import (
        RateLimiter,
        ExponentialBackoff,
        FinMindRateLimiter,
    )

    # 通用速率限制
    limiter = RateLimiter(max_tokens=10, refill_rate=1.0)
    if limiter.acquire():
        # 執行請求
        ...

    # 指數退避
    backoff = ExponentialBackoff()
    for attempt in range(backoff.max_retries):
        wait = backoff.get_wait_time(attempt)
        ...

    # FinMind 專用
    fm_limiter = FinMindRateLimiter(
        quota_checker=my_quota_func,
        circuit_breaker=my_cb,
    )
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from app.core.errors import RateLimitError
from app.core.protocols import CircuitBreakerProtocol
from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# QuotaStatus 資料結構
# ---------------------------------------------------------------------------


@dataclass
class QuotaStatus:
    """FinMind 配額狀態。

    表示目前 FinMind API 帳戶的配額使用狀況，供 FinMindRateLimiter
    決定是否需要降速或切換備援來源。

    Attributes:
        remaining: 剩餘可用請求配額數量。
        sufficient: 配額是否足以完成本次批次請求。
        throttled: 是否已進入降速模式（剩餘配額 < 120% 預計請求量）。
        quota_exhausted: 配額是否已完全耗盡（HTTP 402）。
        error_message: 錯誤訊息（如有）。
    """

    remaining: int = 0
    sufficient: bool = True
    throttled: bool = False
    quota_exhausted: bool = False
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# ExponentialBackoff
# ---------------------------------------------------------------------------


@dataclass
class ExponentialBackoff:
    """指數退避重試策略。

    計算每次重試的等待時間，遵循 2 的次方遞增：
    1s -> 2s -> 4s -> 8s -> ...（上限 max_wait_seconds）。

    Attributes:
        initial_wait: 第一次重試的等待秒數，預設 1.0。
        multiplier: 每次重試的倍數，預設 2.0。
        max_wait_seconds: 單次等待的上限秒數，預設 60.0。
        max_retries: 最大重試次數，預設 3。
    """

    initial_wait: float = 1.0
    multiplier: float = 2.0
    max_wait_seconds: float = 60.0
    max_retries: int = 3

    def get_wait_time(self, attempt: int) -> float:
        """計算第 N 次重試的等待時間。

        等待時間公式：min(initial_wait * multiplier^(attempt), max_wait_seconds)
        attempt 從 0 開始計數（第 1 次重試 attempt=0）。

        Args:
            attempt: 重試次數（0-indexed）。第 1 次重試傳入 0，
                     第 2 次重試傳入 1，以此類推。

        Returns:
            該次重試應等待的秒數。

        Raises:
            ValueError: 若 attempt 為負數。
        """
        if attempt < 0:
            raise ValueError(f"attempt 不得為負數，收到: {attempt}")
        raw_wait = self.initial_wait * (self.multiplier ** attempt)
        return min(raw_wait, self.max_wait_seconds)

    def get_all_wait_times(self) -> List[float]:
        """取得所有重試的等待時間清單。

        Returns:
            長度為 max_retries 的等待時間清單。
        """
        return [self.get_wait_time(i) for i in range(self.max_retries)]


# ---------------------------------------------------------------------------
# RateLimiter（Token Bucket）
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token Bucket 速率限制器。

    使用 Token Bucket 演算法控制請求頻率，支援連續性 token 補充
    （fractional tokens）。執行緒安全（透過 threading.Lock）。

    Token 自動以 refill_rate 的速度補充，最大不超過 max_tokens。
    呼叫 acquire() 消耗 token，token 不足時回傳 False。
    呼叫 wait_and_acquire() 會阻塞等待直到 token 足夠。

    Attributes:
        max_tokens: Token 桶的最大容量。
        refill_rate: 每秒補充的 token 數量。

    Example::

        limiter = RateLimiter(max_tokens=10, refill_rate=2.0)
        if limiter.acquire(tokens=1):
            # 取得 token，執行請求
            response = call_api()
        else:
            # token 不足，稍後重試
            ...
    """

    def __init__(
        self,
        max_tokens: int = 10,
        refill_rate: float = 1.0,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化 Token Bucket 速率限制器。

        Args:
            max_tokens: Token 桶的最大容量（正整數）。
            refill_rate: 每秒補充的 token 數量（正浮點數）。
            time_func: 時間函式，預設為 time.time。
                      可注入自訂函式以利測試。
        """
        if max_tokens <= 0:
            raise ValueError(f"max_tokens 必須為正整數，收到: {max_tokens}")
        if refill_rate <= 0:
            raise ValueError(f"refill_rate 必須為正數，收到: {refill_rate}")

        self.max_tokens: int = max_tokens
        self.refill_rate: float = refill_rate
        self._time_func: Callable[[], float] = time_func
        self._tokens: float = float(max_tokens)
        self._last_refill_time: float = time_func()
        self._lock: threading.Lock = threading.Lock()

    @property
    def available_tokens(self) -> float:
        """目前可用的 token 數量（含未結算的補充）。

        Returns:
            目前可用 token 數（浮點數，不超過 max_tokens）。
        """
        with self._lock:
            self._refill()
            return self._tokens

    def _refill(self) -> None:
        """補充 token（內部方法，需在持有鎖時呼叫）。

        根據自上次補充以來經過的時間，計算應補充的 token 數量。
        Token 數量不會超過 max_tokens。
        """
        now = self._time_func()
        elapsed = now - self._last_refill_time
        if elapsed > 0:
            new_tokens = elapsed * self.refill_rate
            self._tokens = min(self._tokens + new_tokens, float(self.max_tokens))
            self._last_refill_time = now

    def acquire(self, tokens: int = 1) -> bool:
        """嘗試取得指定數量的 token。

        非阻塞式操作。若目前可用 token 足夠則消耗並回傳 True，
        否則回傳 False 且不消耗任何 token。

        Args:
            tokens: 欲消耗的 token 數量，預設為 1。必須為正整數。

        Returns:
            True 表示成功取得 token，False 表示 token 不足。

        Raises:
            ValueError: 若 tokens 不為正整數。
        """
        if tokens <= 0:
            raise ValueError(f"tokens 必須為正整數，收到: {tokens}")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_and_acquire(self, tokens: int = 1) -> None:
        """等待直到 token 可用並消耗（同步阻塞版本）。

        以 sleep-based 方式等待，直到有足夠的 token 可消耗。
        適用於同步呼叫情境。

        Args:
            tokens: 欲消耗的 token 數量，預設為 1。必須為正整數。

        Raises:
            ValueError: 若 tokens 不為正整數或超過 max_tokens。
        """
        if tokens <= 0:
            raise ValueError(f"tokens 必須為正整數，收到: {tokens}")
        if tokens > self.max_tokens:
            raise ValueError(
                f"tokens ({tokens}) 不得超過 max_tokens ({self.max_tokens})"
            )

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                # 計算需要等待的時間
                deficit = tokens - self._tokens
                wait_time = deficit / self.refill_rate

            # 在鎖外面 sleep，避免阻塞其他執行緒
            time.sleep(wait_time)

    def set_rate(self, refill_rate: float) -> None:
        """動態調整補充速率。

        用於 FinMind 配額不足時降速。

        Args:
            refill_rate: 新的每秒補充 token 數量（正浮點數）。

        Raises:
            ValueError: 若 refill_rate 不為正數。
        """
        if refill_rate <= 0:
            raise ValueError(f"refill_rate 必須為正數，收到: {refill_rate}")
        with self._lock:
            self._refill()  # 先結算目前的 token
            self.refill_rate = refill_rate


# ---------------------------------------------------------------------------
# FinMindRateLimiter
# ---------------------------------------------------------------------------


# 型別別名：配額檢查函式簽名
# 接收預計請求數量，回傳剩餘配額數量（或 -1 表示查詢失敗）
QuotaCheckerFunc = Callable[[int], int]


class FinMindRateLimiter(RateLimiter):
    """FinMind 專用速率限制器。

    在通用 Token Bucket 基礎上擴充：
    1. 請求前呼叫 user_info 端點確認配額
    2. 配額 < 120% 預計請求量時降速至 1 req/s
    3. HTTP 402 處理：記錄事件 + 觸發 Circuit Breaker
    4. 整合指數退避重試策略

    Attributes:
        original_refill_rate: 原始補充速率（降速前的值）。
        throttle_threshold: 降速觸發閾值比例（預設 1.2 即 120%）。
        backoff: 指數退避策略實例。

    Example::

        def check_quota(estimated: int) -> int:
            # 呼叫 FinMind user_info API
            resp = requests.get("https://api.finmindtrade.com/api/v4/user_info")
            return resp.json().get("user_count", 0)

        fm_limiter = FinMindRateLimiter(
            max_tokens=10,
            refill_rate=2.0,
            quota_checker=check_quota,
            circuit_breaker=my_circuit_breaker,
        )

        status = fm_limiter.check_quota(estimated_requests=50)
        if status.sufficient and not status.quota_exhausted:
            fm_limiter.wait_and_acquire()
            # 執行 FinMind 請求
    """

    def __init__(
        self,
        max_tokens: int = 10,
        refill_rate: float = 1.0,
        time_func: Callable[[], float] = time.time,
        quota_checker: Optional[QuotaCheckerFunc] = None,
        circuit_breaker: Optional[CircuitBreakerProtocol] = None,
        throttle_threshold: float = 1.2,
        backoff: Optional[ExponentialBackoff] = None,
    ) -> None:
        """初始化 FinMind 專用速率限制器。

        Args:
            max_tokens: Token 桶最大容量。
            refill_rate: 每秒補充 token 數量。
            time_func: 時間函式（可注入以利測試）。
            quota_checker: 配額檢查函式。接收預計請求數，回傳剩餘配額。
                          若為 None 則跳過配額檢查。
            circuit_breaker: 斷路器實例，用於 HTTP 402 時觸發熔斷。
                            若為 None 則不觸發斷路器。
            throttle_threshold: 降速閾值比例。當剩餘配額 < 預計請求量
                               * throttle_threshold 時觸發降速。預設 1.2。
            backoff: 指數退避策略實例。若為 None 則使用預設配置。
        """
        super().__init__(
            max_tokens=max_tokens,
            refill_rate=refill_rate,
            time_func=time_func,
        )
        self._quota_checker: Optional[QuotaCheckerFunc] = quota_checker
        self._circuit_breaker: Optional[CircuitBreakerProtocol] = circuit_breaker
        self.original_refill_rate: float = refill_rate
        self.throttle_threshold: float = throttle_threshold
        self.backoff: ExponentialBackoff = backoff or ExponentialBackoff()
        self._throttled: bool = False
        self._http_402_events: List[float] = []

    @property
    def is_throttled(self) -> bool:
        """是否處於降速模式。

        Returns:
            True 表示目前已因配額不足而降速。
        """
        return self._throttled

    def check_quota(self, estimated_requests: int) -> QuotaStatus:
        """檢查 FinMind 配額狀態並自動調整速率。

        呼叫 quota_checker 函式確認剩餘配額，依據結果決定：
        - 配額充足：維持目前速率
        - 配額 < 120% 預計請求量：降速至 1 req/s 並記錄警告
        - 配額查詢失敗：回傳 sufficient=True（寬鬆策略，允許繼續）

        Args:
            estimated_requests: 本次批次預計發送的請求數量。

        Returns:
            QuotaStatus 資料結構，描述目前配額狀態。
        """
        if self._quota_checker is None:
            # 未設定配額檢查器，視為配額充足
            return QuotaStatus(
                remaining=999999,
                sufficient=True,
                throttled=False,
            )

        try:
            remaining = self._quota_checker(estimated_requests)
        except Exception as exc:
            # 配額查詢失敗，記錄警告但不阻塞（寬鬆策略）
            logger.warning(
                "FinMind 配額查詢失敗，採寬鬆策略繼續執行",
                extra={"source": "finmind"},
                exc_info=exc,
            )
            return QuotaStatus(
                remaining=0,
                sufficient=True,
                throttled=False,
                error_message=f"配額查詢失敗: {exc}",
            )

        if remaining < 0:
            # 負值表示查詢異常
            logger.warning(
                "FinMind 配額查詢回傳負值，採寬鬆策略繼續執行",
                extra={"source": "finmind"},
            )
            return QuotaStatus(
                remaining=0,
                sufficient=True,
                throttled=False,
                error_message="配額查詢回傳負值",
            )

        threshold = estimated_requests * self.throttle_threshold
        throttled = remaining < threshold
        sufficient = remaining >= estimated_requests

        if throttled:
            # 配額 < 120% 預計請求量：降速至 1 req/s
            self._apply_throttle()
            logger.warning(
                f"FinMind 配額接近上限 (剩餘={remaining}, "
                f"閾值={threshold:.0f})，已降速至 1 req/s",
                extra={"source": "finmind"},
            )
        elif not throttled and self._throttled:
            # 配額回復充足：恢復原始速率
            self._release_throttle()
            logger.info(
                f"FinMind 配額回復充足 (剩餘={remaining})，"
                f"恢復原始速率 {self.original_refill_rate} req/s",
                extra={"source": "finmind"},
            )

        return QuotaStatus(
            remaining=remaining,
            sufficient=sufficient,
            throttled=throttled,
        )

    def handle_http_402(self) -> QuotaStatus:
        """處理 FinMind HTTP 402 回應（配額耗盡）。

        動作序列：
        1. 記錄 HTTP 402 事件至日誌
        2. 若已設定 circuit_breaker，觸發 record_failure
        3. 回傳 quota_exhausted=True 的狀態，指示呼叫方切換備援

        Returns:
            QuotaStatus，其中 quota_exhausted=True 且 sufficient=False。
        """
        now = self._time_func()
        self._http_402_events.append(now)

        logger.error(
            "FinMind API 回傳 HTTP 402 (配額耗盡)，"
            "觸發斷路器並建議切換備援來源",
            extra={"source": "finmind"},
        )

        # 觸發 Circuit Breaker
        if self._circuit_breaker is not None:
            self._circuit_breaker.record_failure()

        return QuotaStatus(
            remaining=0,
            sufficient=False,
            throttled=True,
            quota_exhausted=True,
            error_message="HTTP 402: FinMind API 配額耗盡",
        )

    def _apply_throttle(self) -> None:
        """套用降速：將補充速率設為 1 req/s。"""
        if not self._throttled:
            self._throttled = True
            self.set_rate(1.0)

    def _release_throttle(self) -> None:
        """解除降速：恢復原始補充速率。"""
        if self._throttled:
            self._throttled = False
            self.set_rate(self.original_refill_rate)

    def reset_throttle(self) -> None:
        """手動重置降速狀態。

        恢復原始補充速率並清除降速標記。
        """
        self._release_throttle()


# ---------------------------------------------------------------------------
# 重試輔助函式
# ---------------------------------------------------------------------------


def retry_with_backoff(
    func: Callable[[], object],
    backoff: Optional[ExponentialBackoff] = None,
    on_retry: Optional[Callable[[int, float, Exception], None]] = None,
) -> object:
    """以指數退避策略執行函式，失敗時重試。

    Args:
        func: 要執行的可呼叫物件（無參數，回傳任意值）。
        backoff: 退避策略實例。若為 None 則使用預設（1s/2s/4s，最多 3 次）。
        on_retry: 重試時的回呼函式，接收 (attempt, wait_time, exception)。

    Returns:
        func 的回傳值（若最終成功）。

    Raises:
        RateLimitError: 重試次數耗盡後仍然失敗。
    """
    if backoff is None:
        backoff = ExponentialBackoff()

    last_exception: Optional[Exception] = None

    for attempt in range(backoff.max_retries + 1):
        try:
            return func()
        except Exception as exc:
            last_exception = exc
            if attempt >= backoff.max_retries:
                # 重試次數耗盡
                break

            wait_time = backoff.get_wait_time(attempt)
            logger.warning(
                f"請求失敗 (第 {attempt + 1} 次)，"
                f"等待 {wait_time:.1f}s 後重試",
                extra={"source": "retry"},
            )

            if on_retry is not None:
                on_retry(attempt, wait_time, exc)

            time.sleep(wait_time)

    raise RateLimitError(
        message=(
            f"重試 {backoff.max_retries} 次後仍然失敗: "
            f"{last_exception}"
        ),
        retry_after=backoff.get_wait_time(backoff.max_retries - 1)
        if backoff.max_retries > 0
        else None,
    )
