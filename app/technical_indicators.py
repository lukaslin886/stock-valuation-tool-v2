"""
技術指標模組 (Technical Indicators)

提供 RSI 與 MACD 計算，以及對應的篩選判斷函式。
設計原則：
  - 純 pandas / numpy 計算，不觸網、不依賴外部 API，方便單元測試。
  - 輸入採用專案標準價格 schema：欄位含 close_price（DataManager.get_stock_price 輸出）。
  - 亦可直接傳入 close 價格 Series。

對應 TODO.md「加入技術指標篩選 (RSI/MACD)」。
"""

from typing import Optional, Dict
import numpy as np
import pandas as pd


CLOSE_CANDIDATES = ["close_price", "close", "Close", "收盤價"]


def _extract_close(data) -> pd.Series:
    """從 DataFrame / Series / list / ndarray 取出收盤價 Series（float）。"""
    if isinstance(data, pd.Series):
        s = data
    elif isinstance(data, pd.DataFrame):
        col = next((c for c in CLOSE_CANDIDATES if c in data.columns), None)
        if col is None:
            raise ValueError(
                f"找不到收盤價欄位，需為 {CLOSE_CANDIDATES} 之一，實得 {list(data.columns)}"
            )
        s = data[col]
    elif isinstance(data, (list, tuple, np.ndarray, pd.Index)):
        s = pd.Series(data)
    else:
        raise TypeError("data 必須為 pandas Series/DataFrame 或 list/ndarray")
    return pd.to_numeric(s, errors="coerce").astype(float).reset_index(drop=True)


def rsi(data, period: int = 14) -> pd.Series:
    """
    Wilder RSI。

    Args:
        data: 收盤價 Series 或含 close_price 的 DataFrame。
        period: 週期，預設 14。

    Returns:
        RSI Series（0~100），前 period 筆為 NaN。
    """
    close = _extract_close(data)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder 平滑：等價於 ewm(alpha=1/period)，min_periods=period 確保前段為 NaN
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss=0 時 RS=inf → RSI=100；avg_gain=avg_loss=0 時定義為 100（無跌幅）
    out = out.where(avg_loss != 0, 100.0)
    out[avg_gain == 0] = out[avg_gain == 0].where(avg_loss[avg_gain == 0] == 0, 0.0)
    return out


def macd(
    data,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD（12, 26, 9）。

    Returns:
        DataFrame，欄位：macd（DIF）、signal（DEA/訊號線）、hist（柱狀 = macd - signal）。
    """
    close = _extract_close(data)
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return pd.DataFrame({"macd": dif, "signal": dea, "hist": hist})


def macd_cross(data, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[str]:
    """
    偵測最新一根的 MACD 交叉。

    Returns:
        "golden"（黃金交叉，DIF 上穿訊號線）、"dead"（死亡交叉，DIF 下穿）、
        或 None（無交叉 / 資料不足）。
    """
    m = macd(data, fast, slow, signal)
    if len(m) < 2:
        return None
    prev, curr = m.iloc[-2], m.iloc[-1]
    if pd.isna(prev["hist"]) or pd.isna(curr["hist"]):
        return None
    if prev["hist"] <= 0 < curr["hist"]:
        return "golden"
    if prev["hist"] >= 0 > curr["hist"]:
        return "dead"
    return None


def compute_indicators(
    price_df: pd.DataFrame,
    rsi_period: int = 14,
    macd_params: tuple = (12, 26, 9),
) -> Dict[str, float]:
    """
    一次算出最新的指標快照，供篩選器使用。

    Returns:
        dict：rsi、macd、signal、hist、macd_cross（golden/dead/None）。
        資料不足時對應值為 None。
    """
    close = _extract_close(price_df)
    result: Dict[str, float] = {
        "rsi": None,
        "macd": None,
        "signal": None,
        "hist": None,
        "macd_cross": None,
    }
    if len(close) == 0:
        return result

    r = rsi(close, rsi_period)
    if not r.empty and not pd.isna(r.iloc[-1]):
        result["rsi"] = round(float(r.iloc[-1]), 2)

    m = macd(close, *macd_params)
    last = m.iloc[-1]
    if not pd.isna(last["macd"]):
        result["macd"] = round(float(last["macd"]), 4)
        result["signal"] = round(float(last["signal"]), 4)
        result["hist"] = round(float(last["hist"]), 4)
    result["macd_cross"] = macd_cross(close, *macd_params)
    return result


def screen_rsi(price_df, low: float = 30.0, high: float = 70.0, mode: str = "oversold") -> bool:
    """
    RSI 篩選判斷。

    Args:
        mode: "oversold"（RSI <= low，超賣）、"overbought"（RSI >= high，超買）、
              "neutral"（low < RSI < high）。

    Returns:
        是否通過篩選；資料不足回傳 False。
    """
    r = rsi(price_df)
    if r.empty or pd.isna(r.iloc[-1]):
        return False
    val = float(r.iloc[-1])
    if mode == "oversold":
        return val <= low
    if mode == "overbought":
        return val >= high
    if mode == "neutral":
        return low < val < high
    raise ValueError(f"未知 mode: {mode}")


def screen_macd(price_df, want: str = "golden") -> bool:
    """
    MACD 篩選判斷。

    Args:
        want: "golden"（最新為黃金交叉）、"dead"（死亡交叉）、
              "bullish"（hist > 0）、"bearish"（hist < 0）。
    """
    if want in ("golden", "dead"):
        return macd_cross(price_df) == want
    m = macd(price_df)
    if m.empty or pd.isna(m.iloc[-1]["hist"]):
        return False
    hist = float(m.iloc[-1]["hist"])
    if want == "bullish":
        return hist > 0
    if want == "bearish":
        return hist < 0
    raise ValueError(f"未知 want: {want}")
