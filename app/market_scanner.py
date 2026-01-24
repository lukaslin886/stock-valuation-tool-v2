"""
Market Scanner Module
Responsible for scanning the entire market to identify "Low Base" and "Buy & Hold" candidates.
Uses multi-threading to fetch data efficiently from yfinance and caches results in SQLite.
"""

import pandas as pd
import yfinance as yf
import sqlite3
import concurrent.futures
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os

class MarketScanner:
    def __init__(self, db_path: str = "data/market_scan.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for market snapshot."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_snapshot (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                market_cap REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                dividend_yield REAL,
                revenue_growth REAL,
                current_price REAL,
                high_52w REAL,
                low_52w REAL,
                avg_volume REAL,
                last_updated TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def get_market_snapshot(self) -> pd.DataFrame:
        """Get the latest cached market snapshot."""
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql("SELECT * FROM market_snapshot", conn)
            return df
        except Exception as e:
            print(f"Error reading snapshot: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def update_market_snapshot(self, stock_list: List[Dict[str, str]], max_workers: int = 20, progress_callback=None):
        """
        Update market data for the given list of stocks.
        
        Args:
            stock_list: List of dicts with 'stock_id' and 'stock_name'.
            max_workers: Number of threads for parallel fetching.
            progress_callback: Optional callback function(current, total) for UI progress.
        """
        total_stocks = len(stock_list)
        results = []
        
        # Function to process a single stock
        def process_stock(stock):
            code = stock['stock_id']
            name = stock['stock_name']
            ticker_symbol = f"{code}.TW" if code.startswith(('1', '2')) else f"{code}.TWO"
            
            try:
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.info
                
                # Extract metrics (handle missing keys safely)
                market_cap = info.get('marketCap', 0)
                pe_ratio = info.get('trailingPE', 0)
                pb_ratio = info.get('priceToBook', 0)
                dividend_yield = info.get('dividendYield', 0)
                revenue_growth = info.get('revenueGrowth', 0)
                current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                high_52w = info.get('fiftyTwoWeekHigh', 0)
                low_52w = info.get('fiftyTwoWeekLow', 0)
                avg_volume = info.get('averageVolume', 0)

                # Skip if no valid price data
                if current_price == 0:
                    return None

                return {
                    'stock_code': code,
                    'stock_name': name,
                    'market_cap': market_cap,
                    'pe_ratio': pe_ratio,
                    'pb_ratio': pb_ratio,
                    'dividend_yield': dividend_yield,
                    'revenue_growth': revenue_growth,
                    'current_price': current_price,
                    'high_52w': high_52w,
                    'low_52w': low_52w,
                    'avg_volume': avg_volume,
                    'last_updated': datetime.now()
                }
            except Exception as e:
                # print(f"Error fetching {code}: {e}")
                return None

        # Run with ThreadPoolExecutor
        print(f"Starting scan for {total_stocks} stocks...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_stock = {executor.submit(process_stock, stock): stock for stock in stock_list}
            completed_count = 0
            
            for future in concurrent.futures.as_completed(future_to_stock):
                data = future.result()
                if data:
                    results.append(data)
                
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total_stocks)
                    
        # Save to DB
        if results:
            df = pd.DataFrame(results)
            conn = sqlite3.connect(self.db_path)
            # Use 'replace' to update existing records
            df.to_sql('market_snapshot', conn, if_exists='replace', index=False)
            conn.close()
            print(f"Snapshot updated. {len(results)} stocks saved.")
        else:
            print("No data fetched.")

    def filter_stocks(self, 
                      min_market_cap: float = 0, # In Billions
                      max_pe: float = 100,
                      min_yield: float = 0,
                      low_base_enabled: bool = False
                      ) -> pd.DataFrame:
        """
        Filter stocks based on criteria.
        
        Args:
            min_market_cap: Minimum Market Cap in NT$ Billion
            max_pe: Maximum P/E Ratio
            min_yield: Minimum Dividend Yield (e.g., 0.03 for 3%)
            low_base_enabled: If True, filters for stocks trading near 52w low.
        """
        df = self.get_market_snapshot()
        if df.empty:
            return df
        
        # Apply Filters
        
        # 1. Market Cap (Convert Billions to Actual)
        df = df[df['market_cap'] >= min_market_cap * 1_000_000_000]
        
        # 2. P/E Ratio (Filter out 0 or negative PE usually, but user said 'Low PE')
        # We allow 0 PE (loss making) to be filtered OUT if max_pe > 0
        df = df[df['pe_ratio'] > 0] 
        df = df[df['pe_ratio'] <= max_pe]
        
        # 3. Dividend Yield
        df = df[df['dividend_yield'] >= min_yield]
        
        # 4. Low Base Logic
        if low_base_enabled:
            # Definition: Price is in the lower 30% of 52-week range
            # Formula: Position = (Price - Low) / (High - Low)
            # If High == Low, Position = 0
            
            def calculate_position(row):
                if row['high_52w'] == row['low_52w']:
                    return 0
                return (row['current_price'] - row['low_52w']) / (row['high_52w'] - row['low_52w'])
            
            df['price_position'] = df.apply(calculate_position, axis=1)
            
            # Filter: Position <= 0.3 (Lower 30%)
            df = df[df['price_position'] <= 0.3]
            
            # Additional Low Base: PE Low Base?
            # We don't have historical PE in snapshot, so rely on Price Base.
            
        return df

    def perform_deep_scan(self, stock_codes: List[str], max_workers: int = 10, progress_callback=None) -> pd.DataFrame:
        """
        Perform deep analysis on a filtered list of stocks.
        Fetches historical data to calculate Growth (CAGR) and Dividend Consistency.
        
        Args:
            stock_codes: List of stock codes (str).
        """
        results = []
        total = len(stock_codes)
        
        print(f"Starting Deep Scan for {total} stocks...")
        
        def analyze_stock(code):
            ticker_symbol = f"{code}.TW" if code.startswith(('1', '2')) else f"{code}.TWO"
            try:
                ticker = yf.Ticker(ticker_symbol)
                
                # 1. Financials (Income Statement) for Growth
                # yfinance financials are usually annual or quarterly
                fin = ticker.financials
                if fin.empty:
                    return None
                
                # Sort columns by date ascending
                fin = fin[sorted(fin.columns)]
                
                # Get Revenue and Net Income (Profit)
                # Rows might be named 'Total Revenue', 'Net Income' etc.
                revenue_row = next((r for r in ['Total Revenue', 'Revenue', 'Operating Revenue'] if r in fin.index), None)
                profit_row = next((r for r in ['Net Income', 'Net Income Common Stockholders'] if r in fin.index), None)
                
                cagr_revenue_5y = 0
                cagr_profit_5y = 0
                
                if revenue_row:
                    revs = fin.loc[revenue_row].dropna()
                    cagr_revenue_5y = self._calculate_cagr(revs, 5)
                    
                if profit_row:
                    profits = fin.loc[profit_row].dropna()
                    cagr_profit_5y = self._calculate_cagr(profits, 5)

                # 2. Dividends for Consistency
                divs = ticker.dividends
                div_consecutive_years = 0
                if not divs.empty:
                    # Group by year
                    divs_by_year = divs.groupby(divs.index.year).sum()
                    # Check recent years consistency
                    current_year = datetime.now().year
                    consistent = True
                    # Check last 5 years excluding current incomplete year if needed
                    # Let's count backwards from last year
                    last_year = divs_by_year.index.max()
                    count = 0
                    for y in range(last_year, last_year - 10, -1):
                        if y in divs_by_year.index and divs_by_year.loc[y] > 0:
                            count += 1
                        else:
                            break
                    div_consecutive_years = count

                return {
                    'stock_code': code,
                    'revenue_cagr_5y': cagr_revenue_5y,
                    'profit_cagr_5y': cagr_profit_5y,
                    'div_years': div_consecutive_years
                }

            except Exception as e:
                # print(f"Deep scan error {code}: {e}")
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_stock = {executor.submit(analyze_stock, code): code for code in stock_codes}
            completed_count = 0
            
            for future in concurrent.futures.as_completed(future_to_stock):
                data = future.result()
                if data:
                    results.append(data)
                
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total)
        
        if results:
            return pd.DataFrame(results)
        return pd.DataFrame()

    def _calculate_cagr(self, series: pd.Series, years: int) -> float:
        """Calculate CAGR given a pandas Series of values (sorted by date)."""
        if len(series) < 2:
            return 0.0
        
        # Take at most 'years' of data
        # Series is sorted ascending date
        recent = series.iloc[-1]
        start_idx = max(0, len(series) - 1 - years)
        old = series.iloc[start_idx]
        
        # Actual years difference
        # Assuming annual data roughly
        n = len(series) - 1 - start_idx
        if n < 1: n = 1
        
        if old <= 0 or recent <= 0:
             return 0.0 # Handle negative/zero base
             
        try:
            cagr = (recent / old) ** (1/n) - 1
            return cagr
        except:
            return 0.0

