"""Incremental update correctness property test.

Feature: stock-valuation-optimization, Property 17: Incremental update correctness

For any set of stocks, those with last_updated > 4 hours ago SHALL be
re-downloaded; those with last_updated < 4 hours ago SHALL be skipped
(use cached data).

**Validates: Requirements 3.5**
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Tuple

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.data_pipeline import DataPipeline
from app.infra.error_handler import ErrorHandler
from app.infra.resilience.batch_downloader import BatchDownloader
from app.services.market_scanner import MarketScannerService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FOUR_HOURS_SECONDS = 4 * 3600
"""4 hours in seconds (the freshness threshold)."""

_ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
"""ISO format used by SQLiteCache."""

# A fixed "now" epoch for deterministic tests.
_FIXED_NOW = 1_700_000_000.0  # approx 2023-11-14 UTC


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Number of fresh stocks (last_updated within 4 hours)
n_fresh_st = st.integers(min_value=0, max_value=20)

# Number of stale stocks (last_updated > 4 hours ago)
n_stale_st = st.integers(min_value=0, max_value=20)

# Number of stocks with no cache record at all
n_missing_st = st.integers(min_value=0, max_value=10)

# Time offset for fresh stocks: between 1 second and just under 4 hours
fresh_offset_st = st.floats(
    min_value=1.0,
    max_value=_FOUR_HOURS_SECONDS - 1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Time offset for stale stocks: between 4 hours and 48 hours
stale_offset_st = st.floats(
    min_value=_FOUR_HOURS_SECONDS + 1.0,
    max_value=48 * 3600.0,
    allow_nan=False,
    allow_infinity=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stock_code(prefix: str, idx: int) -> str:
    """Generate a unique stock code for test purposes."""
    return f"{prefix}{idx:04d}"


def _epoch_to_iso(epoch: float) -> str:
    """Convert epoch timestamp to ISO format string."""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.strftime(_ISO_FORMAT)


def _setup_cache_with_records(
    db_path: str,
    fresh_codes: List[str],
    fresh_offsets: List[float],
    stale_codes: List[str],
    stale_offsets: List[float],
    now: float,
) -> SQLiteCache:
    """Create a SQLiteCache with pre-populated records.

    Args:
        db_path: Path to the temporary SQLite database.
        fresh_codes: Stock codes that should be considered fresh.
        fresh_offsets: Seconds before 'now' for each fresh stock's last_updated.
        stale_codes: Stock codes that should be considered stale.
        stale_offsets: Seconds before 'now' for each stale stock's last_updated.
        now: The fixed "current" epoch time.

    Returns:
        Initialized SQLiteCache instance.
    """
    cache = SQLiteCache(db_path=db_path, time_func=lambda: now)

    # Insert fresh records
    for code, offset in zip(fresh_codes, fresh_offsets):
        last_updated_ts = now - offset  # offset < 4h -> fresh
        record = {
            "stock_code": code,
            "stock_name": f"Stock {code}",
            "current_price": 100.0,
            "pe_ratio": 15.0,
            "roe": 12.0,
            "dividend_yield": 3.5,
            "market_cap": 500.0,
            "price_position": 0.5,
            "fundamental_score": 75.0,
            "fundamental_grade": "B",
            "last_updated": _epoch_to_iso(last_updated_ts),
        }
        cache.upsert_snapshot(record)

    # Insert stale records
    for code, offset in zip(stale_codes, stale_offsets):
        last_updated_ts = now - offset  # offset > 4h -> stale
        record = {
            "stock_code": code,
            "stock_name": f"Stock {code}",
            "current_price": 80.0,
            "pe_ratio": 20.0,
            "roe": 8.0,
            "dividend_yield": 2.0,
            "market_cap": 200.0,
            "price_position": 0.3,
            "fundamental_score": 60.0,
            "fundamental_grade": "C",
            "last_updated": _epoch_to_iso(last_updated_ts),
        }
        cache.upsert_snapshot(record)

    return cache


def _create_scanner_with_cache(cache: SQLiteCache) -> MarketScannerService:
    """Create a MarketScannerService with the given cache.

    Uses minimal stubs for DataPipeline, BatchDownloader, ErrorHandler
    since we only test _partition_by_freshness which doesn't use them.

    Args:
        cache: Pre-configured SQLiteCache.

    Returns:
        MarketScannerService instance.
    """
    # _partition_by_freshness only uses self._sqlite_cache and self._time_func
    # We can create the scanner with mock/stub dependencies for unused services
    scanner = object.__new__(MarketScannerService)
    scanner._sqlite_cache = cache
    scanner._time_func = cache._time_func
    # Set other attributes to avoid AttributeError if accidentally accessed
    scanner._data_pipeline = None  # type: ignore[assignment]
    scanner._batch_downloader = None  # type: ignore[assignment]
    scanner._error_handler = None  # type: ignore[assignment]
    scanner._lock = __import__("threading").Lock()
    return scanner


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestIncrementalUpdatePartition:
    """Property 17: Incremental update correctness.

    Verify that _partition_by_freshness correctly classifies stocks:
    - Stocks with last_updated >= 4 hours ago -> codes_to_download
    - Stocks with last_updated < 4 hours ago -> codes_from_cache
    - Stocks not in cache -> codes_to_download
    """

    @given(
        n_fresh=n_fresh_st,
        n_stale=n_stale_st,
    )
    @settings(max_examples=200, deadline=30000)
    def test_partition_correctness_fresh_and_stale(
        self,
        n_fresh: int,
        n_stale: int,
    ) -> None:
        """Fresh stocks go to cache set; stale stocks go to download set.

        Generates n_fresh fresh stocks and n_stale stale stocks,
        verifies _partition_by_freshness places them in the correct sets.
        """
        assume(n_fresh + n_stale > 0)

        fresh_codes = [_make_stock_code("F", i) for i in range(n_fresh)]
        stale_codes = [_make_stock_code("S", i) for i in range(n_stale)]

        # All fresh stocks have same offset (2 hours) for simplicity
        fresh_offsets = [2 * 3600.0] * n_fresh
        # All stale stocks have same offset (6 hours)
        stale_offsets = [6 * 3600.0] * n_stale

        all_codes = fresh_codes + stale_codes

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache = _setup_cache_with_records(
                db_path=db_path,
                fresh_codes=fresh_codes,
                fresh_offsets=fresh_offsets,
                stale_codes=stale_codes,
                stale_offsets=stale_offsets,
                now=_FIXED_NOW,
            )
            scanner = _create_scanner_with_cache(cache)

            to_download, from_cache = scanner._partition_by_freshness(all_codes)

            # Verify: all stale codes should be in to_download
            assert set(stale_codes) <= set(to_download), (
                f"Stale codes not all in to_download: "
                f"missing={set(stale_codes) - set(to_download)}"
            )

            # Verify: all fresh codes should be in from_cache
            assert set(fresh_codes) <= set(from_cache), (
                f"Fresh codes not all in from_cache: "
                f"missing={set(fresh_codes) - set(from_cache)}"
            )

            # Verify: no overlap between sets
            assert set(to_download).isdisjoint(set(from_cache)), (
                f"Overlap found: {set(to_download) & set(from_cache)}"
            )

            # Verify: union equals original input
            assert set(to_download) | set(from_cache) == set(all_codes), (
                "Union of partitions does not equal input set"
            )

            cache.close()
        finally:
            os.unlink(db_path)

    @given(
        n_missing=st.integers(min_value=1, max_value=15),
        n_fresh=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=150, deadline=30000)
    def test_missing_stocks_classified_as_download(
        self,
        n_missing: int,
        n_fresh: int,
    ) -> None:
        """Stocks not in cache should be classified as needing download.

        Generates stocks that exist in cache (fresh) and stocks that
        do not exist in cache at all.
        """
        fresh_codes = [_make_stock_code("F", i) for i in range(n_fresh)]
        missing_codes = [_make_stock_code("M", i) for i in range(n_missing)]

        fresh_offsets = [1 * 3600.0] * n_fresh  # 1 hour old -> fresh

        all_codes = fresh_codes + missing_codes

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache = _setup_cache_with_records(
                db_path=db_path,
                fresh_codes=fresh_codes,
                fresh_offsets=fresh_offsets,
                stale_codes=[],
                stale_offsets=[],
                now=_FIXED_NOW,
            )
            scanner = _create_scanner_with_cache(cache)

            to_download, from_cache = scanner._partition_by_freshness(all_codes)

            # All missing stocks must be in to_download
            assert set(missing_codes) <= set(to_download), (
                f"Missing codes not in to_download: "
                f"missing={set(missing_codes) - set(to_download)}"
            )

            # Fresh stocks should be in from_cache
            assert set(fresh_codes) <= set(from_cache), (
                f"Fresh codes not in from_cache: "
                f"missing={set(fresh_codes) - set(from_cache)}"
            )

            # No overlap
            assert set(to_download).isdisjoint(set(from_cache))

            # Union completeness
            assert set(to_download) | set(from_cache) == set(all_codes)

            cache.close()
        finally:
            os.unlink(db_path)

    @given(
        n_fresh=st.integers(min_value=0, max_value=15),
        n_stale=st.integers(min_value=0, max_value=15),
        n_missing=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=200, deadline=30000)
    def test_partition_preserves_all_codes(
        self,
        n_fresh: int,
        n_stale: int,
        n_missing: int,
    ) -> None:
        """Union of to_download and from_cache equals the input set.

        No stock is lost or duplicated during partitioning.
        """
        assume(n_fresh + n_stale + n_missing > 0)

        fresh_codes = [_make_stock_code("F", i) for i in range(n_fresh)]
        stale_codes = [_make_stock_code("S", i) for i in range(n_stale)]
        missing_codes = [_make_stock_code("M", i) for i in range(n_missing)]

        fresh_offsets = [3 * 3600.0] * n_fresh  # 3 hours -> fresh
        stale_offsets = [5 * 3600.0] * n_stale  # 5 hours -> stale

        all_codes = fresh_codes + stale_codes + missing_codes

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache = _setup_cache_with_records(
                db_path=db_path,
                fresh_codes=fresh_codes,
                fresh_offsets=fresh_offsets,
                stale_codes=stale_codes,
                stale_offsets=stale_offsets,
                now=_FIXED_NOW,
            )
            scanner = _create_scanner_with_cache(cache)

            to_download, from_cache = scanner._partition_by_freshness(all_codes)

            # No element lost
            result_set = set(to_download) | set(from_cache)
            input_set = set(all_codes)
            assert result_set == input_set, (
                f"Lost: {input_set - result_set}, "
                f"Extra: {result_set - input_set}"
            )

            # No duplicates within each partition
            assert len(to_download) == len(set(to_download)), (
                "Duplicates in to_download"
            )
            assert len(from_cache) == len(set(from_cache)), (
                "Duplicates in from_cache"
            )

            cache.close()
        finally:
            os.unlink(db_path)

    @given(
        fresh_offset=fresh_offset_st,
        stale_offset=stale_offset_st,
    )
    @settings(max_examples=200, deadline=30000)
    def test_boundary_classification_with_varying_offsets(
        self,
        fresh_offset: float,
        stale_offset: float,
    ) -> None:
        """Single fresh and single stale stock with varying time offsets.

        Verifies the 4-hour boundary is respected for arbitrary offsets.
        """
        fresh_code = "FR01"
        stale_code = "ST01"

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache = _setup_cache_with_records(
                db_path=db_path,
                fresh_codes=[fresh_code],
                fresh_offsets=[fresh_offset],
                stale_codes=[stale_code],
                stale_offsets=[stale_offset],
                now=_FIXED_NOW,
            )
            scanner = _create_scanner_with_cache(cache)

            to_download, from_cache = scanner._partition_by_freshness(
                [fresh_code, stale_code]
            )

            # fresh_offset < 4h -> should be in from_cache
            assert fresh_code in from_cache, (
                f"Fresh stock (offset={fresh_offset:.1f}s) "
                f"wrongly classified as needing download"
            )

            # stale_offset > 4h -> should be in to_download
            assert stale_code in to_download, (
                f"Stale stock (offset={stale_offset:.1f}s) "
                f"wrongly classified as cacheable"
            )

            cache.close()
        finally:
            os.unlink(db_path)

    @given(
        n_stocks=st.integers(min_value=1, max_value=20),
        offset_exactly_4h=st.just(_FOUR_HOURS_SECONDS),
    )
    @settings(max_examples=50, deadline=30000)
    def test_exact_threshold_boundary(
        self,
        n_stocks: int,
        offset_exactly_4h: float,
    ) -> None:
        """Stocks at exactly 4 hours boundary should be re-downloaded.

        The condition uses >= threshold, so exactly 4 hours means stale.
        """
        codes = [_make_stock_code("E", i) for i in range(n_stocks)]

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            cache = _setup_cache_with_records(
                db_path=db_path,
                fresh_codes=[],
                fresh_offsets=[],
                stale_codes=codes,
                stale_offsets=[offset_exactly_4h] * n_stocks,
                now=_FIXED_NOW,
            )
            scanner = _create_scanner_with_cache(cache)

            to_download, from_cache = scanner._partition_by_freshness(codes)

            # At exactly 4h boundary, elapsed >= threshold -> to_download
            assert set(codes) == set(to_download), (
                f"Stocks at exact 4h boundary should be in to_download, "
                f"but found in from_cache: {set(codes) & set(from_cache)}"
            )
            assert from_cache == [], (
                "No stock should be in from_cache at exact threshold"
            )

            cache.close()
        finally:
            os.unlink(db_path)
