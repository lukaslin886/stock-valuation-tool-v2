# Feature: stock-valuation-optimization, Property 16: Trade signal queue roundtrip
"""訊號佇列往返屬性測試。

驗證對任意有效的 TradeSignal 實例，寫入 SQLite 訊號佇列後再讀取回來
SHALL 產生與原始訊號欄位值相等的物件（stock_code, signal_type,
confidence, trigger_description, suggested_price_low,
suggested_price_high match）。

**Validates: Requirements 13.3**
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.models.trade import SignalType, TradeSignal
from app.infra.cache.sqlite_cache import SQLiteCache
from app.services.trade_engine import TradeSignalEngine

# --- Hypothesis Strategies ---

# 非空文字策略（避免 NULL 字元）
non_empty_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# 股票代碼策略
stock_code_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() != "")

# 訊號類型策略
signal_type_strategy = st.sampled_from(
    [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
)

# 固定格式 datetime 策略（精度限制在秒，符合 SQLite 儲存格式 %Y-%m-%d %H:%M:%S）
from datetime import datetime

datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2030, 12, 31),
).map(lambda dt: dt.replace(microsecond=0))


@st.composite
def trade_signal_strategy(draw: st.DrawFn) -> TradeSignal:
    """產生有效的 TradeSignal 實例。

    約束：
    - stock_code 非空
    - confidence in [0, 100]
    - suggested_price_low > 0
    - suggested_price_high >= suggested_price_low
    - generated_at 精度為秒（配合 SQLite 儲存格式）
    """
    stock_code = draw(stock_code_strategy)
    signal_type = draw(signal_type_strategy)
    confidence = draw(st.integers(min_value=0, max_value=100))
    trigger_description = draw(non_empty_text)
    suggested_price_low = draw(
        st.floats(
            min_value=0.01,
            max_value=50000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    suggested_price_high = draw(
        st.floats(
            min_value=suggested_price_low,
            max_value=max(suggested_price_low * 2, suggested_price_low + 1000.0),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    generated_at = draw(datetime_strategy)

    return TradeSignal(
        stock_code=stock_code,
        signal_type=signal_type,
        confidence=confidence,
        trigger_description=trigger_description,
        suggested_price_low=suggested_price_low,
        suggested_price_high=suggested_price_high,
        generated_at=generated_at,
    )


# --- Property Tests ---


@pytest.mark.property
class TestSignalQueueRoundtrip:
    """Property 16: 交易訊號佇列往返特性。

    For any 有效的 TradeSignal 實例，寫入 SQLite 訊號佇列後再讀取回來
    SHALL 產生與原始訊號欄位值相等的物件。

    **Validates: Requirements 13.3**
    """

    @given(signal=trade_signal_strategy())
    @settings(max_examples=200, deadline=30000)
    def test_signal_roundtrip_via_engine(self, signal: TradeSignal) -> None:
        """TradeSignal 經 TradeSignalEngine emit 後 get_pending_signals 讀回欄位相等。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "test_signals.db")
            cache = SQLiteCache(db_path=db_path)
            try:
                engine = TradeSignalEngine(sqlite_cache=cache)

                # 寫入訊號
                signal_id = engine.emit_signal(signal)
                assert signal_id > 0

                # 讀取回來
                pending = engine.get_pending_signals(stock_code=signal.stock_code)
                assert len(pending) >= 1

                # 找到剛寫入的訊號（以 stock_code 篩選後取最新）
                restored = pending[0]

                # 驗證欄位值相等
                assert restored.stock_code == signal.stock_code
                assert restored.signal_type == signal.signal_type
                assert restored.confidence == signal.confidence
                assert restored.trigger_description == signal.trigger_description
                assert abs(restored.suggested_price_low - signal.suggested_price_low) < 1e-6
                assert abs(restored.suggested_price_high - signal.suggested_price_high) < 1e-6
                assert restored.generated_at == signal.generated_at
            finally:
                cache.close()
