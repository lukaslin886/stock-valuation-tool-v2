"""
YFinance 資料來源實作
使用 yfinance 套件獲取台股資料
"""

from typing import Optional, Dict
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

from .base import DataSource


class YFinanceSource(DataSource):
    """YFinance 資料來源"""
    
    def __init__(self):
        """初始化 YFinance 資料來源"""
        super().__init__('yfinance')
    
    def _init_source(self) -> None:
        """初始化資料來源（yfinance 不需要登入）"""
        try:
            # 測試 yfinance 是否可用
            test_ticker = yf.Ticker("2330.TW")
            _ = test_ticker.info
            self.is_available = True
            print("[OK] YFinance 已準備就緒")
        except Exception as e:
            self.is_available = False
            print(f"[FAIL] YFinance 初始化失敗: {str(e)}")
    
    def _normalize_ticker(self, stock_code: str) -> str:
        """
        將台股代碼轉換為 yfinance 格式
        
        Args:
            stock_code: 股票代碼（例如：2330）
            
        Returns:
            yfinance 格式的股票代碼（例如：2330.TW 或 2330.TWO）
        """
        # 上市股票通常以 1-2 開頭，使用 .TW
        # 上櫃股票通常以 3-9 開頭，使用 .TWO
        if stock_code.startswith(('1', '2')):
            return f"{stock_code}.TW"
        else:
            return f"{stock_code}.TWO"
    
    def get_stock_price(
        self,
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """獲取股價資料"""
        if not self.is_available:
            return None
        
        try:
            if start_date is None:
                start_date = datetime.now() - timedelta(days=365*5)
            if end_date is None:
                end_date = datetime.now()
            
            ticker_symbol = self._normalize_ticker(stock_code)
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(start=start_date, end=end_date)
            
            if len(hist) == 0:
                return None
            
            # 標準化欄位名稱
            df = pd.DataFrame({
                'date': hist.index,
                'open_price': hist['Open'].values,
                'high_price': hist['High'].values,
                'low_price': hist['Low'].values,
                'close_price': hist['Close'].values,
                'volume': hist['Volume'].values
            })
            
            return df
            
        except Exception as e:
            print(f"  YFinance 獲取股價失敗: {str(e)}")
            return None
    
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """獲取財務報表資料"""
        if not self.is_available:
            return None
        
        try:
            ticker_symbol = self._normalize_ticker(stock_code)
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
            print(f"  YFinance 獲取財務數據失敗: {str(e)}")
            return None
    
    def get_latest_eps(self, stock_code: str) -> Optional[float]:
        """獲取最新 EPS"""
        if not self.is_available:
            return None
        
        try:
            ticker_symbol = self._normalize_ticker(stock_code)
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
                    if 'Earnings' in earnings.columns:
                        latest_earnings = earnings['Earnings'].iloc[-1]
                        if latest_earnings > 0:
                            return float(latest_earnings)
            except Exception as e:
                print(f"  從 earnings 獲取 EPS 失敗: {str(e)}")
            
            # 方法 3: 從 financials 計算
            try:
                financials = ticker.financials
                if financials is not None and len(financials) > 0:
                    for row_name in ['Net Income', 'Net Income Common Stockholders']:
                        if row_name in financials.index:
                            net_income = financials.loc[row_name].iloc[0]
                            
                            info = ticker.info
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
            print(f"  YFinance 獲取 EPS 完全失敗: {str(e)}")
            return None
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """獲取股票基本資訊"""
        if not self.is_available:
            return None
        
        try:
            ticker_symbol = self._normalize_ticker(stock_code)
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            
            return {
                'stock_code': stock_code,
                'stock_name': info.get('longName', info.get('shortName', f'股票{stock_code}')),
                'industry': info.get('industry', '未分類'),
                'market': '上市' if stock_code.startswith(('1', '2')) else '上櫃'
            }
            
        except Exception as e:
            print(f"  YFinance 獲取股票資訊失敗: {str(e)}")
            return None
