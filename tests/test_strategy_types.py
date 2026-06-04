"""
Unit tests for strategy/types.py
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

from strategy.types import (
    DecisionType,
    PositionSizeMode,
    StopLossMode,
    TakeProfitMode,
    WeightsSnapshot,
    IndicatorSnapshot,
    TradingDecision,
    ConfirmationState,
    PositionState,
    RiskState
)


# --- Enum tests ---

def test_decision_type_values():
    """Test DecisionType enum values"""
    assert DecisionType.ENTRY_LONG.value == "entry_long"
    assert DecisionType.EXIT.value == "exit"
    assert DecisionType.SKIP.value == "skip"


def test_position_size_mode_values():
    """Test PositionSizeMode enum values"""
    assert PositionSizeMode.FIXED.value == "fixed"
    assert PositionSizeMode.CONFIDENCE.value == "confidence"
    assert PositionSizeMode.RISK_ATR.value == "risk_atr"


def test_stop_loss_mode_values():
    """Test StopLossMode enum values"""
    assert StopLossMode.ATR.value == "atr"
    assert StopLossMode.FIXED.value == "fixed"


def test_take_profit_mode_values():
    """Test TakeProfitMode enum values"""
    assert TakeProfitMode.ATR.value == "atr"
    assert TakeProfitMode.FIXED.value == "fixed"


# --- WeightsSnapshot tests ---

def test_weights_snapshot_creation():
    """Test WeightsSnapshot creation"""
    weights_id = uuid4()
    now = datetime.now(timezone.utc)

    snapshot = WeightsSnapshot(
        weights_set_id=weights_id,
        weights_set_name="Test Weights",
        weights={"ema": 0.15, "macd": 0.20},
        timestamp=now
    )

    assert snapshot.weights_set_id == weights_id
    assert snapshot.weights_set_name == "Test Weights"
    assert snapshot.weights["ema"] == 0.15
    assert snapshot.timestamp == now


def test_weights_snapshot_to_dict():
    """Test WeightsSnapshot.to_dict() conversion"""
    weights_id = uuid4()
    now = datetime.now(timezone.utc)

    snapshot = WeightsSnapshot(
        weights_set_id=weights_id,
        weights_set_name="Test",
        weights={"ema": 0.15},
        timestamp=now
    )

    result = snapshot.to_dict()

    assert result["weights_set_id"] == str(weights_id)
    assert result["weights_set_name"] == "Test"
    assert result["weights"]["ema"] == 0.15
    assert result["timestamp"] == now.isoformat()


# --- IndicatorSnapshot tests ---

def test_indicator_snapshot_creation():
    """Test IndicatorSnapshot creation"""
    now = datetime.now(timezone.utc)

    snapshot = IndicatorSnapshot(
        timestamp=now,
        symbol="BTCUSDT",
        candle_close=Decimal("42000"),
        indicators={"ema": {"ema_50": 41000, "signal": 0.45}}
    )

    assert snapshot.timestamp == now
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.candle_close == Decimal("42000")
    assert snapshot.indicators["ema"]["signal"] == 0.45


def test_indicator_snapshot_to_dict():
    """Test IndicatorSnapshot.to_dict() conversion"""
    now = datetime.now(timezone.utc)

    snapshot = IndicatorSnapshot(
        timestamp=now,
        symbol="BTCUSDT",
        candle_close=Decimal("42000"),
        indicators={"ema": {"signal": 0.45}}
    )

    result = snapshot.to_dict()

    assert result["timestamp"] == now.isoformat()
    assert result["symbol"] == "BTCUSDT"
    assert result["candle_close"] == 42000.0  # Converted to float
    assert result["indicators"]["ema"]["signal"] == 0.45


# --- TradingDecision tests ---

def test_trading_decision_skip():
    """Test TradingDecision for SKIP"""
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
        indicators={"ema": {"signal": 0.45}}
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

    assert decision.decision_type == DecisionType.SKIP
    assert decision.weighted_score == 0.45
    assert decision.entry_price is None


def test_trading_decision_entry_long():
    """Test TradingDecision for ENTRY_LONG"""
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
        decision_reason="Entry signal confirmed",
        entry_price=Decimal("42000"),
        position_size_usdt=Decimal("1000"),
        position_size_qty=Decimal("0.02381"),
        stop_loss_price=Decimal("41000"),
        take_profit_price=Decimal("43500")
    )

    assert decision.decision_type == DecisionType.ENTRY_LONG
    assert decision.entry_price == Decimal("42000")
    assert decision.position_size_usdt == Decimal("1000")
    assert decision.stop_loss_price == Decimal("41000")


def test_trading_decision_invalid_score():
    """Test TradingDecision with invalid weighted score"""
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
        indicators={"ema": {"signal": 0.45}}
    )

    with pytest.raises(ValueError, match="Weighted score must be in \\[-1, 1\\]"):
        TradingDecision(
            decision_type=DecisionType.SKIP,
            timestamp=now,
            symbol="BTCUSDT",
            weighted_score=1.5,  # Invalid
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            decision_reason="Test"
        )


def test_trading_decision_entry_missing_price():
    """Test TradingDecision ENTRY_LONG missing entry_price"""
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

    with pytest.raises(ValueError, match="entry_price is required"):
        TradingDecision(
            decision_type=DecisionType.ENTRY_LONG,
            timestamp=now,
            symbol="BTCUSDT",
            weighted_score=0.75,
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            decision_reason="Entry signal confirmed"
            # Missing entry_price
        )


# --- ConfirmationState tests ---

def test_confirmation_state_creation():
    """Test ConfirmationState creation"""
    now = datetime.now(timezone.utc)

    state = ConfirmationState(
        decision_type=DecisionType.ENTRY_LONG,
        consecutive_candles=2,
        first_seen_at=now,
        last_weighted_score=0.75
    )

    assert state.decision_type == DecisionType.ENTRY_LONG
    assert state.consecutive_candles == 2
    assert state.last_weighted_score == 0.75


def test_confirmation_state_is_confirmed():
    """Test ConfirmationState.is_confirmed()"""
    now = datetime.now(timezone.utc)

    state = ConfirmationState(
        decision_type=DecisionType.ENTRY_LONG,
        consecutive_candles=2,
        first_seen_at=now,
        last_weighted_score=0.75
    )

    assert state.is_confirmed(2) is True
    assert state.is_confirmed(3) is False


# --- PositionState tests ---

def test_position_state_closed():
    """Test PositionState when closed"""
    state = PositionState(is_open=False)

    assert state.is_open is False
    assert state.symbol is None
    assert state.exposure_usdt == Decimal("0")


def test_position_state_open():
    """Test PositionState when open"""
    now = datetime.now(timezone.utc)

    state = PositionState(
        is_open=True,
        symbol="BTCUSDT",
        entry_price=Decimal("42000"),
        quantity=Decimal("0.1"),
        entry_time=now,
        stop_loss_price=Decimal("41000"),
        take_profit_price=Decimal("43500")
    )

    assert state.is_open is True
    assert state.symbol == "BTCUSDT"
    assert state.exposure_usdt == Decimal("4200")  # 42000 * 0.1


# --- RiskState tests ---

def test_risk_state_creation():
    """Test RiskState creation"""
    now = datetime.now(timezone.utc)

    state = RiskState(
        trades_today=3,
        last_trade_closed_at=now,
        current_exposure_usdt=Decimal("2000")
    )

    assert state.trades_today == 3
    assert state.last_trade_closed_at == now
    assert state.current_exposure_usdt == Decimal("2000")


def test_risk_state_is_in_cooldown():
    """Test RiskState.is_in_cooldown()"""
    now = datetime.now(timezone.utc)
    last_trade = now - timedelta(seconds=1800)  # 30 minutes ago

    state = RiskState(
        trades_today=2,
        last_trade_closed_at=last_trade,
        current_exposure_usdt=Decimal("1000")
    )

    # Cooldown is 3600 seconds (1 hour), so should still be in cooldown
    assert state.is_in_cooldown(3600, now) is True

    # With cooldown of 1800 seconds (30 min), should not be in cooldown
    assert state.is_in_cooldown(1800, now) is False


def test_risk_state_can_open_new_trade_quota_exceeded():
    """Test RiskState.can_open_new_trade() when quota exceeded"""
    now = datetime.now(timezone.utc)

    state = RiskState(
        trades_today=5,  # At max
        last_trade_closed_at=now - timedelta(hours=2),
        current_exposure_usdt=Decimal("1000")
    )

    can_open, reason = state.can_open_new_trade(
        max_trades_per_day=5,
        max_exposure_percent=30.0,
        total_capital=Decimal("10000"),
        new_position_size=Decimal("1000"),
        cooldown_seconds=3600,
        current_time=now
    )

    assert can_open is False
    assert "quota" in reason.lower()


def test_risk_state_can_open_new_trade_in_cooldown():
    """Test RiskState.can_open_new_trade() when in cooldown"""
    now = datetime.now(timezone.utc)
    last_trade = now - timedelta(minutes=30)  # 30 min ago

    state = RiskState(
        trades_today=2,
        last_trade_closed_at=last_trade,
        current_exposure_usdt=Decimal("1000")
    )

    can_open, reason = state.can_open_new_trade(
        max_trades_per_day=5,
        max_exposure_percent=30.0,
        total_capital=Decimal("10000"),
        new_position_size=Decimal("1000"),
        cooldown_seconds=3600,  # 1 hour cooldown
        current_time=now
    )

    assert can_open is False
    assert "cooldown" in reason.lower()


def test_risk_state_can_open_new_trade_exposure_exceeded():
    """Test RiskState.can_open_new_trade() when exposure limit exceeded"""
    now = datetime.now(timezone.utc)

    state = RiskState(
        trades_today=2,
        last_trade_closed_at=now - timedelta(hours=2),
        current_exposure_usdt=Decimal("2000")
    )

    can_open, reason = state.can_open_new_trade(
        max_trades_per_day=5,
        max_exposure_percent=30.0,  # Max 30% = $3000
        total_capital=Decimal("10000"),
        new_position_size=Decimal("1500"),  # Would make total $3500
        cooldown_seconds=3600,
        current_time=now
    )

    assert can_open is False
    assert "exposure" in reason.lower()


def test_risk_state_can_open_new_trade_ok():
    """Test RiskState.can_open_new_trade() when all checks pass"""
    now = datetime.now(timezone.utc)

    state = RiskState(
        trades_today=2,
        last_trade_closed_at=now - timedelta(hours=2),
        current_exposure_usdt=Decimal("1000")
    )

    can_open, reason = state.can_open_new_trade(
        max_trades_per_day=5,
        max_exposure_percent=30.0,  # Max $3000
        total_capital=Decimal("10000"),
        new_position_size=Decimal("1000"),  # Total would be $2000
        cooldown_seconds=3600,
        current_time=now
    )

    assert can_open is True
    assert reason == "OK"
