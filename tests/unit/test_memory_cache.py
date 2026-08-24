"""LRU Memory Cache 單元測試。

驗證 MemoryCache 的核心行為：LRU 驅逐、per-type TTL、
淺複製保護、invalidate_by_stock、stats 統計一致性。
"""

import threading
import time
from typing import List

import pytest

from app.infra.cache.memory_cache import (
    CacheEntry,
    CacheEntryType,
    MemoryCache,
    TTL_CONFIG,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache() -> MemoryCache:
    """預設容量 200 的快取實例，使用固定時間函式。"""
    current_time = [0.0]

    def time_func() -> float:
        return current_time[0]

    c = MemoryCache(max_size=200, time_func=time_func)
    c._test_time = current_time  # type: ignore[attr-defined]
    return c


@pytest.fixture
def small_cache() -> MemoryCache:
    """容量 3 的小快取，方便測試 LRU 驅逐行為。"""
    current_time = [0.0]

    def time_func() -> float:
        return current_time[0]

    c = MemoryCache(max_size=3, time_func=time_func)
    c._test_time = current_time  # type: ignore[attr-defined]
    return c


def advance_time(cache: MemoryCache, seconds: float) -> None:
    """輔助函式：推進快取的時間。"""
    cache._test_time[0] += seconds  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 基本 get/set/delete 測試
# ---------------------------------------------------------------------------


class TestBasicOperations:
    """基本 CRUD 操作測試。"""

    def test_set_and_get(self, cache: MemoryCache) -> None:
        """設定後取得應回傳相同值。"""
        cache.set("key1", {"price": 500}, CacheEntryType.PRICE, stock_code="2330")
        result = cache.get("key1")
        assert result == {"price": 500}

    def test_get_nonexistent_key_returns_none(self, cache: MemoryCache) -> None:
        """取得不存在的鍵應回傳 None。"""
        result = cache.get("nonexistent")
        assert result is None

    def test_delete_existing_key(self, cache: MemoryCache) -> None:
        """刪除存在的鍵後應無法取得。"""
        cache.set("key1", "value1", CacheEntryType.PRICE)
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent_key_no_error(self, cache: MemoryCache) -> None:
        """刪除不存在的鍵不應拋出例外。"""
        cache.delete("nonexistent")  # Should not raise

    def test_set_overwrites_existing_key(self, cache: MemoryCache) -> None:
        """對同一鍵設定新值應覆寫舊值。"""
        cache.set("key1", "old_value", CacheEntryType.PRICE)
        cache.set("key1", "new_value", CacheEntryType.FINANCIAL)
        assert cache.get("key1") == "new_value"

    def test_clear_removes_all_entries(self, cache: MemoryCache) -> None:
        """clear() 應清除所有條目並重置統計。"""
        cache.set("k1", "v1", CacheEntryType.PRICE)
        cache.set("k2", "v2", CacheEntryType.FINANCIAL)
        cache.clear()
        # 統計應在 clear 後立即歸零
        stats = cache.stats()
        assert stats["current_size"] == 0
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0
        assert stats["eviction_count"] == 0
        # 條目已清除，get 回傳 None
        assert cache.get("k1") is None
        assert cache.get("k2") is None


# ---------------------------------------------------------------------------
# LRU 驅逐測試
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """LRU 驅逐策略測試。"""

    def test_evicts_lru_when_full(self, small_cache: MemoryCache) -> None:
        """快取滿時應驅逐最久未使用的條目。"""
        small_cache.set("a", 1, CacheEntryType.PRICE)
        small_cache.set("b", 2, CacheEntryType.PRICE)
        small_cache.set("c", 3, CacheEntryType.PRICE)
        # 快取已滿（容量 3），新增第四筆應驅逐 "a"
        small_cache.set("d", 4, CacheEntryType.PRICE)
        assert small_cache.get("a") is None
        assert small_cache.get("b") == 2
        assert small_cache.get("c") == 3
        assert small_cache.get("d") == 4

    def test_get_refreshes_lru_order(self, small_cache: MemoryCache) -> None:
        """get() 應刷新條目的存取順序。"""
        small_cache.set("a", 1, CacheEntryType.PRICE)
        small_cache.set("b", 2, CacheEntryType.PRICE)
        small_cache.set("c", 3, CacheEntryType.PRICE)
        # 存取 "a"，使其成為最近使用
        small_cache.get("a")
        # 新增 "d"，應驅逐 "b"（最久未使用）
        small_cache.set("d", 4, CacheEntryType.PRICE)
        assert small_cache.get("b") is None
        assert small_cache.get("a") == 1

    def test_capacity_never_exceeded(self, small_cache: MemoryCache) -> None:
        """快取條目數永不超過容量上限。"""
        for i in range(100):
            small_cache.set(f"key_{i}", i, CacheEntryType.PRICE)
        stats = small_cache.stats()
        assert stats["current_size"] <= 3

    def test_eviction_count_increments(self, small_cache: MemoryCache) -> None:
        """每次驅逐應正確增加 eviction_count。"""
        small_cache.set("a", 1, CacheEntryType.PRICE)
        small_cache.set("b", 2, CacheEntryType.PRICE)
        small_cache.set("c", 3, CacheEntryType.PRICE)
        small_cache.set("d", 4, CacheEntryType.PRICE)  # evicts "a"
        small_cache.set("e", 5, CacheEntryType.PRICE)  # evicts "b"
        stats = small_cache.stats()
        assert stats["eviction_count"] == 2

    def test_overwrite_does_not_trigger_eviction(
        self, small_cache: MemoryCache
    ) -> None:
        """覆寫已存在的鍵不應觸發驅逐。"""
        small_cache.set("a", 1, CacheEntryType.PRICE)
        small_cache.set("b", 2, CacheEntryType.PRICE)
        small_cache.set("c", 3, CacheEntryType.PRICE)
        # 覆寫 "a"，不應驅逐
        small_cache.set("a", 10, CacheEntryType.PRICE)
        stats = small_cache.stats()
        assert stats["eviction_count"] == 0
        assert stats["current_size"] == 3


# ---------------------------------------------------------------------------
# TTL 過期測試
# ---------------------------------------------------------------------------


class TestTTLExpiration:
    """Per-type TTL 過期行為測試。"""

    def test_price_ttl_5_minutes(self, cache: MemoryCache) -> None:
        """股價快取 5 分鐘後過期。"""
        cache.set("price:2330", 500, CacheEntryType.PRICE)
        # 4 分 59 秒未過期
        advance_time(cache, 299)
        assert cache.get("price:2330") == 500
        # 5 分 1 秒已過期
        advance_time(cache, 2)
        assert cache.get("price:2330") is None

    def test_financial_ttl_1_hour(self, cache: MemoryCache) -> None:
        """財報快取 1 小時後過期。"""
        cache.set("fin:2330", {"eps": 15.5}, CacheEntryType.FINANCIAL)
        advance_time(cache, 3599)
        assert cache.get("fin:2330") is not None
        advance_time(cache, 2)
        assert cache.get("fin:2330") is None

    def test_company_ttl_24_hours(self, cache: MemoryCache) -> None:
        """公司資訊快取 24 小時後過期。"""
        cache.set("company:2330", {"name": "TSMC"}, CacheEntryType.COMPANY)
        advance_time(cache, 86399)
        assert cache.get("company:2330") is not None
        advance_time(cache, 2)
        assert cache.get("company:2330") is None

    def test_chip_ttl_4_hours(self, cache: MemoryCache) -> None:
        """籌碼快取 4 小時後過期。"""
        cache.set("chip:2330", {"foreign_buy": 1000}, CacheEntryType.CHIP)
        advance_time(cache, 14399)
        assert cache.get("chip:2330") is not None
        advance_time(cache, 2)
        assert cache.get("chip:2330") is None

    def test_expired_entry_triggers_miss(self, cache: MemoryCache) -> None:
        """過期條目存取應計為 miss。"""
        cache.set("k", "v", CacheEntryType.PRICE)
        advance_time(cache, 301)
        cache.get("k")
        stats = cache.stats()
        assert stats["miss_count"] == 1
        assert stats["hit_count"] == 0


# ---------------------------------------------------------------------------
# 淺複製保護測試
# ---------------------------------------------------------------------------


class TestShallowCopyProtection:
    """取值回傳淺複製，防止外部修改汙染快取。"""

    def test_external_modification_does_not_affect_cache(
        self, cache: MemoryCache
    ) -> None:
        """外部修改回傳值不應影響快取內容。"""
        original = {"price": 500, "volume": 10000}
        cache.set("k1", original, CacheEntryType.PRICE)
        result = cache.get("k1")
        assert result is not None
        result["price"] = 999  # 修改回傳值
        # 再次取得快取值應保持不變
        assert cache.get("k1") == {"price": 500, "volume": 10000}

    def test_list_modification_does_not_affect_cache(
        self, cache: MemoryCache
    ) -> None:
        """外部修改回傳的 list 不應影響快取內容。"""
        original = [1, 2, 3]
        cache.set("k1", original, CacheEntryType.PRICE)
        result = cache.get("k1")
        assert result is not None
        result.append(4)
        assert cache.get("k1") == [1, 2, 3]

    def test_returned_value_is_different_object(
        self, cache: MemoryCache
    ) -> None:
        """回傳值應為不同的物件（非同一參考）。"""
        original = {"data": [1, 2, 3]}
        cache.set("k1", original, CacheEntryType.PRICE)
        result = cache.get("k1")
        assert result is not original


# ---------------------------------------------------------------------------
# invalidate_by_stock 測試
# ---------------------------------------------------------------------------


class TestInvalidateByStock:
    """清除特定股票所有條目。"""

    def test_removes_all_entries_for_stock(self, cache: MemoryCache) -> None:
        """應移除指定股票的所有快取條目。"""
        cache.set("price:2330", 500, CacheEntryType.PRICE, stock_code="2330")
        cache.set("fin:2330", {}, CacheEntryType.FINANCIAL, stock_code="2330")
        cache.set("chip:2330", {}, CacheEntryType.CHIP, stock_code="2330")
        cache.set("price:2317", 100, CacheEntryType.PRICE, stock_code="2317")

        count = cache.invalidate_by_stock("2330")
        assert count == 3
        assert cache.get("price:2330") is None
        assert cache.get("fin:2330") is None
        assert cache.get("chip:2330") is None
        # 其他股票不受影響
        assert cache.get("price:2317") == 100

    def test_returns_zero_when_no_match(self, cache: MemoryCache) -> None:
        """無匹配條目時應回傳 0。"""
        cache.set("price:2330", 500, CacheEntryType.PRICE, stock_code="2330")
        count = cache.invalidate_by_stock("9999")
        assert count == 0

    def test_invalidate_empty_cache(self, cache: MemoryCache) -> None:
        """空快取 invalidate 不應拋出例外。"""
        count = cache.invalidate_by_stock("2330")
        assert count == 0


# ---------------------------------------------------------------------------
# invalidate_prefix 測試
# ---------------------------------------------------------------------------


class TestInvalidatePrefix:
    """批次失效前綴匹配條目。"""

    def test_removes_entries_with_matching_prefix(
        self, cache: MemoryCache
    ) -> None:
        """應移除所有前綴匹配的條目。"""
        cache.set("price:2330:daily", 500, CacheEntryType.PRICE)
        cache.set("price:2330:weekly", 510, CacheEntryType.PRICE)
        cache.set("fin:2330:q4", {}, CacheEntryType.FINANCIAL)

        count = cache.invalidate_prefix("price:2330")
        assert count == 2
        assert cache.get("price:2330:daily") is None
        assert cache.get("price:2330:weekly") is None
        assert cache.get("fin:2330:q4") is not None


# ---------------------------------------------------------------------------
# stats 統計測試
# ---------------------------------------------------------------------------


class TestStats:
    """快取統計計數器一致性。"""

    def test_hit_and_miss_counts(self, cache: MemoryCache) -> None:
        """hit_count 與 miss_count 應正確計數。"""
        cache.set("k1", "v1", CacheEntryType.PRICE)
        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("nonexistent")  # miss
        stats = cache.stats()
        assert stats["hit_count"] == 2
        assert stats["miss_count"] == 1

    def test_stats_current_size(self, cache: MemoryCache) -> None:
        """current_size 應反映目前條目數量。"""
        cache.set("a", 1, CacheEntryType.PRICE)
        cache.set("b", 2, CacheEntryType.PRICE)
        assert cache.stats()["current_size"] == 2
        cache.delete("a")
        assert cache.stats()["current_size"] == 1

    def test_stats_after_clear(self, cache: MemoryCache) -> None:
        """clear() 後統計應重置為零。"""
        cache.set("k", "v", CacheEntryType.PRICE)
        cache.get("k")
        cache.clear()
        stats = cache.stats()
        assert stats == {
            "hit_count": 0,
            "miss_count": 0,
            "eviction_count": 0,
            "current_size": 0,
        }

    def test_hit_plus_miss_equals_total_queries(
        self, cache: MemoryCache
    ) -> None:
        """hit_count + miss_count 應等於總查詢次數。"""
        cache.set("a", 1, CacheEntryType.PRICE)
        cache.set("b", 2, CacheEntryType.FINANCIAL)

        total_queries = 0
        # 幾次 hit
        cache.get("a")
        total_queries += 1
        cache.get("b")
        total_queries += 1
        # 幾次 miss
        cache.get("c")
        total_queries += 1
        cache.get("d")
        total_queries += 1

        stats = cache.stats()
        assert stats["hit_count"] + stats["miss_count"] == total_queries


# ---------------------------------------------------------------------------
# 執行緒安全測試
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """多執行緒並行存取測試。"""

    def test_concurrent_set_and_get(self) -> None:
        """多執行緒同時讀寫不應發生資料損毀。"""
        cache = MemoryCache(max_size=100)
        errors: List[Exception] = []

        def writer(start: int) -> None:
            try:
                for i in range(100):
                    cache.set(
                        f"key_{start}_{i}",
                        i,
                        CacheEntryType.PRICE,
                        stock_code=str(start),
                    )
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(200):
                    cache.get("key_0_50")
                    cache.stats()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(1,)),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 容量不應超限
        assert cache.stats()["current_size"] <= 100


# ---------------------------------------------------------------------------
# CacheProtocol 相容性測試
# ---------------------------------------------------------------------------


class TestCacheProtocolCompatibility:
    """驗證 MemoryCache 實作 CacheProtocol 介面。"""

    def test_implements_cache_protocol(self) -> None:
        """MemoryCache 應為 CacheProtocol 的結構化子型別。"""
        from app.core.protocols import CacheProtocol

        cache = MemoryCache()
        assert isinstance(cache, CacheProtocol)


# ---------------------------------------------------------------------------
# 邊界情境
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """邊界情境測試。"""

    def test_max_size_one(self) -> None:
        """容量為 1 的快取應正常運作。"""
        cache = MemoryCache(max_size=1)
        cache.set("a", 1, CacheEntryType.PRICE)
        cache.set("b", 2, CacheEntryType.PRICE)
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_none_value_cached(self, cache: MemoryCache) -> None:
        """None 作為值也應可快取（雖然 get 回傳 None 有歧義，此處驗證內部行為）。"""
        # 注意：快取 None 值時 get 回傳 None 與 miss 無法區分
        # 但實作上 set None 是允許的
        cache.set("k", None, CacheEntryType.PRICE)
        # get 回傳 copy.copy(None) 即 None，但 hit 會增加
        cache.get("k")
        stats = cache.stats()
        assert stats["hit_count"] == 1

    def test_empty_string_key(self, cache: MemoryCache) -> None:
        """空字串作為鍵也應正常運作。"""
        cache.set("", "empty_key", CacheEntryType.PRICE)
        assert cache.get("") == "empty_key"

    def test_large_value(self, cache: MemoryCache) -> None:
        """大型值（如長 list）應可正常快取與取回。"""
        big_data = list(range(10000))
        cache.set("big", big_data, CacheEntryType.FINANCIAL)
        result = cache.get("big")
        assert result == big_data
        # 確認是淺複製
        assert result is not big_data
