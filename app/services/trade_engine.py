"""交易訊號引擎。

提供 TradeSignalEngine 與 PaperTrader 兩個核心類別：
- TradeSignalEngine：根據 DCF 估值結果與法人籌碼資料產生買入/賣出訊號
- PaperTrader：模擬交易模式，記錄虛擬交易並追蹤報酬率

訊號產生條件：
- 買入：DCF 低估 >30% AND 法人連續買超 >3 日
- 賣出：DCF 高估 >20% OR 法人連續賣超 >5 日

訊號持久化至 SQLite trade_signals 資料表（狀態：pending/consumed/expired）。
模擬交易記錄至 paper_trades 資料表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.models.financial import DCFResult
from app.core.models.trade import SignalType, TradeSignal
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

_BUY_UPSIDE_THRESHOLD = 0.3
"""買入訊號：DCF 低估門檻（30%）。"""

_BUY_CONSECUTIVE_BUY_DAYS = 3
"""買入訊號：法人連續買超最少天數。"""

_SELL_DOWNSIDE_THRESHOLD = -0.2
"""賣出訊號：DCF 高估門檻（-20%）。"""

_SELL_CONSECUTIVE_SELL_DAYS = 5
"""賣出訊號：法人連續賣超天數門檻。"""

_CONFIDENCE_BASE_MULTIPLIER = 100
"""信心度計算：upside_potential 的乘數基礎。"""

_CONFIDENCE_CHIP_BONUS = 5
"""信心度計算：每日法人連續買超加分。"""


# ---------------------------------------------------------------------------
# TradeSignalEngine
# ---------------------------------------------------------------------------


class TradeSignalEngine:
    """交易訊號引擎。

    根據 DCF 估值結果與法人籌碼資料評估買入/賣出條件，
    產生交易訊號並持久化至 SQLite。

    Args:
        sqlite_cache: SQLiteCache 實例，用於訊號持久化。

    Example::

        engine = TradeSignalEngine(sqlite_cache=cache)
        signal = engine.evaluate_buy_signal("2330", dcf_result, chip_data)
        if signal:
            signal_id = engine.emit_signal(signal)
    """

    def __init__(self, sqlite_cache: SQLiteCache) -> None:
        """初始化交易訊號引擎。

        Args:
            sqlite_cache: SQLiteCache 實例，提供訊號讀寫操作。
        """
        self._cache = sqlite_cache
        logger.info("TradeSignalEngine initialized")

    def evaluate_buy_signal(
        self,
        stock_code: str,
        dcf_result: DCFResult,
        chip_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[TradeSignal]:
        """評估買入訊號。

        買入條件：
        - DCF upside_potential > 0.3（30% 低估）
        - 法人連續買超 > 3 日（若籌碼資料可用）

        信心度 = min(100, int(upside_potential * 100) + foreign_days * 5)

        Args:
            stock_code: 股票代碼。
            dcf_result: DCF 估值結果。
            chip_data: 籌碼資料字典，應包含 "foreign_consecutive_buy" 欄位。
                若為 None 則略過籌碼條件。

        Returns:
            符合條件時回傳 TradeSignal 買入訊號，否則回傳 None。
        """
        upside = dcf_result.upside_potential

        # 條件 1：DCF 低估超過 30%
        if upside <= _BUY_UPSIDE_THRESHOLD:
            return None

        # 條件 2：法人連續買超（若有籌碼資料）
        foreign_days = 0
        if chip_data is not None:
            foreign_days = chip_data.get("foreign_consecutive_buy", 0)
            if foreign_days <= _BUY_CONSECUTIVE_BUY_DAYS:
                return None

        # 計算信心度
        confidence = min(
            100,
            int(upside * _CONFIDENCE_BASE_MULTIPLIER) + foreign_days * _CONFIDENCE_CHIP_BONUS,
        )

        # 建立觸發條件描述
        trigger_parts = [
            f"DCF upside {upside:.1%}",
        ]
        if chip_data is not None:
            trigger_parts.append(f"foreign consecutive buy {foreign_days} days")

        trigger_description = " AND ".join(trigger_parts)

        # 計算建議價格區間
        current_price = dcf_result.current_price
        intrinsic_value = dcf_result.intrinsic_value
        suggested_low = current_price * 0.98
        suggested_high = min(intrinsic_value, current_price * 1.05)
        # 確保 suggested_high >= suggested_low
        if suggested_high < suggested_low:
            suggested_high = suggested_low

        signal = TradeSignal(
            stock_code=stock_code,
            signal_type=SignalType.BUY,
            confidence=confidence,
            trigger_description=trigger_description,
            suggested_price_low=suggested_low,
            suggested_price_high=suggested_high,
        )

        logger.info(
            "Buy signal generated: %s confidence=%d",
            stock_code,
            confidence,
        )
        return signal

    def evaluate_sell_signal(
        self,
        stock_code: str,
        dcf_result: DCFResult,
        chip_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[TradeSignal]:
        """評估賣出訊號。

        賣出條件（滿足任一即觸發）：
        - DCF upside_potential < -0.2（20% 高估）
        - 法人連續賣超 > 5 日（若籌碼資料可用）

        Args:
            stock_code: 股票代碼。
            dcf_result: DCF 估值結果。
            chip_data: 籌碼資料字典，應包含 "foreign_consecutive_sell" 欄位。
                若為 None 則僅檢查 DCF 條件。

        Returns:
            符合條件時回傳 TradeSignal 賣出訊號，否則回傳 None。
        """
        upside = dcf_result.upside_potential
        foreign_sell_days = 0
        if chip_data is not None:
            foreign_sell_days = chip_data.get("foreign_consecutive_sell", 0)

        # 條件判斷（OR 邏輯）
        dcf_triggered = upside < _SELL_DOWNSIDE_THRESHOLD
        chip_triggered = foreign_sell_days > _SELL_CONSECUTIVE_SELL_DAYS

        if not dcf_triggered and not chip_triggered:
            return None

        # 建立觸發條件描述
        trigger_parts: List[str] = []
        if dcf_triggered:
            trigger_parts.append(f"DCF overvalued {upside:.1%}")
        if chip_triggered:
            trigger_parts.append(
                f"foreign consecutive sell {foreign_sell_days} days"
            )
        trigger_description = " OR ".join(trigger_parts)

        # 計算信心度
        confidence_from_dcf = int(abs(upside) * _CONFIDENCE_BASE_MULTIPLIER) if dcf_triggered else 0
        confidence_from_chip = foreign_sell_days * _CONFIDENCE_CHIP_BONUS if chip_triggered else 0
        confidence = min(100, confidence_from_dcf + confidence_from_chip)

        # 計算建議賣出價格區間
        current_price = dcf_result.current_price
        suggested_low = current_price * 0.95
        suggested_high = current_price * 1.02
        # 確保 suggested_high >= suggested_low
        if suggested_high < suggested_low:
            suggested_high = suggested_low

        signal = TradeSignal(
            stock_code=stock_code,
            signal_type=SignalType.SELL,
            confidence=confidence,
            trigger_description=trigger_description,
            suggested_price_low=suggested_low,
            suggested_price_high=suggested_high,
        )

        logger.info(
            "Sell signal generated: %s confidence=%d",
            stock_code,
            confidence,
        )
        return signal

    def emit_signal(self, signal: TradeSignal) -> int:
        """將訊號持久化至 SQLite trade_signals 資料表。

        Args:
            signal: 要儲存的交易訊號。

        Returns:
            新增記錄的 signal_id。
        """
        signal_dict = {
            "stock_code": signal.stock_code,
            "signal_type": signal.signal_type.value,
            "confidence": signal.confidence,
            "trigger_description": signal.trigger_description,
            "suggested_price_low": signal.suggested_price_low,
            "suggested_price_high": signal.suggested_price_high,
            "generated_at": signal.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending",
        }
        signal_id = self._cache.insert_signal(signal_dict)
        logger.info("Signal emitted: id=%d stock=%s", signal_id, signal.stock_code)
        return signal_id

    def get_pending_signals(
        self, stock_code: Optional[str] = None
    ) -> List[TradeSignal]:
        """取得所有待處理的交易訊號。

        Args:
            stock_code: 限定特定股票代碼（可選）。

        Returns:
            待處理的 TradeSignal 列表。
        """
        rows = self._cache.get_pending_signals(stock_code=stock_code)
        signals: List[TradeSignal] = []
        for row in rows:
            try:
                signal = TradeSignal(
                    stock_code=row["stock_code"],
                    signal_type=SignalType(row["signal_type"]),
                    confidence=row["confidence"],
                    trigger_description=row.get("trigger_description", ""),
                    suggested_price_low=row.get("suggested_price_low", 0.01),
                    suggested_price_high=row.get("suggested_price_high", 0.01),
                    generated_at=datetime.strptime(
                        row["generated_at"], "%Y-%m-%d %H:%M:%S"
                    ),
                )
                signals.append(signal)
            except (ValueError, KeyError) as e:
                logger.warning(
                    "Skipping invalid signal row id=%s: %s",
                    row.get("id", "?"),
                    str(e),
                )
        return signals

    def consume_signal(self, signal_id: int) -> bool:
        """將訊號標記為已消費。

        Args:
            signal_id: 訊號 ID。

        Returns:
            True 表示成功消費，False 表示訊號不存在或已非 pending 狀態。
        """
        result = self._cache.consume_signal(signal_id)
        if result:
            logger.info("Signal consumed: id=%d", signal_id)
        else:
            logger.warning("Failed to consume signal: id=%d", signal_id)
        return result


# ---------------------------------------------------------------------------
# PaperTrader
# ---------------------------------------------------------------------------


class PaperTrader:
    """模擬交易器。

    記錄虛擬交易至 paper_trades 資料表，追蹤投資組合與績效指標。
    不涉及實際下單，僅供回測與策略驗證使用。

    Args:
        sqlite_cache: SQLiteCache 實例，用於交易記錄持久化。

    Example::

        trader = PaperTrader(sqlite_cache=cache)
        trade_id = trader.execute_trade(signal, quantity=1000, price=580.0)
        performance = trader.get_performance()
    """

    def __init__(self, sqlite_cache: SQLiteCache) -> None:
        """初始化模擬交易器。

        Args:
            sqlite_cache: SQLiteCache 實例，提供交易記錄讀寫操作。
        """
        self._cache = sqlite_cache
        logger.info("PaperTrader initialized")

    def execute_trade(
        self,
        signal: TradeSignal,
        quantity: int,
        price: float,
    ) -> int:
        """執行模擬交易。

        將交易記錄寫入 paper_trades 資料表。

        Args:
            signal: 觸發此交易的訊號。
            quantity: 交易股數（須 > 0）。
            price: 成交價格（須 > 0）。

        Returns:
            新增模擬交易記錄的 id。

        Raises:
            ValueError: 當 quantity <= 0 或 price <= 0 時。
        """
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        trade_dict = {
            "stock_code": signal.stock_code,
            "action": signal.signal_type.value,
            "quantity": quantity,
            "price": price,
            "signal_id": None,
            "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notes": f"Paper trade: {signal.trigger_description}",
        }
        trade_id = self._cache.insert_paper_trade(trade_dict)
        logger.info(
            "Paper trade executed: id=%d stock=%s action=%s qty=%d price=%.2f",
            trade_id,
            signal.stock_code,
            signal.signal_type.value,
            quantity,
            price,
        )
        return trade_id

    def get_portfolio(self) -> Dict[str, Any]:
        """取得目前模擬投資組合。

        彙整所有模擬交易計算各股持倉數量與平均成本。

        Returns:
            字典，鍵為股票代碼，值為持倉資訊字典：
            - quantity: 持倉股數（正數為持有，負數應不存在）
            - avg_cost: 加權平均成本
            - total_cost: 總投入成本
        """
        trades = self._cache.get_paper_trades()
        positions: Dict[str, Dict[str, float]] = {}

        for trade in trades:
            code = trade["stock_code"]
            action = trade["action"]
            qty = trade["quantity"]
            price = trade["price"]

            if code not in positions:
                positions[code] = {"quantity": 0, "total_cost": 0.0}

            if action == SignalType.BUY.value:
                positions[code]["total_cost"] += qty * price
                positions[code]["quantity"] += qty
            elif action == SignalType.SELL.value:
                positions[code]["quantity"] -= qty
                # 賣出時按比例減少總成本
                if positions[code]["quantity"] > 0:
                    avg = (
                        positions[code]["total_cost"]
                        / (positions[code]["quantity"] + qty)
                    )
                    positions[code]["total_cost"] = avg * positions[code]["quantity"]
                else:
                    positions[code]["total_cost"] = 0.0

        # 計算平均成本
        portfolio: Dict[str, Any] = {}
        for code, pos in positions.items():
            qty = pos["quantity"]
            total_cost = pos["total_cost"]
            avg_cost = total_cost / qty if qty > 0 else 0.0
            portfolio[code] = {
                "quantity": int(qty),
                "avg_cost": round(avg_cost, 2),
                "total_cost": round(total_cost, 2),
            }

        return portfolio

    def get_performance(self) -> Dict[str, float]:
        """取得模擬交易績效指標。

        計算項目：
        - win_rate: 獲利交易比例（以已平倉配對計算）
        - avg_return: 平均報酬率
        - max_drawdown: 最大回撤（以累計損益計算）
        - total_trades: 總交易筆數

        Returns:
            績效指標字典。
        """
        trades = self._cache.get_paper_trades()
        total_trades = len(trades)

        if total_trades == 0:
            return {
                "win_rate": 0.0,
                "avg_return": 0.0,
                "max_drawdown": 0.0,
                "total_trades": 0.0,
            }

        # 計算已完成的買賣配對
        buy_records: Dict[str, List[Dict[str, Any]]] = {}
        closed_returns: List[float] = []

        # 按時間排序（最舊的在前）
        sorted_trades = sorted(trades, key=lambda t: t.get("executed_at", ""))

        for trade in sorted_trades:
            code = trade["stock_code"]
            action = trade["action"]
            qty = trade["quantity"]
            price = trade["price"]

            if action == SignalType.BUY.value:
                if code not in buy_records:
                    buy_records[code] = []
                buy_records[code].append({"quantity": qty, "price": price})
            elif action == SignalType.SELL.value:
                # FIFO 配對計算報酬
                if code in buy_records and buy_records[code]:
                    remaining_sell = qty
                    while remaining_sell > 0 and buy_records[code]:
                        buy = buy_records[code][0]
                        matched = min(remaining_sell, buy["quantity"])
                        ret = (price - buy["price"]) / buy["price"]
                        closed_returns.append(ret)
                        remaining_sell -= matched
                        buy["quantity"] -= matched
                        if buy["quantity"] <= 0:
                            buy_records[code].pop(0)

        # 計算績效指標
        win_rate = 0.0
        avg_return = 0.0
        max_drawdown = 0.0

        if closed_returns:
            wins = sum(1 for r in closed_returns if r > 0)
            win_rate = wins / len(closed_returns)
            avg_return = sum(closed_returns) / len(closed_returns)

            # 計算最大回撤（累計損益序列）
            cumulative = 0.0
            peak = 0.0
            for ret in closed_returns:
                cumulative += ret
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        return {
            "win_rate": round(win_rate, 4),
            "avg_return": round(avg_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "total_trades": float(total_trades),
        }
