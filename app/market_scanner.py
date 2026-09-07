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
            
            # Save to SQLite — UPSERT (保留既有 current_price/high_52w/low_52w，避免 FinLab
            # 無價格資料時把整表清成 0；2026-08-22 修復 if_exists="replace" 每日清空價格的 bug)
            conn = sqlite3.connect(self.db_path)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 讀出現有價格，作為 fallback
            try:
                old = pd.read_sql("SELECT stock_code, current_price, high_52w, low_52w FROM market_snapshot", conn)
            except Exception:
                old = pd.DataFrame(columns=["stock_code", "current_price", "high_52w", "low_52w"])
            old_map = old.set_index("stock_code").to_dict("index")
            
            upsert_cols = ["stock_code", "stock_name", "current_price", "pe_ratio", "pb_ratio",
                           "dividend_yield", "roe", "market_cap", "revenue_growth",
                           "high_52w", "low_52w", "last_updated"]
            cur = conn.cursor()
            for _, row in df.iterrows():
                code = str(row.get("stock_code", ""))
                if not code:
                    continue
                price = float(row.get("current_price") or 0.0)
                hi = float(row.get("high_52w") or 0.0)
                lo = float(row.get("low_52w") or 0.0)
                if code in old_map:
                    # 新值無效時保留舊值（只在新值有效時覆蓋）
                    if price <= 0:
                        price = float(old_map[code].get("current_price") or 0.0)
                    if hi <= 0:
                        hi = float(old_map[code].get("high_52w") or 0.0)
                    if lo <= 0:
                        lo = float(old_map[code].get("low_52w") or 0.0)
                    cur.execute(
                        """UPDATE market_snapshot SET stock_name=?, current_price=?, pe_ratio=?,
                           pb_ratio=?, dividend_yield=?, roe=?, market_cap=?, revenue_growth=?,
                           high_52w=?, low_52w=?, last_updated=?
                           WHERE stock_code=?""",
                        (row.get("stock_name", ""), price,
                         float(row.get("pe_ratio") or 0.0), float(row.get("pb_ratio") or 0.0),
                         float(row.get("dividend_yield") or 0.0), float(row.get("roe") or 0.0),
                         float(row.get("market_cap") or 0.0), float(row.get("revenue_growth") or 0.0),
                         hi, lo, now, code)
                    )
                else:
                    cur.execute(
                        """INSERT INTO market_snapshot (stock_code, stock_name, current_price,
                           pe_ratio, pb_ratio, dividend_yield, roe, market_cap, revenue_growth,
                           high_52w, low_52w, last_updated)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (code, row.get("stock_name", ""), price,
                         float(row.get("pe_ratio") or 0.0), float(row.get("pb_ratio") or 0.0),
                         float(row.get("dividend_yield") or 0.0), float(row.get("roe") or 0.0),
                         float(row.get("market_cap") or 0.0), float(row.get("revenue_growth") or 0.0),
                         hi, lo, now)
                    )
            conn.commit()
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
                    
                    raw_data = data.get(actual_key).dropna(how='all')
                    # For ROE, calculate TTM (rolling 4 quarters sum) for annualized ROE
                    if any(k in str(keywords).lower() or k in actual_key.lower() for k in ["roe", "股東權益報酬率"]):
                        s = raw_data.rolling(4, min_periods=1).sum().iloc[-1].reindex(master_index).fillna(0.0)
                    else:
                        s = raw_data.iloc[-1].reindex(master_index).fillna(0.0)
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
        # 舊快照可能缺欄位：欄位存在才套用門檻；缺欄位且門檻 > 0 時視為無法驗證 → 不通過
        if "dividend_yield" in df.columns:
            df = df[df["dividend_yield"] >= min_yield]
        elif min_yield > 0:
            df = df.iloc[0:0]
        if "roe" in df.columns:
            df = df[df["roe"] >= min_roe]
        elif min_roe > 0:
            df = df.iloc[0:0]

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
            # 缺欄位時以 0 視為「無資料」：不計分也不扣分（容錯降級）
            roe = row.get("roe", 0) or 0
            pe = row.get("pe_ratio", 0) or 0
            pb = row.get("pb_ratio", 0) or 0
            dividend_yield = row.get("dividend_yield", 0) or 0
            revenue_growth = row.get("revenue_growth", 0) or 0

            # 單位正規化：0 < v <= 1 視為小數（0.22 = 22%），否則視為百分比（22.0 = 22%）
            if 0 < roe <= 1: roe *= 100
            if 0 < dividend_yield <= 1: dividend_yield *= 100

            # 加分：優於門檻的基本面
            if roe > 15: score += 15
            elif roe > 10: score += 10
            if 0 < pe < 15: score += 10
            if dividend_yield > 5: score += 5

            # 扣分：明顯偏弱的基本面（0 / 缺值不扣，避免誤傷無資料股票）
            if pe > 40: score -= 20
            elif pe > 25: score -= 10
            if 0 < roe < 5: score -= 10
            if pb > 3: score -= 10
            if revenue_growth < 0: score -= 15
        except Exception:
            pass
        score = max(0, min(score, 100))
        grade = (
            "A+" if score >= 90 else
            "A" if score >= 80 else
            "B+" if score >= 70 else
            "B" if score >= 60 else
            "C" if score >= 50 else
            "D"
        )
        return score, grade
