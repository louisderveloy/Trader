"""
Unit tests for strategy/stops.py
"""

import pytest
from decimal import Decimal

from strategy.stops import (
    calculate_stop_loss,
    calculate_take_profit,
    calculate_risk_reward_ratio,
    _calculate_atr_stop_loss,
    _calculate_fixed_stop_loss,
    _calculate_atr_take_profit,
    _calculate_fixed_take_profit
)
from strategy.types import StopLossMode, TakeProfitMode
from strategy.config import StopLossConfig, TakeProfitConfig


# --- calculate_stop_loss tests ---

def test_calculate_stop_loss_atr():
    """Test ATR-based stop-loss calculation"""
    config = StopLossConfig(
        mode=StopLossMode.ATR,
        atr_multiplier=2.0
    )

    sl = calculate_stop_loss(
        mode=StopLossMode.ATR,
        config=config,
        entry_price=Decimal("42000"),
        atr_value=Decimal("500")
    )

    # SL = 42000 - (500 × 2.0) = 41000
    assert sl == Decimal("41000.00")


def test_calculate_stop_loss_fixed():
    """Test fixed percentage stop-loss calculation"""
    config = StopLossConfig(
        mode=StopLossMode.FIXED,
        fixed_percent=2.0
    )

    sl = calculate_stop_loss(
        mode=StopLossMode.FIXED,
        config=config,
        entry_price=Decimal("42000")
    )

    # SL = 42000 × (1 - 0.02) = 41160
    assert sl == Decimal("41160.00")


def test_calculate_stop_loss_atr_missing_atr():
    """Test ATR mode without ATR value"""
    config = StopLossConfig(mode=StopLossMode.ATR)

    with pytest.raises(ValueError, match="atr_value is required"):
        calculate_stop_loss(
            mode=StopLossMode.ATR,
            config=config,
            entry_price=Decimal("42000"),
            atr_value=None
        )


def test_calculate_stop_loss_invalid_entry_price():
    """Test stop-loss with invalid entry price"""
    config = StopLossConfig(mode=StopLossMode.FIXED)

    with pytest.raises(ValueError, match="entry_price must be > 0"):
        calculate_stop_loss(
            mode=StopLossMode.FIXED,
            config=config,
            entry_price=Decimal("-100")
        )


def test_calculate_stop_loss_invalid_atr():
    """Test stop-loss with invalid ATR value"""
    config = StopLossConfig(mode=StopLossMode.ATR)

    with pytest.raises(ValueError, match="atr_value must be > 0"):
        calculate_stop_loss(
            mode=StopLossMode.ATR,
            config=config,
            entry_price=Decimal("42000"),
            atr_value=Decimal("-50")
        )


def test_calculate_stop_loss_above_entry():
    """Test that stop-loss above entry raises error"""
    config = StopLossConfig(
        mode=StopLossMode.ATR,
        atr_multiplier=2.0  # Valid value initially
    )
    # Bypass config validation by setting after initialization
    object.__setattr__(config, 'atr_multiplier', -1.0)  # This would put SL above entry

    with pytest.raises(ValueError, match="Stop-loss must be below entry"):
        calculate_stop_loss(
            mode=StopLossMode.ATR,
            config=config,
            entry_price=Decimal("42000"),
            atr_value=Decimal("500")
        )


# --- calculate_take_profit tests ---

def test_calculate_take_profit_atr():
    """Test ATR-based take-profit calculation"""
    config = TakeProfitConfig(
        mode=TakeProfitMode.ATR,
        atr_multiplier=3.0
    )

    tp = calculate_take_profit(
        mode=TakeProfitMode.ATR,
        config=config,
        entry_price=Decimal("42000"),
        atr_value=Decimal("500")
    )

    # TP = 42000 + (500 × 3.0) = 43500
    assert tp == Decimal("43500.00")


def test_calculate_take_profit_fixed():
    """Test fixed percentage take-profit calculation"""
    config = TakeProfitConfig(
        mode=TakeProfitMode.FIXED,
        fixed_percent=4.0
    )

    tp = calculate_take_profit(
        mode=TakeProfitMode.FIXED,
        config=config,
        entry_price=Decimal("42000")
    )

    # TP = 42000 × (1 + 0.04) = 43680
    assert tp == Decimal("43680.00")


def test_calculate_take_profit_atr_missing_atr():
    """Test ATR mode without ATR value"""
    config = TakeProfitConfig(mode=TakeProfitMode.ATR)

    with pytest.raises(ValueError, match="atr_value is required"):
        calculate_take_profit(
            mode=TakeProfitMode.ATR,
            config=config,
            entry_price=Decimal("42000"),
            atr_value=None
        )


def test_calculate_take_profit_invalid_entry_price():
    """Test take-profit with invalid entry price"""
    config = TakeProfitConfig(mode=TakeProfitMode.FIXED)

    with pytest.raises(ValueError, match="entry_price must be > 0"):
        calculate_take_profit(
            mode=TakeProfitMode.FIXED,
            config=config,
            entry_price=Decimal("0")
        )


def test_calculate_take_profit_below_entry():
    """Test that take-profit below entry raises error"""
    config = TakeProfitConfig(
        mode=TakeProfitMode.ATR,
        atr_multiplier=3.0  # Valid value initially
    )
    # Bypass config validation by setting after initialization
    object.__setattr__(config, 'atr_multiplier', -1.0)  # This would put TP below entry

    with pytest.raises(ValueError, match="Take-profit must be above entry"):
        calculate_take_profit(
            mode=TakeProfitMode.ATR,
            config=config,
            entry_price=Decimal("42000"),
            atr_value=Decimal("500")
        )


# --- ATR stop-loss tests ---

def test_atr_stop_loss_calculation():
    """Test ATR stop-loss calculation"""
    sl = _calculate_atr_stop_loss(
        entry_price=Decimal("42000"),
        atr_value=Decimal("500"),
        atr_multiplier=2.0
    )

    assert sl == Decimal("41000")  # 42000 - 1000


def test_atr_stop_loss_larger_multiplier():
    """Test ATR stop-loss with larger multiplier"""
    sl = _calculate_atr_stop_loss(
        entry_price=Decimal("42000"),
        atr_value=Decimal("500"),
        atr_multiplier=3.0
    )

    assert sl == Decimal("40500")  # 42000 - 1500


# --- Fixed stop-loss tests ---

def test_fixed_stop_loss_calculation():
    """Test fixed percentage stop-loss calculation"""
    sl = _calculate_fixed_stop_loss(
        entry_price=Decimal("42000"),
        fixed_percent=2.0
    )

    assert sl == Decimal("41160")  # 42000 × 0.98


def test_fixed_stop_loss_larger_percent():
    """Test fixed stop-loss with larger percentage"""
    sl = _calculate_fixed_stop_loss(
        entry_price=Decimal("42000"),
        fixed_percent=5.0
    )

    assert sl == Decimal("39900")  # 42000 × 0.95


# --- ATR take-profit tests ---

def test_atr_take_profit_calculation():
    """Test ATR take-profit calculation"""
    tp = _calculate_atr_take_profit(
        entry_price=Decimal("42000"),
        atr_value=Decimal("500"),
        atr_multiplier=3.0
    )

    assert tp == Decimal("43500")  # 42000 + 1500


def test_atr_take_profit_smaller_multiplier():
    """Test ATR take-profit with smaller multiplier"""
    tp = _calculate_atr_take_profit(
        entry_price=Decimal("42000"),
        atr_value=Decimal("500"),
        atr_multiplier=2.0
    )

    assert tp == Decimal("43000")  # 42000 + 1000


# --- Fixed take-profit tests ---

def test_fixed_take_profit_calculation():
    """Test fixed percentage take-profit calculation"""
    tp = _calculate_fixed_take_profit(
        entry_price=Decimal("42000"),
        fixed_percent=4.0
    )

    assert tp == Decimal("43680")  # 42000 × 1.04


def test_fixed_take_profit_larger_percent():
    """Test fixed take-profit with larger percentage"""
    tp = _calculate_fixed_take_profit(
        entry_price=Decimal("42000"),
        fixed_percent=10.0
    )

    assert tp == Decimal("46200")  # 42000 × 1.10


# --- Risk/reward ratio tests ---

def test_calculate_risk_reward_ratio():
    """Test risk/reward ratio calculation"""
    ratio = calculate_risk_reward_ratio(
        entry_price=Decimal("42000"),
        stop_loss_price=Decimal("41000"),  # Risk: $1000
        take_profit_price=Decimal("43500")  # Reward: $1500
    )

    assert ratio == Decimal("1.5")  # 1.5:1 reward:risk


def test_calculate_risk_reward_ratio_1_to_1():
    """Test risk/reward ratio of 1:1"""
    ratio = calculate_risk_reward_ratio(
        entry_price=Decimal("42000"),
        stop_loss_price=Decimal("41000"),  # Risk: $1000
        take_profit_price=Decimal("43000")  # Reward: $1000
    )

    assert ratio == Decimal("1")  # 1:1


def test_calculate_risk_reward_ratio_3_to_1():
    """Test risk/reward ratio of 3:1"""
    ratio = calculate_risk_reward_ratio(
        entry_price=Decimal("42000"),
        stop_loss_price=Decimal("41000"),  # Risk: $1000
        take_profit_price=Decimal("45000")  # Reward: $3000
    )

    assert ratio == Decimal("3")  # 3:1


def test_calculate_risk_reward_ratio_invalid_entry():
    """Test risk/reward with invalid entry price"""
    with pytest.raises(ValueError, match="entry_price must be > 0"):
        calculate_risk_reward_ratio(
            entry_price=Decimal("0"),
            stop_loss_price=Decimal("41000"),
            take_profit_price=Decimal("43500")
        )


def test_calculate_risk_reward_ratio_sl_above_entry():
    """Test risk/reward with stop-loss above entry"""
    with pytest.raises(ValueError, match="stop_loss_price .* must be < entry_price"):
        calculate_risk_reward_ratio(
            entry_price=Decimal("42000"),
            stop_loss_price=Decimal("43000"),  # Above entry
            take_profit_price=Decimal("45000")
        )


def test_calculate_risk_reward_ratio_tp_below_entry():
    """Test risk/reward with take-profit below entry"""
    with pytest.raises(ValueError, match="take_profit_price .* must be > entry_price"):
        calculate_risk_reward_ratio(
            entry_price=Decimal("42000"),
            stop_loss_price=Decimal("41000"),
            take_profit_price=Decimal("40000")  # Below entry
        )
