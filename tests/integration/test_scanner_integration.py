"""Market Scanner 完整掃描整合測試。

測試完整掃描管線：data source -> DataPipeline -> MarketScannerService
-> SQLiteCache -> filter_results query。

使用：
    - Real MemoryCache、SQLiteCache（tempfile）、ErrorHandler、BatchDownloader
    - Mock data sources 回傳 fixture 資料
    - Real MarketScannerService

Scenarios:
    1. Full scan: 下載所有股票 -> 處理 -> 寫入 SQLite -> filter_results 回傳正確子集
    2. Incremental scan: 部分股票快取仍新鮮，僅過期者重新下載
    3. Batch download partial failure: 部分股票下載失敗 -> scanner 繼續處理成功的股票

Validates: Requirements 19.2, 19.5
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest

from app.core.models.scan import MarketSnapshot, ScanResult
from app.infra.cache.memory_cache import MemoryCache
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.data_pipeline import DataPipeline, FetchResult
from app.infra.error_handler import ErrorHandler
from app.infra.resilience.batch_downloader import BatchDownloader
from app.services.market_scanner import MarketScannerService


# ---------------------------------------------------------------------------
# Fixture 資料
# ---------------------------------------------------------------------------

FIXTURE_STOCKS: Dict[str, Dict[str, Any]] = {
    "2330": {
        "stock_code": "2330",
        "stock_name": "台積電",
        "current_price": 580.0,
        "pe_ratio": 22.5,
        "roe": 28.0,
        "dividend_yield": 2.1,
        "market_cap": 15000.0,
        "high_52w": 620.0,
        "low_52w": 480.0,
    },
    "2317": {
        "stock_code": "2317",
        "stock_name": "鴻海",
        "current_price": 105.0,
        "pe_ratio": 11.2,
        "roe": 12.5,
        "dividend_yield": 5.3,
        "market_cap": 1450.0,
        "high_52w": 115.0,
        "low_52w": 90.0,
    },
    "2454": {
        "stock_code": "2454",
        "stock_name": "聯發科",
        "current_price": 750.0,
        "pe_ratio": 16.8,
        "roe": 20.3,
        "dividend_yield": 3.5,
        "market_cap": 1200.0,
        "high_52w": 800.0,
        "low_52w": 600.0,
    },
    "2382": {
        "stock_code": "2382",
        "stock_name": "廣達",
        "current_price": 220.0,
        "pe_ratio": 14.5,
        "roe": 18.0,
        "dividend_yield": 4.2,
        "market_cap": 850.0,
        "high_52w": 250.0,
        "low_52w": 180.0,
    },
    "3008": {
        "stock_code": "3008",
        "stock_name": "大立光",
        "current_price": 2100.0,
        "pe_ratio": 25.0,
        "roe": 15.5,
        "dividend_yield": 2.8,
        "market_cap": 2800.0,
        "high_52w": 2500.0,
        "low_52w": 1800.0,
    },
}


# ---------------------------------------------------------------------------
# Mock DataSource
# ---------------------------------------------------------------------------


class MockDataSource:
    """Mock 資料來源，回傳預錄 fixture 資料。

    可透過 fail_codes 設定特定股票代碼回傳 None 模擬失敗。
    """

    def __init__(
        self,
        name: str = "mock_source",
        fixture_data: Optional[Dict[str, Dict[str, Any]]] = None,
        fail_codes: Optional[List[str]] = None,
    ) -> None:
        self._name = name
        self._fixture = fixture_data or FIXTURE_STOCKS
        self._fail_codes = set(fail_codes or [])
        self._available = True

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
        if stock_code in self._fail_codes:
            return None
        data = self._fixture.get(stock_code)
        if data is None:
            return None
        return pd.DataFrame(
            [{"open": data["current_price"], "high": data["current_price"],
              "low": data["current_price"], "close": data["current_price"],
              "volume": 10000}]
        )

    def get_financial_data(
        self, stock_code: str, years: int = 5
    ) -> Optional[pd.DataFrame]:
        if stock_code in self._fail_codes:
            return None
        data = self._fixture.get(stock_code)
        if data is None:
            return None
        return pd.DataFrame(
            [{"eps": 10.0, "roe": data.get("roe", 15.0),
              "pe_ratio": data.get("pe_ratio", 15.0)}]
        )

    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        if stock_code in self._fail_codes:
            return None
        return self._fixture.get(stock_code)


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path() -> str:
    """產生臨時 SQLite 資料庫路徑。"""
    import os
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_market_scan.db")
    yield db_path
    # 清理
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        # WAL/SHM 附屬檔案
        for suffix in ("-wal", "-shm"):
            wal_path = db_path + suffix
            if os.path.exists(wal_path):
                os.remove(wal_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


@pytest.fixture
def memory_cache() -> MemoryCache:
    """建立乾淨的 MemoryCache 實例。"""
    return MemoryCache(max_size=200)


@pytest.fixture
def sqlite_cache(tmp_db_path: str) -> SQLiteCache:
    """建立使用臨時檔案的 SQLiteCache 實例。"""
    cache = SQLiteCache(db_path=tmp_db_path)
    yield cache
    cache.close()


@pytest.fixture
def error_handler() -> ErrorHandler:
    """建立 ErrorHandler 實例。"""
    return ErrorHandler()


@pytest.fixture
def batch_downloader() -> BatchDownloader:
    """建立 BatchDownloader，注入 noop sleep 加速測試。"""
    return BatchDownloader(
        batch_size=50,
        batch_delay=0.0,
        timeout_seconds=10.0,
        max_workers=5,
        max_consecutive_failures=3,
        sleep_func=lambda _: None,
    )


@pytest.fixture
def mock_source() -> MockDataSource:
    """建立正常的 mock 資料來源。"""
    return MockDataSource(name="finlab_mock", fixture_data=FIXTURE_STOCKS)


@pytest.fixture
def data_pipeline(
    mock_source: MockDataSource,
    memory_cache: MemoryCache,
    sqlite_cache: SQLiteCache,
    error_handler: ErrorHandler,
) -> DataPipeline:
    """建立使用 mock 來源的 DataPipeline。"""
    pipeline = DataPipeline(
        sources=[mock_source],
        memory_cache=memory_cache,
        sqlite_cache=sqlite_cache,
        error_handler=error_handler,
        max_workers=5,
        per_request_timeout=10.0,
    )
    yield pipeline
    pipeline.shutdown(wait=False)


@pytest.fixture
def scanner_service(
    data_pipeline: DataPipeline,
    batch_downloader: BatchDownloader,
    sqlite_cache: SQLiteCache,
    error_handler: ErrorHandler,
) -> MarketScannerService:
    """建立完整的 MarketScannerService（使用真實元件 + mock 來源）。"""
    return MarketScannerService(
        data_pipeline=data_pipeline,
        batch_downloader=batch_downloader,
        sqlite_cache=sqlite_cache,
        error_handler=error_handler,
    )


# ---------------------------------------------------------------------------
# Scenario 1: Full Scan
# ---------------------------------------------------------------------------


class TestFullScan:
    """Full scan: 下載所有股票 -> 處理 -> 寫入 SQLite -> filter_results 正確回傳。"""

    def test_full_scan_downloads_all_stocks(
        self, scanner_service: MarketScannerService
    ) -> None:
        """完整掃描應處理所有指定股票並回傳 MarketSnapshot。"""
        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner_service.scan_market(
            stock_codes=codes, incremental=False
        )

        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.total_stocks == len(codes)
        result_codes = {r.stock_code for r in snapshot.results}
        assert result_codes == set(codes)

    def test_full_scan_writes_to_sqlite(
        self,
        scanner_service: MarketScannerService,
        sqlite_cache: SQLiteCache,
    ) -> None:
        """完整掃描後 SQLite 應包含所有成功處理的股票記錄。"""
        codes = list(FIXTURE_STOCKS.keys())
        scanner_service.scan_market(stock_codes=codes, incremental=False)

        # 從 SQLite 查詢驗證寫入
        for code in codes:
            record = sqlite_cache.get_snapshot(code)
            assert record is not None, f"{code} 應存在於 SQLite"
            assert record["stock_code"] == code

    def test_full_scan_data_values_correct(
        self, scanner_service: MarketScannerService
    ) -> None:
        """完整掃描後 ScanResult 中的數值應與 fixture 一致。"""
        codes = ["2330", "2317"]
        snapshot = scanner_service.scan_market(
            stock_codes=codes, incremental=False
        )

        result_map = {r.stock_code: r for r in snapshot.results}

        # 2330: 台積電
        r2330 = result_map["2330"]
        assert r2330.current_price == 580.0
        assert r2330.pe_ratio == 22.5
        assert r2330.roe == 28.0
        assert r2330.dividend_yield == 2.1

        # 2317: 鴻海
        r2317 = result_map["2317"]
        assert r2317.current_price == 105.0
        assert r2317.pe_ratio == 11.2

    def test_filter_results_returns_correct_subset(
        self, scanner_service: MarketScannerService
    ) -> None:
        """filter_results 應依條件正確篩選結果子集。"""
        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner_service.scan_market(
            stock_codes=codes, incremental=False
        )

        # 篩選 ROE >= 20
        filtered = scanner_service.filter_results(
            snapshot, {"roe_min": 20.0}
        )
        assert filtered.total_stocks <= snapshot.total_stocks
        for r in filtered.results:
            assert r.roe >= 20.0

    def test_filter_pe_max(
        self, scanner_service: MarketScannerService
    ) -> None:
        """filter_results 以 pe_max 篩選應排除高 PE 股票。"""
        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner_service.scan_market(
            stock_codes=codes, incremental=False
        )

        filtered = scanner_service.filter_results(
            snapshot, {"pe_max": 15.0}
        )
        for r in filtered.results:
            assert r.pe_ratio <= 15.0

    def test_filter_dividend_yield_min(
        self, scanner_service: MarketScannerService
    ) -> None:
        """filter_results 以 dividend_yield_min 應只保留高殖利率股票。"""
        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner_service.scan_market(
            stock_codes=codes, incremental=False
        )

        filtered = scanner_service.filter_results(
            snapshot, {"dividend_yield_min": 4.0}
        )
        for r in filtered.results:
            assert r.dividend_yield >= 4.0


# ---------------------------------------------------------------------------
# Scenario 2: Incremental Scan
# ---------------------------------------------------------------------------


class TestIncrementalScan:
    """Incremental scan: 部分股票快取新鮮，僅過期者重新下載。"""

    def test_fresh_stocks_loaded_from_cache(
        self,
        sqlite_cache: SQLiteCache,
        data_pipeline: DataPipeline,
        batch_downloader: BatchDownloader,
        error_handler: ErrorHandler,
    ) -> None:
        """快取內 4 小時內的股票不應觸發重新下載。"""
        # 設定目前時間為固定值
        current_time = 1700000000.0

        # 先寫入「新鮮」的快取記錄（last_updated 在 2 小時前）
        from datetime import datetime as dt

        fresh_time = dt.fromtimestamp(
            current_time - 2 * 3600, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        sqlite_cache.upsert_snapshot({
            "stock_code": "2330",
            "stock_name": "台積電",
            "current_price": 580.0,
            "pe_ratio": 22.5,
            "roe": 28.0,
            "dividend_yield": 2.1,
            "market_cap": 15000.0,
            "price_position": 0.7,
            "fundamental_score": 85.0,
            "fundamental_grade": "A",
            "last_updated": fresh_time,
        })

        # 寫入「過期」的快取記錄（last_updated 在 5 小時前）
        stale_time = dt.fromtimestamp(
            current_time - 5 * 3600, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        sqlite_cache.upsert_snapshot({
            "stock_code": "2317",
            "stock_name": "鴻海",
            "current_price": 100.0,
            "pe_ratio": 10.0,
            "roe": 11.0,
            "dividend_yield": 5.0,
            "market_cap": 1400.0,
            "price_position": 0.5,
            "fundamental_score": 75.0,
            "fundamental_grade": "B",
            "last_updated": stale_time,
        })

        # 建立注入固定時間的 scanner
        scanner = MarketScannerService(
            data_pipeline=data_pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            time_func=lambda: current_time,
        )

        snapshot = scanner.scan_market(
            stock_codes=["2330", "2317"], incremental=True
        )

        assert snapshot.total_stocks == 2
        result_map = {r.stock_code: r for r in snapshot.results}

        # 2330 應從快取載入（保持快取中的舊值 580.0）
        assert "2330" in result_map
        assert result_map["2330"].current_price == 580.0

        # 2317 應重新下載（從 fixture 取得新值 105.0）
        assert "2317" in result_map
        assert result_map["2317"].current_price == 105.0

    def test_incremental_only_downloads_stale(
        self,
        sqlite_cache: SQLiteCache,
        data_pipeline: DataPipeline,
        batch_downloader: BatchDownloader,
        error_handler: ErrorHandler,
    ) -> None:
        """增量模式應僅下載超過 4 小時未更新的股票。"""
        current_time = 1700000000.0

        from datetime import datetime as dt

        # 3 支新鮮（2h 前）、2 支過期（5h 前）
        fresh_time = dt.fromtimestamp(
            current_time - 2 * 3600, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
        stale_time = dt.fromtimestamp(
            current_time - 5 * 3600, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        fresh_codes = ["2330", "2454", "3008"]
        stale_codes = ["2317", "2382"]

        for code in fresh_codes:
            fixture = FIXTURE_STOCKS[code]
            sqlite_cache.upsert_snapshot({
                "stock_code": code,
                "stock_name": fixture["stock_name"],
                "current_price": fixture["current_price"],
                "pe_ratio": fixture["pe_ratio"],
                "roe": fixture["roe"],
                "dividend_yield": fixture["dividend_yield"],
                "market_cap": fixture["market_cap"],
                "price_position": 0.5,
                "fundamental_score": 70.0,
                "fundamental_grade": "B",
                "last_updated": fresh_time,
            })

        for code in stale_codes:
            sqlite_cache.upsert_snapshot({
                "stock_code": code,
                "stock_name": "old",
                "current_price": 1.0,
                "pe_ratio": 1.0,
                "roe": 1.0,
                "dividend_yield": 1.0,
                "market_cap": 1.0,
                "price_position": 0.1,
                "fundamental_score": 50.0,
                "fundamental_grade": "C",
                "last_updated": stale_time,
            })

        scanner = MarketScannerService(
            data_pipeline=data_pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            time_func=lambda: current_time,
        )

        all_codes = fresh_codes + stale_codes
        snapshot = scanner.scan_market(
            stock_codes=all_codes, incremental=True
        )

        assert snapshot.total_stocks == 5
        result_map = {r.stock_code: r for r in snapshot.results}

        # 新鮮股票應從快取載入（保持快取值）
        for code in fresh_codes:
            assert code in result_map
            assert result_map[code].current_price == FIXTURE_STOCKS[code]["current_price"]

        # 過期股票應重新下載（從 fixture 取得新值）
        assert result_map["2317"].current_price == 105.0
        assert result_map["2382"].current_price == 220.0


# ---------------------------------------------------------------------------
# Scenario 3: Batch Download Partial Failure
# ---------------------------------------------------------------------------


class TestBatchPartialFailure:
    """Batch download partial failure: 部分股票失敗，scanner 繼續處理成功者。"""

    def test_partial_failure_continues_processing(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        batch_downloader: BatchDownloader,
    ) -> None:
        """部分股票下載失敗時，scanner 仍應成功處理其他股票。"""
        # 建立會讓 2317、3008 失敗的 mock source
        fail_source = MockDataSource(
            name="partial_fail_source",
            fixture_data=FIXTURE_STOCKS,
            fail_codes=["2317", "3008"],
        )

        pipeline = DataPipeline(
            sources=[fail_source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            max_workers=5,
            per_request_timeout=10.0,
        )

        scanner = MarketScannerService(
            data_pipeline=pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner.scan_market(stock_codes=codes, incremental=False)

        # 成功的股票數 < 總數（因為 2317、3008 失敗）
        success_codes = {r.stock_code for r in snapshot.results}
        assert "2330" in success_codes
        assert "2454" in success_codes
        assert "2382" in success_codes
        # 失敗的不應出現在結果中
        assert "2317" not in success_codes
        assert "3008" not in success_codes

        pipeline.shutdown(wait=False)

    def test_partial_failure_writes_successful_to_cache(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        batch_downloader: BatchDownloader,
    ) -> None:
        """部分失敗時，成功的股票仍應寫入 SQLite 快取。"""
        fail_source = MockDataSource(
            name="partial_fail_source",
            fixture_data=FIXTURE_STOCKS,
            fail_codes=["2454"],
        )

        pipeline = DataPipeline(
            sources=[fail_source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            max_workers=5,
            per_request_timeout=10.0,
        )

        scanner = MarketScannerService(
            data_pipeline=pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        codes = ["2330", "2317", "2454"]
        scanner.scan_market(stock_codes=codes, incremental=False)

        # 成功的應在快取中
        assert sqlite_cache.get_snapshot("2330") is not None
        assert sqlite_cache.get_snapshot("2317") is not None
        # 失敗的不應在快取中
        assert sqlite_cache.get_snapshot("2454") is None

        pipeline.shutdown(wait=False)

    def test_scan_with_all_sources_failing_returns_empty(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        batch_downloader: BatchDownloader,
    ) -> None:
        """所有股票都下載失敗時應回傳空的 MarketSnapshot。"""
        all_fail_source = MockDataSource(
            name="all_fail_source",
            fixture_data=FIXTURE_STOCKS,
            fail_codes=list(FIXTURE_STOCKS.keys()),
        )

        pipeline = DataPipeline(
            sources=[all_fail_source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            max_workers=5,
            per_request_timeout=10.0,
        )

        scanner = MarketScannerService(
            data_pipeline=pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner.scan_market(stock_codes=codes, incremental=False)

        assert snapshot.total_stocks == 0
        assert snapshot.results == []

        pipeline.shutdown(wait=False)

    def test_filter_after_partial_failure(
        self,
        memory_cache: MemoryCache,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        batch_downloader: BatchDownloader,
    ) -> None:
        """部分失敗後，filter_results 仍應正確篩選成功的結果。"""
        fail_source = MockDataSource(
            name="partial_fail_source",
            fixture_data=FIXTURE_STOCKS,
            fail_codes=["3008"],
        )

        pipeline = DataPipeline(
            sources=[fail_source],
            memory_cache=memory_cache,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
            max_workers=5,
            per_request_timeout=10.0,
        )

        scanner = MarketScannerService(
            data_pipeline=pipeline,
            batch_downloader=batch_downloader,
            sqlite_cache=sqlite_cache,
            error_handler=error_handler,
        )

        codes = list(FIXTURE_STOCKS.keys())
        snapshot = scanner.scan_market(stock_codes=codes, incremental=False)

        # 篩選殖利率 >= 4
        filtered = scanner.filter_results(
            snapshot, {"dividend_yield_min": 4.0}
        )
        for r in filtered.results:
            assert r.dividend_yield >= 4.0
        # 確認 3008 不在結果中（因為下載失敗）
        assert all(r.stock_code != "3008" for r in filtered.results)

        pipeline.shutdown(wait=False)
