"""Property 15: 美股代碼辨識正確性。

使用 Hypothesis 驗證：
- 1-5 個英文字母組成的字串 -> detect_market 回傳 Market.US
- 4-6 位數字組成的字串 -> detect_market 回傳 Market.TW (< 6000) 或 Market.TWO (>= 6000)

**Validates: Requirements 11.1, 11.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.models.stock import Market, detect_market


# ============================================================================
# Property 15: 美股代碼辨識正確性
# ============================================================================


class TestProperty15MarketDetectionCorrectness:
    """Property 15: Market detection correctness.

    For any string of 1-5 alphabetic characters, detect_market SHALL return Market.US.
    For any string of 4-6 digits, detect_market SHALL return Market.TW (if < 6000)
    or Market.TWO (if >= 6000).

    **Validates: Requirements 11.1, 11.2**
    """

    @given(
        ticker=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_alphabetic_1_to_5_chars_returns_us(self, ticker: str) -> None:
        """1-5 個英文字母（含大小寫）應辨識為美股 Market.US。"""
        result = detect_market(ticker)
        assert result == Market.US, (
            f"detect_market('{ticker}') = {result}, expected Market.US"
        )

    @given(
        ticker=st.text(
            alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_uppercase_alphabetic_returns_us(self, ticker: str) -> None:
        """1-5 個大寫英文字母應辨識為美股 Market.US。"""
        result = detect_market(ticker)
        assert result == Market.US, (
            f"detect_market('{ticker}') = {result}, expected Market.US"
        )

    @given(
        code=st.integers(min_value=1000, max_value=5999).map(str)
    )
    @settings(max_examples=200, deadline=30000)
    def test_4digit_below_6000_returns_tw(self, code: str) -> None:
        """4 位數字且 < 6000 應辨識為台灣上市 Market.TW。"""
        result = detect_market(code)
        assert result == Market.TW, (
            f"detect_market('{code}') = {result}, expected Market.TW"
        )

    @given(
        code=st.integers(min_value=6000, max_value=9999).map(str)
    )
    @settings(max_examples=200, deadline=30000)
    def test_4digit_gte_6000_returns_two(self, code: str) -> None:
        """4 位數字且 >= 6000 應辨識為台灣上櫃 Market.TWO。"""
        result = detect_market(code)
        assert result == Market.TWO, (
            f"detect_market('{code}') = {result}, expected Market.TWO"
        )

    @given(
        code=st.integers(min_value=10000, max_value=99999).map(str)
    )
    @settings(max_examples=200, deadline=30000)
    def test_5digit_numeric_market_detection(self, code: str) -> None:
        """5 位數字依數值決定 Market.TW (< 6000 不適用) 或 Market.TWO (>= 6000)。"""
        numeric_value = int(code)
        result = detect_market(code)
        if numeric_value >= 6000:
            assert result == Market.TWO, (
                f"detect_market('{code}') = {result}, expected Market.TWO"
            )
        else:
            assert result == Market.TW, (
                f"detect_market('{code}') = {result}, expected Market.TW"
            )

    @given(
        code=st.integers(min_value=100000, max_value=999999).map(str)
    )
    @settings(max_examples=200, deadline=30000)
    def test_6digit_numeric_market_detection(self, code: str) -> None:
        """6 位數字依數值決定市場別（全部 >= 6000，應為 Market.TWO）。"""
        result = detect_market(code)
        assert result == Market.TWO, (
            f"detect_market('{code}') = {result}, expected Market.TWO"
        )
