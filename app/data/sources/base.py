"""
資料來源抽象基礎類別
定義所有資料來源必須實作的介面
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd


class DataSource(ABC):
    """資料來源抽象基礎類別"""
    
    def __init__(self, name: str):
        """
        初始化資料來源
        
        Args:
            name: 資料來源名稱（例如：'yfinance', 'finmind', 'finlab'）
        """
        self.name = name
        self.is_available = False
        self._init_source()
    
    @abstractmethod
    def _init_source(self) -> None:
        """
        初始化資料來源（登入、設定等）
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
        獲取股價資料
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            包含以下欄位的 DataFrame 或 None：
            - date: 日期
            - open_price: 開盤價
            - high_price: 最高價
            - low_price: 最低價
            - close_price: 收盤價
            - volume: 成交量
        """
        pass
    
    @abstractmethod
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        獲取財務報表資料
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的資料
            
        Returns:
            包含以下欄位的 DataFrame 或 None：
            - date: 日期
            - eps: 每股盈餘
            - revenue: 營收
            - profit: 淨利
            - roe: 股東權益報酬率
            - debt_ratio: 負債比率
        """
        pass
    
    @abstractmethod
    def get_latest_eps(self, stock_code: str) -> Optional[float]:
        """
        獲取最新 EPS
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            最新 EPS 值或 None
        """
        pass
    
    @abstractmethod
    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """
        獲取股票基本資訊
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            包含股票資訊的字典或 None：
            {
                'stock_code': str,
                'stock_name': str,
                'industry': str,
                'market': str
            }
        """
        pass
    
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """
        獲取所有股票清單（可選實作）
        
        Returns:
            包含 stock_code 和 stock_name 的 DataFrame 或 None
        """
        return None
    
    def is_ready(self) -> bool:
        """
        檢查資料來源是否可用
        
        Returns:
            True 如果資料來源已準備好，否則 False
        """
        return self.is_available
    
    def get_source_name(self) -> str:
        """
        獲取資料來源名稱
        
        Returns:
            資料來源名稱
        """
        return self.name
    
    def __str__(self) -> str:
        """字串表示"""
        status = "可用" if self.is_available else "不可用"
        return f"{self.name} ({status})"
    
    def __repr__(self) -> str:
        """偵錯用字串表示"""
        return f"DataSource(name='{self.name}', available={self.is_available})"
