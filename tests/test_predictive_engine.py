"""
Unit tests for PredictiveStrategyEngine decision making, fixed SL/TP and risk integration.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from strategy.config import (
    CooldownConfig,
    RiskConfig,
    StopLossConfig,
    StrategyConfig,
    StrategyEngineConfig,
    TakeProfitConfig,
    TradingEngineConfig,
)
from strategy.predictive_engine import PredictiveStrategyEngine
from strategy.types import DecisionType, PositionSizeMode, PositionState, StopLossMode, TakeProfitMode


@pytest.fixture
def mock_strategy_config() -> StrategyEngineConfig:
    """StrategyEngineConfig configured for predictive ML engine."""
    return StrategyEngineConfig(
        trading_engine=TradingEngineConfig(engine_type="predictive_model"),
        strategy=StrategyConfig(
            entry_threshold=0.845,
            exit_threshold=0.880,
            confirmation_candles=1,
            engine_type="predictive_model",
        ),
        risk=RiskConfig(
            max_trades_per_day=5,
            max_exposure_percent=30.0,
            position_size_mode=PositionSizeMode.FIXED,
            fixed_size_percent=10.0,
        ),
        stop_loss=StopLossConfig(
            mode=StopLossMode.FIXED,
            fixed_percent=7.9,
        ),
        take_profit=TakeProfitConfig(
            mode=TakeProfitMode.FIXED,
            fixed_percent=1.1,
        ),
        cooldown=CooldownConfig(
            after_trade_seconds=3600,
        ),
    )


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg database connection pool."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval.return_value = 1
    conn.fetchrow.return_value = None

    class MockAcquireContext:
        async def __aenter__(self):
            return conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    pool.acquire.return_value = MockAcquireContext()
    return pool


@pytest.fixture
def predictive_engine(mock_strategy_config, mock_db_pool):
    """PredictiveStrategyEngine with mocked models."""
    with patch("strategy.predictive_engine.ort.InferenceSession") as mock_ort, \
         patch("strategy.predictive_engine.xgb.Booster") as mock_xgb, \
         patch("strategy.predictive_engine._find_model_file") as mock_find:

        mock_find.side_effect = lambda fn: f"/mock/path/{fn}"

        # Mock ONNX Session: returns dummy 10-dim dense array
        session_instance = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "candles_sequence"
        session_instance.get_inputs.return_value = [mock_input]
        session_instance.run.return_value = [np.ones((1, 10), dtype=np.float32)]
        mock_ort.return_value = session_instance

        # Mock XGBoost Booster: default returns [hold=0.8, buy=0.1, sell=0.1]
        booster_instance = MagicMock()
        booster_instance.inplace_predict.return_value = np.array([[0.8, 0.1, 0.1]], dtype=np.float32)
        mock_xgb.return_value = booster_instance

        risk_mgr = MagicMock()
        risk_mgr.can_open_new_trade = AsyncMock(return_value=(True, "Allowed"))
        risk_mgr.risk_config = mock_strategy_config.risk
        risk_mgr.cooldown_config = mock_strategy_config.cooldown

        engine = PredictiveStrategyEngine(
            config=mock_strategy_config,
            run_id=42,
            db_pool=mock_db_pool,
            risk_manager=risk_mgr,
        )

        # Inject warmed up buffer
        engine.buffer = MagicMock()
        engine.buffer.is_warmed_up = True
        engine.buffer.candle_count = 60
        engine.buffer.add_candle.return_value = (True, np.ones((1, 60, 11), dtype=np.float32))
        engine.buffer.get_latest_sequence.return_value = np.ones((1, 60, 11), dtype=np.float32)

        return engine


@pytest.mark.asyncio
async def test_predictive_engine_entry_long(predictive_engine):
    """Verify entry long triggered when prob_buy >= entry_threshold (0.845)."""
    # Configure booster to return high buy probability: [hold=0.05, buy=0.90, sell=0.05]
    predictive_engine.xgb_booster.inplace_predict.return_value = np.array([[0.05, 0.90, 0.05]], dtype=np.float32)

    current_price = Decimal("50000.0")
    total_capital = Decimal("10000.0")
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    decision = await predictive_engine.make_decision(
        candles=[{"time": now, "close": 50000.0}],
        current_price=current_price,
        current_time=now,
        total_capital=total_capital,
        symbol="BTCUSDC",
    )

    assert decision.decision_type == DecisionType.ENTRY_LONG
    assert "prob_buy 0.9000 >= threshold 0.8450" in decision.decision_reason
    assert decision.stop_loss_price is not None
    assert decision.take_profit_price is not None

    # Verify fixed Stop-Loss = price * (1 - 0.079) = 46,050
    expected_sl = current_price * Decimal("0.921")
    assert decision.stop_loss_price == expected_sl

    # Verify fixed Take-Profit = price * (1 + 0.011) = 50,550
    expected_tp = current_price * Decimal("1.011")
    assert decision.take_profit_price == expected_tp


@pytest.mark.asyncio
async def test_predictive_engine_stop_loss_exit(predictive_engine):
    """Verify exit triggered when open position loss exceeds 7.9%."""
    predictive_engine.update_position_state(PositionState(
        is_open=True,
        symbol="BTCUSDC",
        entry_price=Decimal("50000.0"),
        quantity=Decimal("0.1"),
    ))

    # Price dropped by 8% to 46,000 (below 7.9% stop loss)
    current_price = Decimal("46000.0")
    now = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

    decision = await predictive_engine.make_decision(
        candles=[{"time": now, "close": 46000.0}],
        current_price=current_price,
        current_time=now,
        total_capital=Decimal("10000.0"),
        symbol="BTCUSDC",
    )

    assert decision.decision_type == DecisionType.EXIT
    assert "Stop-Loss: profit" in decision.decision_reason


@pytest.mark.asyncio
async def test_predictive_engine_take_profit_exit(predictive_engine):
    """Verify exit triggered when open position gain exceeds 1.1%."""
    predictive_engine.update_position_state(PositionState(
        is_open=True,
        symbol="BTCUSDC",
        entry_price=Decimal("50000.0"),
        quantity=Decimal("0.1"),
    ))

    # Price increased by 1.5% to 50,750 (above 1.1% take profit)
    current_price = Decimal("50750.0")
    now = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

    decision = await predictive_engine.make_decision(
        candles=[{"time": now, "close": 50750.0}],
        current_price=current_price,
        current_time=now,
        total_capital=Decimal("10000.0"),
        symbol="BTCUSDC",
    )

    assert decision.decision_type == DecisionType.EXIT
    assert "Take-Profit: profit" in decision.decision_reason


@pytest.mark.asyncio
async def test_predictive_engine_model_sell_signal_exit(predictive_engine):
    """Verify exit triggered when prob_sell >= exit_threshold (0.880)."""
    predictive_engine.update_position_state(PositionState(
        is_open=True,
        symbol="BTCUSDC",
        entry_price=Decimal("50000.0"),
        quantity=Decimal("0.1"),
    ))

    # Booster predicts strong sell probability: [0.05, 0.05, 0.90]
    predictive_engine.xgb_booster.inplace_predict.return_value = np.array([[0.05, 0.05, 0.90]], dtype=np.float32)

    # Price unchanged (neither SL nor TP hit)
    current_price = Decimal("50000.0")
    now = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

    decision = await predictive_engine.make_decision(
        candles=[{"time": now, "close": 50000.0}],
        current_price=current_price,
        current_time=now,
        total_capital=Decimal("10000.0"),
        symbol="BTCUSDC",
    )

    assert decision.decision_type == DecisionType.EXIT
    assert "Model Exit Signal: prob_sell 0.9000 >= threshold 0.8800" in decision.decision_reason
