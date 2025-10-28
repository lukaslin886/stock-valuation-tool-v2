"""
數據管理模組
負責從 FinLab、FinMind 和 yfinance 獲取台股數據
優先順序：FinLab > FinMind > yfinance
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Callable
import pandas as pd
import sqlite3
from FinMind.data import DataLoader
import yfinance as yf
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# FinLab 相關 import
try:
    import finlab
    from finlab import data as finlab_data
    FINLAB_AVAILABLE = True
except ImportError:
    FINLAB_AVAILABLE = False
    print("警告：FinLab 套件未安裝，將使用 FinMind 作為主要資料源")


class DataManager:
    """數據管理器 - 整合 FinMind 和 yfinance API"""

    def __init__(self, api_token: Optional[str] = None, db_path: Optional[str] = None):
        """
        初始化數據管理器

        Args:
            api_token: FinMind API Token (向下相容參數)
            db_path: SQLite 資料庫路徑
        """
        # 資料來源 Token
        self.finmind_token = api_token or os.getenv('FINMIND_TOKEN')
        self.finlab_token = os.getenv('FINLAB_API_TOKEN')
        
        self.db_path = db_path or os.getenv('DATABASE_PATH', 'data/stock_data.db')
        
        # 確保數據目錄存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 初始化資料庫
        self._init_database()
        
        # 初始化 FinLab（優先）
        self.finlab_ready = False
        if FINLAB_AVAILABLE and self.finlab_token:
            try:
                finlab.login(self.finlab_token)
                self.finlab_ready = True
                print("✓ FinLab 已成功初始化並登入")
            except Exception as e:
                print(f"✗ FinLab 初始化失敗: {str(e)}")
                print("  將使用 FinMind 作為主要資料源")
        elif not FINLAB_AVAILABLE:
            print("ℹ FinLab 套件未安裝，使用 FinMind 作為主要資料源")
        elif not self.finlab_token:
            print("ℹ 未設定 FINLAB_API_TOKEN，使用 FinMind 作為主要資料源")
        
        # 初始化 FinMind（備援）
        self.finmind = DataLoader()
        if self.finmind_token:
            self.finmind.login_by_token(api_token=self.finmind_token)
            print("✓ FinMind 已成功初始化")
        
        # 資料源使用統計
        self.data_source_stats = {
            'finlab_success': 0,
            'finlab_fail': 0,
            'finmind_success': 0,
            'finmind_fail': 0,
            'yfinance_success': 0,
            'yfinance_fail': 0
        }

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
        獲取財務數據（優先使用 yfinance，備援使用 FinMind）
        
        資料來源優先序列：
        1. yfinance (主要來源)
        2. FinMind (備援)
        3. 快取資料 (最後選擇)

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
        
        # 使用多層備援策略（yfinance → FinMind）
        fetch_functions = [
            ('yfinance', lambda: self._fetch_financial_from_yfinance(stock_code, years)),
            ('FinMind', lambda: self._fetch_financial_from_finmind(stock_code, years))
        ]
        
        data = self._fetch_with_priority(fetch_functions, '獲取財務數據')
        
        # 處理結果
        if data is not None and len(data) > 0:
            self._save_financial_data(stock_code, data)
            return data
        
        # 最後備援：返回快取或空 DataFrame
        cached_data = self._get_cached_financial_data(stock_code, years)
        return cached_data if cached_data is not None else pd.DataFrame()

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

    def _normalize_yfinance_ticker(self, stock_code: str) -> str:
        """
        將台股代碼轉換為 yfinance 格式
        
        Args:
            stock_code: 股票代碼（例如：2330）
            
        Returns:
            yfinance 格式的股票代碼（例如：2330.TW 或 2330.TWO）
        """
        # 上市股票通常以 1-2 開頭，使用 .TW
        # 上櫃股票通常以 3-9 開頭，使用 .TWO
        # 這是簡化的判斷，實際上應該查詢市場別
        if stock_code.startswith(('1', '2')):
            return f"{stock_code}.TW"
        else:
            return f"{stock_code}.TWO"
    
    def _fetch_eps_from_yfinance(self, stock_code: str) -> Optional[float]:
        """
        從 yfinance 獲取 EPS
        
        嘗試多個欄位來源：
        1. info['trailingEps']
        2. info['epsTrailingTwelveMonths']
        3. financials 中的 'Basic EPS' 或 'Net Income'
        4. earnings 歷史數據
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            EPS 值，失敗返回 None
        """
        try:
            ticker_symbol = self._normalize_yfinance_ticker(stock_code)
            ticker = yf.Ticker(ticker_symbol)
            
            # 方法 1: 從 info 物件獲取
            try:
                info = ticker.info
                
                # 嘗試 trailingEps
                if 'trailingEps' in info and info['trailingEps']:
                    eps = float(info['trailingEps'])
                    if eps > 0:
                        return eps
                
                # 嘗試 epsTrailingTwelveMonths
                if 'epsTrailingTwelveMonths' in info and info['epsTrailingTwelveMonths']:
                    eps = float(info['epsTrailingTwelveMonths'])
                    if eps > 0:
                        return eps
                
                # 嘗試 epsForward（預測值，作為備援）
                if 'forwardEps' in info and info['forwardEps']:
                    eps = float(info['forwardEps'])
                    if eps > 0:
                        return eps
                        
            except Exception as e:
                print(f"  從 info 獲取 EPS 失敗: {str(e)}")
            
            # 方法 2: 從 earnings 獲取歷史數據
            try:
                earnings = ticker.earnings
                if earnings is not None and len(earnings) > 0:
                    # 取最近一年的數據
                    if 'Earnings' in earnings.columns:
                        latest_earnings = earnings['Earnings'].iloc[-1]
                        # 需要除以流通股數才是 EPS，但這裡可能已經是 EPS
                        if latest_earnings > 0:
                            return float(latest_earnings)
            except Exception as e:
                print(f"  從 earnings 獲取 EPS 失敗: {str(e)}")
            
            # 方法 3: 從 financials 計算
            try:
                financials = ticker.financials
                if financials is not None and len(financials) > 0:
                    # 尋找 Net Income
                    for row_name in ['Net Income', 'Net Income Common Stockholders']:
                        if row_name in financials.index:
                            net_income = financials.loc[row_name].iloc[0]  # 最近一期
                            
                            # 獲取流通股數
                            if 'sharesOutstanding' in info and info['sharesOutstanding']:
                                shares = float(info['sharesOutstanding'])
                                eps = net_income / shares
                                if eps > 0:
                                    return float(eps)
                            break
            except Exception as e:
                print(f"  從 financials 計算 EPS 失敗: {str(e)}")
            
            return None
            
        except Exception as e:
            print(f"  yfinance 獲取 EPS 完全失敗: {str(e)}")
            return None
    
    def _fetch_financial_from_yfinance(self, stock_code: str, years: int) -> Optional[pd.DataFrame]:
        """
        從 yfinance 獲取完整財務數據
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的數據
            
        Returns:
            財務數據 DataFrame（格式與 FinMind 相容）或 None
        """
        try:
            ticker_symbol = self._normalize_yfinance_ticker(stock_code)
            ticker = yf.Ticker(ticker_symbol)
            
            # 獲取財務報表
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            
            if financials is None or len(financials) == 0:
                return None
            
            # 建立結果 DataFrame
            data_list = []
            
            # 遍歷每一期財報
            for date in financials.columns[:years*4]:  # 假設每年4季
                try:
                    row_data = {'date': pd.to_datetime(date)}
                    
                    # 提取 Revenue（營收）
                    if 'Total Revenue' in financials.index:
                        row_data['revenue'] = float(financials.loc['Total Revenue', date])
                    elif 'Revenue' in financials.index:
                        row_data['revenue'] = float(financials.loc['Revenue', date])
                    else:
                        row_data['revenue'] = 0
                    
                    # 提取 Net Income（淨利）
                    if 'Net Income' in financials.index:
                        row_data['profit'] = float(financials.loc['Net Income', date])
                    elif 'Net Income Common Stockholders' in financials.index:
                        row_data['profit'] = float(financials.loc['Net Income Common Stockholders', date])
                    else:
                        row_data['profit'] = 0
                    
                    # 計算 EPS（如果有流通股數）
                    info = ticker.info
                    if 'sharesOutstanding' in info and info['sharesOutstanding'] and row_data['profit'] != 0:
                        shares = float(info['sharesOutstanding'])
                        row_data['eps'] = row_data['profit'] / shares
                    else:
                        row_data['eps'] = 0
                    
                    # 提取資產負債表數據（如果有對應日期）
                    if balance_sheet is not None and date in balance_sheet.columns:
                        # Total Assets
                        if 'Total Assets' in balance_sheet.index:
                            total_assets = float(balance_sheet.loc['Total Assets', date])
                        else:
                            total_assets = 0
                        
                        # Total Liabilities
                        if 'Total Liabilities Net Minority Interest' in balance_sheet.index:
                            total_liabilities = float(balance_sheet.loc['Total Liabilities Net Minority Interest', date])
                        elif 'Total Liabilities' in balance_sheet.index:
                            total_liabilities = float(balance_sheet.loc['Total Liabilities', date])
                        else:
                            total_liabilities = 0
                        
                        # Stockholder Equity
                        if 'Stockholders Equity' in balance_sheet.index:
                            equity = float(balance_sheet.loc['Stockholders Equity', date])
                        elif 'Total Equity Gross Minority Interest' in balance_sheet.index:
                            equity = float(balance_sheet.loc['Total Equity Gross Minority Interest', date])
                        else:
                            equity = 0
                        
                        # 計算 ROE
                        if equity > 0 and row_data['profit'] != 0:
                            row_data['roe'] = (row_data['profit'] / equity) * 100
                        else:
                            row_data['roe'] = 0
                        
                        # 計算負債比率
                        if total_assets > 0:
                            row_data['debt_ratio'] = (total_liabilities / total_assets) * 100
                        else:
                            row_data['debt_ratio'] = 0
                    else:
                        row_data['roe'] = 0
                        row_data['debt_ratio'] = 0
                    
                    data_list.append(row_data)
                    
                except Exception as e:
                    print(f"  處理 {date} 的數據時出錯: {str(e)}")
                    continue
            
            if len(data_list) > 0:
                df = pd.DataFrame(data_list)
                df = df.sort_values('date')
                return df
            
            return None
            
        except Exception as e:
            print(f"  yfinance 獲取財務數據失敗: {str(e)}")
            return None
    
    def _fetch_financial_from_finmind(self, stock_code: str, years: int) -> Optional[pd.DataFrame]:
        """
        從 FinMind 獲取財務數據（重構自原 get_financial_data 方法）
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的數據
            
        Returns:
            財務數據 DataFrame 或 None
        """
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
            
            # 獲取財報數據
            financial_df = self.finmind.taiwan_stock_financial_statement(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if financial_df is not None and len(financial_df) > 0:
                # 處理數據格式
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
            print(f"  FinMind 獲取失敗: {str(e)}")
            return None

    def get_latest_eps(self, stock_code: str) -> float:
        """
        獲取最新的 EPS（優先使用 yfinance）
        
        資料來源優先序列：
        1. yfinance (主要來源)
        2. FinMind (備援)
        3. 預設值 (最後選擇)
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            最新的 EPS 值
        """
        try:
            print(f"\n正在獲取 {stock_code} 的最新 EPS...")
            
            # 🥇 第一優先：yfinance
            yf_eps = self._fetch_eps_from_yfinance(stock_code)
            if yf_eps is not None and yf_eps > 0:
                print(f"✓ 從 yfinance 獲取 EPS: {yf_eps}")
                self.data_source_stats['yfinance_success'] += 1
                return yf_eps
            else:
                print("✗ yfinance 未返回有效的 EPS")
                self.data_source_stats['yfinance_fail'] += 1
            
            # 🥈 第二優先：FinMind 財務數據
            print("嘗試從 FinMind 獲取 EPS...")
            financial_data = self._fetch_financial_from_finmind(stock_code, years=2)
            if financial_data is not None and len(financial_data) > 0:
                # 過濾掉 NaN 和 0 值
                valid_eps = financial_data['eps'].dropna()
                valid_eps = valid_eps[valid_eps > 0]
                
                if len(valid_eps) > 0:
                    latest_eps = float(valid_eps.iloc[-1])
                    print(f"✓ 從 FinMind 獲取 EPS: {latest_eps}")
                    self.data_source_stats['finmind_success'] += 1
                    return latest_eps
                else:
                    print("✗ FinMind 財務數據中沒有有效的 EPS")
                    self.data_source_stats['finmind_fail'] += 1
            else:
                print("✗ 無法從 FinMind 獲取財務數據")
                self.data_source_stats['finmind_fail'] += 1
            
            # 🥉 最後：使用預設值或返回 0
            print("⚠ 所有資料源均無法提供有效的 EPS")
            
            # 特殊處理：台積電使用預設值
            if stock_code == "2330":
                default_eps = 32.0
                print(f"使用台積電預設 EPS: {default_eps}")
                return default_eps
            
            return 0.0
            
        except Exception as e:
            print(f"✗ 獲取 EPS 過程發生錯誤: {str(e)}")
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

    def calculate_historical_growth_rate(self, stock_code: str, years: int = 3) -> Dict:
        """
        計算歷史 EPS 成長率（基於 CAGR）
        
        Args:
            stock_code: 股票代碼
            years: 回溯年數（預設3年）
        
        Returns:
            {
                'growth_rate_1_5': float,  # 1-5年建議成長率
                'growth_rate_6_10': float, # 6-10年建議成長率
                'data_quality': str,       # 'good'/'fair'/'poor'
                'sample_size': int,        # 有效樣本數
                'message': str             # 說明訊息
            }
        """
        try:
            print(f"\n正在計算 {stock_code} 的歷史成長率...")
            
            # 獲取財務數據
            financial_data = self.get_financial_data(stock_code, years=years)
            
            if financial_data is None or len(financial_data) == 0:
                print(f"警告：無法獲取 {stock_code} 的財務數據")
                return self._get_default_growth_rates('poor', 0, '無歷史數據，使用產業平均值')
            
            # 過濾有效的 EPS 數據
            valid_eps = financial_data[['date', 'eps']].copy()
            valid_eps = valid_eps.dropna()
            valid_eps = valid_eps[valid_eps['eps'] > 0]  # 只保留正值
            
            if len(valid_eps) < 2:
                print(f"警告：有效 EPS 數據不足（僅 {len(valid_eps)} 筆）")
                return self._get_default_growth_rates('poor', len(valid_eps), '歷史數據不足，使用產業平均值')
            
            # 排序並取最早和最新的 EPS
            valid_eps = valid_eps.sort_values('date')
            earliest_eps = float(valid_eps.iloc[0]['eps'])
            latest_eps = float(valid_eps.iloc[-1]['eps'])
            
            # 計算時間跨度（年數）
            date_range = (valid_eps.iloc[-1]['date'] - valid_eps.iloc[0]['date']).days / 365.25
            
            if date_range < 0.5:
                print(f"警告：數據時間跨度太短（{date_range:.1f}年）")
                return self._get_default_growth_rates('poor', len(valid_eps), '時間跨度不足，使用產業平均值')
            
            # 計算 CAGR（年複合成長率）
            if earliest_eps > 0 and latest_eps > 0:
                cagr = (latest_eps / earliest_eps) ** (1 / date_range) - 1
                
                # 檢查成長率是否合理（-30% ~ 100%）
                if cagr < -0.30:
                    print(f"警告：計算出的成長率過低（{cagr:.1%}），限制為 -20%")
                    cagr = -0.20
                    data_quality = 'fair'
                    message = f'基於 {len(valid_eps)} 筆數據，成長率已調整至合理範圍'
                elif cagr > 1.00:
                    print(f"警告：計算出的成長率過高（{cagr:.1%}），限制為 50%")
                    cagr = 0.50
                    data_quality = 'fair'
                    message = f'基於 {len(valid_eps)} 筆數據，成長率已調整至合理範圍'
                else:
                    data_quality = 'good' if len(valid_eps) >= 3 else 'fair'
                    message = f'基於過去 {date_range:.1f} 年歷史數據（{len(valid_eps)} 筆）'
                
                # 計算兩個階段的成長率
                growth_rate_1_5 = cagr  # 1-5年使用歷史 CAGR
                growth_rate_6_10 = cagr * 0.6  # 6-10年假設趨緩至 60%
                
                print(f"計算完成：")
                print(f"  歷史 CAGR: {cagr:.1%}")
                print(f"  建議成長率(1-5年): {growth_rate_1_5:.1%}")
                print(f"  建議成長率(6-10年): {growth_rate_6_10:.1%}")
                print(f"  數據品質: {data_quality}")
                print(f"  樣本數: {len(valid_eps)}")
                
                return {
                    'growth_rate_1_5': growth_rate_1_5,
                    'growth_rate_6_10': growth_rate_6_10,
                    'data_quality': data_quality,
                    'sample_size': len(valid_eps),
                    'message': message
                }
            else:
                print(f"警告：EPS 數據異常（最早:{earliest_eps}, 最新:{latest_eps}）")
                return self._get_default_growth_rates('poor', len(valid_eps), 'EPS 數據異常，使用產業平均值')
            
        except Exception as e:
            print(f"計算成長率失敗: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._get_default_growth_rates('poor', 0, f'計算失敗: {str(e)}')
    
    def _get_default_growth_rates(self, quality: str, sample_size: int, message: str) -> Dict:
        """
        返回預設的成長率（當無法計算歷史成長率時）
        
        Args:
            quality: 數據品質
            sample_size: 樣本數量
            message: 說明訊息
        
        Returns:
            預設成長率字典
        """
        # 使用產業平均值：15%（1-5年）、9%（6-10年）
        return {
            'growth_rate_1_5': 0.15,
            'growth_rate_6_10': 0.09,
            'data_quality': quality,
            'sample_size': sample_size,
            'message': message
        }

    # === FinLab 專屬方法 ===
    
    def _fetch_with_priority(
        self, 
        fetch_functions: List[Tuple[str, Callable]], 
        error_msg: str
    ) -> Optional[pd.DataFrame]:
        """
        依序嘗試多個資料源，返回第一個成功的結果
        
        Args:
            fetch_functions: [(source_name, fetch_func), ...] 資料源與對應函式的列表
            error_msg: 當所有資料源均失敗時的錯誤訊息前綴
        
        Returns:
            成功獲取的 DataFrame，或 None
        """
        for source_name, fetch_func in fetch_functions:
            try:
                print(f"嘗試從 {source_name} 獲取資料...")
                data = fetch_func()
                
                if data is not None and len(data) > 0:
                    print(f"✓ 從 {source_name} 成功獲取 {len(data)} 筆資料")
                    # 更新統計
                    stat_key = f"{source_name.lower()}_success"
                    if stat_key in self.data_source_stats:
                        self.data_source_stats[stat_key] += 1
                    return data
                else:
                    print(f"✗ {source_name} 未返回有效資料")
                    
            except Exception as e:
                print(f"✗ {source_name} 發生錯誤: {str(e)}")
                # 更新統計
                stat_key = f"{source_name.lower()}_fail"
                if stat_key in self.data_source_stats:
                    self.data_source_stats[stat_key] += 1
                continue
        
        print(f"✗ {error_msg}: 所有資料源均失敗")
        return None
    
    def _fetch_financial_from_finlab(self, stock_code: str, years: int) -> Optional[pd.DataFrame]:
        """
        從 FinLab 獲取財務數據
        
        注意：FinLab 免費版不支援財務數據，此方法僅供付費版使用
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的數據
            
        Returns:
            財務數據 DataFrame 或 None
        """
        if not self.finlab_ready:
            return None
        
        # FinLab 免費版不支援財務數據
        print("提示：FinLab 免費版不支援財務數據，將使用 FinMind")
        return None
    
    def _fetch_price_from_finlab(
        self, 
        stock_code: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        從 FinLab 獲取股價數據
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            股價數據 DataFrame 或 None
        """
        if not self.finlab_ready:
            return None
        
        try:
            # 獲取收盤價
            close_data = finlab_data.get('price:收盤價', stock_code)
            
            if close_data is None or len(close_data) == 0:
                return None
            
            # 過濾日期範圍
            close_data = close_data[(close_data.index >= start_date) & (close_data.index <= end_date)]
            
            if len(close_data) == 0:
                return None
            
            # 建立基本 DataFrame
            df = pd.DataFrame({
                'date': pd.to_datetime(close_data.index),
                'stock_code': stock_code,
                'close_price': close_data.values
            })
            
            # 嘗試獲取其他價格資訊
            try:
                open_data = finlab_data.get('price:開盤價', stock_code)
                if open_data is not None and len(open_data) > 0:
                    open_data = open_data[(open_data.index >= start_date) & (open_data.index <= end_date)]
                    open_df = pd.DataFrame({
                        'date': pd.to_datetime(open_data.index),
                        'open_price': open_data.values
                    })
                    df = df.merge(open_df, on='date', how='left')
            except:
                df['open_price'] = df['close_price']
            
            try:
                high_data = finlab_data.get('price:最高價', stock_code)
                if high_data is not None and len(high_data) > 0:
                    high_data = high_data[(high_data.index >= start_date) & (high_data.index <= end_date)]
                    high_df = pd.DataFrame({
                        'date': pd.to_datetime(high_data.index),
                        'high_price': high_data.values
                    })
                    df = df.merge(high_df, on='date', how='left')
            except:
                df['high_price'] = df['close_price']
            
            try:
                low_data = finlab_data.get('price:最低價', stock_code)
                if low_data is not None and len(low_data) > 0:
                    low_data = low_data[(low_data.index >= start_date) & (low_data.index <= end_date)]
                    low_df = pd.DataFrame({
                        'date': pd.to_datetime(low_data.index),
                        'low_price': low_data.values
                    })
                    df = df.merge(low_df, on='date', how='left')
            except:
                df['low_price'] = df['close_price']
            
            try:
                volume_data = finlab_data.get('price:成交股數', stock_code)
                if volume_data is not None and len(volume_data) > 0:
                    volume_data = volume_data[(volume_data.index >= start_date) & (volume_data.index <= end_date)]
                    volume_df = pd.DataFrame({
                        'date': pd.to_datetime(volume_data.index),
                        'volume': volume_data.values
                    })
                    df = df.merge(volume_df, on='date', how='left')
            except:
                df['volume'] = 0
            
            # 填充缺失的欄位
            for col in ['open_price', 'high_price', 'low_price', 'volume']:
                if col not in df.columns:
                    df[col] = df['close_price'] if col != 'volume' else 0
            
            return df
            
        except Exception as e:
            print(f"FinLab 股價數據獲取失敗: {str(e)}")
            return None

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

    def get_all_stocks_info(self, force_update: bool = False) -> pd.DataFrame:
        """
        獲取所有台股的代碼與名稱清單
        
        Args:
            force_update: 是否強制更新
            
        Returns:
            包含 stock_code 和 stock_name 的 DataFrame
        """
        # 先檢查快取
        if not force_update:
            cached_list = self._get_cached_stock_list()
            if cached_list is not None and len(cached_list) > 0:
                return cached_list
        
        # 從 FinMind 獲取
        try:
            info = self.finmind.taiwan_stock_info()
            if info is not None and len(info) > 0:
                # 只保留需要的欄位
                df = pd.DataFrame({
                    'stock_code': info['stock_id'],
                    'stock_name': info['stock_name']
                })
                
                # 儲存到快取
                self._save_stock_list(df)
                
                return df
        except Exception as e:
            print(f"獲取股票清單失敗: {str(e)}")
        
        # 如果失敗，返回快取數據
        cached_list = self._get_cached_stock_list()
        if cached_list is not None:
            return cached_list
        
        return pd.DataFrame(columns=['stock_code', 'stock_name'])

    def normalize_stock_input(self, user_input: str) -> Dict:
        """
        標準化使用者輸入（支援股票代碼或完整名稱）
        
        Args:
            user_input: 使用者輸入的字串（代碼或名稱）
            
        Returns:
            {
                'stock_code': str,      # 標準化的股票代碼
                'stock_name': str,      # 股票名稱
                'is_valid': bool,       # 是否為有效輸入
                'display_name': str     # 顯示用格式 "代碼 名稱"
            }
        """
        if not user_input or not user_input.strip():
            return {
                'stock_code': '',
                'stock_name': '',
                'is_valid': False,
                'display_name': ''
            }
        
        user_input = user_input.strip()
        
        # 獲取股票清單
        stocks_df = self.get_all_stocks_info()
        
        if len(stocks_df) == 0:
            # 如果無法獲取股票清單，嘗試直接查詢
            stock_name = self._get_stock_name(user_input)
            if stock_name and not stock_name.startswith('股票'):
                return {
                    'stock_code': user_input,
                    'stock_name': stock_name,
                    'is_valid': True,
                    'display_name': f"{user_input} {stock_name}"
                }
            return {
                'stock_code': user_input,
                'stock_name': '',
                'is_valid': False,
                'display_name': ''
            }
        
        # 情況 1: 使用者輸入純數字（當作代碼處理）
        if user_input.isdigit():
            match = stocks_df[stocks_df['stock_code'] == user_input]
            if len(match) > 0:
                stock_name = match.iloc[0]['stock_name']
                return {
                    'stock_code': user_input,
                    'stock_name': stock_name,
                    'is_valid': True,
                    'display_name': f"{user_input} {stock_name}"
                }
        
        # 情況 2: 使用者輸入名稱（完整匹配）
        # 先嘗試完全匹配
        match = stocks_df[stocks_df['stock_name'] == user_input]
        if len(match) > 0:
            stock_code = match.iloc[0]['stock_code']
            stock_name = match.iloc[0]['stock_name']
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'is_valid': True,
                'display_name': f"{stock_code} {stock_name}"
            }
        
        # 情況 3: 不區分大小寫的匹配（支援英文名稱）
        match = stocks_df[stocks_df['stock_name'].str.upper() == user_input.upper()]
        if len(match) > 0:
            stock_code = match.iloc[0]['stock_code']
            stock_name = match.iloc[0]['stock_name']
            return {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'is_valid': True,
                'display_name': f"{stock_code} {stock_name}"
            }
        
        # 無法匹配
        return {
            'stock_code': user_input,
            'stock_name': '',
            'is_valid': False,
            'display_name': ''
        }

    def _get_cached_stock_list(self) -> Optional[pd.DataFrame]:
        """從資料庫獲取快取的股票清單"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 檢查是否有最近更新的資料（7天內）
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM stock_info 
                WHERE update_time >= datetime('now', '-7 days')
            ''')
            count = cursor.fetchone()[0]
            
            if count > 0:
                df = pd.read_sql_query('''
                    SELECT stock_code, stock_name
                    FROM stock_info
                    ORDER BY stock_code
                ''', conn)
                conn.close()
                return df if len(df) > 0 else None
            
            conn.close()
            return None
        except Exception as e:
            print(f"讀取快取股票清單失敗: {str(e)}")
            return None

    def _save_stock_list(self, df: pd.DataFrame):
        """儲存股票清單到資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            update_time = datetime.now()
            
            for _, row in df.iterrows():
                cursor.execute('''
                    INSERT OR REPLACE INTO stock_info
                    (stock_code, stock_name, industry, market, update_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    row['stock_code'],
                    row['stock_name'],
                    '',  # industry 可以之後補充
                    '',  # market 可以之後補充
                    update_time
                ))
            
            conn.commit()
            conn.close()
            print(f"已儲存 {len(df)} 筆股票資訊到快取")
        except Exception as e:
            print(f"儲存股票清單失敗: {str(e)}")


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
