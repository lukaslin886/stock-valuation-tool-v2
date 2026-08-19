"""LRU Memory Cache 模組。

使用 OrderedDict 實作 LRU（Least Recently Used）快取策略，
搭配 per-type TTL 配置，提供執行緒安全的記憶體快取層。

核心特性：
    - 容量上限 200 筆（可配置），滿時驅逐最久未使用條目
    - Per-type TTL：股價 5min、財報 1hr、公司資訊 24hr、籌碼 4hr
    - 取值回傳淺複製（copy.copy()），防止外部修改汙染快取
    - invalidate_by_stock() 清除特定股票所有條目
    - stats() 回傳 hit_count、miss_count、eviction_count
    - 執行緒安全（threading.Lock）
    - time_func 可注入以利測試

Usage::

    from app.infra.cache.memory_cache import MemoryCache, CacheEntryType

    cache = MemoryCache(max_size=200)
    cache.set("price:2330:daily", price_data, CacheEntryType.PRICE, stock_code="2330")
    result = cache.get("price:2330:daily")  # 回傳淺複製或 None
"""

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# TTL 配置
# ---------------------------------------------------------------------------


class CacheEntryType(Enum):
    """快取條目類型，決定對應的 TTL。

    Members:
        PRICE: 股價資料，TTL 5 分鐘 (300s)
        FINANCIAL: 財報資料，TTL 1 小時 (3600s)
        COMPANY: 公司基本資訊，TTL 24 小時 (86400s)
        CHIP: 籌碼資料，TTL 4 小時 (14400s)
    """

    PRICE = "price"
    FINANCIAL = "financial"
    COMPANY = "company"
    CHIP = "chip"


TTL_CONFIG: Dict[CacheEntryType, int] = {
    CacheEntryType.PRICE: 300,
    CacheEntryType.FINANCIAL: 3600,
    CacheEntryType.COMPANY: 86400,
    CacheEntryType.CHIP: 14400,
}
"""Per-type TTL 配置（秒）。"""


# ---------------------------------------------------------------------------
# CacheEntry 資料結構
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """快取條目，儲存值與元資料。

    Attributes:
        value: 快取的實際資料。
        entry_type: 條目類型（決定 TTL）。
        created_at: 條目建立的時間戳記（epoch seconds）。
        stock_code: 關聯的股票代碼，用於 invalidate_by_stock。
    """

    value: Any
    entry_type: CacheEntryType
    created_at: float
    stock_code: str = ""


# ---------------------------------------------------------------------------
# MemoryCache
# ---------------------------------------------------------------------------


class MemoryCache:
    """LRU Memory Cache，搭配 per-type TTL。

    實作 CacheProtocol 介面，提供 get/set/delete/invalidate_by_stock/stats 操作。
    內部使用 OrderedDict 維護存取順序，以 threading.Lock 保障執行緒安全。

    Args:
        max_size: 快取容量上限，預設 200 筆。
        time_func: 時間函式，預設 time.time。可注入自訂函式以利測試。
    """

    def __init__(
        self,
        max_size: int = 200,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化 MemoryCache。

        Args:
            max_size: 快取容量上限，預設 200 筆。
            time_func: 取得目前時間的函式，預設 time.time。
        """
        self._max_size = max_size
        self._time_func = time_func
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

        # 統計計數器
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._eviction_count: int = 0

    def get(self, key: str) -> Optional[Any]:
        """依鍵值取得快取條目。

        若條目存在且未過期，將其移至 OrderedDict 尾端（標記為最近使用），
        並回傳值的淺複製。若條目已過期，則刪除並回傳 None。

        Args:
            key: 快取鍵值字串。

        Returns:
            快取值的淺複製（copy.copy），若不存在或已過期則回傳 None。
        """
        with self._lock:
            if key not in self._cache:
                self._miss_count += 1
                return None

            entry = self._cache[key]

            # 檢查 TTL 是否過期
            if self._is_expired(entry):
                del self._cache[key]
                self._miss_count += 1
                return None

            # 移至尾端（標記為最近使用）
            self._cache.move_to_end(key)
            self._hit_count += 1
            return copy.copy(entry.value)

    def set(
        self,
        key: str,
        value: Any,
        entry_type: CacheEntryType,
        stock_code: str = "",
    ) -> None:
        """設定快取條目。

        若鍵已存在則更新並移至尾端。若達容量上限，先驅逐最久未使用的條目。

        Args:
            key: 快取鍵值字串。
            value: 要快取的值。
            entry_type: 條目類型（決定 TTL）。
            stock_code: 關聯的股票代碼，用於 invalidate_by_stock。
        """
        with self._lock:
            # 若鍵已存在，先移除（稍後重新加入尾端）
            if key in self._cache:
                del self._cache[key]
            else:
                # 新增前檢查容量
                self._evict_if_needed()

            entry = CacheEntry(
                value=value,
                entry_type=entry_type,
                created_at=self._time_func(),
                stock_code=stock_code,
            )
            self._cache[key] = entry

    def delete(self, key: str) -> None:
        """刪除指定鍵值的快取條目。

        若鍵不存在則靜默忽略。

        Args:
            key: 要刪除的快取鍵值字串。
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def invalidate_by_stock(self, stock_code: str) -> int:
        """清除特定股票代碼相關的所有快取條目。

        遍歷所有條目，移除 stock_code 欄位匹配者。

        Args:
            stock_code: 要清除的股票代碼。

        Returns:
            被刪除的條目數量。
        """
        with self._lock:
            keys_to_delete = [
                k for k, entry in self._cache.items()
                if entry.stock_code == stock_code
            ]
            for k in keys_to_delete:
                del self._cache[k]

            if keys_to_delete:
                logger.debug(
                    "invalidate_by_stock: %d entries removed",
                    len(keys_to_delete),
                    extra={"stock_code": stock_code},
                )

            return len(keys_to_delete)

    def invalidate_prefix(self, prefix: str) -> int:
        """批次失效具有特定前綴的所有快取條目。

        實作 CacheProtocol 要求的 invalidate_prefix 方法。

        Args:
            prefix: 鍵值前綴字串。

        Returns:
            被刪除的條目數量。
        """
        with self._lock:
            keys_to_delete = [
                k for k in self._cache if k.startswith(prefix)
            ]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    def stats(self) -> Dict[str, int]:
        """取得快取統計資訊。

        Returns:
            包含以下欄位的字典：
            - hit_count: 快取命中次數
            - miss_count: 快取未命中次數
            - eviction_count: 因容量限制被驅逐的次數
            - current_size: 目前快取條目數量
        """
        with self._lock:
            return {
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "eviction_count": self._eviction_count,
                "current_size": len(self._cache),
            }

    def clear(self) -> None:
        """清除所有快取條目並重置統計計數器。"""
        with self._lock:
            self._cache.clear()
            self._hit_count = 0
            self._miss_count = 0
            self._eviction_count = 0

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _is_expired(self, entry: CacheEntry) -> bool:
        """檢查條目是否已過期。

        Args:
            entry: 快取條目。

        Returns:
            True 表示已過期，False 表示仍有效。
        """
        ttl = TTL_CONFIG[entry.entry_type]
        return (self._time_func() - entry.created_at) > ttl

    def _evict_if_needed(self) -> None:
        """若快取已滿，驅逐最久未使用的條目（OrderedDict 頭部）。

        此方法應在持有 _lock 的情況下呼叫。
        """
        while len(self._cache) >= self._max_size:
            # popitem(last=False) 移除 OrderedDict 頭部（最久未使用）
            self._cache.popitem(last=False)
            self._eviction_count += 1
