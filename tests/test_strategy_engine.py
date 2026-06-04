"""
Unit tests for strategy/engine.py

Tests StrategyEngine with database and indicator mocking.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from strategy.engine import StrategyEngine
from strategy.config import (
    StrategyEngineConfig,
    StrategyConfig,
    RiskConfig,
    StopLossConfig,
    TakeProfitConfig,
    CooldownConfig
)
from strategy.types import (
    DecisionType,
    PositionSizeMode,
    StopLossMode,
    TakeProfitMode,
    WeightsSnapshot,
    IndicatorSnapshot
)
from strategy.risk import RiskManager


# Fixtures

@pytest.fixture
def run_id():
    """Generate a test run ID"""
    return uuid4()


@pytest.fixture
def weights_id():
    """Generate a test weights set ID"""
    return uuid4()


@pytest.fixture
def strategy_config():
    """Create a test strategy engine configuration"""
    return StrategyEngineConfig(
        strategy=StrategyConfig(
            entry_threshold=0.6,
            exit_threshold=-0.3,
            confirmation_candles=2
        ),
        risk=RiskConfig(
            max_trades_per_day=5,
            max_exposure_percent=30.0,
            position_size_mode=PositionSizeMode.FIXED,
            fixed_size_usdt=1000.0
        ),
        stop_loss=StopLossConfig(
            mode=StopLossMode.ATR,
            atr_multiplier=2.0
        ),
        take_profit=TakeProfitConfig(
            mode=TakeProfitMode.ATR,
            atr_multiplier=3.0
        ),
        cooldown=CooldownConfig(
            after_trade_seconds=3600
        )
    )


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool"""
    return MagicMock()


@pytest.fixture
def mock_risk_manager(run_id, strategy_config, mock_db_pool):
    """Create a mock risk manager"""
    return RiskManager(
        run_id=run_id,
        risk_config=strategy_config.risk,
        cooldown_config=strategy_config.cooldown,
        db_pool=mock_db_pool
    )


@pytest.fixture
def strategy_engine(run_id, strategy_config, mock_db_pool, mock_risk_manager):
    """Create a StrategyEngine instance"""
    return StrategyEngine(
        config=strategy_config,
        run_id=run_id,
        db_pool=mock_db_pool,
        risk_manager=mock_risk_manager
    )


@pytest.fixture
def sample_weights(weights_id):
    """Create sample weights snapshot"""
    now = datetime.now(timezone.utc)
    return WeightsSnapshot(
        weights_set_id=weights_id,
        weights_set_name="Test Weights",
        weights={
            "ema": 0.15,
            "macd": 0.20,
            "rsi": 0.12,
            "stoch_rsi": 0.08,
            "bollinger": 0.10,
            "atr": 0.05,
            "obv": 0.15,
            "fear_greed": 0.10,
            "user_indicator": 0.05
        },
        timestamp=now
    )


@pytest.fixture
def sample_indicator_results():
    """Create sample indicator results"""
    # Mock IndicatorResult objects
    results = {}

    for indicator, signal in [
        ("ema", 0.45),
        ("macd", 0.65),
        ("rsi", 0.17),
        ("stoch_rsi", 0.24),
        ("bollinger", -0.15),
        ("atr", 0.0),
        ("obv", 0.35),
        ("fear_greed", 0.30),
        ("user_indicator", 0.80)
    ]:
        mock_result = MagicMock()
        mock_result.signal.value = signal
        mock_result.values = {"signal": signal, "value": 42000}  # Simplified
        results[indicator] = mock_result

    # Add ATR value for position sizing
    results["atr"].values = {"value": Decimal("500"), "signal": 0.0}

    return results


# --- StrategyEngine initialization tests ---

def test_strategy_engine_initialization(run_id, strategy_config, mock_db_pool):
    """Test StrategyEngine initialization"""
    engine = StrategyEngine(
        config=strategy_config,
        run_id=run_id,
        db_pool=mock_db_pool
    )

    assert engine.run_id == run_id
    assert engine.config == strategy_config
    assert engine.db_pool == mock_db_pool
    assert engine.risk_manager is not None
    assert engine._active_weights is None
    assert engine._confirmation_state is None


def test_strategy_engine_with_custom_risk_manager(run_id, strategy_config, mock_db_pool, mock_risk_manager):
    """Test StrategyEngine with custom risk manager"""
    engine = StrategyEngine(
        config=strategy_config,
        run_id=run_id,
        db_pool=mock_db_pool,
        risk_manager=mock_risk_manager
    )

    assert engine.risk_manager == mock_risk_manager


# --- load_active_weights tests ---

@pytest.mark.asyncio
async def test_load_active_weights_success(strategy_engine, mock_db_pool, weights_id):
    """Test loading active weights from database"""
    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock database row
    mock_row = {
        "id": weights_id,
        "name": "Test Weights",
        "weights": {"ema": 0.15, "macd": 0.20},
        "created_at": now
    }
    mock_conn.fetchrow.return_value = mock_row

    weights = await strategy_engine.load_active_weights()

    assert weights.weights_set_id == weights_id
    assert weights.weights_set_name == "Test Weights"
    assert weights.weights["ema"] == 0.15
    assert strategy_engine._active_weights == weights


@pytest.mark.asyncio
async def test_load_active_weights_not_found(strategy_engine, mock_db_pool):
    """Test loading active weights when none exist"""
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="No active weights set found"):
        await strategy_engine.load_active_weights()


# --- calculate_weighted_score tests ---

def test_calculate_weighted_score_success(strategy_engine, sample_weights):
    """Test weighted score calculation"""
    strategy_engine._active_weights = sample_weights

    signals = {
        "ema": 0.45,
        "macd": 0.65,
        "rsi": 0.17,
        "stoch_rsi": 0.24,
        "bollinger": -0.15,
        "atr": 0.0,
        "obv": 0.35,
        "fear_greed": 0.30,
        "user_indicator": 0.80
    }

    score = strategy_engine.calculate_weighted_score(signals)

    # Calculate expected: sum(signal_i * weight_i)
    expected = (
        0.45 * 0.15 +  # ema
        0.65 * 0.20 +  # macd
        0.17 * 0.12 +  # rsi
        0.24 * 0.08 +  # stoch_rsi
        -0.15 * 0.10 +  # bollinger
        0.0 * 0.05 +  # atr
        0.35 * 0.15 +  # obv
        0.30 * 0.10 +  # fear_greed
        0.80 * 0.05  # user_indicator
    )

    assert abs(score - expected) < 0.001  # Allow small floating point error


def test_calculate_weighted_score_custom_weights(strategy_engine):
    """Test weighted score with custom weights"""
    signals = {"ema": 0.5, "macd": 0.6}
    weights = {"ema": 0.4, "macd": 0.6}

    score = strategy_engine.calculate_weighted_score(signals, weights=weights)

    expected = 0.5 * 0.4 + 0.6 * 0.6
    assert abs(score - expected) < 0.001


def test_calculate_weighted_score_invalid_signal(strategy_engine, sample_weights):
    """Test weighted score with invalid signal value"""
    strategy_engine._active_weights = sample_weights

    signals = {"ema": 1.5}  # Invalid: > 1.0

    with pytest.raises(ValueError, match="Signal .* must be in \\[-1, 1\\]"):
        strategy_engine.calculate_weighted_score(signals)


def test_calculate_weighted_score_no_weights_loaded(strategy_engine):
    """Test weighted score without loading weights first"""
    signals = {"ema": 0.5}

    with pytest.raises(ValueError, match="Active weights not loaded"):
        strategy_engine.calculate_weighted_score(signals)


# --- _check_confirmation tests ---

@pytest.mark.asyncio
async def test_check_confirmation_first_signal(strategy_engine):
    """Test confirmation check for first signal"""
    now = datetime.now(timezone.utc)

    confirmed = await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )

    # First signal: count = 1, needs 2 for confirmation
    assert confirmed is False
    assert strategy_engine._confirmation_state is not None
    assert strategy_engine._confirmation_state.consecutive_candles == 1


@pytest.mark.asyncio
async def test_check_confirmation_second_signal_confirmed(strategy_engine):
    """Test confirmation on second consecutive signal"""
    now = datetime.now(timezone.utc)

    # First signal
    await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )

    # Second signal (should confirm)
    confirmed = await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.80,
        current_time=now
    )

    assert confirmed is True
    assert strategy_engine._confirmation_state.consecutive_candles == 2


@pytest.mark.asyncio
async def test_check_confirmation_reset_on_different_decision(strategy_engine):
    """Test confirmation resets when decision type changes"""
    now = datetime.now(timezone.utc)

    # First signal: ENTRY_LONG
    await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )

    # Second signal: EXIT (different decision type)
    confirmed = await strategy_engine._check_confirmation(
        decision_type=DecisionType.EXIT,
        weighted_score=-0.5,
        current_time=now
    )

    # Should reset count
    assert confirmed is False
    assert strategy_engine._confirmation_state.decision_type == DecisionType.EXIT
    assert strategy_engine._confirmation_state.consecutive_candles == 1


@pytest.mark.asyncio
async def test_check_confirmation_single_candle_requirement(strategy_engine):
    """Test confirmation with single candle requirement"""
    # Change config to require only 1 candle
    strategy_engine.config.strategy.confirmation_candles = 1
    now = datetime.now(timezone.utc)

    confirmed = await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )

    # Should confirm immediately
    assert confirmed is True


# --- _enhance_entry_decision tests ---

@pytest.mark.asyncio
async def test_enhance_entry_decision(strategy_engine, sample_indicator_results):
    """Test enhancing entry decision with position size and stops"""
    from strategy.types import TradingDecision, WeightsSnapshot, IndicatorSnapshot

    now = datetime.now(timezone.utc)
    weights_id = uuid4()

    weights_snapshot = WeightsSnapshot(
        weights_set_id=weights_id,
        weights_set_name="Test",
        weights={"ema": 0.15},
        timestamp=now
    )

    indicators_snapshot = IndicatorSnapshot(
        timestamp=now,
        symbol="BTCUSDT",
        candle_close=Decimal("42000"),
        indicators={"ema": {"signal": 0.75}}
    )

    decision = TradingDecision(
        decision_type=DecisionType.ENTRY_LONG,
        timestamp=now,
        symbol="BTCUSDT",
        weighted_score=0.75,
        weights_snapshot=weights_snapshot,
        indicators_snapshot=indicators_snapshot,
        decision_reason="Entry signal",
        entry_price=Decimal("42000"),
        position_size_usdt=Decimal("1000")
    )

    enhanced = await strategy_engine._enhance_entry_decision(
        decision=decision,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000"),
        indicator_results=sample_indicator_results
    )

    assert enhanced.position_size_usdt is not None
    assert enhanced.position_size_qty is not None
    assert enhanced.stop_loss_price is not None
    assert enhanced.take_profit_price is not None
    assert "SL:" in enhanced.decision_reason
    assert "TP:" in enhanced.decision_reason


# --- _log_decision tests ---

@pytest.mark.asyncio
async def test_log_decision(strategy_engine, mock_db_pool):
    """Test logging decision to database"""
    from strategy.types import TradingDecision, WeightsSnapshot, IndicatorSnapshot

    now = datetime.now(timezone.utc)
    weights_id = uuid4()
    signal_id = uuid4()

    weights_snapshot = WeightsSnapshot(
        weights_set_id=weights_id,
        weights_set_name="Test",
        weights={"ema": 0.15},
        timestamp=now
    )

    indicators_snapshot = IndicatorSnapshot(
        timestamp=now,
        symbol="BTCUSDT",
        candle_close=Decimal("42000"),
        indicators={"ema": {"signal": 0.75}}
    )

    decision = TradingDecision(
        decision_type=DecisionType.SKIP,
        timestamp=now,
        symbol="BTCUSDT",
        weighted_score=0.45,
        weights_snapshot=weights_snapshot,
        indicators_snapshot=indicators_snapshot,
        decision_reason="Score below threshold"
    )

    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.return_value = signal_id

    await strategy_engine._log_decision(decision)

    # Verify INSERT query was called
    mock_conn.fetchval.assert_called_once()


# --- update_position_state tests ---

def test_update_position_state(strategy_engine):
    """Test updating position state"""
    from strategy.types import PositionState

    now = datetime.now(timezone.utc)

    position = PositionState(
        is_open=True,
        symbol="BTCUSDT",
        entry_price=Decimal("42000"),
        quantity=Decimal("0.1"),
        entry_time=now
    )

    strategy_engine.update_position_state(position)

    assert strategy_engine._position_state == position
    assert strategy_engine._position_state.is_open is True


def test_get_position_state(strategy_engine):
    """Test getting position state"""
    state = strategy_engine.get_position_state()

    # Should have default closed position
    assert state.is_open is False


# --- reset_confirmation_state tests ---

def test_reset_confirmation_state(strategy_engine):
    """Test resetting confirmation state"""
    from strategy.types import ConfirmationState

    now = datetime.now(timezone.utc)

    # Set a confirmation state
    strategy_engine._confirmation_state = ConfirmationState(
        decision_type=DecisionType.ENTRY_LONG,
        consecutive_candles=1,
        first_seen_at=now,
        last_weighted_score=0.75
    )

    strategy_engine.reset_confirmation_state()

    assert strategy_engine._confirmation_state is None


# --- Integration test: make_decision ---

@pytest.mark.asyncio
async def test_make_decision_skip_below_threshold(
    strategy_engine,
    mock_db_pool,
    weights_id,
    sample_weights,
    sample_indicator_results
):
    """Test make_decision when score is below entry threshold"""
    now = datetime.now(timezone.utc)

    # Mock load_active_weights
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_row = {
        "id": weights_id,
        "name": "Test Weights",
        "weights": sample_weights.weights,
        "created_at": now
    }
    mock_conn.fetchrow.return_value = mock_row

    # Mock _log_decision
    signal_id = uuid4()
    mock_conn.fetchval.return_value = signal_id

    # Adjust signals to be below threshold
    for indicator in sample_indicator_results:
        sample_indicator_results[indicator].signal.value = 0.3  # Low score

    decision = await strategy_engine.make_decision(
        candles=[],
        indicator_results=sample_indicator_results,
        current_price=Decimal("42000"),
        current_time=now,
        total_capital=Decimal("10000"),
        symbol="BTCUSDT"
    )

    assert decision.decision_type == DecisionType.SKIP
    assert decision.weighted_score < 0.6  # Below entry threshold


@pytest.mark.asyncio
async def test_make_decision_entry_long_after_confirmation(
    strategy_engine,
    mock_db_pool,
    weights_id,
    sample_weights,
    sample_indicator_results,
    mock_risk_manager
):
    """Test make_decision for ENTRY_LONG after confirmation"""
    now = datetime.now(timezone.utc)

    # Mock load_active_weights
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_row = {
        "id": weights_id,
        "name": "Test Weights",
        "weights": sample_weights.weights,
        "created_at": now
    }
    mock_conn.fetchrow.return_value = mock_row

    # Mock _log_decision
    signal_id = uuid4()
    mock_conn.fetchval.return_value = signal_id

    # Mock risk manager to allow trade
    mock_risk_manager.can_open_new_trade = AsyncMock(return_value=(True, "OK"))

    # First decision (pending confirmation)
    decision1 = await strategy_engine.make_decision(
        candles=[],
        indicator_results=sample_indicator_results,
        current_price=Decimal("42000"),
        current_time=now,
        total_capital=Decimal("10000"),
        symbol="BTCUSDT"
    )

    assert decision1.decision_type == DecisionType.SKIP
    assert "pending confirmation" in decision1.decision_reason.lower()

    # Second decision (should confirm)
    decision2 = await strategy_engine.make_decision(
        candles=[],
        indicator_results=sample_indicator_results,
        current_price=Decimal("42000"),
        current_time=now,
        total_capital=Decimal("10000"),
        symbol="BTCUSDT"
    )

    assert decision2.decision_type == DecisionType.ENTRY_LONG
    assert decision2.entry_price is not None
    assert decision2.position_size_usdt is not None


@pytest.mark.asyncio
async def test_make_decision_entry_blocked_by_risk(
    strategy_engine,
    mock_db_pool,
    weights_id,
    sample_weights,
    sample_indicator_results,
    mock_risk_manager
):
    """Test make_decision when entry is blocked by risk management"""
    now = datetime.now(timezone.utc)

    # Mock load_active_weights
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_row = {
        "id": weights_id,
        "name": "Test Weights",
        "weights": sample_weights.weights,
        "created_at": now
    }
    mock_conn.fetchrow.return_value = mock_row
    mock_conn.fetchval.return_value = uuid4()

    # Mock risk manager to block trade
    mock_risk_manager.can_open_new_trade = AsyncMock(
        return_value=(False, "Daily quota reached")
    )

    # Confirm the signal first
    await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )
    await strategy_engine._check_confirmation(
        decision_type=DecisionType.ENTRY_LONG,
        weighted_score=0.75,
        current_time=now
    )

    decision = await strategy_engine.make_decision(
        candles=[],
        indicator_results=sample_indicator_results,
        current_price=Decimal("42000"),
        current_time=now,
        total_capital=Decimal("10000"),
        symbol="BTCUSDT"
    )

    assert decision.decision_type == DecisionType.SKIP
    assert "risk management" in decision.decision_reason.lower()
