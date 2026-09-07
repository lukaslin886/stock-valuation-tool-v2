"""市場掃描結果與市場快照模型。

此模組定義 ScanResult 與 MarketSnapshot 模型，
包含百分比歸一化驗證器。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from app.core.models.financial import normalize_percentage


class ScanResult(BaseModel):
    """市場掃描結果。

    儲存單一股票經市場掃描後的綜合評估結果，包含基本面分數、
    籌碼資料與價格位階等。

    Attributes:
        stock_code: 股票代碼。
        stock_name: 股票名稱。
        current_price: 目前股價（須 >= 0）。
        pe_ratio: 本益比。
        roe: 股東權益報酬率（%）。
        dividend_yield: 殖利率（%）。
        market_cap: 市值（億元）。
        price_position: 52 週價格位階（0 ~ 1.0）。
        fundamental_score: 基本面綜合評分（0 ~ 100）。
        fundamental_grade: 基本面等級（如 A、B、C）。
        chip_data_available: 籌碼資料是否可用。
        foreign_consecutive_buy: 外資連續買超天數。
        trust_consecutive_buy: 投信連續買超天數。
    """

    stock_code: str
    stock_name: str = ""
    current_price: float = Field(0, ge=0, description="目前股價")
    pe_ratio: float = Field(0, ge=-100, le=10000, description="本益比")
    roe: float = Field(0, ge=-100, le=200, description="股東權益報酬率（%）")
    dividend_yield: float = Field(0, ge=0, le=100, description="殖利率（%）")
    market_cap: float = Field(0, ge=0, description="市值（億）")
    price_position: float = Field(0, ge=0, le=1.0, description="52週價格位階")
    fundamental_score: float = Field(0, ge=0, le=100, description="基本面綜合評分")
    fundamental_grade: str = ""
    chip_data_available: bool = True
    foreign_consecutive_buy: Optional[int] = None
    trust_consecutive_buy: Optional[int] = None
    total_institutional_buy: Optional[int] = None

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
    def from_json(cls, json_str: str) -> ScanResult:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            ScanResult 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        return pd.DataFrame([self.model_dump()])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> ScanResult | list[ScanResult]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 ScanResult；
            若有多列，回傳 ScanResult 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]


class MarketSnapshot(BaseModel):
    """市場快照。

    儲存某一時刻的多支股票掃描結果，提供批次操作介面。

    Attributes:
        snapshot_time: 快照產生時間。
        total_stocks: 掃描股票總數。
        results: 個別股票的掃描結果列表。
    """

    snapshot_time: datetime = Field(default_factory=datetime.now)
    total_stocks: int = Field(0, ge=0, description="掃描股票總數")
    results: List[ScanResult] = Field(default_factory=list, description="掃描結果列表")

    def to_json(self) -> str:
        """將模型序列化為 JSON 字串。

        Returns:
            JSON 格式字串。
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> MarketSnapshot:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            MarketSnapshot 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將所有掃描結果轉換為 pandas DataFrame。

        Returns:
            包含所有 ScanResult 資料的 DataFrame。
            若無結果，回傳空 DataFrame。
        """
        if not self.results:
            return pd.DataFrame()
        return pd.DataFrame([r.model_dump() for r in self.results])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> MarketSnapshot:
        """從 DataFrame 建立 MarketSnapshot 實例。

        將 DataFrame 的每一列視為一個 ScanResult。

        Args:
            df: 包含 ScanResult 欄位的 DataFrame。

        Returns:
            MarketSnapshot 實例。
        """
        results = [ScanResult.model_validate(row.to_dict()) for _, row in df.iterrows()]
        return cls(
            total_stocks=len(results),
            results=results,
        )
