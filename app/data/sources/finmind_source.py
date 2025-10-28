"""
FinMind 資料來源實作
使用 FinMind API 獲取台股資料
"""

from typing import Optional, Dict
from datetime import datetime, timedelta
import pandas as pd
from FinMind.data import DataLoader
import os

from .base import DataSource


class FinMindSource(DataSource):
    """FinMind 資料來源"""
    
    def __init__(self, api_token: Optional[str] = None):
        """
        初始化 FinMind 資料來源
        
        Args:
            api_token: FinMind API Token
        """
        self.api_token = api_token or os.getenv('FINMIND_TOKEN')
        self.data_loader = None
        super().__init__('finmind')
    
    def _init_source(self) -> None:
        """初始化資料來源"""
        try:
            self.data_loader = DataLoader()
            if self.api_token:
                self.data_loader.login_by_token(api_token=self.api_token)
            self.is_available = True
            print("✓ FinMind 已準備就緒")
        except Exception as e:
            self.is_available = False
            print(f"✗ FinMind 初始化失敗: {str(e)}")
    
    def get_stock_price(
        self,
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """獲取股價資料"""
        if not self.is_available or not self.data_loader:
            return None
        
        try:
            if start_date is None:
                start_date = datetime.now() - timedelta(days=365*5)
            if end_date is None:
                end_date = datetime.now()
            
            price_df = self.data_loader.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if price_df is None or len(price_df) == 0:
                return None
            
            # 標準化欄位名稱
            df = pd.DataFrame({
                'date': pd.to_datetime(price_df['date']),
                'open_price': price_df['open'],
                'high_price': price_df['max'],
                'low_price': price_df['min'],
                'close_price': price_df['close'],
                'volume': price_df['Trading_Volume']
            })
            
            return df
            
        except Exception as e:
            print(f"  FinMind 獲取股價失敗: {str(e)}")
            return None
    
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """獲取財務報表資料"""
        if not self.is_available or not self.data_loader:
            return None
        
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
            
            # 獲取財報數據
            financial_df = self.data_loader.taiwan_stock_financial_statement(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if financial_df is None or len(financial_df) == 0:
                return None
            
            # 標準化欄位名稱
            df = pd.DataFrame()
            df['date'] = pd.to_datetime(financial_df.get('date', financial_df.index))
            
            # EPS 欄位
            if 'EPS' in financial_df.columns:
                df['eps'] = pd.to_numeric(financial_df['EPS'], errors='coerce')
            elif 'BasicEarningsPerShare' in financial_df.columns:
                df['eps'] = pd.to_numeric(financial_df['BasicEarningsPerShare'], errors='coerce')
            else:
                df['eps'] = 0
            
            # 其他欄位
            df['revenue'] = pd.to_numeric(financial_df.get('Revenue', 0), errors='coerce')
            df['profit'] = pd.to_numeric(financial_df.get('ProfitLoss', 0), errors='coerce')
            df['roe'] = pd.to_numeric(financial_df.get('ROE', 0), errors='coerce')
            df['debt_ratio'] = pd.to_numeric(financial_df.get('DebtRatio', 0), errors='coerce')
            
            # 移除 NaN 行
            df = df.dropna(subset=['date'])
            
            if len(df) > 0:
                return df
            
            return None
            
        except Exception as e:
            print(f"  FinMind 獲取財務數據失敗: {str(e)}")
            return None
    
    def get_latest_eps(self, stock_code: str) -> Optional[float]:
        """獲取最新 EPS"""
        if not self.is_available:
            return None
        
        try:
            financial_data = self.get_financial_data(stock_code, years=2)
            if financial_data is not None and len(financial_data) > 0:
                # 過濾掉 NaN 和 0 值
                valid_eps = financial_data['eps'].dropna()
                valid_eps = valid_eps[valid_eps > 0]
                
                if len(valid_eps) > 0:
                    return float(valid_eps.iloc[-1])
            
            return None
            
        except Exception as e:
            print(f"  FinMind 獲取 EPS 失敗: {str(e)}")
            return None
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """獲取股票基本資訊"""
        if not self.is_available or not self.data_loader:
            return None
        
        try:
            info = self.data_loader.taiwan_stock_info()
            if info is not None and len(info) > 0:
                match = info[info['stock_id'] == stock_code]
                if len(match) > 0:
                    row = match.iloc[0]
                    return {
                        'stock_code': stock_code,
                        'stock_name': row.get('stock_name', f'股票{stock_code}'),
                        'industry': row.get('industry', '未分類'),
                        'market': '上市' if stock_code.startswith('2') else '上櫃'
                    }
            
            return None
            
        except Exception as e:
            print(f"  FinMind 獲取股票資訊失敗: {str(e)}")
            return None
    
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """獲取所有股票清單"""
        if not self.is_available or not self.data_loader:
            return None
        
        try:
            info = self.data_loader.taiwan_stock_info()
            if info is not None and len(info) > 0:
                return pd.DataFrame({
                    'stock_id': info['stock_id'],
                    'stock_name': info['stock_name']
                })
            
            return None
            
        except Exception as e:
            print(f"  FinMind 獲取股票清單失敗: {str(e)}")
            return None
