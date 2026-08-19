"""美股支援整合工具模組。

提供市場上下文資訊（MarketContext）給 UI 層使用，
包含幣別標示、市場標籤、價格格式化，以及美股專屬錯誤訊息。

此模組作為 Streamlit 視圖層與底層市場偵測邏輯之間的橋接層，
讓 UI 程式碼不需直接操作 Market enum 與 detect_market 邏輯。

Usage::

    from app.services.us_stock_support import get_market_context, format_price

    ctx = get_market_context("AAPL")
    assert ctx.is_us_stock is True
    assert ctx.currency == "USD"

    formatted = format_price(175.50, ctx.market)
    assert formatted == "$175.50"
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models.stock import Market, detect_market


# ---------------------------------------------------------------------------
# 市場上下文資料類別
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketContext:
    """市場上下文，供 UI 層使用。

    封裝市場偵測結果及其對應的顯示屬性，讓視圖層能直接使用
    幣別符號、市場標籤等資訊，無需自行判斷。

    Attributes:
        market: 市場別列舉值（TW/TWO/US）。
        currency: 幣別代碼，如 "TWD" 或 "USD"。
        currency_symbol: 幣別符號，如 "NT$" 或 "$"。
        market_label: 市場中文標籤，如 "台股" 或 "美股"。
        is_us_stock: 是否為美股。
    """

    market: Market
    currency: str
    currency_symbol: str
    market_label: str
    is_us_stock: bool


# ---------------------------------------------------------------------------
# 市場屬性對照表
# ---------------------------------------------------------------------------

_MARKET_DISPLAY_CONFIG: dict[Market, dict[str, str]] = {
    Market.TW: {
        "currency": "TWD",
        "currency_symbol": "NT$",
        "market_label": "台股（上市）",
    },
    Market.TWO: {
        "currency": "TWD",
        "currency_symbol": "NT$",
        "market_label": "台股（上櫃）",
    },
    Market.US: {
        "currency": "USD",
        "currency_symbol": "$",
        "market_label": "美股",
    },
}


# ---------------------------------------------------------------------------
# 公開函式
# ---------------------------------------------------------------------------


def get_market_context(stock_code: str) -> MarketContext:
    """依據股票代碼取得市場上下文。

    內部呼叫 detect_market 辨識市場別，再對應為完整的
    MarketContext 供 UI 層使用。

    Args:
        stock_code: 使用者輸入的股票代碼（如 "2330"、"AAPL"）。

    Returns:
        MarketContext 實例，包含市場別、幣別、標籤等資訊。
    """
    market = detect_market(stock_code)
    config = _MARKET_DISPLAY_CONFIG[market]

    return MarketContext(
        market=market,
        currency=config["currency"],
        currency_symbol=config["currency_symbol"],
        market_label=config["market_label"],
        is_us_stock=(market == Market.US),
    )


def get_us_stock_error_message() -> str:
    """取得美股資料取得失敗時的專屬錯誤訊息。

    回傳供 UI 層顯示的使用者友善訊息，符合需求 11.5 的規範。

    Returns:
        美股資料取得失敗的中文錯誤訊息字串。
    """
    return "美股資料暫時無法取得，請確認網路連線"


def format_price(price: float, market: Market) -> str:
    """將價格依市場別格式化為含幣別符號的字串。

    台股以整數顯示（小數點後無位數），美股保留兩位小數。

    Args:
        price: 股票價格數值。
        market: 市場別列舉值。

    Returns:
        格式化後的價格字串（如 "NT$973" 或 "$175.50"）。
    """
    config = _MARKET_DISPLAY_CONFIG[market]
    symbol = config["currency_symbol"]

    if market == Market.US:
        return f"{symbol}{price:,.2f}"
    else:
        # 台股價格通常顯示至整數或一位小數
        if price == int(price):
            return f"{symbol}{int(price):,}"
        return f"{symbol}{price:,.2f}"


def format_market_info(stock_code: str) -> str:
    """產生股票代碼的市場資訊摘要字串。

    供 UI 標題或狀態列顯示，格式如：「AAPL (美股 / USD)」。

    Args:
        stock_code: 使用者輸入的股票代碼。

    Returns:
        含市場標籤與幣別的摘要字串。
    """
    ctx = get_market_context(stock_code)
    return f"{stock_code.upper()} ({ctx.market_label} / {ctx.currency})"
