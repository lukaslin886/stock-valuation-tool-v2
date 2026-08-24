"""Tests for SQLite cache schema behavior."""

import sqlite3

from app.data.cache.sqlite_cache import SQLiteCache


class TestSQLiteCacheSchema:
    """Validate SQLite cache schema setup."""

    def test_init_cache_creates_ttl_indexes(self, tmp_path) -> None:
        """TTL validation paths should have dedicated indexes."""
        db_path = tmp_path / "cache.db"

        SQLiteCache(db_path=str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA index_list('price_data')")
        price_indexes = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA index_list('financial_data')")
        financial_indexes = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA index_list('stock_info')")
        stock_info_indexes = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "idx_price_data_stock_code_update_time" in price_indexes
        assert "idx_financial_data_stock_code_update_time" in financial_indexes
        assert "idx_stock_info_update_time" in stock_info_indexes