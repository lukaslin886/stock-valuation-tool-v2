"""MarketScanner 單元測試。"""

import sqlite3

import pandas as pd

from app.market_scanner import MarketScanner


def _write_snapshot(db_path: str, df: pd.DataFrame) -> None:
    """將測試資料寫入 market_snapshot。"""
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql("market_snapshot", conn, if_exists="replace", index=False)
    finally:
        conn.close()


def test_filter_stocks_with_multi_conditions(tmp_path):
    """測試市值、PE、殖利率、ROE 與低基期可交集篩選。"""
    db_path = str(tmp_path / "market_scan.db")
    scanner = MarketScanner(db_path=db_path)

    df = pd.DataFrame(
        [
            {
                "stock_code": "1111",
                "stock_name": "A",
                "market_cap": 80_000_000_000,
                "pe_ratio": 15.0,
                "pb_ratio": 1.5,
                "roe": 0.15,
                "dividend_yield": 0.05,
                "revenue_growth": 0.08,
                "current_price": 68,
                "high_52w": 100,
                "low_52w": 60,
                "avg_volume": 50000,
                "last_updated": "2026-04-30 00:00:00",
            },
            {
                "stock_code": "2222",
                "stock_name": "B",
                "market_cap": 120_000_000_000,
                "pe_ratio": 30.0,
                "pb_ratio": 2.0,
                "roe": 0.20,
                "dividend_yield": 0.04,
                "revenue_growth": 0.10,
                "current_price": 90,
                "high_52w": 110,
                "low_52w": 70,
                "avg_volume": 60000,
                "last_updated": "2026-04-30 00:00:00",
            },
            {
                "stock_code": "3333",
                "stock_name": "C",
                "market_cap": 90_000_000_000,
                "pe_ratio": 12.0,
                "pb_ratio": 1.2,
                "roe": 0.08,
                "dividend_yield": 0.02,
                "revenue_growth": 0.03,
                "current_price": 75,
                "high_52w": 100,
                "low_52w": 60,
                "avg_volume": 45000,
                "last_updated": "2026-04-30 00:00:00",
            },
        ]
    )
    _write_snapshot(db_path, df)

    result = scanner.filter_stocks(
        min_market_cap=50,
        max_pe=20,
        min_yield=0.03,
        min_roe=0.10,
        low_base_enabled=True,
    )

    assert len(result) == 1
    assert result.iloc[0]["stock_code"] == "1111"


def test_filter_stocks_compatible_without_roe_column(tmp_path):
    """測試舊快照缺少 roe 欄位時不會拋錯且可正常篩選。"""
    db_path = str(tmp_path / "market_scan.db")
    scanner = MarketScanner(db_path=db_path)

    df = pd.DataFrame(
        [
            {
                "stock_code": "4444",
                "stock_name": "D",
                "market_cap": 70_000_000_000,
                "pe_ratio": 10.0,
                "pb_ratio": 1.1,
                "dividend_yield": 0.06,
                "revenue_growth": 0.06,
                "current_price": 70,
                "high_52w": 100,
                "low_52w": 60,
                "avg_volume": 38000,
                "last_updated": "2026-04-30 00:00:00",
            }
        ]
    )
    _write_snapshot(db_path, df)

    result_with_roe_filter = scanner.filter_stocks(min_roe=0.10)
    result_without_roe_filter = scanner.filter_stocks(min_roe=0.0)

    assert result_with_roe_filter.empty
    assert len(result_without_roe_filter) == 1
    assert result_without_roe_filter.iloc[0]["stock_code"] == "4444"


def test_fundamental_score_high_quality_stock_gets_a_grade(tmp_path):
    """高品質基本面應得到較高分數與 A+/A 級。"""
    db_path = str(tmp_path / "market_scan.db")
    scanner = MarketScanner(db_path=db_path)

    df = pd.DataFrame(
        [
            {
                "stock_code": "5555",
                "stock_name": "High",
                "market_cap": 200_000_000_000,
                "pe_ratio": 12.0,
                "pb_ratio": 1.1,
                "roe": 0.22,
                "dividend_yield": 0.05,
                "revenue_growth": 0.15,
                "current_price": 120,
                "high_52w": 150,
                "low_52w": 80,
                "avg_volume": 150000,
                "last_updated": "2026-05-01 00:00:00",
            }
        ]
    )
    _write_snapshot(db_path, df)

    result = scanner.filter_stocks()

    assert len(result) == 1
    assert "fundamental_score" in result.columns
    assert "fundamental_grade" in result.columns
    assert result.iloc[0]["fundamental_score"] >= 80
    assert result.iloc[0]["fundamental_grade"] in ["A+", "A"]


def test_fundamental_score_weak_stock_gets_low_grade(tmp_path):
    """弱基本面樣本應得到低分與 C/D 級。"""
    db_path = str(tmp_path / "market_scan.db")
    scanner = MarketScanner(db_path=db_path)

    df = pd.DataFrame(
        [
            {
                "stock_code": "6666",
                "stock_name": "Weak",
                "market_cap": 30_000_000_000,
                "pe_ratio": 45.0,
                "pb_ratio": 5.0,
                "roe": 0.01,
                "dividend_yield": 0.0,
                "revenue_growth": -0.10,
                "current_price": 35,
                "high_52w": 80,
                "low_52w": 30,
                "avg_volume": 25000,
                "last_updated": "2026-05-01 00:00:00",
            }
        ]
    )
    _write_snapshot(db_path, df)

    result = scanner.filter_stocks(max_pe=100)

    assert len(result) == 1
    assert result.iloc[0]["fundamental_score"] < 50
    assert result.iloc[0]["fundamental_grade"] in ["C", "D"]


def test_fundamental_score_handles_missing_columns_and_values(tmp_path):
    """缺欄位與缺值時不應拋錯，且分數維持 0-100 區間。"""
    db_path = str(tmp_path / "market_scan.db")
    scanner = MarketScanner(db_path=db_path)

    # Intentionally omit pb_ratio, roe, dividend_yield, revenue_growth
    df = pd.DataFrame(
        [
            {
                "stock_code": "7777",
                "stock_name": "Missing",
                "market_cap": 50_000_000_000,
                "pe_ratio": 18.0,
                "current_price": 50,
                "high_52w": 70,
                "low_52w": 40,
                "avg_volume": 20000,
                "last_updated": "2026-05-01 00:00:00",
            }
        ]
    )
    _write_snapshot(db_path, df)

    result = scanner.filter_stocks(max_pe=30)

    assert len(result) == 1
    assert "fundamental_score" in result.columns
    assert "fundamental_grade" in result.columns
    score = float(result.iloc[0]["fundamental_score"])
    grade = result.iloc[0]["fundamental_grade"]
    assert 0.0 <= score <= 100.0
    assert grade in ["A+", "A", "B+", "B", "C", "D"]
