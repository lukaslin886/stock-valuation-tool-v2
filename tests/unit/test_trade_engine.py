"""Unit tests for app/services/trade_engine.py (TradeSignalEngine + PaperTrader).

Written 2026-09-06 to close a real coverage gap (71.51% covered, 51/179
statements missed before this file — see HANDOFF.md 第 10 節 follow-up on
raising app/core+app/infra+app/services coverage to genuinely >=80%).
Uses a real SQLiteCache against a temp DB file, matching the existing
constructor-injection design (both TradeSignalEngine and PaperTrader take
a sqlite_cache instance) rather than mocking the persistence layer.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta

import pytest

from app.core.models.financial import DCFResult
from app.core.models.trade import SignalType, TradeSignal
from app.infra.cache.sqlite_cache import SQLiteCache
from app.services.trade_engine import PaperTrader, TradeSignalEngine


@pytest.fixture
def temp_cache():
    db_dir = tempfile.mkdtemp(prefix="trade_engine_test_")
    db_path = os.path.join(db_dir, "test.db")
    cache = SQLiteCache(db_path=db_path)
    yield cache
    cache.close()
    shutil.rmtree(db_dir, ignore_errors=True)


def _dcf(
    stock_code: str = "2330",
    current_price: float = 100.0,
    intrinsic_value: float = 150.0,
    upside_potential: float = 0.5,
) -> DCFResult:
    return DCFResult(
        stock_code=stock_code,
        current_price=current_price,
        intrinsic_value=intrinsic_value,
        upside_potential=upside_potential,
        discount_rate=0.1,
        growth_rates=[0.05, 0.05, 0.05],
        terminal_value=1000.0,
        recommendation="buy",
    )


class TestEvaluateBuySignal:
    def test_below_upside_threshold_no_signal(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.1)
        assert engine.evaluate_buy_signal("2330", dcf) is None

    def test_passes_without_chip_data(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert "foreign consecutive buy" not in signal.trigger_description

    def test_insufficient_consecutive_buy_days_no_signal(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.5)
        chip_data = {"foreign_consecutive_buy": 1}
        assert engine.evaluate_buy_signal("2330", dcf, chip_data) is None

    def test_passes_with_sufficient_chip_data(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.5)
        chip_data = {"foreign_consecutive_buy": 5}
        signal = engine.evaluate_buy_signal("2330", dcf, chip_data)
        assert signal is not None
        assert "foreign consecutive buy 5 days" in signal.trigger_description
        # confidence = min(100, int(0.5*100) + 5*5) = min(100, 75) = 75
        assert signal.confidence == 75

    def test_suggested_high_clamped_to_low_when_intrinsic_value_below_range(
        self, temp_cache: SQLiteCache
    ) -> None:
        """intrinsic_value can be independently below current_price*0.98 even
        while upside_potential (a separate field) clears the 0.3 threshold —
        exercises the suggested_high < suggested_low clamp branch."""
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(current_price=100.0, intrinsic_value=90.0, upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf)
        assert signal is not None
        assert signal.suggested_price_high == signal.suggested_price_low


class TestEvaluateSellSignal:
    def test_neither_condition_no_signal(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.0)
        assert engine.evaluate_sell_signal("2330", dcf) is None

    def test_dcf_triggered_only(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=-0.3)
        signal = engine.evaluate_sell_signal("2330", dcf)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert "DCF overvalued" in signal.trigger_description
        assert "OR" not in signal.trigger_description

    def test_chip_triggered_only(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.0)
        chip_data = {"foreign_consecutive_sell": 6}
        signal = engine.evaluate_sell_signal("2330", dcf, chip_data)
        assert signal is not None
        assert "foreign consecutive sell 6 days" in signal.trigger_description

    def test_both_triggered(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=-0.3)
        chip_data = {"foreign_consecutive_sell": 6}
        signal = engine.evaluate_sell_signal("2330", dcf, chip_data)
        assert signal is not None
        assert " OR " in signal.trigger_description


class TestSignalPersistenceLifecycle:
    def test_emit_and_get_pending_signals(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        dcf = _dcf(upside_potential=0.5)
        signal = engine.evaluate_buy_signal("2330", dcf)
        assert signal is not None
        signal_id = engine.emit_signal(signal)
        assert signal_id > 0

        pending = engine.get_pending_signals()
        assert len(pending) == 1
        assert pending[0].stock_code == "2330"

    def test_get_pending_signals_filters_by_stock_code(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        s1 = engine.evaluate_buy_signal("2330", _dcf(stock_code="2330", upside_potential=0.5))
        s2 = engine.evaluate_buy_signal("2317", _dcf(stock_code="2317", upside_potential=0.5))
        assert s1 is not None and s2 is not None
        engine.emit_signal(s1)
        engine.emit_signal(s2)

        pending = engine.get_pending_signals(stock_code="2317")
        assert len(pending) == 1
        assert pending[0].stock_code == "2317"

    def test_get_pending_signals_skips_invalid_rows(
        self, temp_cache: SQLiteCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed row (bad generated_at format) should be logged and
        skipped rather than raising, while valid rows are still returned."""
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        good_row = {
            "id": 1,
            "stock_code": "2330",
            "signal_type": "buy",
            "confidence": 80,
            "trigger_description": "ok",
            "suggested_price_low": 90.0,
            "suggested_price_high": 100.0,
            "generated_at": "2026-09-05 10:00:00",
            "status": "pending",
        }
        bad_row = {
            "id": 2,
            "stock_code": "2317",
            "signal_type": "buy",
            "confidence": 80,
            "trigger_description": "bad",
            "suggested_price_low": 90.0,
            "suggested_price_high": 100.0,
            "generated_at": "not-a-valid-date",
            "status": "pending",
        }
        monkeypatch.setattr(
            temp_cache, "get_pending_signals", lambda stock_code=None: [good_row, bad_row]
        )
        result = engine.get_pending_signals()
        assert len(result) == 1
        assert result[0].stock_code == "2330"

    def test_consume_signal_success_and_failure(self, temp_cache: SQLiteCache) -> None:
        engine = TradeSignalEngine(sqlite_cache=temp_cache)
        signal = engine.evaluate_buy_signal("2330", _dcf(upside_potential=0.5))
        assert signal is not None
        signal_id = engine.emit_signal(signal)

        assert engine.consume_signal(signal_id) is True
        # Consuming again should fail (already consumed, no longer pending).
        assert engine.consume_signal(signal_id) is False
        # Consuming a nonexistent id should fail too.
        assert engine.consume_signal(999999) is False


class TestPaperTraderExecuteTrade:
    def test_execute_trade_success(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        signal = TradeSignal(
            stock_code="2330",
            signal_type=SignalType.BUY,
            confidence=80,
            trigger_description="test",
            suggested_price_low=95.0,
            suggested_price_high=105.0,
        )
        trade_id = trader.execute_trade(signal, quantity=1000, price=100.0)
        assert trade_id > 0

    def test_execute_trade_rejects_nonpositive_quantity(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        signal = TradeSignal(
            stock_code="2330", signal_type=SignalType.BUY, confidence=80,
            trigger_description="t", suggested_price_low=1.0, suggested_price_high=2.0,
        )
        with pytest.raises(ValueError, match="quantity must be > 0"):
            trader.execute_trade(signal, quantity=0, price=100.0)

    def test_execute_trade_rejects_nonpositive_price(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        signal = TradeSignal(
            stock_code="2330", signal_type=SignalType.BUY, confidence=80,
            trigger_description="t", suggested_price_low=1.0, suggested_price_high=2.0,
        )
        with pytest.raises(ValueError, match="price must be > 0"):
            trader.execute_trade(signal, quantity=100, price=0)


def _buy_signal(stock_code: str = "2330") -> TradeSignal:
    return TradeSignal(
        stock_code=stock_code, signal_type=SignalType.BUY, confidence=80,
        trigger_description="buy", suggested_price_low=1.0, suggested_price_high=2.0,
    )


def _sell_signal(stock_code: str = "2330") -> TradeSignal:
    return TradeSignal(
        stock_code=stock_code, signal_type=SignalType.SELL, confidence=80,
        trigger_description="sell", suggested_price_low=1.0, suggested_price_high=2.0,
    )


class TestPaperTraderPortfolio:
    def test_empty_portfolio(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        assert trader.get_portfolio() == {}

    def test_single_buy(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        portfolio = trader.get_portfolio()
        assert portfolio["2330"]["quantity"] == 100
        assert portfolio["2330"]["avg_cost"] == 50.0
        assert portfolio["2330"]["total_cost"] == 5000.0

    def test_buy_then_partial_sell_keeps_remaining_position(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal(), quantity=40, price=60.0)
        portfolio = trader.get_portfolio()
        assert portfolio["2330"]["quantity"] == 60
        # avg cost recalculated proportionally: total_cost stays avg*remaining_qty
        assert portfolio["2330"]["avg_cost"] == 50.0

    def test_buy_then_full_sell_zeroes_out_cost(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal(), quantity=100, price=60.0)
        portfolio = trader.get_portfolio()
        assert portfolio["2330"]["quantity"] == 0
        assert portfolio["2330"]["total_cost"] == 0.0
        assert portfolio["2330"]["avg_cost"] == 0.0

    def test_multiple_stocks_tracked_independently(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal("2330"), quantity=100, price=50.0)
        trader.execute_trade(_buy_signal("2317"), quantity=200, price=20.0)
        portfolio = trader.get_portfolio()
        assert set(portfolio.keys()) == {"2330", "2317"}
        assert portfolio["2317"]["quantity"] == 200


class TestPaperTraderPerformance:
    def test_no_trades_returns_zeroed_metrics(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        perf = trader.get_performance()
        assert perf == {
            "win_rate": 0.0,
            "avg_return": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0.0,
        }

    def test_only_open_positions_no_closed_returns(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        perf = trader.get_performance()
        assert perf["total_trades"] == 1.0
        assert perf["win_rate"] == 0.0
        assert perf["avg_return"] == 0.0

    def test_single_winning_round_trip(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal(), quantity=100, price=60.0)
        perf = trader.get_performance()
        assert perf["total_trades"] == 2.0
        assert perf["win_rate"] == 1.0
        assert perf["avg_return"] == pytest.approx(0.2)
        assert perf["max_drawdown"] == 0.0

    def test_single_losing_round_trip_has_drawdown(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal(), quantity=100, price=40.0)
        perf = trader.get_performance()
        assert perf["win_rate"] == 0.0
        assert perf["avg_return"] == pytest.approx(-0.2)
        assert perf["max_drawdown"] == pytest.approx(0.2)

    def test_fifo_matching_across_multiple_buys(self, temp_cache: SQLiteCache) -> None:
        """Two separate buys, then one sell that spans both (FIFO) — exercises
        the inner while-loop's multi-buy-record consumption path."""
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal(), quantity=50, price=40.0)
        trader.execute_trade(_buy_signal(), quantity=50, price=60.0)
        trader.execute_trade(_sell_signal(), quantity=100, price=60.0)
        perf = trader.get_performance()
        assert perf["total_trades"] == 3.0
        # closed returns: (60-40)/40=0.5 for first 50 shares, (60-60)/60=0.0 for next 50
        assert perf["avg_return"] == pytest.approx(0.25)
        assert perf["win_rate"] == pytest.approx(0.5)

    def test_win_rate_and_avg_return_mixed_wins_and_losses(self, temp_cache: SQLiteCache) -> None:
        trader = PaperTrader(sqlite_cache=temp_cache)
        trader.execute_trade(_buy_signal("2330"), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal("2330"), quantity=100, price=60.0)  # win +0.2
        trader.execute_trade(_buy_signal("2317"), quantity=100, price=50.0)
        trader.execute_trade(_sell_signal("2317"), quantity=100, price=45.0)  # loss -0.1
        perf = trader.get_performance()
        assert perf["win_rate"] == pytest.approx(0.5)
        assert perf["total_trades"] == 4.0
