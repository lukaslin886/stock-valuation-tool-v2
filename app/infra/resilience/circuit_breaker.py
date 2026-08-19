"""斷路器模式實作模組。

實作 Circuit Breaker 狀態機，保護系統免受外部服務連續失敗的影響。
每個外部資料來源（Yahoo Finance、FinMind、FinLab）各自維護獨立的斷路器實例。

狀態轉換：
    - CLOSED -> OPEN: 60 秒滑動視窗內失敗達 5 次
    - OPEN -> HALF_OPEN: 開啟超過 5 分鐘（300 秒）後
    - HALF_OPEN -> CLOSED: 探測性請求成功
    - HALF_OPEN -> OPEN: 探測性請求失敗

Usage::

    from app.infra.resilience.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(source_name="yahoo_finance")

    if cb.allow_request():
        try:
            result = call_external_api()
            cb.record_success()
        except Exception:
            cb.record_failure()
    else:
        # 斷路器開啟，使用備援來源
        ...
"""

import threading
import time
from collections import deque
from typing import Callable, Deque

from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 狀態常數
# ---------------------------------------------------------------------------

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    """斷路器實作。

    使用滑動時間視窗（deque + timestamp）追蹤失敗次數，
    當失敗達閾值時自動開啟斷路器，保護系統不重複呼叫已知故障的服務。

    本實作為執行緒安全（透過 threading.Lock）。

    Attributes:
        source_name: 對應的外部資料來源名稱。
        failure_threshold: 觸發 open 狀態的失敗次數閾值。
        window_seconds: 滑動視窗時間長度（秒）。
        recovery_timeout: open 狀態恢復至 half_open 的等待時間（秒）。

    Example::

        cb = CircuitBreaker(
            source_name="finmind",
            failure_threshold=5,
            window_seconds=60.0,
            recovery_timeout=300.0,
        )
    """

    def __init__(
        self,
        source_name: str,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        recovery_timeout: float = 300.0,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化斷路器。

        Args:
            source_name: 外部資料來源名稱（如 "yahoo_finance"、"finmind"、"finlab"）。
            failure_threshold: 滑動視窗內觸發 open 的失敗次數閾值，預設 5。
            window_seconds: 滑動視窗長度（秒），預設 60.0。
            recovery_timeout: open 轉 half_open 的冷卻時間（秒），預設 300.0。
            time_func: 時間取得函式，預設為 time.time。可注入自訂函式以利測試。
        """
        self.source_name = source_name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self._time_func = time_func

        self._state: str = STATE_CLOSED
        self._failures: Deque[float] = deque()
        self._opened_at: float = 0.0
        self._half_open_probe_sent: bool = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """目前斷路器狀態。

        若處於 open 狀態且已超過 recovery_timeout，
        會自動轉換為 half_open 狀態。

        Returns:
            狀態字串："closed"、"open" 或 "half_open"。
        """
        with self._lock:
            self._check_recovery()
            return self._state

    def allow_request(self) -> bool:
        """判斷目前是否允許發送請求。

        根據斷路器狀態決定：
        - closed: 允許所有請求
        - open: 檢查是否已過冷卻期，若是則轉為 half_open 並允許一次探測
        - half_open: 僅允許一次探測性請求（後續請求拒絕直到狀態改變）

        Returns:
            True 表示允許發送請求，False 表示應跳過該來源。
        """
        with self._lock:
            self._check_recovery()

            if self._state == STATE_CLOSED:
                return True

            if self._state == STATE_HALF_OPEN:
                if not self._half_open_probe_sent:
                    self._half_open_probe_sent = True
                    logger.info(
                        "[OK] CircuitBreaker [%s] half_open: 允許探測性請求",
                        self.source_name,
                    )
                    return True
                return False

            # STATE_OPEN
            return False

    def record_success(self) -> None:
        """記錄一次成功的請求。

        狀態行為：
        - half_open: 探測成功，重置為 closed 狀態
        - closed: 無特殊動作（失敗記錄仍由時間視窗自然過期）
        - open: 無動作（正常情況下 open 不會有請求到達）
        """
        with self._lock:
            if self._state == STATE_HALF_OPEN:
                self._transition_to_closed()
                logger.info(
                    "[OK] CircuitBreaker [%s] half_open -> closed: 探測成功，恢復服務",
                    self.source_name,
                )

    def record_failure(self) -> None:
        """記錄一次失敗的請求。

        狀態行為：
        - closed: 將失敗時間戳記加入滑動視窗，剔除過期記錄，檢查是否達閾值
        - half_open: 探測失敗，立即回到 open 狀態
        - open: 無動作（正常情況下 open 不會有請求到達）
        """
        with self._lock:
            now = self._time_func()

            if self._state == STATE_CLOSED:
                self._failures.append(now)
                self._prune_old_failures(now)

                if len(self._failures) >= self.failure_threshold:
                    self._transition_to_open(now)
                    logger.warning(
                        "[FAIL] CircuitBreaker [%s] closed -> open: "
                        "%d 次失敗在 %.0f 秒內達閾值",
                        self.source_name,
                        len(self._failures),
                        self.window_seconds,
                    )

            elif self._state == STATE_HALF_OPEN:
                self._transition_to_open(now)
                logger.warning(
                    "[FAIL] CircuitBreaker [%s] half_open -> open: 探測失敗",
                    self.source_name,
                )

    def reset(self) -> None:
        """重置斷路器至初始關閉狀態。

        清除所有失敗記錄與計時器，恢復為 closed 狀態。
        用於手動恢復或測試場景。
        """
        with self._lock:
            self._transition_to_closed()
            logger.info(
                "[OK] CircuitBreaker [%s] 手動重置為 closed",
                self.source_name,
            )

    # ------------------------------------------------------------------
    # 內部方法（須在持有 _lock 的情況下呼叫）
    # ------------------------------------------------------------------

    def _check_recovery(self) -> None:
        """檢查 open 狀態是否已超過冷卻期，若是則轉為 half_open。

        此方法須在持有 _lock 的情況下呼叫。
        """
        if self._state == STATE_OPEN:
            elapsed = self._time_func() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = STATE_HALF_OPEN
                self._half_open_probe_sent = False
                logger.info(
                    "[OK] CircuitBreaker [%s] open -> half_open: "
                    "冷卻 %.0f 秒已過，允許探測",
                    self.source_name,
                    elapsed,
                )

    def _prune_old_failures(self, now: float) -> None:
        """剔除滑動視窗外的過期失敗記錄。

        Args:
            now: 目前時間戳記。
        """
        cutoff = now - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _transition_to_open(self, now: float) -> None:
        """轉換至 open 狀態。

        Args:
            now: 狀態轉換發生的時間戳記。
        """
        self._state = STATE_OPEN
        self._opened_at = now
        self._half_open_probe_sent = False

    def _transition_to_closed(self) -> None:
        """轉換至 closed 狀態，重置所有計數器。"""
        self._state = STATE_CLOSED
        self._failures.clear()
        self._opened_at = 0.0
        self._half_open_probe_sent = False
