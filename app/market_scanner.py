import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import sqlite3
import os
from typing import Optional, List, Dict
import warnings
from dotenv import load_dotenv

warnings.filterwarnings('ignore')

class MarketScanner:
    """
    Unified Market Scanner Engine (v2.4.0)
    Integrates FinLab, FinMind, and Yahoo Finance into a single Data Fusion Pipeline.
    """
    def __init__(self, db_path: str = "app/data/market_scan.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_snapshot (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                current_price REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                dividend_yield REAL,
                roe REAL,
                market_cap REAL,
                revenue_growth REAL,
                high_52w REAL,
                low_52w REAL,
                last_updated TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def get_market_snapshot(self) -> pd.DataFrame:
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql("SELECT * FROM market_snapshot", conn)
            conn.close()
            return df
        except Exception:
            return pd.DataFrame()

    def _finalize_and_save_snapshot(self, df: pd.DataFrame, progress_callback: Optional[callable] = None) -> bool:
        """
        [Data Fusion Hub] Standardizes schema and patches real-time 2026 data via Yahoo Finance.
        """
        try:
            if df.empty: return False
            
            # Ensure standard columns exist
            cols = ["stock_code", "stock_name", "current_price", "pe_ratio", "pb_ratio", 
                    "dividend_yield", "roe", "market_cap", "revenue_growth", "high_52w", "low_52w"]
            for col in cols:
                if col not in df.columns: df[col] = 0.0
            
            # --- 2026 Real-time Sync (Yahoo Finance) ---
            if progress_callback:
                progress_callback(90, 100, "正在同步 2026 即時行情 (Yahoo Finance)...")
            
            stock_codes = df["stock_code"].astype(str).tolist()
            tickers = [f"{s}.TW" if len(s) <= 4 and int(s) < 10000 else f"{s}.TWO" for s in stock_codes if s.isdigit()]
            
            # Download 1y data for current price and 52w range
            data_yf = yf.download(tickers, period="1y", interval="1d", group_by='ticker', threads=True, progress=False)
            
            for code in stock_codes:
                t = f"{code}.TW" if len(code) <= 4 and int(code) < 10000 else f"{code}.TWO"
                try:
                    if t in data_yf.columns.levels[0]:
                        hist = data_yf[t].dropna()
                        if not hist.empty:
                            mask = df["stock_code"] == code
                            df.loc[mask, "current_price"] = hist['Close'].iloc[-1]
                            df.loc[mask, "high_52w"] = hist['High'].max()
                            df.loc[mask, "low_52w"] = hist['Low'].min()
                except: continue
            
            df["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Save to SQLite
            conn = sqlite3.connect(self.db_path)
            df[cols + ["last_updated"]].to_sql("market_snapshot", conn, if_exists="replace", index=False)
            conn.close()
            return True
        except Exception as e:
            print(f"Data Fusion Error: {e}")
            return False

    def update_market_snapshot_finlab(self, token: str, progress_callback: Optional[callable] = None) -> bool:
        """
        FinLab Engine with Data Fusion.
        """
        try:
            import finlab
            from finlab import data
            finlab.login(token)
            
            if progress_callback: progress_callback(10, 100, "正在下載 FinLab 基礎數據...")
            
            close_df = data.get('price:收盤價')
            close_price = close_df.dropna(how='all').iloc[-1]
            master_index = close_price.dropna().index

            def safe_series(keywords: list, category: str = "", default_key: str = "") -> pd.Series:
                try:
                    entries = data.entry_names
                    actual_key = None
                    for k in keywords:
                        for e in entries:
                            if (not category or category in e) and k in e:
                                actual_key = e
                                break
                        if actual_key: break
                    
                    actual_key = actual_key or default_key
                    if not actual_key: return pd.Series(0.0, index=master_index)
                    
                    s = data.get(actual_key).dropna(how='all').iloc[-1].reindex(master_index).fillna(0.0)
                    # Unit correction
                    if ("roe" in str(keywords).lower() or "yield" in str(keywords).lower() or "殖利率" in str(keywords)) and s.mean() < 0.5:
                        s *= 100.0
                    return s
                except: return pd.Series(0.0, index=master_index)

            df = pd.DataFrame({
                "stock_code": master_index,
                "pe_ratio": safe_series(["本益比", "PER"], default_key="price:本益比"),
                "pb_ratio": safe_series(["股價淨值比", "PBR"], default_key="price:股價淨值比"),
                "dividend_yield": safe_series(["殖利率", "Yield"], category="price"),
                "roe": safe_series(["ROE", "股東權益報酬率"]),
                "market_cap": safe_series(["市值", "MarketCap"]),
                "revenue_growth": safe_series(["營收成長率"])
            })

            # Name mapping
            try:
                df_info = data.get('company_basic_info')
                name_map = df_info.set_index('stock_id')['公司簡稱'].to_dict()
                df["stock_name"] = df["stock_code"].map(name_map)
            except: df["stock_name"] = df["stock_code"]

            return self._finalize_and_save_snapshot(df, progress_callback)
        except Exception: return False

    def update_market_snapshot_finmind(self, all_stocks_df: pd.DataFrame, token: str, progress_callback: Optional[callable] = None) -> bool:
        """
        FinMind Engine with Data Fusion.
        """
        try:
            from FinMind.data import DataLoader
            dl = DataLoader()
            dl.login_by_token(token)
            
            price_df = dl.taiwan_stock_daily(start_date=(datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
            if price_df.empty: return False
            latest_date = price_df['date'].max()
            
            stats_df = dl.taiwan_stock_per_pbr(start_date=latest_date)
            if stats_df.empty: return False
            
            df = price_df[price_df['date'] == latest_date][['stock_id', 'close']].rename(columns={'stock_id': 'stock_code', 'close': 'current_price'})
            stats = stats_df[['stock_id', 'PE', 'PB', 'dividend_yield']].rename(columns={'stock_id': 'stock_code', 'PE': 'pe_ratio', 'PB': 'pb_ratio'})
            df = df.merge(stats, on='stock_code', how='left')
            
            # Merge name from all_stocks_df
            df = df.merge(all_stocks_df[['stock_id', 'stock_name']], left_on='stock_code', right_on='stock_id', how='left').drop(columns=['stock_id'])
            
            return self._finalize_and_save_snapshot(df, progress_callback)
        except Exception: return False

    def filter_stocks(self, min_market_cap: float = 0, max_pe: float = 100, min_yield: float = 0, min_roe: float = 0, low_base_enabled: bool = False) -> pd.DataFrame:
        df = self.get_market_snapshot()
        if df.empty: return pd.DataFrame()
        
        df = df.copy()
        numeric_cols = ["market_cap", "pe_ratio", "pb_ratio", "dividend_yield", "roe", "current_price", "high_52w", "low_52w"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Market Cap Normalization
        if df["market_cap"].max() > 1e8: df["market_cap"] /= 1e8
        
        # Filters (Resilient to 0.0)
        if min_market_cap > 0: df = df[(df["market_cap"] >= min_market_cap) | (df["market_cap"] == 0.0)]
        if max_pe < 100: df = df[((df["pe_ratio"] > 0) & (df["pe_ratio"] <= max_pe)) | (df["pe_ratio"] == 0.0)]
        df = df[df["dividend_yield"] >= min_yield]
        df = df[df["roe"] >= min_roe]

        # Price Position
        if "high_52w" in df.columns and "low_52w" in df.columns:
            def calculate_pos(row):
                h, l, p = row["high_52w"], row["low_52w"], row["current_price"]
                return (p - l) / (h - l) if h > l else 0.5
            df["price_position"] = df.apply(calculate_pos, axis=1)
            if low_base_enabled: df = df[df["price_position"] <= 0.3]
        
        # Scoring
        if not df.empty:
            score_cols = df.apply(self._calculate_fundamental_score, axis=1, result_type="expand")
            df[["fundamental_score", "fundamental_grade"]] = score_cols
        return df

    def _calculate_fundamental_score(self, row) -> tuple:
        score = 70
        try:
            if row['roe'] > 15: score += 15
            elif row['roe'] > 10: score += 10
            if 0 < row['pe_ratio'] < 15: score += 10
            if row['dividend_yield'] > 5: score += 5
        except: pass
        score = min(score, 100)
        grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C"
        return score, grade
