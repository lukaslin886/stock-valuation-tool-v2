"""Unit tests for app/services/chip_analyzer.py (ChipAnalyzer).

Written 2026-09-06 to close a real coverage gap: chip_analyzer.py had
181/233 statements (22.32%) uncovered before this file (see HANDOFF.md
10.6/10.7 — the coverage-narrowing shortcut was rejected in favor of
actually writing tests). Uses a real SQLiteCache against a temp DB file
(not mocked) and a real ErrorHandler, and only monkeypatches the actual
network boundary (`_get_finmind_loader`), matching the DI design the class
already has (data_pipeline/sqlite_cache/error_handler/time_func are all
constructor-injected specifically to make this kind of testing possible).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.error_handler import ErrorHandler
from app.services.chip_analyzer import ChipAnalysisResult, ChipAnalyzer, UpdateResult


@pytest.fixture
def temp_cache():
    """Real SQLiteCache backed by a temp file (not a mock)."""
    db_dir = tempfile.mkdtemp(prefix="chip_analyzer_test_")
    db_path = os.path.join(db_dir, "test.db")
    cache = SQLiteCache(db_path=db_path)
    yield cache
    cache.close()
    shutil.rmtree(db_dir, ignore_errors=True)


def _fixed_time(ts: datetime):
    """Build a time_func that always returns the given datetime's epoch seconds."""
    return lambda: ts.timestamp()


def _make_analyzer(temp_cache: SQLiteCache, now: datetime | None = None) -> ChipAnalyzer:
    time_func = _fixed_time(now) if now is not None else __import__("time").time
    return ChipAnalyzer(
        data_pipeline=None,
        sqlite_cache=temp_cache,
        error_handler=ErrorHandler(),
        time_func=time_func,
    )


def _record(
    trade_date: str,
    foreign_buy: int = 0,
    foreign_sell: int = 0,
    trust_buy: int = 0,
    trust_sell: int = 0,
    dealer_buy: int = 0,
    dealer_sell: int = 0,
) -> Dict[str, Any]:
    return {
        "trade_date": trade_date,
        "foreign_buy": foreign_buy,
        "foreign_sell": foreign_sell,
        "trust_buy": trust_buy,
        "trust_sell": trust_sell,
        "dealer_buy": dealer_buy,
        "dealer_sell": dealer_sell,
    }


class TestInvestorNameClassification:
    """_is_foreign_investor / _is_trust_investor / _is_dealer_investor."""

    @pytest.mark.parametrize(
        "name", ["Foreign_Investor", "foreign", "外資", "外國機構", "FINI"]
    )
    def test_foreign_matches(self, temp_cache: SQLiteCache, name: str) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_foreign_investor(name) is True
        assert analyzer._is_trust_investor(name) is False
        assert analyzer._is_dealer_investor(name) is False

    @pytest.mark.parametrize("name", ["Investment_Trust", "投信", "SITC"])
    def test_trust_matches(self, temp_cache: SQLiteCache, name: str) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_trust_investor(name) is True
        assert analyzer._is_foreign_investor(name) is False

    @pytest.mark.parametrize("name", ["Dealer", "自營商", "自營"])
    def test_dealer_matches(self, temp_cache: SQLiteCache, name: str) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_dealer_investor(name) is True

    def test_unknown_name_matches_none(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_foreign_investor("散戶") is False
        assert analyzer._is_trust_investor("散戶") is False
        assert analyzer._is_dealer_investor("散戶") is False


class TestConsecutiveBuyAndNetBuy:
    """_count_consecutive_buy / _sum_net_buy / calculate_consecutive_buy_days /
    calculate_holding_change (pure calculation logic)."""

    def test_count_consecutive_buy_all_positive(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        records = [
            _record("2026-09-05", foreign_buy=10, foreign_sell=2),
            _record("2026-09-04", foreign_buy=5, foreign_sell=1),
            _record("2026-09-03", foreign_buy=3, foreign_sell=3),  # net 0, breaks
        ]
        assert analyzer._count_consecutive_buy(records, "foreign_buy", "foreign_sell") == 2

    def test_count_consecutive_buy_breaks_immediately(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        records = [_record("2026-09-05", foreign_buy=1, foreign_sell=5)]
        assert analyzer._count_consecutive_buy(records, "foreign_buy", "foreign_sell") == 0

    def test_count_consecutive_buy_empty(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._count_consecutive_buy([], "foreign_buy", "foreign_sell") == 0

    def test_sum_net_buy(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        records = [
            _record("2026-09-05", foreign_buy=10, foreign_sell=2, trust_buy=5, trust_sell=1, dealer_buy=1, dealer_sell=1),
            _record("2026-09-04", foreign_buy=3, foreign_sell=8, trust_buy=0, trust_sell=0, dealer_buy=0, dealer_sell=0),
        ]
        # day1 net = (10-2)+(5-1)+(1-1) = 12 ; day2 net = (3-8) = -5 ; total = 7
        assert analyzer._sum_net_buy(records) == 7

    def test_sum_net_buy_empty(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._sum_net_buy([]) == 0.0

    def test_calculate_consecutive_buy_days_no_records(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        result = analyzer.calculate_consecutive_buy_days("9999")
        assert result == {"foreign": 0, "trust": 0, "dealer": 0}

    def test_calculate_consecutive_buy_days_with_records(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        temp_cache.bulk_upsert_chip_data([
            {"stock_code": "2330", "trade_date": "2026-09-05", "foreign_buy": 10, "foreign_sell": 2,
             "trust_buy": 5, "trust_sell": 1, "dealer_buy": 0, "dealer_sell": 3},
            {"stock_code": "2330", "trade_date": "2026-09-04", "foreign_buy": 4, "foreign_sell": 1,
             "trust_buy": 0, "trust_sell": 2, "dealer_buy": 0, "dealer_sell": 1},
        ])
        result = analyzer.calculate_consecutive_buy_days("2330")
        assert result["foreign"] == 2
        assert result["trust"] == 1
        assert result["dealer"] == 0

    def test_calculate_holding_change_no_records(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        result = analyzer.calculate_holding_change("9999")
        assert result == {"5d": 0.0, "20d": 0.0, "60d": 0.0}

    def test_calculate_holding_change_with_records(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        temp_cache.bulk_upsert_chip_data([
            {"stock_code": "2330", "trade_date": "2026-09-05", "foreign_buy": 10, "foreign_sell": 0,
             "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0},
        ])
        result = analyzer.calculate_holding_change("2330")
        assert result["5d"] == 10.0
        assert result["20d"] == 10.0
        assert result["60d"] == 10.0


class TestCacheValidity:
    """_is_cache_valid."""

    def test_empty_records_invalid(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_cache_valid([]) is False

    def test_missing_last_updated_invalid(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_cache_valid([{"trade_date": "2026-09-05"}]) is False

    def test_malformed_last_updated_invalid(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._is_cache_valid([{"last_updated": "not-a-date"}]) is False

    def test_fresh_cache_is_valid(self, temp_cache: SQLiteCache) -> None:
        now = datetime.now(tz=timezone.utc)
        analyzer = _make_analyzer(temp_cache, now=now)
        one_hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        assert analyzer._is_cache_valid([{"last_updated": one_hour_ago}]) is True

    def test_stale_cache_is_invalid(self, temp_cache: SQLiteCache) -> None:
        now = datetime.now(tz=timezone.utc)
        analyzer = _make_analyzer(temp_cache, now=now)
        five_hours_ago = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
        assert analyzer._is_cache_valid([{"last_updated": five_hours_ago}]) is False


class TestNormalizeInstitutionalData:
    """_normalize_institutional_data — FinMind raw -> per-day normalized rows."""

    def test_empty_dataframe_returns_none(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        assert analyzer._normalize_institutional_data(pd.DataFrame(), "2330") is None

    def test_missing_required_columns_returns_none(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        df = pd.DataFrame([{"foo": 1, "bar": 2}])
        assert analyzer._normalize_institutional_data(df, "2330") is None

    def test_standard_columns_grouped_by_investor_type(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        df = pd.DataFrame([
            {"date": "2026-09-05", "name": "Foreign_Investor", "buy": 100, "sell": 20},
            {"date": "2026-09-05", "name": "Investment_Trust", "buy": 30, "sell": 5},
            {"date": "2026-09-05", "name": "Dealer_self", "buy": 10, "sell": 1},
            {"date": "2026-09-04", "name": "Foreign_Investor", "buy": 50, "sell": 50},
        ])
        result = analyzer._normalize_institutional_data(df, "2330")
        assert result is not None
        assert len(result) == 2

        row_0905 = result[result["trade_date"] == "2026-09-05"].iloc[0]
        assert row_0905["foreign_buy"] == 100
        assert row_0905["foreign_sell"] == 20
        assert row_0905["trust_buy"] == 30
        assert row_0905["trust_sell"] == 5
        assert row_0905["dealer_buy"] == 10
        assert row_0905["dealer_sell"] == 1
        assert row_0905["stock_code"] == "2330"

    def test_alternate_column_names(self, temp_cache: SQLiteCache) -> None:
        """FinMind may use trade_date/investor_name/buy_volume/sell_volume."""
        analyzer = _make_analyzer(temp_cache)
        df = pd.DataFrame([
            {"trade_date": "2026-09-05", "investor_name": "外資", "buy_volume": 200, "sell_volume": 10},
        ])
        result = analyzer._normalize_institutional_data(df, "2330")
        assert result is not None
        assert result.iloc[0]["foreign_buy"] == 200

    def test_unrecognized_investor_name_contributes_nothing(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        df = pd.DataFrame([
            {"date": "2026-09-05", "name": "散戶", "buy": 999, "sell": 999},
        ])
        result = analyzer._normalize_institutional_data(df, "2330")
        assert result is not None
        row = result.iloc[0]
        assert row["foreign_buy"] == 0
        assert row["trust_buy"] == 0
        assert row["dealer_buy"] == 0


class TestPersistChipData:
    def test_persist_writes_through_to_cache(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        df = pd.DataFrame([
            {"trade_date": "2026-09-05", "foreign_buy": 10, "foreign_sell": 2,
             "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0},
        ])
        analyzer._persist_chip_data("2330", df)
        records = temp_cache.get_chip_data("2330", days=60)
        assert len(records) == 1
        assert records[0]["foreign_buy"] == 10

    def test_persist_empty_dataframe_is_noop(self, temp_cache: SQLiteCache) -> None:
        analyzer = _make_analyzer(temp_cache)
        analyzer._persist_chip_data("2330", pd.DataFrame())
        assert temp_cache.get_chip_data("2330", days=60) == []


class TestGetFinmindLoader:
    def test_no_token_returns_none(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        monkeypatch.delenv("FINMIND_TOKEN", raising=False)
        assert analyzer._get_finmind_loader() is None

    def test_loader_init_exception_returns_none(
        self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(temp_cache)
        monkeypatch.setenv("FINMIND_TOKEN", "fake-token")

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("network unreachable")

        import FinMind.data as finmind_data_module

        monkeypatch.setattr(finmind_data_module, "DataLoader", _boom)
        assert analyzer._get_finmind_loader() is None


class TestFetchChipDataFromApi:
    def test_loader_unavailable_returns_none(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        monkeypatch.setattr(analyzer, "_get_finmind_loader", lambda: None)
        assert analyzer._fetch_chip_data_from_api("2330") is None

    def test_api_call_raises_returns_none_and_records_error(
        self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(temp_cache)
        fake_loader = MagicMock()
        fake_loader.taiwan_stock_institutional_investors.side_effect = RuntimeError("boom")
        monkeypatch.setattr(analyzer, "_get_finmind_loader", lambda: fake_loader)
        assert analyzer._fetch_chip_data_from_api("2330") is None

    def test_empty_response_returns_none(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        fake_loader = MagicMock()
        fake_loader.taiwan_stock_institutional_investors.return_value = pd.DataFrame()
        monkeypatch.setattr(analyzer, "_get_finmind_loader", lambda: fake_loader)
        assert analyzer._fetch_chip_data_from_api("2330") is None

    def test_valid_response_normalized(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        fake_loader = MagicMock()
        fake_loader.taiwan_stock_institutional_investors.return_value = pd.DataFrame([
            {"date": "2026-09-05", "name": "Foreign_Investor", "buy": 100, "sell": 20},
        ])
        monkeypatch.setattr(analyzer, "_get_finmind_loader", lambda: fake_loader)
        result = analyzer._fetch_chip_data_from_api("2330")
        assert result is not None
        assert result.iloc[0]["foreign_buy"] == 100


class TestGetChipDataFullFlow:
    """get_chip_data — the main public entrypoint, exercising all 4 branches."""

    def test_valid_cache_hit_skips_api(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        temp_cache.bulk_upsert_chip_data([
            {"stock_code": "2330", "trade_date": "2026-09-05", "foreign_buy": 10, "foreign_sell": 0,
             "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0},
        ])

        def _should_not_be_called(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("API should not be called on a valid cache hit")

        monkeypatch.setattr(analyzer, "_fetch_chip_data_from_api", _should_not_be_called)
        result = analyzer.get_chip_data("2330")
        assert result.data_available is True
        assert result.foreign_consecutive_buy == 1

    def test_cache_miss_fetches_and_persists(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        fresh_df = pd.DataFrame([
            {"trade_date": "2026-09-05", "foreign_buy": 5, "foreign_sell": 0,
             "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0},
        ])
        monkeypatch.setattr(analyzer, "_fetch_chip_data_from_api", lambda code, days=60: fresh_df)
        result = analyzer.get_chip_data("2330")
        assert result.data_available is True
        assert result.foreign_consecutive_buy == 1
        # verify it was actually persisted, not just returned in-memory
        assert temp_cache.get_chip_data("2330", days=60) != []

    def test_api_fails_falls_back_to_stale_cache(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)
        # Seed a stale (old) cache entry directly, bypassing freshness.
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        temp_cache.bulk_upsert_chip_data([
            {"stock_code": "2330", "trade_date": "2026-09-01", "foreign_buy": 1, "foreign_sell": 0,
             "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0,
             "last_updated": old_ts},
        ])
        monkeypatch.setattr(analyzer, "_fetch_chip_data_from_api", lambda code, days=60: None)
        result = analyzer.get_chip_data("2330")
        assert result.data_available is True
        assert result.unavailable_reason is not None
        assert "過期" in result.unavailable_reason

    def test_no_cache_and_api_fails_returns_unavailable(
        self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = _make_analyzer(temp_cache)
        monkeypatch.setattr(analyzer, "_fetch_chip_data_from_api", lambda code, days=60: None)
        result = analyzer.get_chip_data("9999")
        assert result.data_available is False
        assert result.unavailable_reason == "籌碼資料不可用"


class TestUpdateChipData:
    def test_batch_success_and_failure_mix(self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch) -> None:
        analyzer = _make_analyzer(temp_cache)

        def _fake_fetch(code: str, days: int = 60):
            if code == "2330":
                return pd.DataFrame([
                    {"trade_date": "2026-09-05", "foreign_buy": 1, "foreign_sell": 0,
                     "trust_buy": 0, "trust_sell": 0, "dealer_buy": 0, "dealer_sell": 0},
                ])
            if code == "0000":
                raise RuntimeError("simulated failure")
            return None  # empty result for e.g. "9999"

        monkeypatch.setattr(analyzer, "_fetch_chip_data_from_api", _fake_fetch)
        result = analyzer.update_chip_data(["2330", "9999", "0000"])

        assert isinstance(result, UpdateResult)
        assert result.total == 3
        assert result.success_count == 1
        assert result.failed_count == 2
        assert "9999" in result.failed_codes
        assert "0000" in result.failed_codes
