"""TradeSignalEngine 與 PaperTrader 單元測試。"""

import os
import tempfile
from datetime import datetime

import pytest

from app.core.models.financial import DCFResult
from app.core.models.trade import SignalType, TradeSignal
from app.infra.cache.sqlite_cache import SQLiteCache
from app.services.trade_engine import (
    PaperTrader,
    TradeSignalEngine,
)


@pytest.fixture
def sqlite_cache():
    """建立暫存 SQLite 快取實例。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = SQLiteCache(db_path=path)
    yield cache
    cache.close()
    os.unlink(path)


@pytest.fixture
def engine(sqlite_cache):
    """建立 TradeSignalEngine 實例。"""
    return TradeSignalEngine(sqlite_cache=sqlite_cache)


@pytest.fixture
def paper_trader(sqlite_cache):
    """建立 PaperTrader 實例。"""
    return PaperTrader(sqlite_cache=sqlite_cache)


def _make_dcf_result(
    stock_code: str = "2330",
    current_price: float = 500.0,
    intrinsic_value: float = 700.0,
    upside_potential: float = 0.4,
) -> DCFResult:
    """建立測試用 DCFResult。"""
    return DCFResult(
        stock_code=stock_code,
        stock_name="Test Stock",
        current_price=current_price,
        intrinsic_value=intrinsic_value,
        upside_potential=upside_potential,
        discount_rate=0.08,
        growth_rates=[0.1, 0.1, 0.1],
        terminal_value=1000.0,
        recommendation="buy",
        data_source="test",
    )


# ---------------------------------------------------------------------------
# TradeSignalEngine: evaluate_buy_signal
# ---------------------------------------------------------------------------


class TestEvaluateBuySignal:
    """買入訊號評估測試。"""

    def test_buy_signal_triggered(self, engine):
        """DCF 低估 >30% 且法人連續買超 >3 日 -> 產生買入訊號。"""
        dcf = _make_dcf_result(upside_potential=0.4)
        chip = {"foreign_consecutive_buy": 5}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.stock_code == "2330"

    def test_buy_signal_not_triggered_low_upside(self, engine):
        """DCF 低估 <= 30% -> 不產生訊號。"""
        dcf = _make_dcf_result(upside_potential=0.25)
        chip = {"foreign_consecutive_buy": 5}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is None

    def test_buy_signal_not_triggered_low_foreign_days(self, engine):
        """法人連續買超 <= 3 日 -> 不產生訊號。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        chip = {"foreign_consecutive_buy": 2}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is None

    def test_buy_signal_no_chip_data_still_triggers(self, engine):
        """無籌碼資料時僅靠 DCF 低估觸發。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_buy_signal_confidence_calculation(self, engine):
        """信心度 = min(100, int(upside*100) + days*5)。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        chip = {"foreign_consecutive_buy": 6}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is not None
        # confidence = min(100, int(0.5*100) + 6*5) = min(100, 50+30) = 80
        assert signal.confidence == 80

    def test_buy_signal_confidence_capped_at_100(self, engine):
        """信心度不超過 100。"""
        dcf = _make_dcf_result(upside_potential=0.9)
        chip = {"foreign_consecutive_buy": 10}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is not None
        # confidence = min(100, int(0.9*100) + 10*5) = min(100, 90+50) = 100
        assert signal.confidence == 100

    def test_buy_signal_boundary_upside_30_not_triggered(self, engine):
        """upside_potential 恰好 0.3 -> 不觸發（需要 > 0.3）。"""
        dcf = _make_dcf_result(upside_potential=0.3)
        chip = {"foreign_consecutive_buy": 5}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is None

    def test_buy_signal_boundary_foreign_days_3_not_triggered(self, engine):
        """法人連續買超恰好 3 日 -> 不觸發（需要 > 3）。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        chip = {"foreign_consecutive_buy": 3}
        signal = engine.evaluate_buy_signal("2330", dcf, chip)
        assert signal is None


# ---------------------------------------------------------------------------
# TradeSignalEngine: evaluate_sell_signal
# ---------------------------------------------------------------------------


class TestEvaluateSellSignal:
    """賣出訊號評估測試。"""

    def test_sell_signal_dcf_overvalued(self, engine):
        """DCF 高估 >20% -> 產生賣出訊號。"""
        dcf = _make_dcf_result(upside_potential=-0.3)
        signal = engine.evaluate_sell_signal("2330", dcf, None)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    def test_sell_signal_foreign_sell(self, engine):
        """法人連續賣超 >5 日 -> 產生賣出訊號。"""
        dcf = _make_dcf_result(upside_potential=0.1)
        chip = {"foreign_consecutive_sell": 7}
        signal = engine.evaluate_sell_signal("2330", dcf, chip)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    def test_sell_signal_not_triggered(self, engine):
        """兩個條件都不滿足 -> 不產生訊號。"""
        dcf = _make_dcf_result(upside_potential=-0.1)
        chip = {"foreign_consecutive_sell": 3}
        signal = engine.evaluate_sell_signal("2330", dcf, chip)
        assert signal is None

    def test_sell_signal_boundary_upside_minus_02_not_triggered(self, engine):
        """upside_potential 恰好 -0.2 -> 不觸發（需要 < -0.2）。"""
        dcf = _make_dcf_result(upside_potential=-0.2)
        signal = engine.evaluate_sell_signal("2330", dcf, None)
        assert signal is None

    def test_sell_signal_boundary_foreign_days_5_not_triggered(self, engine):
        """法人連續賣超恰好 5 日 -> 不觸發（需要 > 5）。"""
        dcf = _make_dcf_result(upside_potential=0.0)
        chip = {"foreign_consecutive_sell": 5}
        signal = engine.evaluate_sell_signal("2330", dcf, chip)
        assert signal is None


# ---------------------------------------------------------------------------
# TradeSignalEngine: emit_signal / get_pending / consume
# ---------------------------------------------------------------------------


class TestSignalQueue:
    """訊號佇列操作測試。"""

    def test_emit_and_get_pending(self, engine):
        """emit 後可透過 get_pending_signals 取回。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        assert signal is not None
        signal_id = engine.emit_signal(signal)
        assert signal_id > 0

        pending = engine.get_pending_signals()
        assert len(pending) >= 1
        assert pending[0].stock_code == "2330"

    def test_consume_signal(self, engine):
        """consume 後訊號不再出現於 pending 清單。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        signal_id = engine.emit_signal(signal)

        result = engine.consume_signal(signal_id)
        assert result is True

        pending = engine.get_pending_signals()
        assert len(pending) == 0

    def test_consume_nonexistent_signal(self, engine):
        """消費不存在的訊號回傳 False。"""
        result = engine.consume_signal(99999)
        assert result is False

    def test_get_pending_by_stock_code(self, engine):
        """依股票代碼篩選 pending 訊號。"""
        dcf_a = _make_dcf_result(stock_code="2330", upside_potential=0.5)
        dcf_b = _make_dcf_result(stock_code="2317", upside_potential=0.6)
        signal_a = engine.evaluate_buy_signal("2330", dcf_a, None)
        signal_b = engine.evaluate_buy_signal("2317", dcf_b, None)
        engine.emit_signal(signal_a)
        engine.emit_signal(signal_b)

        pending = engine.get_pending_signals(stock_code="2330")
        assert len(pending) == 1
        assert pending[0].stock_code == "2330"


# ---------------------------------------------------------------------------
# PaperTrader
# ---------------------------------------------------------------------------


class TestPaperTrader:
    """模擬交易器測試。"""

    def test_execute_trade(self, paper_trader, engine):
        """執行模擬交易回傳 trade_id > 0。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        trade_id = paper_trader.execute_trade(signal, quantity=1000, price=500.0)
        assert trade_id > 0

    def test_execute_trade_invalid_quantity(self, paper_trader, engine):
        """quantity <= 0 應 raise ValueError。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        with pytest.raises(ValueError, match="quantity"):
            paper_trader.execute_trade(signal, quantity=0, price=500.0)

    def test_execute_trade_invalid_price(self, paper_trader, engine):
        """price <= 0 應 raise ValueError。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        with pytest.raises(ValueError, match="price"):
            paper_trader.execute_trade(signal, quantity=100, price=-1.0)

    def test_get_portfolio_empty(self, paper_trader):
        """無交易時投資組合為空。"""
        portfolio = paper_trader.get_portfolio()
        assert portfolio == {}

    def test_get_portfolio_after_buy(self, paper_trader, engine):
        """買入後投資組合反映持倉。"""
        dcf = _make_dcf_result(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf, None)
        paper_trader.execute_trade(signal, quantity=1000, price=500.0)

        portfolio = paper_trader.get_portfolio()
        assert "2330" in portfolio
        assert portfolio["2330"]["quantity"] == 1000
        assert portfolio["2330"]["avg_cost"] == 500.0

    def test_get_performance_empty(self, paper_trader):
        """無交易時績效指標為零。"""
        perf = paper_trader.get_performance()
        assert perf["win_rate"] == 0.0
        assert perf["avg_return"] == 0.0
        assert perf["max_drawdown"] == 0.0
        assert perf["total_trades"] == 0.0
