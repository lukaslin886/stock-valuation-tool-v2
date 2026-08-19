"""交易訊號模型。

此模組定義 TradeSignal 與 SignalType 列舉，
包含價格範圍驗證器。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator


class SignalType(str, Enum):
    """交易訊號類型。

    Attributes:
        BUY: 買入訊號。
        SELL: 賣出訊號。
        HOLD: 觀望訊號。
    """

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradeSignal(BaseModel):
    """交易訊號。

    儲存系統產生的交易訊號，包含訊號類型、信心度、
    觸發條件描述與建議價格區間。

    Attributes:
        stock_code: 股票代碼。
        signal_type: 訊號類型（買入/賣出/觀望）。
        confidence: 信心度（0 ~ 100）。
        trigger_description: 觸發條件描述文字。
        suggested_price_low: 建議價格下限（須 > 0）。
        suggested_price_high: 建議價格上限（須 > 0）。
        generated_at: 訊號產生時間。
    """

    stock_code: str
    signal_type: SignalType = Field(..., description="訊號類型")
    confidence: int = Field(..., ge=0, le=100, description="信心度")
    trigger_description: str = Field(..., description="觸發條件描述")
    suggested_price_low: float = Field(..., gt=0, description="建議價格下限")
    suggested_price_high: float = Field(..., gt=0, description="建議價格上限")
    generated_at: datetime = Field(default_factory=datetime.now)

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

    @model_validator(mode="after")
    def validate_price_range(self) -> TradeSignal:
        """驗證價格上限不得低於下限。

        Returns:
            通過驗證的模型實例。

        Raises:
            ValueError: 當價格上限低於下限時。
        """
        if self.suggested_price_high < self.suggested_price_low:
            raise ValueError("價格上限不得低於下限")
        return self

    def to_json(self) -> str:
        """將模型序列化為 JSON 字串。

        Returns:
            JSON 格式字串。
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> TradeSignal:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            TradeSignal 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        data = self.model_dump()
        # 將 Enum 轉為其值
        if isinstance(data.get("signal_type"), SignalType):
            data["signal_type"] = data["signal_type"].value
        return pd.DataFrame([data])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> TradeSignal | list[TradeSignal]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 TradeSignal；
            若有多列，回傳 TradeSignal 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]
