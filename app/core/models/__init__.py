"""Pydantic 核心資料模型。

此套件提供台股估值工具的所有核心資料模型，包含：
- stock: 股票基本資訊與股價資料（StockInfo, PriceData, Market）
- financial: 財報資料與 DCF 結果（FinancialData, DCFResult）
- scan: 市場掃描結果（ScanResult, MarketSnapshot）
- trade: 交易訊號（TradeSignal, SignalType）
"""

from app.core.models.financial import DCFResult, FinancialData, normalize_percentage
from app.core.models.scan import MarketSnapshot, ScanResult
from app.core.models.stock import Market, PriceData, StockInfo, detect_market
from app.core.models.trade import SignalType, TradeSignal

__all__ = [
    "Market",
    "StockInfo",
    "PriceData",
    "FinancialData",
    "DCFResult",
    "ScanResult",
    "MarketSnapshot",
    "SignalType",
    "TradeSignal",
    "normalize_percentage",
    "detect_market",
]
