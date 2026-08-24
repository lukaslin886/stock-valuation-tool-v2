"""detect_market 函式單元測試。

驗證股票代碼辨識邏輯能正確區分美股、台灣上市、台灣上櫃市場。
"""

import pytest

from app.core.models.stock import Market, detect_market


class TestDetectMarketUS:
    """美股代碼辨識測試。"""

    def test_single_letter(self) -> None:
        """單一英文字母應辨識為美股。"""
        assert detect_market("A") == Market.US

    def test_two_letters(self) -> None:
        """兩個英文字母應辨識為美股。"""
        assert detect_market("GE") == Market.US

    def test_three_letters(self) -> None:
        """三個英文字母應辨識為美股（如 IBM）。"""
        assert detect_market("IBM") == Market.US

    def test_four_letters(self) -> None:
        """四個英文字母應辨識為美股（如 AAPL）。"""
        assert detect_market("AAPL") == Market.US

    def test_five_letters(self) -> None:
        """五個英文字母應辨識為美股（如 GOOGL）。"""
        assert detect_market("GOOGL") == Market.US

    def test_lowercase_input(self) -> None:
        """小寫輸入應正確辨識為美股。"""
        assert detect_market("aapl") == Market.US

    def test_mixed_case_input(self) -> None:
        """混合大小寫輸入應正確辨識為美股。"""
        assert detect_market("Msft") == Market.US

    def test_with_leading_trailing_spaces(self) -> None:
        """前後含空白的英文代碼應正確辨識。"""
        assert detect_market("  TSLA  ") == Market.US


class TestDetectMarketTW:
    """台灣上市代碼辨識測試。"""

    def test_four_digit_below_6000(self) -> None:
        """四位數且小於 6000 應辨識為上市。"""
        assert detect_market("2330") == Market.TW

    def test_four_digit_boundary_5999(self) -> None:
        """代碼 5999 應辨識為上市。"""
        assert detect_market("5999") == Market.TW

    def test_four_digit_low_value(self) -> None:
        """代碼 1000 應辨識為上市。"""
        assert detect_market("1000") == Market.TW

    def test_suffix_tw(self) -> None:
        """帶 .TW 後綴應辨識為上市。"""
        assert detect_market("2330.TW") == Market.TW

    def test_suffix_tw_lowercase(self) -> None:
        """帶小寫 .tw 後綴應辨識為上市。"""
        assert detect_market("2330.tw") == Market.TW


class TestDetectMarketTWO:
    """台灣上櫃代碼辨識測試。"""

    def test_four_digit_6000(self) -> None:
        """代碼 6000 應辨識為上櫃。"""
        assert detect_market("6000") == Market.TWO

    def test_four_digit_above_6000(self) -> None:
        """代碼 6005 應辨識為上櫃。"""
        assert detect_market("6005") == Market.TWO

    def test_four_digit_high_value(self) -> None:
        """代碼 8299 應辨識為上櫃。"""
        assert detect_market("8299") == Market.TWO

    def test_five_digit(self) -> None:
        """五位數字代碼且 >= 6000 應辨識為上櫃。"""
        assert detect_market("60001") == Market.TWO

    def test_six_digit(self) -> None:
        """六位數字代碼應辨識為上櫃（假設 >= 6000）。"""
        assert detect_market("600001") == Market.TWO

    def test_suffix_two(self) -> None:
        """帶 .TWO 後綴應辨識為上櫃。"""
        assert detect_market("6005.TWO") == Market.TWO

    def test_suffix_two_lowercase(self) -> None:
        """帶小寫 .two 後綴應辨識為上櫃。"""
        assert detect_market("6005.two") == Market.TWO


class TestDetectMarketEdgeCases:
    """邊界情況與預設行為測試。"""

    def test_six_letters_defaults_to_tw(self) -> None:
        """超過五個英文字母應預設為台股。"""
        assert detect_market("ABCDEF") == Market.TW

    def test_alphanumeric_defaults_to_tw(self) -> None:
        """英數混合不含後綴應預設為台股。"""
        assert detect_market("2330A") == Market.TW

    def test_three_digit_defaults_to_tw(self) -> None:
        """三位數字（不在 4-6 位範圍內）應預設為台股。"""
        assert detect_market("123") == Market.TW

    def test_suffix_tw_takes_precedence_over_code_range(self) -> None:
        """帶 .TW 後綴時，即使代碼 >= 6000 也應辨識為上市。"""
        assert detect_market("6005.TW") == Market.TW

    def test_suffix_two_takes_precedence(self) -> None:
        """帶 .TWO 後綴時，即使代碼 < 6000 也應辨識為上櫃。"""
        assert detect_market("2330.TWO") == Market.TWO

    def test_empty_after_strip_defaults_to_tw(self) -> None:
        """空白字串應預設為台股（不會拋出例外）。"""
        assert detect_market("   ") == Market.TW

    def test_five_digit_below_6000_with_leading_zero(self) -> None:
        """五位數字且整數值小於 6000（含前導零）應辨識為上市。"""
        assert detect_market("05999") == Market.TW

    def test_five_digit_above_6000(self) -> None:
        """五位數字且整數值 >= 6000 應辨識為上櫃。"""
        assert detect_market("10001") == Market.TWO
