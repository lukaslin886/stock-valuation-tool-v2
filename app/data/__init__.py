"""
Data Module - 資料層模組

提供統一的資料存取介面，整合多個資料來源與快取機制
"""

# 匯出新一代資料管理器
from .manager import DataManagerV2, DataManager

# 匯出資料來源抽象類別
from .sources.base import DataSource

# 匯出具體資料來源實作
from .sources.yfinance_source import YFinanceSource
from .sources.finmind_source import FinMindSource

# 匯出快取抽象類別
from .cache.base import CacheBackend

# 匯出具體快取實作
from .cache.sqlite_cache import SQLiteCache

__all__ = [
    # 主要類別
    'DataManagerV2',
    'DataManager',  # 向下相容別名
    
    # 資料來源
    'DataSource',
    'YFinanceSource',
    'FinMindSource',
    
    # 快取
    'CacheBackend',
    'SQLiteCache',
]

__version__ = '2.0.0'
