"""
Integration tests for the live/paper trading loop's stop-loss handling (issue #17).

These drive the real ``TradingBot._trading_iteration`` (with the StrategyEngine
wired in) against synthetic candles, mocking only the exchange and the
DB-writing leaf methods. They verify the behaviours the unit suite cannot:

1. An entry uses the engine-computed (ATR-based) stop-loss / take-profit, NOT the
   old hardcoded 2% / 4%.
2. When the price breaches the stored stop level, the loop exits with reason
   "stop_loss" (price-level monitoring takes precedence over signal exits).
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

from scripts.trading import TradingBot
from strategy.engine import StrategyEngine
from strategy.config import (
    StrategyEngineConfig, StrategyConfig, RiskConfig,
    StopLossConfig, TakeProfitConfig, CooldownConfig,
)
from strategy.types import (
    DecisionType, PositionSizeMode, StopLossMode, TakeProfitMode, WeightsSnapshot,
)


def _uptrend_candles(n=200, start=40000.0, step=20.0):
    """Synthetic clean uptrend so EMA/MACD/OBV read strongly bullish."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(n):
        close = start + i * step
        candles.append({
            "time": base + timedelta(minutes=15 * i),
            "open": close - 2,
            "high": close + 5,
            "low": close - 5,
            "close": close,
            "volume": 10.0,
        })
    return candles


def _make_config():
    # Weight everything on EMA so a clean uptrend reliably clears entry_threshold;
    # FIXED sizing keeps the position size deterministic. ATR-based SL/TP is the
    # point under test.
    return StrategyEngineConfig(
        strategy=StrategyConfig(entry_threshold=0.6, exit_threshold=-0.3, confirmation_candles=1),
        risk=RiskConfig(max_trades_per_day=5, max_exposure_percent=100.0,
                        position_size_mode=PositionSizeMode.FIXED, fixed_size_percent=10.0),
        stop_loss=StopLossConfig(mode=StopLossMode.ATR, atr_multiplier=2.0),
        take_profit=TakeProfitConfig(mode=TakeProfitMode.ATR, atr_multiplier=3.0),
        cooldown=CooldownConfig(after_trade_seconds=0),
    )


def _build_bot(config):
    bot = TradingBot(symbol="BTCUSDT", timeframe="15m", mode="paper",
                     testnet=True, initial_capital=Decimal("10000"), run_id=1)
    bot.db_pool = MagicMock()
    bot.config = config
    bot.config_id = None

    # Engine with preloaded weights (all on EMA) and DB leaf-methods stubbed out.
    engine = StrategyEngine(config=config, run_id=1, db_pool=MagicMock(), config_id=None)
    engine._active_weights = WeightsSnapshot(
        weights_set_id=None, weights_set_name="test",
        weights={"ema": 1.0, "macd": 0.0, "rsi": 0.0, "stoch_rsi": 0.0,
                 "bollinger": 0.0, "atr": 0.0, "obv": 0.0,
                 "fear_greed": 0.0, "user_indicator": 0.0},
        timestamp=datetime.now(timezone.utc),
    )
    engine.risk_manager.can_open_new_trade = AsyncMock(return_value=(True, "ok"))
    engine._log_score = AsyncMock()
    engine._log_decision = AsyncMock()
    bot.engine = engine

    # Exchange + DB-writing leaves mocked
    bot.exchange = MagicMock()
    bot.exchange.get_candles = AsyncMock(return_value=_uptrend_candles())
    bot._store_candles = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_entry_uses_engine_atr_stop_not_hardcoded():
    """A confirmed entry must carry the engine's ATR-based SL/TP, not 2%/4%."""
    config = _make_config()
    bot = _build_bot(config)
    bot._execute_entry = AsyncMock()

    await bot._trading_iteration()

    bot._execute_entry.assert_awaited_once()
    decision = bot._execute_entry.await_args.args[0]
    price = bot._execute_entry.await_args.args[1]

    assert decision.decision_type == DecisionType.ENTRY_LONG
    assert decision.stop_loss_price is not None and decision.take_profit_price is not None
    # Below entry, and NOT the legacy hardcoded 2% level (would be price*0.98).
    assert decision.stop_loss_price < price
    assert decision.stop_loss_price != (price * Decimal("0.98")).quantize(Decimal("0.01"))
    # ATR-based distance with multiplier 2 on a ~10-wide range is far tighter than 2%.
    assert decision.take_profit_price > price


@pytest.mark.asyncio
async def test_price_breach_triggers_stop_loss_exit():
    """When price <= stored stop_loss, the loop exits with reason 'stop_loss'."""
    config = _make_config()
    bot = _build_bot(config)
    bot._execute_exit = AsyncMock()

    candles = _uptrend_candles()
    current_price = Decimal(str(candles[-1]["close"]))
    # Open position whose stop sits just above current price → immediate breach.
    bot.position = {
        "trade_id": 1,
        "entry_price": current_price,
        "entry_time": datetime.now(timezone.utc),
        "quantity": Decimal("0.01"),
        "entry_commission": Decimal("0"),
        "stop_loss": current_price + Decimal("1"),
        "take_profit": current_price + Decimal("100000"),
        "order_id": "paper_x",
        "entry_order_id": 1,
        "entry_score": 0.7,
        "entry_signals": {},
    }

    await bot._trading_iteration()

    bot._execute_exit.assert_awaited_once()
    reason = bot._execute_exit.await_args.args[1]
    assert reason == "stop_loss"
