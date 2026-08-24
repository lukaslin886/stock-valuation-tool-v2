"""Property 12 & 13: 資料驗證拒絕不合理數值與單位歸一化冪等性。

使用 Hypothesis 驗證：
- Property 12: 超出合理範圍的 PE ratio、ROE、股價 <= 0 被 Pydantic 拒絕
- Property 13: normalize_percentage 冪等性

**Validates: Requirements 8.3, 8.4, 18.2**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.models.financial import FinancialData, normalize_percentage
from app.core.models.stock import PriceData


# ============================================================================
# Property 12: 資料驗證拒絕不合理數值
# ============================================================================


class TestProperty12ValidationRejection:
    """Property 12: Values outside valid ranges are rejected by Pydantic models.

    驗證超出範圍的 PE ratio (> 10000 or < -100)、ROE (> 200 or < -100)、
    股價 (<= 0) 被 Pydantic 模型以 ValidationError 拒絕。

    **Validates: Requirements 8.3**
    """

    @given(
        pe_ratio=st.floats(min_value=10001, max_value=1e10).filter(
            lambda x: x == x  # 排除 NaN
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_pe_ratio_above_upper_bound_rejected(self, pe_ratio: float) -> None:
        """PE ratio > 10000 應被 FinancialData 拒絕。"""
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q4",
                revenue=1000.0,
                eps=5.0,
                roe=15.0,
                pe_ratio=pe_ratio,
            )

    @given(
        pe_ratio=st.floats(max_value=-101, min_value=-1e10).filter(
            lambda x: x == x  # 排除 NaN
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_pe_ratio_below_lower_bound_rejected(self, pe_ratio: float) -> None:
        """PE ratio < -100 應被 FinancialData 拒絕。"""
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q4",
                revenue=1000.0,
                eps=5.0,
                roe=15.0,
                pe_ratio=pe_ratio,
            )

    @given(
        roe=st.floats(min_value=201, max_value=1e10).filter(
            lambda x: x == x
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_roe_above_upper_bound_rejected(self, roe: float) -> None:
        """ROE > 200 應被 FinancialData 拒絕。

        注意：normalize_percentage 只會轉換 -1.0 < v < 1.0 的值，
        所以直接傳入 > 200 的值不會被歸一化邏輯修改。
        """
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q4",
                revenue=1000.0,
                eps=5.0,
                roe=roe,
            )

    @given(
        roe=st.floats(max_value=-101, min_value=-1e10).filter(
            lambda x: x == x
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_roe_below_lower_bound_rejected(self, roe: float) -> None:
        """ROE < -100 應被 FinancialData 拒絕。"""
        with pytest.raises(ValidationError):
            FinancialData(
                stock_code="2330",
                period="2024Q4",
                revenue=1000.0,
                eps=5.0,
                roe=roe,
            )

    @given(
        price=st.floats(max_value=0.0, min_value=-1e10).filter(
            lambda x: x == x
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_price_less_or_equal_zero_rejected(self, price: float) -> None:
        """股價 <= 0 應被 PriceData 拒絕（close_price 使用 gt=0 約束）。"""
        with pytest.raises(ValidationError):
            PriceData(
                stock_code="2330",
                date="2024-01-15",
                open_price=price,
                high_price=price,
                low_price=price,
                close_price=price,
                volume=1000,
            )

    @given(
        price=st.floats(max_value=-0.01, min_value=-1e10).filter(
            lambda x: x == x
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_negative_price_rejected(self, price: float) -> None:
        """負值股價應被 PriceData 的各個價格欄位拒絕。"""
        with pytest.raises(ValidationError):
            PriceData(
                stock_code="2330",
                date="2024-01-15",
                open_price=100.0,
                high_price=100.0,
                low_price=100.0,
                close_price=price,
                volume=1000,
            )


# ============================================================================
# Property 13: 單位歸一化冪等性
# ============================================================================


class TestProperty13NormalizePercentageIdempotent:
    """Property 13: normalize_percentage 冪等性。

    對任意 float 值，normalize_percentage(normalize_percentage(x)) == normalize_percentage(x)。
    已經是百分比形式的值（>= 1.0 或 <= -1.0 或 == 0）不應被修改。

    **Validates: Requirements 8.4**
    """

    @given(
        value=st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_normalize_percentage_idempotent(self, value: float) -> None:
        """normalize_percentage 套用兩次結果等同套用一次。"""
        once = normalize_percentage(value)
        twice = normalize_percentage(once)
        assert twice == once, (
            f"normalize_percentage 非冪等: "
            f"normalize_percentage({value}) = {once}, "
            f"normalize_percentage({once}) = {twice}"
        )

    @given(
        value=st.floats(
            min_value=1.0,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_values_gte_one_unchanged(self, value: float) -> None:
        """值 >= 1.0 不應被 normalize_percentage 修改。"""
        result = normalize_percentage(value)
        assert result == value, (
            f"值 >= 1.0 不應被修改: normalize_percentage({value}) = {result}"
        )

    @given(
        value=st.floats(
            min_value=-1e6,
            max_value=-1.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200, deadline=30000)
    def test_values_lte_neg_one_unchanged(self, value: float) -> None:
        """值 <= -1.0 不應被 normalize_percentage 修改。"""
        result = normalize_percentage(value)
        assert result == value, (
            f"值 <= -1.0 不應被修改: normalize_percentage({value}) = {result}"
        )

    def test_zero_unchanged(self) -> None:
        """值 == 0 不應被 normalize_percentage 修改。"""
        result = normalize_percentage(0.0)
        assert result == 0.0

    def test_none_returns_none(self) -> None:
        """None 輸入應回傳 None。"""
        result = normalize_percentage(None)
        assert result is None
