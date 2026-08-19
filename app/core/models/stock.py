"""股票基本資訊與股價資料模型。

此模組定義 StockInfo 與 PriceData 兩個核心 Pydantic 模型，
包含市場別 Enum、欄位驗證器與模型驗證器。
另提供 detect_market 函式用於辨識股票代碼對應的市場別。
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator


class Market(str, Enum):
    """市場別列舉。

    Attributes:
        TW: 台灣上市市場。
        TWO: 台灣上櫃市場。
        US: 美國市場。
    """

    TW = "TW"
    TWO = "TWO"
    US = "US"


class StockInfo(BaseModel):
    """股票基本資訊。

    儲存股票的識別資訊、市場別、產業類別等基礎資料。

    Attributes:
        stock_code: 股票代碼（如 2330、AAPL）。
        stock_name: 股票名稱。
        market: 市場別（TW/TWO/US）。
        industry: 產業類別。
        listed_date: 上市/上櫃日期。
        shares_outstanding: 流通在外股數。
    """

    stock_code: str = Field(..., description="股票代碼")
    stock_name: str = Field("", description="股票名稱")
    market: Market = Field(Market.TW, description="市場別")
    industry: str = Field("", description="產業類別")
    listed_date: Optional[date] = Field(None, description="上市日期")
    shares_outstanding: Optional[int] = Field(None, ge=0, description="流通股數")

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
    def from_json(cls, json_str: str) -> StockInfo:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            StockInfo 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        data = self.model_dump()
        # 將 Enum 轉為其值
        if isinstance(data.get("market"), Market):
            data["market"] = data["market"].value
        return pd.DataFrame([data])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> StockInfo | list[StockInfo]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 StockInfo；
            若有多列，回傳 StockInfo 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]


class PriceData(BaseModel):
    """股價資料。

    儲存個股某一交易日的 OHLCV 資料，並驗證價格一致性。

    Attributes:
        stock_code: 股票代碼。
        date: 交易日期。
        open_price: 開盤價（須 > 0）。
        high_price: 最高價（須 > 0）。
        low_price: 最低價（須 > 0）。
        close_price: 收盤價（須 > 0）。
        volume: 成交量（股）（須 >= 0）。
    """

    stock_code: str
    date: date
    open_price: float = Field(..., gt=0, description="開盤價")
    high_price: float = Field(..., gt=0, description="最高價")
    low_price: float = Field(..., gt=0, description="最低價")
    close_price: float = Field(..., gt=0, description="收盤價")
    volume: int = Field(..., ge=0, description="成交量（股）")

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
    def validate_price_consistency(self) -> PriceData:
        """驗證價格一致性：最高價 >= 最低價，收盤價介於最高與最低之間。

        Returns:
            通過驗證的模型實例。

        Raises:
            ValueError: 當價格關係不一致時。
        """
        if self.high_price < self.low_price:
            raise ValueError("最高價不得低於最低價")
        if self.close_price > self.high_price or self.close_price < self.low_price:
            raise ValueError("收盤價須在最高最低價之間")
        return self

    def to_json(self) -> str:
        """將模型序列化為 JSON 字串。

        Returns:
            JSON 格式字串。
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> PriceData:
        """從 JSON 字串反序列化為模型實例。

        Args:
            json_str: JSON 格式字串。

        Returns:
            PriceData 實例。
        """
        return cls.model_validate_json(json_str)

    def to_dataframe(self) -> pd.DataFrame:
        """將模型轉換為 pandas DataFrame（單列）。

        Returns:
            包含模型所有欄位的 DataFrame。
        """
        return pd.DataFrame([self.model_dump()])

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> PriceData | list[PriceData]:
        """從 DataFrame 建立模型實例。

        Args:
            df: 包含模型欄位的 DataFrame。

        Returns:
            若 DataFrame 僅有一列，回傳單一 PriceData；
            若有多列，回傳 PriceData 列表。
        """
        if len(df) == 1:
            return cls.model_validate(df.iloc[0].to_dict())
        return [cls.model_validate(row.to_dict()) for _, row in df.iterrows()]


def detect_market(stock_input: str) -> Market:
    """辨識股票代碼對應的市場別。

    依據輸入格式判斷股票所屬市場：
    - 純英文字母 1-5 字元 -> 美股（Market.US）
    - 純數字 4-6 位 -> 台股上市或上櫃（代碼 >= 6000 為上櫃）
    - 帶後綴 .TW -> 台灣上市
    - 帶後綴 .TWO -> 台灣上櫃
    - 其他情況預設為台灣上市

    Args:
        stock_input: 使用者輸入的股票代碼字串。

    Returns:
        對應的 Market 列舉值。
    """
    stock_input = stock_input.strip().upper()

    # 純英文字母 1-5 字元 -> 美股
    if re.match(r"^[A-Z]{1,5}$", stock_input):
        return Market.US

    # 純數字 4-6 位 -> 台股（上市或上櫃）
    if re.match(r"^\d{4,6}$", stock_input):
        code = int(stock_input)
        if code >= 6000:
            return Market.TWO  # 上櫃
        return Market.TW  # 上市

    # 帶後綴的格式
    if stock_input.endswith(".TWO"):
        return Market.TWO
    if stock_input.endswith(".TW"):
        return Market.TW

    return Market.TW  # 預設台股
