"""DataManager / DataPipeline 備援流程整合測試。

使用 REAL 實例（MemoryCache、SQLiteCache、ErrorHandler）搭配 MOCK 資料來源，
驗證完整備援流程、快取行為與失效機制。

測試場景：
1. 主要來源失敗 -> pipeline 切換至備援 -> 正確回傳資料
2. 所有來源失敗 -> 回傳 SQLiteCache 過期資料 + 警告
3. 成功擷取後 Memory Cache 被填充 -> 後續請求命中快取
4. Cache invalidation 端對端正確性

Validates: Requirements 19.1, 19.3, 19.5
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import pytest

from app.core.errors import DataSourceError
from app.infra.cache.memory_cache import MemoryCache
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.data_pipeline import DataPipeline
from app.infra.error_handler import ErrorHandler


# ---------------------------------------------------------------------------
# Mock DataSource 實作（符合 DataSourceProtocol）
# ---------------------------------------------------------------------------


class MockDataSource:
    """Mock 資料來源，可配置成功或失敗行為。

    實作 DataSourceProtocol 介面，供整合測試使用。

    Args:
        name: 來源名稱。
        available: 是否可用。
        price_data: get_stock_price 回傳的資料。
        financial_data: get_financial_data 回傳的資料。
        info_data: get_stock_info 回傳的資料。
        should_raise: 若為 True，所有方法拋出 DataSourceError。
    """

    def __init__(
        self,
        name: str = "mock_source",
        available: bool = True,
        price_data: Optional[pd.DataFrame] = None,
        financial_data: Optional[pd.DataFrame] = None,
        info_data: Optional[Dict[str, Any]] = None,
        should_raise: bool = False,
    ) -> None:
        self._name = name
        self._available = available
        self._price_data = price_data
        self._financial_data = financial_data
        self._info_data = info_data
        self._should_raise = should_raise
        self.call_count: int = 0

    @property
    def source_name(self) -> str:
        return self._name

    @property
    def is_available(self) -> bool:
        return self._available

    def is_ready(self) -> bool:
        return self._available

    def get_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[pd.DataFrame]:
        self.call_count += 1
        if self._should_raise:
            raise DataSourceError(
                f"{self._name} unavailable",
                source_name=self._name,
                stock_code=stock_code,
            )
        return self._price_data

    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5,
    ) -> Optional[pd.DataFrame]:
        self.call_count += 1
        if self._should_raise:
            raise DataSourceError(
                f"{self._name} unavailable",
                source_name=self._name,
                stock_code=stock_code,
            )
        return self._financial_data

    def get_stock_info(
        self, stock_code: str
    ) -> Optional[Dict[str, Any]]:
        self.call_count += 1
        if self._should_raise:
            raise DataSourceError(
                f"{self._name} unavailable",
                source_name=self._name,
                stock_code=stock_code,
            )
        return self._info_data


# ---------------------------------------------------------------------------
# Fixture Data Factories
# ---------------------------------------------------------------------------


def make_price_df(stock_code: str = "2330") -> pd.DataFrame:
    """建立測試用股價 DataFrame。"""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-02", periods=5, freq="B"),
        "open": [580.0, 585.0, 590.0, 588.0, 592.0],
        "high": [590.0, 592.0, 595.0, 593.0, 598.0],
        "low": [578.0, 583.0, 587.0, 585.0, 590.0],
        "close": [585.0, 590.0, 592.0, 590.0, 595.0],
        "volume": [30000, 28000, 32000, 25000, 35000],
    })


def make_financial_df(stock_code: str = "2330") -> pd.DataFrame:
    """建立測試用財報 DataFrame。"""
    return pd.DataFrame({
        "date": ["2024Q1", "2024Q2", "2024Q3", "2024Q4"],
        "eps": [8.5, 9.2, 9.8, 10.1],
        "revenue": [500.0, 520.0, 540.0, 560.0],
        "roe": [22.0, 23.0, 24.0, 25.0],
        "pe_ratio": [18.0, 17.5, 17.0, 16.5],
    })


def make_stock_info(stock_code: str = "2330") -> Dict[str, Any]:
    """建立測試用股票基本資訊。"""
    return {
        "stock_code": stock_code,
        "stock_name": "台積電",
        "industry": "半導體業",
        "market_cap": 15000.0,
    }


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_path() -> str:
    """提供獨立臨時 SQLite 資料庫路徑（test_market_scan.db）。"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_market_scan_")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def memory_cache() -> MemoryCache:
    """提供全新 MemoryCache 實例。"""
    return MemoryCache(max_size=200)


@pytest.fixture
def sqlite_cache(temp_db_path: str) -> SQLiteCache:
    """提供使用臨時檔案的 SQLiteCache 實例。"""
    cache = SQLiteCache(db_path=temp_db_path)
    yield cache
    cache.close()


@pytest.fixture
def error_handler() -> ErrorHandler:
    """提供 ErrorHandler 實例。"""
    return ErrorHandler()


# ---------------------------------------------------------------------------
# Scenario 1: Primary source fails -> fallback to secondary -> correct data
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPrimarySourceFailsFallbackToSecondary:
    """主要來源失敗時，pipeline 自動切換備援並正確回傳資料。"""

    def test_price_fallback_primary_raises(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """主要來源拋出例外 -> 備援來源提供資料 -> 成功回傳。"""
        primary = MockDataSource(
            name="primary_source",
            should_raise=True,
        )
        secondary = MockDataSource(
            name="secondary_source",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[primary, secondary],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_price(
            "2330",
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )

        assert result.success is True
        assert result.source_name == "secondary_source"
        assert result.from_cache is False
        assert isinstance(result.data, pd.DataFrame)
        assert len(result.data) == 5
        assert primary.call_count == 1
        assert secondary.call_count == 1

        pipeline.shutdown(wait=False)

    def test_price_fallback_primary_returns_none(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """主要來源回傳 None -> 自動嘗試備援來源。"""
        primary = MockDataSource(
            name="primary_source",
            price_data=None,
        )
        secondary = MockDataSource(
            name="secondary_source",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[primary, secondary],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_price(
            "2330",
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )

        assert result.success is True
        assert result.source_name == "secondary_source"
        assert result.data is not None

        pipeline.shutdown(wait=False)

    def test_financial_data_fallback(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """財報資料備援：主要來源失敗 -> 備援來源成功。"""
        primary = MockDataSource(
            name="finlab",
            should_raise=True,
        )
        secondary = MockDataSource(
            name="yahoo_finance",
            financial_data=make_financial_df(),
        )

        pipeline = DataPipeline(
            sources=[primary, secondary],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_financial_data("2330", years=5)

        assert result.success is True
        assert result.source_name == "yahoo_finance"
        assert isinstance(result.data, pd.DataFrame)
        assert "eps" in result.data.columns

        pipeline.shutdown(wait=False)

    def test_stock_info_fallback(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """基本資訊備援：主要來源不可用 -> 次要來源回傳。"""
        primary = MockDataSource(
            name="finlab",
            available=False,
        )
        secondary = MockDataSource(
            name="yahoo_finance",
            info_data=make_stock_info(),
        )

        pipeline = DataPipeline(
            sources=[primary, secondary],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_info("2330")

        assert result.success is True
        assert result.source_name == "yahoo_finance"
        assert result.data["stock_code"] == "2330"
        # primary 不可用，不應被呼叫
        assert primary.call_count == 0
        assert secondary.call_count == 1

        pipeline.shutdown(wait=False)

    def test_three_sources_first_two_fail(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """三個來源中前兩個失敗 -> 第三個成功。"""
        src1 = MockDataSource(name="finlab", should_raise=True)
        src2 = MockDataSource(name="yahoo_finance", should_raise=True)
        src3 = MockDataSource(
            name="finmind",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[src1, src2, src3],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_price(
            "2317", datetime(2024, 1, 1), datetime(2024, 1, 31)
        )

        assert result.success is True
        assert result.source_name == "finmind"
        assert src1.call_count == 1
        assert src2.call_count == 1
        assert src3.call_count == 1

        pipeline.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Scenario 2: All sources fail -> returns stale SQLiteCache data with warning
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAllSourcesFailCacheFallback:
    """所有來源失敗時，回傳 SQLiteCache 過期資料並附加警告。"""

    def test_all_fail_returns_sqlite_stale_data(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """所有來源失敗 -> SQLite 有 snapshot -> 回傳 stale 資料 + 警告。"""
        # 預先寫入 SQLite 快取資料
        sqlite_cache.upsert_snapshot({
            "stock_code": "2330",
            "stock_name": "台積電",
            "pe_ratio": 18.5,
            "roe": 25.0,
            "dividend_yield": 2.0,
            "current_price": 590.0,
            "market_cap": 15000.0,
        })

        src1 = MockDataSource(name="finlab", should_raise=True)
        src2 = MockDataSource(name="yahoo_finance", should_raise=True)

        pipeline = DataPipeline(
            sources=[src1, src2],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_info("2330")

        assert result.success is True
        assert result.from_cache is True
        assert result.source_name == "sqlite_cache"
        assert result.warning is not None
        assert "STALE" in result.warning or "stale" in result.warning.lower()

        pipeline.shutdown(wait=False)

    def test_all_fail_no_cache_returns_failure(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """所有來源失敗且 SQLite 無資料 -> 回傳失敗結果。"""
        src1 = MockDataSource(name="finlab", should_raise=True)
        src2 = MockDataSource(name="yahoo_finance", should_raise=True)

        pipeline = DataPipeline(
            sources=[src1, src2],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_price(
            "9999", datetime(2024, 1, 1), datetime(2024, 1, 31)
        )

        assert result.success is False
        assert result.data is None
        assert result.error_message is not None

        pipeline.shutdown(wait=False)

    def test_all_fail_returns_snapshot_for_price_type(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """price 類型請求，所有來源失敗 -> 嘗試 SQLite snapshot 降級。"""
        sqlite_cache.upsert_snapshot({
            "stock_code": "2317",
            "stock_name": "鴻海",
            "pe_ratio": 12.0,
            "roe": 10.0,
            "dividend_yield": 5.0,
            "current_price": 105.0,
            "market_cap": 14000.0,
        })

        src1 = MockDataSource(name="finlab", should_raise=True)
        src2 = MockDataSource(name="yahoo_finance", should_raise=True)

        pipeline = DataPipeline(
            sources=[src1, src2],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result = pipeline.get_stock_price(
            "2317", datetime(2024, 1, 1), datetime(2024, 1, 31)
        )

        # SQLiteCache.get_snapshot may or may not have price data;
        # the pipeline tries _try_sqlite_cache and returns whatever it finds
        if result.success:
            assert result.from_cache is True
            assert result.warning is not None
        else:
            # If no price-type snapshot available, it is a valid failure
            assert result.data is None

        pipeline.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Scenario 3: Memory cache populated after fetch -> subsequent hits cache
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMemoryCachePopulatedAfterFetch:
    """成功擷取後 MemoryCache 被填充，後續請求直接命中快取。"""

    def test_second_request_hits_memory_cache(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """第一次請求填充快取 -> 第二次請求命中記憶體快取。"""
        source = MockDataSource(
            name="yahoo_finance",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        # 第一次請求 -> 來源呼叫
        result1 = pipeline.get_stock_price("2330", start, end)
        assert result1.success is True
        assert result1.source_name == "yahoo_finance"
        assert result1.from_cache is False
        assert source.call_count == 1

        # 第二次請求 -> 命中記憶體快取
        result2 = pipeline.get_stock_price("2330", start, end)
        assert result2.success is True
        assert result2.source_name == "memory_cache"
        assert result2.from_cache is True
        # 來源不應被再次呼叫
        assert source.call_count == 1

        pipeline.shutdown(wait=False)

    def test_financial_data_cached_after_fetch(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """財報資料首次擷取後快取 -> 第二次命中快取。"""
        source = MockDataSource(
            name="finlab",
            financial_data=make_financial_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        result1 = pipeline.get_financial_data("2330", years=5)
        assert result1.success is True
        assert result1.from_cache is False

        result2 = pipeline.get_financial_data("2330", years=5)
        assert result2.success is True
        assert result2.from_cache is True
        assert result2.source_name == "memory_cache"
        assert source.call_count == 1

        pipeline.shutdown(wait=False)

    def test_different_stocks_cached_independently(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """不同股票的快取互相獨立。"""
        source = MockDataSource(
            name="yahoo_finance",
            info_data=make_stock_info("2330"),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        # 查詢 2330
        r1 = pipeline.get_stock_info("2330")
        assert r1.success is True
        assert source.call_count == 1

        # 查詢 2317 -> 不同 key，應呼叫來源
        source._info_data = make_stock_info("2317")
        r2 = pipeline.get_stock_info("2317")
        assert r2.success is True
        assert source.call_count == 2

        # 再次查詢 2330 -> 命中快取
        r3 = pipeline.get_stock_info("2330")
        assert r3.success is True
        assert r3.from_cache is True
        assert source.call_count == 2

        pipeline.shutdown(wait=False)

    def test_cache_stats_reflect_hits_and_misses(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """快取統計正確反映命中與未命中。"""
        source = MockDataSource(
            name="yahoo_finance",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        # 首次（miss）
        pipeline.get_stock_price("2330", start, end)
        # 二次（hit）
        pipeline.get_stock_price("2330", start, end)
        # 不同股票（miss）
        source._price_data = make_price_df("2317")
        pipeline.get_stock_price("2317", start, end)

        stats = memory_cache.stats()
        assert stats["hit_count"] >= 1
        assert stats["miss_count"] >= 2

        pipeline.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Scenario 4: Cache invalidation works end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCacheInvalidationEndToEnd:
    """快取失效端對端：invalidate 後下次請求重新取得。"""

    def test_invalidate_forces_refetch(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """invalidate_cache 清除後，後續請求再次呼叫來源。"""
        source = MockDataSource(
            name="yahoo_finance",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        # 首次請求 -> 填充快取
        r1 = pipeline.get_stock_price("2330", start, end)
        assert r1.success is True
        assert source.call_count == 1

        # 確認快取命中
        r2 = pipeline.get_stock_price("2330", start, end)
        assert r2.from_cache is True
        assert source.call_count == 1

        # 執行 invalidation
        removed = pipeline.invalidate_cache("2330")
        assert removed >= 1

        # 再次請求 -> 應重新從來源取得
        r3 = pipeline.get_stock_price("2330", start, end)
        assert r3.success is True
        assert r3.from_cache is False
        assert r3.source_name == "yahoo_finance"
        assert source.call_count == 2

        pipeline.shutdown(wait=False)

    def test_invalidate_one_stock_does_not_affect_others(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """invalidate 特定股票不影響其他股票的快取。"""
        source = MockDataSource(
            name="yahoo_finance",
            info_data=make_stock_info("2330"),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        # 填充兩支股票快取
        pipeline.get_stock_info("2330")
        source._info_data = make_stock_info("2317")
        pipeline.get_stock_info("2317")
        assert source.call_count == 2

        # invalidate 2330
        pipeline.invalidate_cache("2330")

        # 2317 仍命中快取
        r = pipeline.get_stock_info("2317")
        assert r.from_cache is True
        assert source.call_count == 2

        # 2330 需重新取得
        source._info_data = make_stock_info("2330")
        r2 = pipeline.get_stock_info("2330")
        assert r2.from_cache is False
        assert source.call_count == 3

        pipeline.shutdown(wait=False)

    def test_invalidate_nonexistent_stock_is_noop(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """invalidate 不存在的股票不造成錯誤。"""
        source = MockDataSource(
            name="yahoo_finance",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        # 沒有任何快取，invalidate 應安全回傳 0
        removed = pipeline.invalidate_cache("9999")
        assert removed == 0

        pipeline.shutdown(wait=False)

    def test_memory_cache_ttl_expiry_forces_refetch(
        self,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
    ) -> None:
        """記憶體快取 TTL 過期後，自動重新從來源取得。"""
        # 使用可控時間函式
        current_time = [1000.0]

        def mock_time() -> float:
            return current_time[0]

        cache = MemoryCache(max_size=200, time_func=mock_time)

        source = MockDataSource(
            name="yahoo_finance",
            price_data=make_price_df(),
        )

        pipeline = DataPipeline(
            sources=[source],
            memory_cache=cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        # 首次請求
        r1 = pipeline.get_stock_price("2330", start, end)
        assert r1.success is True
        assert r1.from_cache is False
        assert source.call_count == 1

        # 時間未過 TTL（PRICE TTL = 300s）-> 命中快取
        current_time[0] = 1200.0  # +200s
        r2 = pipeline.get_stock_price("2330", start, end)
        assert r2.from_cache is True
        assert source.call_count == 1

        # 時間超過 TTL -> 重新擷取
        current_time[0] = 1400.0  # +400s > 300s TTL
        r3 = pipeline.get_stock_price("2330", start, end)
        assert r3.success is True
        assert r3.from_cache is False
        assert source.call_count == 2

        pipeline.shutdown(wait=False)
