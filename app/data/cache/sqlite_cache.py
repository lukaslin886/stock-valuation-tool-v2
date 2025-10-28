"""
SQLite 快取後端實作
使用 SQLite 資料庫儲存快取資料
"""

from typing import Optional
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import os

from .base import CacheBackend


class SQLiteCache(CacheBackend):
    """SQLite 快取後端"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化 SQLite 快取
        
        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = db_path or os.getenv('DATABASE_PATH', 'data/stock_data.db')
        super().__init__('sqlite')
    
    def _init_cache(self) -> None:
        """初始化快取（建立資料表）"""
        try:
            # 確保資料目錄存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 建立股票基本資料表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_info (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT,
                    industry TEXT,
                    market TEXT,
                    update_time TIMESTAMP
                )
            ''')
            
            # 建立財務數據表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS financial_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT,
                    date TEXT,
                    eps REAL,
                    revenue REAL,
                    profit REAL,
                    roe REAL,
                    debt_ratio REAL,
                    update_time TIMESTAMP,
                    UNIQUE(stock_code, date)
                )
            ''')
            
            # 建立價格數據表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT,
                    date TEXT,
                    open_price REAL,
                    high_price REAL,
                    low_price REAL,
                    close_price REAL,
                    volume INTEGER,
                    update_time TIMESTAMP,
                    UNIQUE(stock_code, date)
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.is_available = True
            print("✓ SQLite 快取已準備就緒")
            
        except Exception as e:
            self.is_available = False
            print(f"✗ SQLite 快取初始化失敗: {str(e)}")
    
    def get_stock_price(
        self,
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """從快取獲取股價資料"""
        if not self.is_available:
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            if start_date and end_date:
                df = pd.read_sql_query('''
                    SELECT date, open_price, high_price, low_price, close_price, volume
                    FROM price_data
                    WHERE stock_code = ? AND date >= ? AND date <= ?
                    ORDER BY date
                ''', conn, params=(stock_code, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            else:
                df = pd.read_sql_query('''
                    SELECT date, open_price, high_price, low_price, close_price, volume
                    FROM price_data
                    WHERE stock_code = ?
                    ORDER BY date
                ''', conn, params=(stock_code,))
            
            conn.close()
            
            if len(df) > 0:
                df['date'] = pd.to_datetime(df['date'])
                return df
            
            return None
            
        except Exception as e:
            print(f"  SQLite 獲取股價快取失敗: {str(e)}")
            return None
    
    def save_stock_price(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> bool:
        """儲存股價資料到快取"""
        if not self.is_available or data is None or len(data) == 0:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for _, row in data.iterrows():
                cursor.execute('''
                    INSERT OR REPLACE INTO price_data
                    (stock_code, date, open_price, high_price, low_price, close_price, volume, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else row['date'],
                    row.get('open_price'),
                    row.get('high_price'),
                    row.get('low_price'),
                    row.get('close_price'),
                    row.get('volume'),
                    datetime.now()
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  SQLite 儲存股價快取失敗: {str(e)}")
            return False
    
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """從快取獲取財務資料"""
        if not self.is_available:
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            cutoff_date = datetime.now() - timedelta(days=years*365)
            
            df = pd.read_sql_query('''
                SELECT date, eps, revenue, profit, roe, debt_ratio
                FROM financial_data
                WHERE stock_code = ? AND date >= ?
                ORDER BY date
            ''', conn, params=(stock_code, cutoff_date.strftime('%Y-%m-%d')))
            
            conn.close()
            
            if len(df) > 0:
                df['date'] = pd.to_datetime(df['date'])
                return df
            
            return None
            
        except Exception as e:
            print(f"  SQLite 獲取財務快取失敗: {str(e)}")
            return None
    
    def save_financial_data(
        self,
        stock_code: str,
        data: pd.DataFrame
    ) -> bool:
        """儲存財務資料到快取"""
        if not self.is_available or data is None or len(data) == 0:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for _, row in data.iterrows():
                cursor.execute('''
                    INSERT OR REPLACE INTO financial_data
                    (stock_code, date, eps, revenue, profit, roe, debt_ratio, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else row['date'],
                    row.get('eps'),
                    row.get('revenue'),
                    row.get('profit'),
                    row.get('roe'),
                    row.get('debt_ratio'),
                    datetime.now()
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  SQLite 儲存財務快取失敗: {str(e)}")
            return False
    
    def get_stock_info(self, stock_code: str) -> Optional[dict]:
        """從快取獲取股票資訊"""
        if not self.is_available:
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT stock_code, stock_name, industry, market, update_time
                FROM stock_info
                WHERE stock_code = ?
            ''', (stock_code,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'stock_code': row[0],
                    'stock_name': row[1],
                    'industry': row[2],
                    'market': row[3],
                    'update_time': row[4]
                }
            
            return None
            
        except Exception as e:
            print(f"  SQLite 獲取股票資訊快取失敗: {str(e)}")
            return None
    
    def save_stock_info(self, stock_code: str, info: dict) -> bool:
        """儲存股票資訊到快取"""
        if not self.is_available or not info:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO stock_info 
                (stock_code, stock_name, industry, market, update_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                stock_code,
                info.get('stock_name', ''),
                info.get('industry', ''),
                info.get('market', ''),
                datetime.now()
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  SQLite 儲存股票資訊快取失敗: {str(e)}")
            return False
    
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """從快取獲取所有股票清單"""
        if not self.is_available:
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            df = pd.read_sql_query('''
                SELECT stock_code AS stock_id, stock_name
                FROM stock_info
                ORDER BY stock_code
            ''', conn)
            
            conn.close()
            
            if len(df) > 0:
                return df
            
            return None
            
        except Exception as e:
            print(f"  SQLite 獲取股票清單快取失敗: {str(e)}")
            return None
    
    def save_all_stocks(self, data: pd.DataFrame) -> bool:
        """儲存股票清單到快取"""
        if not self.is_available or data is None or len(data) == 0:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            update_time = datetime.now()
            
            for _, row in data.iterrows():
                # 支援 stock_id 或 stock_code 欄位名稱
                stock_code = row.get('stock_id') or row.get('stock_code')
                
                cursor.execute('''
                    INSERT OR REPLACE INTO stock_info
                    (stock_code, stock_name, industry, market, update_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    row.get('stock_name'),
                    '',  # industry 可以之後補充
                    '',  # market 可以之後補充
                    update_time
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  SQLite 儲存股票清單快取失敗: {str(e)}")
            return False
    
    def is_cache_valid(
        self,
        cache_type: str,
        stock_code: str,
        max_age_days: int = 7
    ) -> bool:
        """檢查快取是否有效（未過期）"""
        if not self.is_available:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            if cache_type == 'price':
                cursor.execute('''
                    SELECT COUNT(*) FROM price_data
                    WHERE stock_code = ? AND update_time >= ?
                ''', (stock_code, cutoff_date))
            elif cache_type == 'financial':
                cursor.execute('''
                    SELECT COUNT(*) FROM financial_data
                    WHERE stock_code = ? AND update_time >= ?
                ''', (stock_code, cutoff_date))
            elif cache_type == 'info':
                cursor.execute('''
                    SELECT COUNT(*) FROM stock_info
                    WHERE stock_code = ? AND update_time >= ?
                ''', (stock_code, cutoff_date))
            elif cache_type == 'stocks':
                cursor.execute('''
                    SELECT COUNT(*) FROM stock_info
                    WHERE update_time >= ?
                ''', (cutoff_date,))
            else:
                conn.close()
                return False
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            print(f"  SQLite 檢查快取有效性失敗: {str(e)}")
            return False
    
    def clear_cache(
        self,
        cache_type: Optional[str] = None,
        stock_code: Optional[str] = None
    ) -> bool:
        """清除快取"""
        if not self.is_available:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if cache_type is None:
                # 清除所有快取
                cursor.execute('DELETE FROM price_data')
                cursor.execute('DELETE FROM financial_data')
                cursor.execute('DELETE FROM stock_info')
            elif cache_type == 'price':
                if stock_code:
                    cursor.execute('DELETE FROM price_data WHERE stock_code = ?', (stock_code,))
                else:
                    cursor.execute('DELETE FROM price_data')
            elif cache_type == 'financial':
                if stock_code:
                    cursor.execute('DELETE FROM financial_data WHERE stock_code = ?', (stock_code,))
                else:
                    cursor.execute('DELETE FROM financial_data')
            elif cache_type == 'info':
                if stock_code:
                    cursor.execute('DELETE FROM stock_info WHERE stock_code = ?', (stock_code,))
                else:
                    cursor.execute('DELETE FROM stock_info')
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  SQLite 清除快取失敗: {str(e)}")
            return False
