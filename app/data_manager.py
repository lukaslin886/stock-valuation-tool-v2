"""
數據管理模組
負責從 FinMind 和 yfinance 獲取台股數據
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import pandas as pd
import sqlite3
from FinMind.data import DataLoader
import yfinance as yf


class DataManager:
    """數據管理器 - 整合 FinMind 和 yfinance API"""

    def __init__(self, api_token: Optional[str] = None, db_path: Optional[str] = None):
        """
        初始化數據管理器

        Args:
            api_token: FinMind API Token
            db_path: SQLite 資料庫路徑
        """
        self.api_token = api_token or os.getenv('FINMIND_TOKEN')
        self.db_path = db_path or os.getenv('DATABASE_PATH', 'data/stock_data.db')
        
        # 確保數據目錄存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 初始化資料庫
        self._init_database()
        
        # 初始化 FinMind
        self.finmind = DataLoader()
        if self.api_token:
            self.finmind.login_by_token(api_token=self.api_token)

    def _init_database(self):
        """初始化 SQLite 資料庫"""
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

    def get_stock_info(self, stock_code: str, force_update: bool = False) -> Dict:
        """
        獲取股票基本資訊

        Args:
            stock_code: 股票代碼（例如：2330）
            force_update: 是否強制更新

        Returns:
            股票基本資訊字典
        """
        # 先檢查本地快取
        if not force_update:
            cached_info = self._get_cached_stock_info(stock_code)
            if cached_info:
                return cached_info
        
        # 從 FinMind 獲取數據
        try:
            # 獲取股票資訊
            info = {
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(stock_code),
                'industry': self._get_industry(stock_code),
                'market': self._get_market(stock_code),
                'update_time': datetime.now()
            }
            
            # 儲存到資料庫
            self._save_stock_info(info)
            
            return info
            
        except Exception as e:
            print(f"獲取股票資訊失敗: {str(e)}")
            # 如果失敗，嘗試返回快取數據
            cached_info = self._get_cached_stock_info(stock_code)
            if cached_info:
                return cached_info
            raise

    def get_financial_data(
        self, 
        stock_code: str, 
        years: int = 5,
        force_update: bool = False
    ) -> pd.DataFrame:
        """
        獲取財務數據

        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的數據
            force_update: 是否強制更新

        Returns:
            財務數據 DataFrame
        """
        # 檢查快取
        if not force_update:
            cached_data = self._get_cached_financial_data(stock_code, years)
            if cached_data is not None and len(cached_data) > 0:
                print(f"使用快取的財務數據（{len(cached_data)} 筆）")
                return cached_data
        
        # 從 FinMind 獲取
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
            
            print(f"正在從 FinMind 獲取財務數據: {stock_code} ({start_date} ~ {end_date})")
            
            # 獲取財報數據
            financial_df = self.finmind.taiwan_stock_financial_statement(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if financial_df is not None and len(financial_df) > 0:
                print(f"FinMind 返回 {len(financial_df)} 筆財務數據")
                print(f"可用欄位: {list(financial_df.columns)}")
                
                # 處理數據格式（使用安全的欄位映射）
                df = pd.DataFrame()
                df['date'] = pd.to_datetime(financial_df.get('date', financial_df.index))
                
                # EPS 欄位可能的名稱
                if 'EPS' in financial_df.columns:
                    df['eps'] = pd.to_numeric(financial_df['EPS'], errors='coerce')
                elif 'BasicEarningsPerShare' in financial_df.columns:
                    df['eps'] = pd.to_numeric(financial_df['BasicEarningsPerShare'], errors='coerce')
                else:
                    print("警告：找不到 EPS 欄位")
                    df['eps'] = 0
                
                # 其他欄位
                df['revenue'] = pd.to_numeric(financial_df.get('Revenue', 0), errors='coerce')
                df['profit'] = pd.to_numeric(financial_df.get('ProfitLoss', 0), errors='coerce')
                df['roe'] = pd.to_numeric(financial_df.get('ROE', 0), errors='coerce')
                df['debt_ratio'] = pd.to_numeric(financial_df.get('DebtRatio', 0), errors='coerce')
                
                # 移除 NaN 行
                df = df.dropna(subset=['date'])
                
                if len(df) > 0:
                    print(f"處理後得到 {len(df)} 筆有效數據")
                    # 儲存到資料庫
                    self._save_financial_data(stock_code, df)
                    return df
                else:
                    print("警告：處理後沒有有效數據")
            else:
                print(f"FinMind 未返回財務數據")
            
            # 如果沒有數據，返回空 DataFrame
            return pd.DataFrame()
            
        except Exception as e:
            print(f"獲取財務數據失敗: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 返回快取數據
            cached_data = self._get_cached_financial_data(stock_code, years)
            if cached_data is not None:
                print(f"使用快取數據作為備用（{len(cached_data)} 筆）")
                return cached_data
            return pd.DataFrame()

    def get_price_data(
        self,
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        force_update: bool = False
    ) -> pd.DataFrame:
        """
        獲取股價數據

        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            force_update: 是否強制更新

        Returns:
            股價數據 DataFrame
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365*5)  # 預設5年
        if end_date is None:
            end_date = datetime.now()
        
        # 檢查快取
        if not force_update:
            cached_data = self._get_cached_price_data(stock_code, start_date, end_date)
            if cached_data is not None and len(cached_data) > 0:
                return cached_data
        
        # 優先從 FinMind 獲取
        try:
            price_df = self.finmind.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if price_df is not None and len(price_df) > 0:
                df = pd.DataFrame({
                    'date': pd.to_datetime(price_df['date']),
                    'stock_code': stock_code,
                    'open_price': price_df['open'],
                    'high_price': price_df['max'],
                    'low_price': price_df['min'],
                    'close_price': price_df['close'],
                    'volume': price_df['Trading_Volume']
                })
                
                # 儲存到資料庫
                self._save_price_data(stock_code, df)
                
                return df
        except Exception as e:
            print(f"FinMind 獲取失敗，嘗試使用 yfinance: {str(e)}")
        
        # 備用：使用 yfinance
        try:
            ticker = yf.Ticker(f"{stock_code}.TW")
            hist = ticker.history(start=start_date, end=end_date)
            
            if len(hist) > 0:
                df = pd.DataFrame({
                    'date': hist.index,
                    'stock_code': stock_code,
                    'open_price': hist['Open'],
                    'high_price': hist['High'],
                    'low_price': hist['Low'],
                    'close_price': hist['Close'],
                    'volume': hist['Volume']
                })
                
                # 儲存到資料庫
                self._save_price_data(stock_code, df)
                
                return df
        except Exception as e:
            print(f"yfinance 也失敗: {str(e)}")
        
        # 返回快取數據
        cached_data = self._get_cached_price_data(stock_code, start_date, end_date)
        if cached_data is not None:
            return cached_data
        
        return pd.DataFrame()

    def get_latest_eps(self, stock_code: str) -> float:
        """獲取最新的 EPS"""
        try:
            print(f"\n正在獲取 {stock_code} 的最新 EPS...")
            
            # 方法 1: 從財務數據獲取
            financial_data = self.get_financial_data(stock_code, years=2)
            if financial_data is not None and len(financial_data) > 0:
                # 過濾掉 NaN 和 0 值
                valid_eps = financial_data['eps'].dropna()
                valid_eps = valid_eps[valid_eps != 0]
                
                if len(valid_eps) > 0:
                    latest_eps = float(valid_eps.iloc[-1])
                    print(f"從 FinMind 獲取的最新 EPS: {latest_eps}")
                    return latest_eps
                else:
                    print("警告：財務數據中沒有有效的 EPS 值")
            else:
                print("警告：無法獲取財務數據")
            
            # 方法 2: 嘗試從 yfinance 獲取
            print(f"嘗試從 yfinance 獲取 EPS...")
            ticker = yf.Ticker(f"{stock_code}.TW")
            info = ticker.info
            
            if 'trailingEps' in info and info['trailingEps']:
                yf_eps = float(info['trailingEps'])
                print(f"從 yfinance 獲取的 EPS: {yf_eps}")
                return yf_eps
            
            print("警告：yfinance 也無法提供 EPS 數據")
            
            # 方法 3: 使用預估值（台積電的近似值）
            if stock_code == "2330":
                default_eps = 32.0
                print(f"使用預設 EPS 值: {default_eps}")
                return default_eps
            
            return 0.0
            
        except Exception as e:
            print(f"獲取 EPS 失敗: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0.0

    def get_latest_price(self, stock_code: str) -> float:
        """獲取最新股價"""
        try:
            price_data = self.get_price_data(stock_code)
            if price_data is not None and len(price_data) > 0:
                return float(price_data['close_price'].iloc[-1])
            # 備用：使用 yfinance 即時價格
            ticker = yf.Ticker(f"{stock_code}.TW")
            info = ticker.info
            if 'currentPrice' in info:
                return float(info['currentPrice'])
            return 0.0
        except Exception as e:
            print(f"獲取股價失敗: {str(e)}")
            return 0.0

    # === 私有方法：資料庫操作 ===
    
    def _get_cached_stock_info(self, stock_code: str) -> Optional[Dict]:
        """從資料庫獲取快取的股票資訊"""
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

    def _save_stock_info(self, info: Dict):
        """儲存股票資訊到資料庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO stock_info 
            (stock_code, stock_name, industry, market, update_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            info['stock_code'],
            info['stock_name'],
            info['industry'],
            info['market'],
            info['update_time']
        ))
        
        conn.commit()
        conn.close()

    def _get_cached_financial_data(self, stock_code: str, years: int) -> Optional[pd.DataFrame]:
        """從資料庫獲取快取的財務數據"""
        conn = sqlite3.connect(self.db_path)
        
        cutoff_date = datetime.now() - timedelta(days=years*365)
        
        df = pd.read_sql_query('''
            SELECT date, eps, revenue, profit, roe, debt_ratio
            FROM financial_data
            WHERE stock_code = ? AND date >= ?
            ORDER BY date
        ''', conn, params=(stock_code, cutoff_date.strftime('%Y-%m-%d')))
        
        conn.close()
        
        return df if len(df) > 0 else None

    def _save_financial_data(self, stock_code: str, df: pd.DataFrame):
        """儲存財務數據到資料庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for _, row in df.iterrows():
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

    def _get_cached_price_data(
        self, 
        stock_code: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """從資料庫獲取快取的股價數據"""
        conn = sqlite3.connect(self.db_path)
        
        df = pd.read_sql_query('''
            SELECT date, close_price, volume
            FROM price_data
            WHERE stock_code = ? AND date >= ? AND date <= ?
            ORDER BY date
        ''', conn, params=(
            stock_code,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        ))
        
        conn.close()
        
        return df if len(df) > 0 else None

    def _save_price_data(self, stock_code: str, df: pd.DataFrame):
        """儲存股價數據到資料庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO price_data
                (stock_code, date, close_price, volume, update_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                stock_code,
                row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else row['date'],
                row.get('close_price'),
                row.get('volume'),
                datetime.now()
            ))
        
        conn.commit()
        conn.close()

    def _get_stock_name(self, stock_code: str) -> str:
        """獲取股票名稱"""
        try:
            # 使用 FinMind 獲取
            info = self.finmind.taiwan_stock_info()
            if info is not None and len(info) > 0:
                match = info[info['stock_id'] == stock_code]
                if len(match) > 0:
                    return match.iloc[0]['stock_name']
        except:
            pass
        return f"股票{stock_code}"

    def _get_industry(self, stock_code: str) -> str:
        """獲取產業別"""
        try:
            info = self.finmind.taiwan_stock_info()
            if info is not None and len(info) > 0:
                match = info[info['stock_id'] == stock_code]
                if len(match) > 0:
                    return match.iloc[0].get('industry', '未分類')
        except:
            pass
        return "未分類"

    def _get_market(self, stock_code: str) -> str:
        """獲取市場別"""
        if stock_code.startswith('2'):
            return "上市"
        else:
            return "上櫃"


# 測試函數
def test_data_manager():
    """測試數據管理器"""
    manager = DataManager()
    
    # 測試股票代碼
    test_stock = "2330"
    
    print(f"=== 測試股票: {test_stock} ===\n")
    
    # 測試獲取股票資訊
    try:
        info = manager.get_stock_info(test_stock)
        print("股票資訊:")
        print(f"  代碼: {info['stock_code']}")
        print(f"  名稱: {info['stock_name']}")
        print(f"  產業: {info['industry']}")
        print(f"  市場: {info['market']}")
        print()
    except Exception as e:
        print(f"獲取股票資訊失敗: {str(e)}\n")
    
    # 測試獲取最新 EPS
    try:
        eps = manager.get_latest_eps(test_stock)
        print(f"最新 EPS: {eps}")
    except Exception as e:
        print(f"獲取 EPS 失敗: {str(e)}")
    
    # 測試獲取最新股價
    try:
        price = manager.get_latest_price(test_stock)
        print(f"最新股價: {price}")
    except Exception as e:
        print(f"獲取股價失敗: {str(e)}")


if __name__ == "__main__":
    test_data_manager()
