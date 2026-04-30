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
    FUNDAMENTAL_WEIGHTS = {
        "roe": 0.35,
        "valuation": 0.25,
        "dividend": 0.20,
        "growth": 0.20,
    }

    def __init__(self, db_path: str = "data/market_scan.db"):
        self.db_path = db_path
        self._init_db()

    @staticmethod
    def _safe_number(value: Optional[float], default: float = 0.0) -> float:
        """Safely convert value to float, falling back to default for missing/invalid values."""
        if value is None or pd.isna(value):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _grade_from_score(score: float) -> str:
        """Map numeric score (0-100) to letter grade."""
        if score >= 85:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 75:
            return "B+"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        return "D"

    @classmethod
    def _calculate_fundamental_score(cls, row: pd.Series) -> Tuple[float, str]:
        """Calculate weighted fundamental score and grade for a stock row."""
        roe = cls._safe_number(row.get("roe"))
        pe_ratio = cls._safe_number(row.get("pe_ratio"))
        pb_ratio = cls._safe_number(row.get("pb_ratio"))
        dividend_yield = cls._safe_number(row.get("dividend_yield"))
        revenue_growth = cls._safe_number(row.get("revenue_growth"))

        # 1) Profit quality (ROE)
        if roe >= 0.20:
            roe_score = 100.0
        elif roe >= 0.15:
            roe_score = 85.0
        elif roe >= 0.10:
            roe_score = 70.0
        elif roe >= 0.05:
            roe_score = 50.0
        elif roe >= 0:
            roe_score = 30.0
        else:
            roe_score = 10.0

        # 2) Valuation reasonability (PE + PB)
        if pe_ratio <= 0:
            pe_score = 20.0
        elif pe_ratio <= 10:
            pe_score = 100.0
        elif pe_ratio <= 15:
            pe_score = 85.0
        elif pe_ratio <= 20:
            pe_score = 70.0
        elif pe_ratio <= 25:
            pe_score = 55.0
        elif pe_ratio <= 35:
            pe_score = 35.0
        else:
            pe_score = 15.0

        if pb_ratio <= 0:
            pb_score = 30.0
        elif pb_ratio <= 1.0:
            pb_score = 100.0
        elif pb_ratio <= 1.5:
            pb_score = 85.0
        elif pb_ratio <= 2.5:
            pb_score = 70.0
        elif pb_ratio <= 4.0:
            pb_score = 50.0
        else:
            pb_score = 25.0

        valuation_score = pe_score * 0.7 + pb_score * 0.3

        # 3) Shareholder return (Dividend Yield)
        if dividend_yield >= 0.06:
            dividend_score = 100.0
        elif dividend_yield >= 0.04:
            dividend_score = 85.0
        elif dividend_yield >= 0.03:
            dividend_score = 70.0
        elif dividend_yield >= 0.02:
            dividend_score = 55.0
        elif dividend_yield >= 0.01:
            dividend_score = 40.0
        elif dividend_yield >= 0:
            dividend_score = 25.0
        else:
            dividend_score = 10.0

        # 4) Growth quality (Revenue Growth)
        if revenue_growth >= 0.20:
            growth_score = 100.0
        elif revenue_growth >= 0.12:
            growth_score = 85.0
        elif revenue_growth >= 0.06:
            growth_score = 70.0
        elif revenue_growth >= 0.02:
            growth_score = 55.0
        elif revenue_growth >= 0:
            growth_score = 40.0
        elif revenue_growth >= -0.05:
            growth_score = 25.0
        else:
            growth_score = 10.0

        final_score = (
            roe_score * cls.FUNDAMENTAL_WEIGHTS["roe"]
            + valuation_score * cls.FUNDAMENTAL_WEIGHTS["valuation"]
            + dividend_score * cls.FUNDAMENTAL_WEIGHTS["dividend"]
            + growth_score * cls.FUNDAMENTAL_WEIGHTS["growth"]
        )
        final_score = min(max(final_score, 0.0), 100.0)
        return final_score, cls._grade_from_score(final_score)

    def _init_db(self):
        """Initialize SQLite database for market snapshot."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshot (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                market_cap REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                roe REAL,
                dividend_yield REAL,
                revenue_growth REAL,
                current_price REAL,
                high_52w REAL,
                low_52w REAL,
                avg_volume REAL,
                last_updated TIMESTAMP
            )
        """)
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
            code = stock["stock_id"]
            name = stock["stock_name"]
            ticker_symbol = f"{code}.TW" if code.startswith(("1", "2")) else f"{code}.TWO"

            try:
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.info

                # Extract metrics (handle missing keys safely)
                market_cap = info.get("marketCap", 0)
                pe_ratio = info.get("trailingPE", 0)
                pb_ratio = info.get("priceToBook", 0)
                roe = info.get("returnOnEquity", 0)
                dividend_yield = info.get("dividendYield", 0)
                revenue_growth = info.get("revenueGrowth", 0)
                current_price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                high_52w = info.get("fiftyTwoWeekHigh", 0)
                low_52w = info.get("fiftyTwoWeekLow", 0)
                avg_volume = info.get("averageVolume", 0)

                # Skip if no valid price data
                if current_price == 0:
                    return None

                return {
                    "stock_code": code,
                    "stock_name": name,
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                    "pb_ratio": pb_ratio,
                    "roe": roe,
                    "dividend_yield": dividend_yield,
                    "revenue_growth": revenue_growth,
                    "current_price": current_price,
                    "high_52w": high_52w,
                    "low_52w": low_52w,
                    "avg_volume": avg_volume,
                    "last_updated": datetime.now(),
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
            df.to_sql("market_snapshot", conn, if_exists="replace", index=False)
            conn.close()
            print(f"Snapshot updated. {len(results)} stocks saved.")
        else:
            print("No data fetched.")

    def filter_stocks(
        self,
        min_market_cap: float = 0,  # In Billions
        max_pe: float = 100,
        min_yield: float = 0,
        min_roe: float = 0,
        low_base_enabled: bool = False,
    ) -> pd.DataFrame:
        """
        Filter stocks based on criteria.

        Args:
            min_market_cap: Minimum Market Cap in NT$ Billion
            max_pe: Maximum P/E Ratio
            min_yield: Minimum Dividend Yield (e.g., 0.03 for 3%)
            min_roe: Minimum ROE (e.g., 0.1 for 10%)
            low_base_enabled: If True, filters for stocks trading near 52w low.
        """
        df = self.get_market_snapshot()
        if df.empty:
            return df

        df = df.copy()

        # Backward compatibility for old snapshots without scoring columns.
        required_cols = ["roe", "pb_ratio", "dividend_yield", "revenue_growth"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0.0

        # Apply Filters

        # 1. Market Cap (Convert Billions to Actual)
        df = df[df["market_cap"] >= min_market_cap * 1_000_000_000]

        # 2. P/E Ratio (Filter out 0 or negative PE usually, but user said 'Low PE')
        # We allow 0 PE (loss making) to be filtered OUT if max_pe > 0
        df = df[df["pe_ratio"] > 0]
        df = df[df["pe_ratio"] <= max_pe]

        # 3. Dividend Yield
        df = df[df["dividend_yield"] >= min_yield]

        # 4. Return on Equity
        df = df[df["roe"] >= min_roe]

        # 5. Low Base Logic
        if low_base_enabled:
            # Definition: Price is in the lower 30% of 52-week range
            # Formula: Position = (Price - Low) / (High - Low)
            # If High == Low, Position = 0

            def calculate_position(row):
                if row["high_52w"] == row["low_52w"]:
                    return 0
                return (row["current_price"] - row["low_52w"]) / (row["high_52w"] - row["low_52w"])

            df["price_position"] = df.apply(calculate_position, axis=1)

            # Filter: Position <= 0.3 (Lower 30%)
            df = df[df["price_position"] <= 0.3]

            # Additional Low Base: PE Low Base?
            # We don't have historical PE in snapshot, so rely on Price Base.

        # P2-10: Fundamental composite scoring and letter grading.
        if df.empty:
            df["fundamental_score"] = pd.Series(dtype=float)
            df["fundamental_grade"] = pd.Series(dtype=str)
            return df

        score_cols = df.apply(self._calculate_fundamental_score, axis=1, result_type="expand")
        score_cols.columns = ["fundamental_score", "fundamental_grade"]
        df[["fundamental_score", "fundamental_grade"]] = score_cols

        return df

    def perform_deep_scan(self, stock_codes: List[str], max_workers: int = 10, progress_callback=None) -> pd.DataFrame:
        """
        Perform deep analysis on a filtered list of stocks.
        Fetches historical data to calculate Growth (CAGR), Dividend Consistency,
        Valuation Position (PE/PB Bands), and a composite Low Base Score.

        Args:
            stock_codes: List of stock codes (str).
        """
        results = []
        total = len(stock_codes)

        print(f"Starting Deep Scan for {total} stocks...")

        def analyze_stock(code):
            ticker_symbol = f"{code}.TW" if code.startswith(("1", "2")) else f"{code}.TWO"
            try:
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.info

                # --- 1. Growth Metrics (5Y & 10Y) ---
                fin = ticker.financials
                if fin.empty:
                    return None

                # Sort columns by date ascending
                fin = fin[sorted(fin.columns)]

                # Get Revenue and Net Income (Profit)
                revenue_row = next(
                    (r for r in ["Total Revenue", "Revenue", "Operating Revenue"] if r in fin.index), None
                )
                profit_row = next((r for r in ["Net Income", "Net Income Common Stockholders"] if r in fin.index), None)

                cagr_revenue_5y = 0.0
                cagr_profit_5y = 0.0
                cagr_revenue_10y = 0.0
                cagr_profit_10y = 0.0

                if revenue_row:
                    revs = fin.loc[revenue_row].dropna()
                    cagr_revenue_5y = self._calculate_cagr(revs, 5)
                    cagr_revenue_10y = self._calculate_cagr(revs, 10)

                if profit_row:
                    profits = fin.loc[profit_row].dropna()
                    cagr_profit_5y = self._calculate_cagr(profits, 5)
                    cagr_profit_10y = self._calculate_cagr(profits, 10)

                # --- 2. Dividend Consistency ---
                divs = ticker.dividends
                div_consecutive_years = 0
                if not divs.empty:
                    divs_by_year = divs.groupby(divs.index.year).sum()
                    last_year = divs_by_year.index.max()
                    count = 0
                    # Check last 15 years for safety
                    for y in range(last_year, last_year - 15, -1):
                        if y in divs_by_year.index and divs_by_year.loc[y] > 0:
                            count += 1
                        else:
                            break
                    div_consecutive_years = count

                # --- 3. Valuation Position (PE/PB Bands) ---
                hist_5y = ticker.history(period="5y")
                price_pos_5y = 0.5  # Default mid
                if not hist_5y.empty:
                    h_max = hist_5y["High"].max()
                    h_min = hist_5y["Low"].min()
                    curr = info.get("currentPrice", hist_5y["Close"].iloc[-1])
                    if h_max > h_min:
                        price_pos_5y = (curr - h_min) / (h_max - h_min)

                current_pe = info.get("trailingPE", 0)

                # --- 4. Composite Low Base Score ---
                score_components = {
                    "growth": (max(cagr_revenue_5y, 0) + max(cagr_profit_5y, 0)) * 100 / 2,  # simplified %
                    "dividend": min(div_consecutive_years * 5, 20),  # Max 20 pts for 4+ years
                    "valuation": 0,
                    "price_low": (1 - price_pos_5y) * 30,  # Max 30 pts if at 5y low
                }

                # Valuation Score (PE < 15 is good, > 30 is bad)
                val_score = 0
                if current_pe > 0:
                    if current_pe < 10:
                        val_score = 30
                    elif current_pe < 15:
                        val_score = 25
                    elif current_pe < 20:
                        val_score = 15
                    elif current_pe < 25:
                        val_score = 5
                    else:
                        val_score = 0
                score_components["valuation"] = val_score

                # Total Score
                raw_score = (
                    min(score_components["growth"], 20)
                    + score_components["dividend"]
                    + score_components["valuation"]
                    + score_components["price_low"]
                )
                final_score = min(max(raw_score, 0), 100)

                return {
                    "stock_code": code,
                    "revenue_cagr_5y": cagr_revenue_5y,
                    "profit_cagr_5y": cagr_profit_5y,
                    "revenue_cagr_10y": cagr_revenue_10y,
                    "profit_cagr_10y": cagr_profit_10y,
                    "div_years": div_consecutive_years,
                    "price_pos_5y": price_pos_5y,
                    "low_base_score": final_score,
                }

            except Exception as e:
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
        if n < 1:
            n = 1

        if old <= 0 or recent <= 0:
            return 0.0  # Handle negative/zero base

        try:
            cagr = (recent / old) ** (1 / n) - 1
            return cagr
        except:
            return 0.0
