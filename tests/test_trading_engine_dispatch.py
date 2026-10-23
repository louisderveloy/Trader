"""
Unit tests for trading engine dispatching, dynamic switching and DB persistence.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from scripts.trading import TradingBot
from strategy.config import (
    CooldownConfig,
    RiskConfig,
    StopLossConfig,
    StrategyConfig,
    StrategyEngineConfig,
    TakeProfitConfig,
    TradingEngineConfig,
)
from strategy.engine import StrategyEngine
from strategy.predictive_engine import PredictiveStrategyEngine


@pytest.fixture
def base_indicators_config() -> StrategyEngineConfig:
    return StrategyEngineConfig(
        trading_engine=TradingEngineConfig(engine_type="indicators"),
        strategy=StrategyConfig(entry_threshold=0.6, exit_threshold=-0.3, confirmation_candles=2),
        risk=RiskConfig(),
        stop_loss=StopLossConfig(),
        take_profit=TakeProfitConfig(),
        cooldown=CooldownConfig(),
    )


@pytest.fixture
def base_predictive_config() -> StrategyEngineConfig:
    return StrategyEngineConfig(
        trading_engine=TradingEngineConfig(engine_type="predictive_model"),
        strategy=StrategyConfig(
            entry_threshold=0.845,
            exit_threshold=0.880,
            confirmation_candles=1,
            engine_type="predictive_model",
        ),
        risk=RiskConfig(),
        stop_loss=StopLossConfig(),
        take_profit=TakeProfitConfig(),
        cooldown=CooldownConfig(),
    )


@pytest.fixture
def mock_bot(base_indicators_config) -> TradingBot:
    with patch("scripts.trading.BinanceExchange"):
        bot = TradingBot(
            symbol="BTCUSDT",
            timeframe="15m",
            mode="paper",
            testnet=True,
            initial_capital=Decimal("1000"),
            run_id=10,
        )
        bot.db_pool = MagicMock()
        bot.config = base_indicators_config
        return bot


def test_init_engine_indicators_by_default(mock_bot):
    """Test that _init_engine creates StrategyEngine when engine_type is indicators."""
    mock_bot._init_engine()
    assert isinstance(mock_bot.engine, StrategyEngine)
    assert not mock_bot._is_predictive_engine()


@patch("strategy.predictive_engine.ort.InferenceSession")
@patch("strategy.predictive_engine.xgb.Booster")
@patch("strategy.predictive_engine._find_model_file")
def test_init_engine_predictive(mock_find, mock_xgb, mock_ort, mock_bot, base_predictive_config):
    """Test that _init_engine creates PredictiveStrategyEngine when engine_type is predictive_model."""
    mock_find.side_effect = lambda fn: f"/mock/{fn}"
    mock_bot.config = base_predictive_config

    mock_bot._init_engine()
    assert isinstance(mock_bot.engine, PredictiveStrategyEngine)
    assert mock_bot._is_predictive_engine()


@pytest.mark.asyncio
@patch("strategy.predictive_engine.ort.InferenceSession")
@patch("strategy.predictive_engine.xgb.Booster")
@patch("strategy.predictive_engine._find_model_file")
async def test_reload_config_switches_engine(
    mock_find, mock_xgb, mock_ort, mock_bot, base_indicators_config, base_predictive_config
):
    """Test hot-reloading switches engine instance when engine_type changes."""
    mock_find.side_effect = lambda fn: f"/mock/{fn}"
    mock_bot.config = base_indicators_config
    mock_bot._init_engine()
    assert isinstance(mock_bot.engine, StrategyEngine)

    # Mock DB returning new predictive config
    with patch("strategy.config.StrategyEngineConfig.from_db", new_callable=AsyncMock) as mock_from_db:
        mock_from_db.return_value = (base_predictive_config, "new-uuid")
        await mock_bot._reload_config()

        assert isinstance(mock_bot.engine, PredictiveStrategyEngine)
        assert mock_bot._is_predictive_engine()
        assert mock_bot.config.trading_engine.engine_type == "predictive_model"


@pytest.mark.asyncio
async def test_trading_iteration_persists_candles(mock_bot):
    """Test that every trading iteration calls _store_candles to persist data to DB."""
    mock_bot._init_engine()

    dummy_candles = [
        {"time": "2026-01-01T00:00:00Z", "open": 50000, "high": 50100, "low": 49900, "close": 50050, "volume": 100}
        for _ in range(60)
    ]
    mock_bot.exchange = MagicMock()
    mock_bot.exchange.get_candles = AsyncMock(return_value=dummy_candles)
    mock_bot._store_candles = AsyncMock()
    mock_bot._check_pending_order = AsyncMock()
    mock_bot._get_available_capital = AsyncMock(return_value=Decimal("1000"))

    # Mock make_decision
    mock_decision = MagicMock()
    mock_decision.weighted_score = 0.1
    mock_decision.decision_type = MagicMock()
    mock_decision.decision_type.value = "skip"
    mock_decision.decision_reason = "Test"
    mock_bot.engine.make_decision = AsyncMock(return_value=mock_decision)

    await mock_bot._trading_iteration()

    # Verify _store_candles was called with the fetched candles
    mock_bot._store_candles.assert_awaited_once_with(dummy_candles)
