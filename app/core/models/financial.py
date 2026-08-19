"""財報資料與 DCF 估值結果模型。

此模組定義 FinancialData 與 DCFResult 兩個核心 Pydantic 模型，
包含百分比歸一化驗證器與 Field 約束。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator


def normalize_percentage(v: Optional[float]) -> Optional[float]:
    """將小數形式的百分比自動轉為百分比形式（冪等操作）。

    規則：若值不為 None 且 abs(value) < 1.0 且 abs(value) >= 0.01 且 value != 0，
    則視為小數形式並乘以 100。abs(value) < 0.01 的極小值視為已是百分比形式
    （例如 0.005 代表 0.005%），不進行轉換，以確保冪等性。

    冪等性保證：normalize_percentage(normalize_percentage(x)) == normalize_percentage(x)
    轉換後的結果 abs >= 1.0，不會再次觸發轉換。

    Args:
        v: 輸入的百分比數值（可能為小數或百分比形式）。

    Returns:
        歸一化後的百分比數值，或 None。
    """
    if v is not None and v != 0 and -1.0 < v < 1.0 and abs(v) >= 0.01:
        return v * 100
    return v


class FinancialData(BaseModel):
    """財報資料。

    儲存個股某一期間的核心財務指標，並自動歸一化百分比欄位。

    Attributes:
        stock_code: 股票代碼。
        period: 財報期間（如 "2024Q4"）。
        revenue: 營收（百萬元，須 >= 0）。
        eps: 每股盈餘。
        roe: 股東權益報酬率（%）。
        pe_ratio: 本益比。
        dividend_yield: 殖利率（%）。
        operating_margin: 營業利益率（%）。
    """

    stock_code: str
    period: str = Field(..., description="期間，如 2024Q4")
    revenue: float = Field(..., ge=0, description="營收（百萬）")
    eps: float = Field(..., ge=-1000, le=10000, description="每股盈餘")
    roe: float = Field(..., ge=-100, le=200, description="股東權益報酬率（%）")
    pe_ratio: Optional[float] = Field(None, ge=-100, le=10000, description="本益比")
    dividend_yield: Optional[float] = Field(None, ge=0, le=100, description="殖利率（%）")
    operating_margin: Optional[float] = Field(
        None, ge=-100, le=100, description="營業利益率（%）"
    )

    @field_validator("roe", "dividend_yield", mode="before")
    @classmethod
    def _normalize_percentage(cls, v: Optional[float]) -> Optional[float]:
        """自動將小數形式轉為百分比形式。

        Args:
            v: 輸入的百分比數值。

        Returns:
            歸一化後的百分比數值。
        """
        return normalize_percentage(v)

    @field_validator("stock_code")
    @classmethod
    def validate_stock_code(cls, v: str) -> str:
        """驗證股票代碼不得為空。

        Args:
            v: 輸入的股票代碼字串。

        Returns:
            去除前後空白的股票代碼。

        Raises:
            ValueError: 當股票代碼為空時。
        """
        v = v.strip()
        if not v:
            raise ValueError("股票代碼不得為空")
        return v

    def to_json(self) -> str:
        """將模型序列化為 JSON 字串。

        Returns:
            JSON 格式字串。
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> FinancialData:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            FinancialData 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        return pd.DataFrame([self.model_dump()])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> FinancialData | list[FinancialData]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 FinancialData；
            若有多列，回傳 FinancialData 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]


class DCFResult(BaseModel):
    """DCF 估值結果。

    儲存現金流量折現計算的完整輸出，包含內在價值、潛在獲利率等。

    Attributes:
        stock_code: 股票代碼。
        stock_name: 股票名稱。
        current_price: 目前股價（須 > 0）。
        intrinsic_value: DCF 計算出的內在價值。
        upside_potential: 潛在獲利率（-1.0 ~ 100.0）。
        discount_rate: 折現率（0 ~ 1.0）。
        growth_rates: 成長率列表。
        terminal_value: 終值。
        recommendation: 投資建議文字。
        calculated_at: 計算時間。
        data_source: 資料來源描述。
    """

    stock_code: str
    stock_name: str = ""
    current_price: float = Field(..., gt=0, description="目前股價")
    intrinsic_value: float = Field(..., description="內在價值")
    upside_potential: float = Field(..., ge=-1.0, le=100.0, description="潛在獲利率")
    discount_rate: float = Field(..., gt=0, le=1.0, description="折現率")
    growth_rates: List[float] = Field(..., description="成長率列表")
    terminal_value: float = Field(..., description="終值")
    recommendation: str = Field("", description="投資建議")
    calculated_at: datetime = Field(default_factory=datetime.now)
    data_source: str = Field("", description="資料來源")

    @field_validator("stock_code")
    @classmethod
    def validate_stock_code(cls, v: str) -> str:
        """驗證股票代碼不得為空。

        Args:
            v: 輸入的股票代碼字串。

        Returns:
            去除前後空白的股票代碼。

        Raises:
            ValueError: 當股票代碼為空時。
        """
        v = v.strip()
        if not v:
            raise ValueError("股票代碼不得為空")
        return v

    def to_json(self) -> str:
        """將模型序列化為 JSON 字串。

        Returns:
            JSON 格式字串。
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> DCFResult:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            DCFResult 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        return pd.DataFrame([self.model_dump()])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> DCFResult | list[DCFResult]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 DCFResult；
            若有多列，回傳 DCFResult 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]
