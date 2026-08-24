"""LRU Cache 屬性測試。

Feature: stock-valuation-optimization, Property 6, 7, 8: LRU Cache invariants

使用 Hypothesis 驗證 LRU Memory Cache 的核心不變式：
- Property 6: 任意操作序列後，快取大小永不超過 max_size；
  外部修改回傳值不影響快取內容
- Property 7: TTL 內存取回傳有效資料；超過 TTL 回傳 None
- Property 8: hit_count + miss_count == 總 get() 呼叫次數

**Validates: Requirements 5.1, 5.3, 5.5, 10.5**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.infra.cache.memory_cache import CacheEntryType, MemoryCache


# ---------------------------------------------------------------------------
# Property 6: LRU 快取容量上限不變式
# Feature: stock-valuation-optimization, Property 6: LRU cache capacity invariant
# ---------------------------------------------------------------------------


class TestCacheCapacityProperty:
    """驗證快取容量上限與外部修改隔離性。

    **Validates: Requirements 5.1, 5.5**
    """

    @given(
        n_sets=st.integers(min_value=1, max_value=500),
        max_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200, deadline=30000)
    def test_size_never_exceeds_max(self, n_sets: int, max_size: int) -> None:
        """任意數量的 set 操作後，current_size <= max_size。

        Args:
            n_sets: 執行的 set 操作次數。
            max_size: 快取容量上限。
        """
        cache = MemoryCache(max_size=max_size)
        for i in range(n_sets):
            cache.set(f"key_{i}", i, CacheEntryType.PRICE, stock_code="TEST")
        stats = cache.stats()
        assert stats["current_size"] <= max_size

    @given(
        max_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200, deadline=30000)
    def test_external_mutation_does_not_affect_cache(self, max_size: int) -> None:
        """取得的回傳值經外部修改後，快取內容不受影響。

        Args:
            max_size: 快取容量上限。
        """
        cache = MemoryCache(max_size=max_size)
        original_data = {"price": 100.0, "volume": 5000}
        cache.set("mutable_key", original_data, CacheEntryType.PRICE)

        # 取得回傳值並修改
        returned = cache.get("mutable_key")
        assert returned is not None
        returned["price"] = 999.99
        returned["extra_field"] = "injected"

        # 快取內部不受影響
        cached_again = cache.get("mutable_key")
        assert cached_again is not None
        assert cached_again["price"] == 100.0
        assert "extra_field" not in cached_again


# ---------------------------------------------------------------------------
# Property 7: 快取 TTL 過期正確性
# Feature: stock-valuation-optimization, Property 7: Cache TTL expiration correctness
# ---------------------------------------------------------------------------


class TestCacheTTLProperty:
    """驗證 TTL 時間內回傳有效資料、超過 TTL 回傳 None。

    **Validates: Requirements 5.1, 10.5**
    """

    @given(ttl_fraction=st.floats(min_value=0.01, max_value=0.99))
    @settings(max_examples=200, deadline=30000)
    def test_within_ttl_returns_data(self, ttl_fraction: float) -> None:
        """TTL 內存取回傳有效資料。

        PRICE TTL = 300s，以 ttl_fraction * 300 作為經過時間，
        確保仍在有效期內。

        Args:
            ttl_fraction: TTL 的比例（0.01~0.99）。
        """
        current_time: list[float] = [0.0]
        cache = MemoryCache(max_size=100, time_func=lambda: current_time[0])
        cache.set("k", "value", CacheEntryType.PRICE)
        current_time[0] = 300 * ttl_fraction  # within TTL
        assert cache.get("k") == "value"

    @given(extra_seconds=st.floats(min_value=1.0, max_value=1000.0))
    @settings(max_examples=200, deadline=30000)
    def test_after_ttl_returns_none(self, extra_seconds: float) -> None:
        """超過 TTL 後存取回傳 None。

        PRICE TTL = 300s，經過 300 + extra_seconds 秒後取值應為 None。

        Args:
            extra_seconds: 超過 TTL 的額外秒數。
        """
        current_time: list[float] = [0.0]
        cache = MemoryCache(max_size=100, time_func=lambda: current_time[0])
        cache.set("k", "value", CacheEntryType.PRICE)
        current_time[0] = 300 + extra_seconds  # past TTL
        assert cache.get("k") is None


# ---------------------------------------------------------------------------
# Property 8: 快取統計一致性
# Feature: stock-valuation-optimization, Property 8: Cache stats consistency
# ---------------------------------------------------------------------------


class TestCacheStatsProperty:
    """驗證 hit_count + miss_count == 總 get() 呼叫次數。

    **Validates: Requirements 5.3**
    """

    @given(
        n_sets=st.integers(min_value=0, max_value=20),
        n_gets=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200, deadline=30000)
    def test_hit_plus_miss_equals_total_gets(
        self, n_sets: int, n_gets: int
    ) -> None:
        """任意 set/get 操作序列後，hit + miss == 總 get 次數。

        Args:
            n_sets: 預先 set 的條目數量。
            n_gets: 執行的 get 操作次數。
        """
        cache = MemoryCache(max_size=100)
        for i in range(n_sets):
            cache.set(f"key_{i}", i, CacheEntryType.PRICE)
        for i in range(n_gets):
            cache.get(f"key_{i % (n_sets + 5)}")
        stats = cache.stats()
        assert stats["hit_count"] + stats["miss_count"] == n_gets
