"""Circuit Breaker 生命週期整合測試。

驗證 CircuitBreaker 從 closed -> open -> half_open -> closed 的完整生命週期，
以及與 BaseDataSource 的整合行為。

使用 REAL CircuitBreaker 實例搭配可注入的 time_func，
無需真正等待 300 秒即可模擬時間推移。

Validates: Requirements 19.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.core.errors import CircuitOpenError, DataSourceError
from app.infra.resilience.circuit_breaker import CircuitBreaker
from app.infra.sources.base import BaseDataSource


# ---------------------------------------------------------------------------
# 測試用可控時間函式
# ---------------------------------------------------------------------------


class FakeClock:
    """可手動推進的假時鐘，用於控制 CircuitBreaker 的時間判斷。

    Attributes:
        _current: 目前的模擬時間戳記（秒）。
    """

    def __init__(self, start: float = 1000.0) -> None:
        self._current = start

    def __call__(self) -> float:
        return self._current

    def advance(self, seconds: float) -> None:
        """推進時鐘。

        Args:
            seconds: 要推進的秒數。
        """
        self._current += seconds


# ---------------------------------------------------------------------------
# 測試用 BaseDataSource 子類別
# ---------------------------------------------------------------------------


class StubDataSource(BaseDataSource):
    """可控制成功/失敗行為的測試用資料來源。

    透過 should_fail 旗標控制底層呼叫是否拋出例外。

    Attributes:
        should_fail: 設為 True 時，所有 _fetch 方法都會拋出例外。
        call_count: 記錄 _fetch 方法被呼叫的總次數。
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        should_fail: bool = False,
    ) -> None:
        super().__init__(circuit_breaker=circuit_breaker, default_timeout=10.0)
        self.should_fail = should_fail
        self.call_count = 0

    @property
    def source_name(self) -> str:
        return "stub_source"

    def _fetch_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("stub: simulated API failure")
        return pd.DataFrame(
            {
                "date": [start_date],
                "close_price": [100.0],
                "volume": [1000],
            }
        )

    def _fetch_financial_data(
        self,
        stock_code: str,
        years: int,
    ) -> Optional[pd.DataFrame]:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("stub: simulated API failure")
        return pd.DataFrame({"eps": [5.0], "revenue": [100.0]})

    def _fetch_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("stub: simulated API failure")
        return {"stock_code": stock_code, "stock_name": "Test Stock"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_clock() -> FakeClock:
    """建立一個起始於 1000.0 秒的假時鐘。"""
    return FakeClock(start=1000.0)


@pytest.fixture
def circuit_breaker(fake_clock: FakeClock) -> CircuitBreaker:
    """建立使用假時鐘的 CircuitBreaker 實例。"""
    return CircuitBreaker(
        source_name="test_source",
        failure_threshold=5,
        window_seconds=60.0,
        recovery_timeout=300.0,
        time_func=fake_clock,
    )


@pytest.fixture
def stub_source(circuit_breaker: CircuitBreaker) -> StubDataSource:
    """建立搭配 CircuitBreaker 的測試資料來源。"""
    return StubDataSource(circuit_breaker=circuit_breaker, should_fail=False)


# ===========================================================================
# Scenario 1: Closed -> Open
# ===========================================================================


class TestClosedToOpen:
    """驗證 closed 狀態在 60 秒內累積 5 次失敗後轉為 open。"""

    def test_stays_closed_with_fewer_than_threshold_failures(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """4 次失敗不應觸發 open。"""
        for _ in range(4):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "closed"
        assert circuit_breaker.allow_request() is True

    def test_transitions_to_open_at_threshold(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """60 秒內達到 5 次失敗後應轉為 open。"""
        for i in range(5):
            fake_clock.advance(10.0)  # 每次間隔 10 秒，共 50 秒，在 60 秒視窗內
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"
        assert circuit_breaker.allow_request() is False

    def test_failures_outside_window_do_not_count(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """超過 60 秒視窗的失敗不應計入。"""
        # 記錄 3 次失敗
        for _ in range(3):
            circuit_breaker.record_failure()
            fake_clock.advance(5.0)

        # 推進超過視窗
        fake_clock.advance(61.0)

        # 再記錄 3 次失敗（總計在視窗內只有 3 次）
        for _ in range(3):
            circuit_breaker.record_failure()
            fake_clock.advance(5.0)

        assert circuit_breaker.state == "closed"

    def test_open_state_rejects_all_requests(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """open 狀態下多次呼叫 allow_request 都應回傳 False。"""
        for _ in range(5):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"

        for _ in range(10):
            assert circuit_breaker.allow_request() is False


# ===========================================================================
# Scenario 2: Open -> Half-Open
# ===========================================================================


class TestOpenToHalfOpen:
    """驗證 open 狀態在經過 recovery_timeout (300s) 後轉為 half_open。"""

    def test_stays_open_before_recovery_timeout(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """未達 300 秒仍維持 open。"""
        for _ in range(5):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"

        fake_clock.advance(299.0)
        assert circuit_breaker.state == "open"
        assert circuit_breaker.allow_request() is False

    def test_transitions_to_half_open_after_recovery_timeout(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """經過 300 秒後應轉為 half_open。"""
        for _ in range(5):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"

        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"

    def test_half_open_allows_one_probe_request(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """half_open 狀態僅允許一次探測性請求。"""
        for _ in range(5):
            circuit_breaker.record_failure()

        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"

        # 第一次允許
        assert circuit_breaker.allow_request() is True
        # 後續拒絕
        assert circuit_breaker.allow_request() is False
        assert circuit_breaker.allow_request() is False


# ===========================================================================
# Scenario 3: Half-Open -> Closed (success)
# ===========================================================================


class TestHalfOpenToClosed:
    """驗證 half_open 狀態下探測成功後恢復為 closed。"""

    def test_success_in_half_open_resets_to_closed(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """half_open 探測成功 -> closed。"""
        # 進入 open
        for _ in range(5):
            circuit_breaker.record_failure()

        # 推進到 half_open
        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"

        # 探測性請求
        assert circuit_breaker.allow_request() is True
        circuit_breaker.record_success()

        assert circuit_breaker.state == "closed"

    def test_closed_after_recovery_allows_all_requests(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """恢復 closed 後所有請求都應被允許。"""
        # 走完 closed -> open -> half_open -> closed 流程
        for _ in range(5):
            circuit_breaker.record_failure()

        fake_clock.advance(300.0)
        circuit_breaker.allow_request()  # 消耗探測配額
        circuit_breaker.record_success()

        assert circuit_breaker.state == "closed"

        # 驗證恢復後可正常請求
        for _ in range(20):
            assert circuit_breaker.allow_request() is True

    def test_failure_counter_resets_after_recovery(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """恢復 closed 後失敗計數器應被重置。"""
        # 走完一輪恢復
        for _ in range(5):
            circuit_breaker.record_failure()

        fake_clock.advance(300.0)
        circuit_breaker.allow_request()
        circuit_breaker.record_success()

        assert circuit_breaker.state == "closed"

        # 記錄 4 次失敗不應觸發 open（計數器已重置）
        for _ in range(4):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "closed"


# ===========================================================================
# Scenario 4: Half-Open -> Open (failure)
# ===========================================================================


class TestHalfOpenToOpen:
    """驗證 half_open 狀態下探測失敗後回到 open。"""

    def test_failure_in_half_open_returns_to_open(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """half_open 探測失敗 -> open。"""
        # 進入 open
        for _ in range(5):
            circuit_breaker.record_failure()

        # 推進到 half_open
        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"

        # 探測性請求失敗
        circuit_breaker.allow_request()
        circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"
        assert circuit_breaker.allow_request() is False

    def test_open_after_failed_probe_requires_another_timeout(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """探測失敗後回到 open，需要再等 300 秒才能再次 half_open。"""
        # 第一輪：closed -> open -> half_open -> (fail) -> open
        for _ in range(5):
            circuit_breaker.record_failure()

        fake_clock.advance(300.0)
        circuit_breaker.allow_request()
        circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"

        # 只推進 200 秒，不夠
        fake_clock.advance(200.0)
        assert circuit_breaker.state == "open"

        # 再推進 100 秒，總計 300 秒
        fake_clock.advance(100.0)
        assert circuit_breaker.state == "half_open"

    def test_multiple_open_half_open_cycles(
        self,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """多次 open -> half_open -> open 循環後最終恢復。"""
        # 第一輪：觸發 open
        for _ in range(5):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"

        # 第一次探測失敗
        fake_clock.advance(300.0)
        circuit_breaker.allow_request()
        circuit_breaker.record_failure()
        assert circuit_breaker.state == "open"

        # 第二次探測失敗
        fake_clock.advance(300.0)
        circuit_breaker.allow_request()
        circuit_breaker.record_failure()
        assert circuit_breaker.state == "open"

        # 第三次探測成功
        fake_clock.advance(300.0)
        circuit_breaker.allow_request()
        circuit_breaker.record_success()
        assert circuit_breaker.state == "closed"


# ===========================================================================
# Scenario 5: Integration with BaseDataSource
# ===========================================================================


class TestBaseDataSourceIntegration:
    """驗證 BaseDataSource 與 CircuitBreaker 的整合行為。"""

    def test_source_available_when_closed(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """closed 狀態下 source 應可用。"""
        assert stub_source.is_available is True
        assert stub_source.is_ready() is True

    def test_source_returns_data_on_success(
        self,
        stub_source: StubDataSource,
    ) -> None:
        """正常情況下 source 應回傳資料。"""
        result = stub_source.get_stock_price(
            stock_code="2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result is not None
        assert isinstance(result, pd.DataFrame)
        assert stub_source.call_count == 1

    def test_failures_trigger_circuit_breaker_open(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """連續失敗應觸發斷路器開啟，後續請求直接被攔截。"""
        stub_source.should_fail = True

        # 前 5 次失敗觸發 open（每次呼叫都會被包裝為 DataSourceError）
        for _ in range(5):
            with pytest.raises(DataSourceError):
                stub_source.get_stock_price(
                    stock_code="2330",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 1, 31),
                )

        assert circuit_breaker.state == "open"
        assert stub_source.is_available is False

        # 第 6 次應直接被斷路器攔截，不呼叫底層 API
        call_count_before = stub_source.call_count
        with pytest.raises(CircuitOpenError):
            stub_source.get_stock_price(
                stock_code="2330",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 31),
            )

        # 確認底層 API 未被呼叫
        assert stub_source.call_count == call_count_before

    def test_source_recovers_after_timeout(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """斷路器 open 經過 recovery_timeout 後 source 應恢復。"""
        stub_source.should_fail = True

        # 觸發 open
        for _ in range(5):
            with pytest.raises(DataSourceError):
                stub_source.get_stock_price(
                    stock_code="2330",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 1, 31),
                )

        assert circuit_breaker.state == "open"

        # 推進時間，進入 half_open
        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"
        assert stub_source.is_available is True

        # 恢復正常
        stub_source.should_fail = False

        result = stub_source.get_stock_price(
            stock_code="2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result is not None
        assert circuit_breaker.state == "closed"

    def test_source_returns_to_open_on_probe_failure(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """half_open 探測失敗後 source 應再次不可用。"""
        stub_source.should_fail = True

        # 觸發 open
        for _ in range(5):
            with pytest.raises(DataSourceError):
                stub_source.get_stock_price(
                    stock_code="2330",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 1, 31),
                )

        # 推進到 half_open，但保持失敗
        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"

        # 探測失敗
        with pytest.raises(DataSourceError):
            stub_source.get_stock_price(
                stock_code="2330",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 31),
            )

        assert circuit_breaker.state == "open"
        assert stub_source.is_available is False

    def test_full_lifecycle_with_data_source(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """完整生命週期：成功 -> 失敗(open) -> 等待(half_open) -> 恢復(closed)。"""
        # Phase 1: 正常運作
        stub_source.should_fail = False
        result = stub_source.get_stock_price(
            stock_code="2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result is not None
        assert circuit_breaker.state == "closed"

        # Phase 2: 連續失敗觸發 open
        stub_source.should_fail = True
        for _ in range(5):
            with pytest.raises(DataSourceError):
                stub_source.get_stock_price(
                    stock_code="2330",
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 1, 31),
                )

        assert circuit_breaker.state == "open"
        assert stub_source.is_available is False

        # Phase 3: open 期間請求被攔截
        with pytest.raises(CircuitOpenError):
            stub_source.get_stock_price(
                stock_code="2330",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 31),
            )

        # Phase 4: 推進時間，進入 half_open
        fake_clock.advance(300.0)
        assert circuit_breaker.state == "half_open"
        assert stub_source.is_available is True

        # Phase 5: 恢復正常，探測成功
        stub_source.should_fail = False
        result = stub_source.get_stock_price(
            stock_code="2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result is not None
        assert circuit_breaker.state == "closed"
        assert stub_source.is_available is True

    def test_different_operations_share_circuit_breaker(
        self,
        stub_source: StubDataSource,
        circuit_breaker: CircuitBreaker,
        fake_clock: FakeClock,
    ) -> None:
        """不同操作（stock_price、financial_data、stock_info）共用同一斷路器。"""
        stub_source.should_fail = True

        # 混合呼叫不同操作
        with pytest.raises(DataSourceError):
            stub_source.get_stock_price(
                "2330", datetime(2024, 1, 1), datetime(2024, 1, 31)
            )
        with pytest.raises(DataSourceError):
            stub_source.get_financial_data("2330", years=3)
        with pytest.raises(DataSourceError):
            stub_source.get_stock_info("2330")
        with pytest.raises(DataSourceError):
            stub_source.get_stock_price(
                "2317", datetime(2024, 1, 1), datetime(2024, 1, 31)
            )
        with pytest.raises(DataSourceError):
            stub_source.get_financial_data("2317", years=5)

        # 5 次失敗（跨操作類型）應觸發 open
        assert circuit_breaker.state == "open"

    def test_independent_circuit_breakers_for_different_sources(
        self,
        fake_clock: FakeClock,
    ) -> None:
        """不同資料來源使用獨立的斷路器，互不影響。"""
        cb_a = CircuitBreaker(
            source_name="source_a",
            failure_threshold=5,
            window_seconds=60.0,
            recovery_timeout=300.0,
            time_func=fake_clock,
        )
        cb_b = CircuitBreaker(
            source_name="source_b",
            failure_threshold=5,
            window_seconds=60.0,
            recovery_timeout=300.0,
            time_func=fake_clock,
        )

        source_a = StubDataSource(circuit_breaker=cb_a, should_fail=True)
        source_b = StubDataSource(circuit_breaker=cb_b, should_fail=False)

        # source_a 連續失敗
        for _ in range(5):
            with pytest.raises(DataSourceError):
                source_a.get_stock_price(
                    "2330", datetime(2024, 1, 1), datetime(2024, 1, 31)
                )

        # source_a 斷路器開啟
        assert cb_a.state == "open"
        assert source_a.is_available is False

        # source_b 不受影響
        assert cb_b.state == "closed"
        assert source_b.is_available is True
        result = source_b.get_stock_price(
            "2330", datetime(2024, 1, 1), datetime(2024, 1, 31)
        )
        assert result is not None
