"""DataPipeline 單元測試。

涵蓋 app.infra.data_pipeline 模組中 DataPipeline 與 FetchResult 的行為，
包含來源備援、快取命中/未命中、驗證失敗降級、並行擷取、部分失敗、
快取失效、資料驗證邏輯、斷路器互動、可用來源列表等情境。

使用 unittest.mock 替代外部依賴（DataSourceProtocol、MemoryCache、
SQLiteCache、ErrorHandler）。
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from app.core.errors import CircuitOpenError, DataSourceError, StockToolError
from app.infra.data_pipeline import DataPipeline, FetchResult, _cache_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_source(
    name: str = "test_source",
    available: bool = True,
) -> MagicMock:
    """建立符合 DataSourceProtocol 的 mock 來源。"""
    source = MagicMock()
    source.source_name = name
    type(source).is_available = property(lambda self: available)
    source.is_ready.return_value = True
    return source


def _make_memory_cache() -> MagicMock:
    """建立 MemoryCache mock。"""
    cache = MagicMock()
    cache.get.return_value = None
    cache.set.return_value = None
    cache.invalidate_by_stock.return_value = 0
    return cache


def _make_sqlite_cache() -> MagicMock:
    """建立 SQLiteCache mock。"""
    cache = MagicMock()
    cache.get.return_value = None
    cache.get_snapshot.return_value = None
    return cache


def _make_error_handler() -> MagicMock:
    """建立 ErrorHandler mock。"""
    handler = MagicMock()
    handler.handle_error.return_value = None
    return handler


def _sample_price_df() -> pd.DataFrame:
    """建立範例股價 DataFrame。"""
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000, 2000, 3000],
    })


def _sample_financial_df() -> pd.DataFrame:
    """建立範例財報 DataFrame。"""
    return pd.DataFrame({
        "eps": [5.0, 6.0, 7.0],
        "roe": [15.0, 16.0, 17.0],
        "pe_ratio": [20.0, 18.0, 22.0],
        "revenue": [100.0, 110.0, 120.0],
    })


@pytest.fixture
def pipeline_deps():
    """提供標準 DataPipeline 依賴套件。"""
    source_a = _make_source("FinLab")
    source_b = _make_source("YahooFinance")
    source_c = _make_source("FinMind")
    memory_cache = _make_memory_cache()
    sqlite_cache = _make_sqlite_cache()
    error_handler = _make_error_handler()
    return {
        "sources": [source_a, source_b, source_c],
        "memory_cache": memory_cache,
        "sqlite_cache": sqlite_cache,
        "error_handler": error_handler,
    }


@pytest.fixture
def pipeline(pipeline_deps):
    """建立已組裝好的 DataPipeline 實例。"""
    p = DataPipeline(**pipeline_deps)
    yield p
    p.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test: FetchResult 結構
# ---------------------------------------------------------------------------


class TestFetchResult:
    """FetchResult dataclass 基本行為。"""

    def test_default_values(self):
        """FetchResult 預設值正確。"""
        result = FetchResult(stock_code="2330")
        assert result.stock_code == "2330"
        assert result.data is None
        assert result.success is False
        assert result.source_name == ""
        assert result.from_cache is False
        assert result.warning is None
        assert result.error_message is None

    def test_success_result(self):
        """成功 FetchResult 欄位正確。"""
        result = FetchResult(
            stock_code="2317",
            data={"price": 100},
            success=True,
            source_name="YahooFinance",
        )
        assert result.success is True
        assert result.data == {"price": 100}
        assert result.source_name == "YahooFinance"


# ---------------------------------------------------------------------------
# Test: Source Fallback
# ---------------------------------------------------------------------------


class TestSourceFallback:
    """來源備援流程測試。"""

    def test_primary_fails_secondary_succeeds(self, pipeline_deps):
        """主要來源失敗時，成功切換到備援來源。"""
        sources = pipeline_deps["sources"]
        # FinLab 拋出錯誤
        sources[0].get_stock_price.side_effect = DataSourceError(
            "API down", source_name="FinLab"
        )
        # YahooFinance 回傳有效資料
        sources[1].get_stock_price.return_value = _sample_price_df()
        sources[2].get_stock_price.return_value = None

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.source_name == "YahooFinance"
        assert result.from_cache is False

    def test_all_sources_fail_returns_error(self, pipeline_deps):
        """所有來源都失敗時，回傳錯誤結果。"""
        sources = pipeline_deps["sources"]
        for src in sources:
            src.get_stock_price.side_effect = DataSourceError(
                "fail", source_name=src.source_name
            )

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is False
        assert result.error_message is not None

    def test_source_returns_none_tries_next(self, pipeline_deps):
        """來源回傳 None 時嘗試下一個來源。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.return_value = None
        sources[1].get_stock_price.return_value = None
        sources[2].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.source_name == "FinMind"


# ---------------------------------------------------------------------------
# Test: Memory Cache Hit / Miss
# ---------------------------------------------------------------------------


class TestMemoryCache:
    """記憶體快取命中/未命中。"""

    def test_cache_hit_returns_cached_data(self, pipeline_deps):
        """記憶體快取命中時直接回傳，不存取來源。"""
        cached_df = _sample_price_df()
        pipeline_deps["memory_cache"].get.return_value = cached_df

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.from_cache is True
        assert result.source_name == "memory_cache"
        # 來源不應被呼叫
        for src in pipeline_deps["sources"]:
            src.get_stock_price.assert_not_called()

    def test_cache_miss_hits_sources(self, pipeline_deps):
        """記憶體快取未命中時存取來源。"""
        pipeline_deps["memory_cache"].get.return_value = None
        pipeline_deps["sources"][0].get_stock_price.return_value = (
            _sample_price_df()
        )

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.from_cache is False
        pipeline_deps["sources"][0].get_stock_price.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Validation Failure -> Cache Degradation
# ---------------------------------------------------------------------------


class TestValidationFailureDegradation:
    """驗證失敗時降級回傳快取資料。"""

    def test_validation_fail_returns_stale_cache(self, pipeline_deps):
        """所有來源驗證失敗時回傳 SQLite 快取 + 警告。"""
        sources = pipeline_deps["sources"]
        # 所有來源回傳空 DataFrame（驗證後為 None）
        empty_df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []})
        for src in sources:
            src.get_stock_price.return_value = empty_df

        # SQLite 有快取資料
        stale_data = {"stock_code": "2330", "pe_ratio": 15.0}
        pipeline_deps["sqlite_cache"].get_snapshot.return_value = stale_data

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.from_cache is True
        assert result.warning is not None
        assert "STALE" in result.warning

    def test_validation_fail_no_cache_returns_error(self, pipeline_deps):
        """驗證失敗且無快取資料時回傳錯誤。"""
        sources = pipeline_deps["sources"]
        empty_df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []})
        for src in sources:
            src.get_stock_price.return_value = empty_df

        pipeline_deps["sqlite_cache"].get_snapshot.return_value = None

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is False


# ---------------------------------------------------------------------------
# Test: Concurrent Multi-Stock Fetch
# ---------------------------------------------------------------------------


class TestConcurrentFetch:
    """並行多股擷取。"""

    def test_concurrent_fetch_all_succeed(self, pipeline_deps):
        """並行擷取多支股票，全部成功。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        codes = ["2330", "2317", "2454"]
        results = p.get_multiple_prices(codes, start, end)
        p.shutdown(wait=False)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.stock_code == c for r, c in zip(results, codes))

    def test_partial_failure_in_concurrent_fetch(self, pipeline_deps):
        """並行擷取中部分失敗，不影響成功的結果。"""
        sources = pipeline_deps["sources"]

        def side_effect_price(stock_code, start_date, end_date):
            if stock_code == "9999":
                raise DataSourceError("not found", source_name="FinLab")
            return _sample_price_df()

        sources[0].get_stock_price.side_effect = side_effect_price
        sources[1].get_stock_price.side_effect = side_effect_price
        sources[2].get_stock_price.side_effect = side_effect_price

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        codes = ["2330", "9999", "2454"]
        results = p.get_multiple_prices(codes, start, end)
        p.shutdown(wait=False)

        assert len(results) == 3
        # 2330 和 2454 成功
        assert results[0].success is True
        assert results[2].success is True
        # 9999 失敗
        assert results[1].success is False

    def test_empty_stock_list_returns_empty(self, pipeline_deps):
        """空股票清單回傳空結果。"""
        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        results = p.get_multiple_prices([], start, end)
        p.shutdown(wait=False)

        assert results == []


# ---------------------------------------------------------------------------
# Test: Cache Invalidation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    """快取失效操作。"""

    def test_invalidate_cache_calls_memory_cache(self, pipeline_deps):
        """invalidate_cache 清除記憶體快取對應條目。"""
        pipeline_deps["memory_cache"].invalidate_by_stock.return_value = 3

        p = DataPipeline(**pipeline_deps)
        count = p.invalidate_cache("2330")
        p.shutdown(wait=False)

        assert count == 3
        pipeline_deps["memory_cache"].invalidate_by_stock.assert_called_once_with(
            "2330"
        )


# ---------------------------------------------------------------------------
# Test: Price Data Validation
# ---------------------------------------------------------------------------


class TestPriceDataValidation:
    """股價資料驗證邏輯。"""

    def test_removes_rows_with_price_lte_zero(self, pipeline_deps):
        """過濾掉價格 <= 0 的資料列。"""
        sources = pipeline_deps["sources"]
        df_with_bad = pd.DataFrame({
            "open": [100.0, -5.0, 102.0],
            "high": [105.0, 10.0, 107.0],
            "low": [99.0, -10.0, 101.0],
            "close": [103.0, 5.0, 105.0],
            "volume": [1000, 2000, 3000],
        })
        sources[0].get_stock_price.return_value = df_with_bad

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        validated_df = result.data
        # 第二列的 low = -10 被過濾
        assert len(validated_df) == 2
        assert all(validated_df["open"] > 0)


# ---------------------------------------------------------------------------
# Test: Financial Data Validation
# ---------------------------------------------------------------------------


class TestFinancialDataValidation:
    """財報資料驗證邏輯。"""

    def test_roe_normalization_and_range_filter(self, pipeline_deps):
        """ROE 歸一化 (小數->百分比) 與範圍過濾。"""
        sources = pipeline_deps["sources"]
        df = pd.DataFrame({
            "eps": [5.0, 6.0, 7.0],
            "roe": [0.15, 250.0, 18.0],  # 0.15->15%, 250 超出, 18 ok
            "pe_ratio": [20.0, 18.0, 22.0],
        })
        sources[0].get_financial_data.return_value = df

        p = DataPipeline(**pipeline_deps)
        result = p.get_financial_data("2330", years=5)
        p.shutdown(wait=False)

        assert result.success is True
        validated = result.data
        # 250% 超出 [-100, 200] 被過濾
        assert len(validated) == 2
        # 0.15 被歸一化為 15.0
        assert validated.iloc[0]["roe"] == 15.0


# ---------------------------------------------------------------------------
# Test: Stock Info Validation
# ---------------------------------------------------------------------------


class TestStockInfoValidation:
    """股票基本資訊驗證。"""

    def test_market_cap_negative_set_to_none(self, pipeline_deps):
        """market_cap < 0 時設為 None。"""
        sources = pipeline_deps["sources"]
        info = {"stock_code": "2330", "stock_name": "TSMC", "market_cap": -100}
        sources[0].get_stock_info.return_value = info

        p = DataPipeline(**pipeline_deps)
        result = p.get_stock_info("2330")
        p.shutdown(wait=False)

        assert result.success is True
        assert result.data["market_cap"] is None

    def test_valid_stock_info_passes(self, pipeline_deps):
        """有效的股票資訊通過驗證。"""
        sources = pipeline_deps["sources"]
        info = {"stock_code": "2330", "stock_name": "TSMC", "market_cap": 5000}
        sources[0].get_stock_info.return_value = info

        p = DataPipeline(**pipeline_deps)
        result = p.get_stock_info("2330")
        p.shutdown(wait=False)

        assert result.success is True
        assert result.data["market_cap"] == 5000


# ---------------------------------------------------------------------------
# Test: Circuit Breaker Open -> Source Skipped
# ---------------------------------------------------------------------------


class TestCircuitBreakerInteraction:
    """斷路器開啟時跳過來源。"""

    def test_circuit_open_skips_source(self, pipeline_deps):
        """來源拋出 CircuitOpenError 時跳過並嘗試下一來源。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.side_effect = CircuitOpenError(
            "circuit open", source_name="FinLab"
        )
        sources[1].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.source_name == "YahooFinance"


# ---------------------------------------------------------------------------
# Test: Available Sources
# ---------------------------------------------------------------------------


class TestAvailableSources:
    """可用來源列表。"""

    def test_get_available_sources_filters_unavailable(self, pipeline_deps):
        """get_available_sources 只回傳可用的來源。"""
        # 讓第二個來源不可用
        type(pipeline_deps["sources"][1]).is_available = property(
            lambda self: False
        )

        p = DataPipeline(**pipeline_deps)
        available = p.get_available_sources()
        p.shutdown(wait=False)

        assert "FinLab" in available
        assert "YahooFinance" not in available
        assert "FinMind" in available


# ---------------------------------------------------------------------------
# Test: Unavailable Source Skipped
# ---------------------------------------------------------------------------


class TestUnavailableSourceSkipped:
    """不可用的來源被跳過。"""

    def test_unavailable_source_not_called(self, pipeline_deps):
        """is_available=False 的來源不會被嘗試。"""
        sources = pipeline_deps["sources"]
        type(sources[0]).is_available = property(lambda self: False)
        sources[1].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        sources[0].get_stock_price.assert_not_called()
        assert result.success is True
        assert result.source_name == "YahooFinance"


# ---------------------------------------------------------------------------
# Test: Financial Data Fetch
# ---------------------------------------------------------------------------


class TestFinancialDataFetch:
    """財報資料擷取流程。"""

    def test_get_financial_data_success(self, pipeline_deps):
        """成功取得財報資料。"""
        sources = pipeline_deps["sources"]
        sources[0].get_financial_data.return_value = _sample_financial_df()

        p = DataPipeline(**pipeline_deps)
        result = p.get_financial_data("2330", years=5)
        p.shutdown(wait=False)

        assert result.success is True
        assert result.source_name == "FinLab"
        assert not result.data.empty


# ---------------------------------------------------------------------------
# Test: Cache Key Generation
# ---------------------------------------------------------------------------


class TestCacheKey:
    """快取鍵值產生邏輯。"""

    def test_cache_key_format(self):
        """快取鍵值格式正確。"""
        key = _cache_key(
            "price", "2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 30),
        )
        assert "price" in key
        assert "2330" in key
        assert "20240101" in key
        assert "20240630" in key

    def test_cache_key_deterministic(self):
        """相同參數產生相同鍵值。"""
        key1 = _cache_key("financial", "2317", years=5)
        key2 = _cache_key("financial", "2317", years=5)
        assert key1 == key2


# ---------------------------------------------------------------------------
# Test: Write Cache After Successful Fetch
# ---------------------------------------------------------------------------


class TestWriteCache:
    """成功擷取後寫入快取。"""

    def test_successful_fetch_writes_to_memory_cache(self, pipeline_deps):
        """成功取得資料後自動寫入記憶體快取。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        pipeline_deps["memory_cache"].set.assert_called_once()


# ---------------------------------------------------------------------------
# Test: StockToolError Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """各種例外的處理。"""

    def test_stock_tool_error_continues_to_next(self, pipeline_deps):
        """StockToolError 被處理後繼續嘗試下一來源。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.side_effect = StockToolError(
            "generic error", stock_code="2330"
        )
        sources[1].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        pipeline_deps["error_handler"].handle_error.assert_called_once()

    def test_unexpected_exception_handled(self, pipeline_deps):
        """非預期例外被捕獲並記錄。"""
        sources = pipeline_deps["sources"]
        sources[0].get_stock_price.side_effect = RuntimeError("unexpected")
        sources[1].get_stock_price.return_value = _sample_price_df()

        p = DataPipeline(**pipeline_deps)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = p.get_stock_price("2330", start, end)
        p.shutdown(wait=False)

        assert result.success is True
        pipeline_deps["error_handler"].handle_error.assert_called_once()
