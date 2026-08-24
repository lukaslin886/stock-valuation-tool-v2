"""
technical_indicators 單元測試。

驗證 RSI（Wilder）、MACD（12/26/9）與篩選判斷。
以確定性合成序列比對，不觸網。
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from technical_indicators import (  # noqa: E402
    rsi,
    macd,
    macd_cross,
    compute_indicators,
    screen_rsi,
    screen_macd,
)


def _price_df(closes):
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
        "close_price": closes,
    })


def test_rsi_monotonic_rising_is_100():
    # 連續上漲 → 無跌幅 → RSI 應為 100
    closes = list(np.arange(1, 40, dtype=float))
    r = rsi(closes, period=14)
    assert r.iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_rsi_monotonic_falling_is_0():
    closes = list(np.arange(40, 1, -1, dtype=float))
    r = rsi(closes, period=14)
    assert r.iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_warmup_is_nan():
    closes = list(np.arange(1, 40, dtype=float))
    r = rsi(closes, period=14)
    # 前 period 筆應為 NaN
    assert r.iloc[:14].isna().all()


def test_rsi_reference_value():
    # 對已知輸入以獨立參考實作交叉驗證
    rng = np.random.default_rng(42)
    closes = list(np.cumsum(rng.normal(0, 1, 200)) + 100)

    period = 14
    s = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    ref = 100 - 100 / (1 + ag / al)

    got = rsi(closes, period=period)
    assert got.iloc[-1] == pytest.approx(float(ref.iloc[-1]), rel=1e-9)


def test_rsi_bounds():
    rng = np.random.default_rng(7)
    closes = list(np.cumsum(rng.normal(0, 1, 300)) + 50)
    r = rsi(closes).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_macd_columns_and_length():
    closes = list(np.linspace(10, 20, 100))
    m = macd(closes)
    assert list(m.columns) == ["macd", "signal", "hist"]
    assert len(m) == 100


def test_macd_hist_equals_macd_minus_signal():
    rng = np.random.default_rng(1)
    closes = list(np.cumsum(rng.normal(0, 1, 120)) + 100)
    m = macd(closes)
    assert np.allclose((m["macd"] - m["signal"]).values, m["hist"].values)


def test_macd_golden_cross_detected():
    # 先跌後強漲 → 尾端出現黃金交叉
    down = list(np.linspace(100, 70, 40))
    up = list(np.linspace(70, 130, 40))
    closes = down + up
    # 掃描是否曾偵測到黃金交叉
    crosses = []
    for i in range(2, len(closes)):
        crosses.append(macd_cross(closes[: i + 1]))
    assert "golden" in crosses


def test_compute_indicators_snapshot():
    rng = np.random.default_rng(3)
    closes = list(np.cumsum(rng.normal(0, 1, 100)) + 100)
    snap = compute_indicators(_price_df(closes))
    assert set(snap.keys()) == {"rsi", "macd", "signal", "hist", "macd_cross"}
    assert snap["rsi"] is not None
    assert 0 <= snap["rsi"] <= 100
    assert snap["hist"] == pytest.approx(snap["macd"] - snap["signal"], abs=1e-3)


def test_compute_indicators_insufficient_data():
    snap = compute_indicators(_price_df([100.0, 101.0]))
    assert snap["rsi"] is None  # 不足 14 筆


def test_screen_rsi_oversold():
    closes = list(np.arange(40, 1, -1, dtype=float))  # RSI≈0
    assert screen_rsi(closes, low=30, mode="oversold") is True
    assert screen_rsi(closes, high=70, mode="overbought") is False


def test_screen_macd_bullish_bearish():
    rising = list(np.linspace(10, 40, 80))
    assert screen_macd(rising, want="bullish") is True
    assert screen_macd(rising, want="bearish") is False


def test_extract_close_missing_column_raises():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    with pytest.raises(ValueError):
        rsi(df)
