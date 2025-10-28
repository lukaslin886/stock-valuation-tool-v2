"""
快取後端抽象基礎類別
定義所有快取後端必須實作的介面
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import datetime
import pandas as pd


class CacheBackend(ABC):
    """快取後端抽象基礎類別"""
    
    def __init__(self, name: str):
        """
        初始化快取後端
        
        Args:
            name: 快取後端名稱（例如：'sqlite', 'redis', 'parquet'）
        """
        self.name = name
        self.is_available = False
        self._init_cache()
    
    @abstractmethod
    def _init_cache(self) -> None:
        """
        初始化快取後端（建立連線、資料表等）
        子類別必須實作此方法
        """
        pass
    
    @abstractmethod
    def get_stock_price(
        self,
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """
        從快取獲取股價資料
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            股價資料 DataFrame 或 None
        """
        pass
    
    @abstractmethod
    def save_stock_price(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> bool:
        """
        儲存股價資料到快取
        
        Args:
            stock_code: 股票代碼
            data: 股價資料 DataFrame
            
        Returns:
            True 如果成功，否則 False
        """
        pass
    
    @abstractmethod
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        從快取獲取財務資料
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的資料
            
        Returns:
            財務資料 DataFrame 或 None
        """
        pass
    
    @abstractmethod
    def save_financial_data(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> bool:
        """
        儲存財務資料到快取
        
        Args:
            stock_code: 股票代碼
            data: 財務資料 DataFrame
            
        Returns:
            True 如果成功，否則 False
        """
        pass
    
    @abstractmethod
    def get_stock_info(self, stock_code: str) -> Optional[dict]:
        """
        從快取獲取股票資訊
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票資訊字典或 None
        """
        pass
    
    @abstractmethod
    def save_stock_info(self, stock_code: str, info: dict) -> bool:
        """
        儲存股票資訊到快取
        
        Args:
            stock_code: 股票代碼
            info: 股票資訊字典
            
        Returns:
            True 如果成功，否則 False
        """
        pass
    
    @abstractmethod
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """
        從快取獲取所有股票清單
        
        Returns:
            股票清單 DataFrame 或 None
        """
        pass
    
    @abstractmethod
    def save_all_stocks(self, data: pd.DataFrame) -> bool:
        """
        儲存股票清單到快取
        
        Args:
            data: 股票清單 DataFrame
            
        Returns:
            True 如果成功，否則 False
        """
        pass
    
    @abstractmethod
    def is_cache_valid(
        self,
        cache_type: str,
        stock_code: str,
        max_age_days: int = 7
    ) -> bool:
        """
        檢查快取是否有效（未過期）
        
        Args:
            cache_type: 快取類型（'price', 'financial', 'info', 'stocks'）
            stock_code: 股票代碼
            max_age_days: 最大快取天數
            
        Returns:
            True 如果快取有效，否則 False
        """
        pass
    
    @abstractmethod
    def clear_cache(
        self,
        cache_type: Optional[str] = None,
        stock_code: Optional[str] = None
    ) -> bool:
        """
        清除快取
        
        Args:
            cache_type: 快取類型（None 表示全部）
            stock_code: 股票代碼（None 表示全部）
            
        Returns:
            True 如果成功，否則 False
        """
        pass
    
    def is_ready(self) -> bool:
        """
        檢查快取後端是否可用
        
        Returns:
            True 如果快取後端已準備好，否則 False
        """
        return self.is_available
    
    def get_cache_name(self) -> str:
        """
        獲取快取後端名稱
        
        Returns:
            快取後端名稱
        """
        return self.name
    
    def __str__(self) -> str:
        """字串表示"""
        status = "可用" if self.is_available else "不可用"
        return f"{self.name} 快取 ({status})"
    
    def __repr__(self) -> str:
        """偵錯用字串表示"""
        return f"CacheBackend(name='{self.name}', available={self.is_available})"
