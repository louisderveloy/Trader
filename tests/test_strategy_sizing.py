"""
Unit tests for strategy/sizing.py
"""

import pytest
from decimal import Decimal

from strategy.sizing import (
    calculate_position_size,
    calculate_position_quantity,
    _calculate_fixed_size,
    _calculate_confidence_size,
    _calculate_risk_atr_size
)
from strategy.types import PositionSizeMode
from strategy.config import RiskConfig


# --- calculate_position_size tests ---

def test_calculate_position_size_fixed():
    """Test position sizing with FIXED mode"""
    config = RiskConfig(
        position_size_mode=PositionSizeMode.FIXED,
        fixed_size_usdt=100.0
    )

    size = calculate_position_size(
        mode=PositionSizeMode.FIXED,
        config=config,
        weighted_score=0.75,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000")
    )

    assert size == Decimal("100.0")


def test_calculate_position_size_confidence():
    """Test position sizing with CONFIDENCE mode"""
    config = RiskConfig(
        position_size_mode=PositionSizeMode.CONFIDENCE,
        max_exposure_percent=30.0
    )

    # Score of 0.6 (entry threshold) should give minimum exposure (10%)
    # Score of 1.0 should give maximum exposure (30%)
    # Score of 0.8 should be midway: 20%
    size = calculate_position_size(
        mode=PositionSizeMode.CONFIDENCE,
        config=config,
        weighted_score=0.8,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000")
    )

    # Expected: 20% of 10000 = 2000
    assert size == Decimal("2000")


def test_calculate_position_size_risk_atr():
    """Test position sizing with RISK_ATR mode"""
    config = RiskConfig(
        position_size_mode=PositionSizeMode.RISK_ATR,
        atr_multiplier=2.0,
        capital_risk_percent=1.0
    )

    size = calculate_position_size(
        mode=PositionSizeMode.RISK_ATR,
        config=config,
        weighted_score=0.75,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000"),
        atr_value=Decimal("500")
    )

    # Risk amount: $10,000 × 1% = $100
    # Stop distance: $500 × 2.0 = $1,000
    # Stop distance %: $1,000 / $42,000 = 0.0238
    # Position size: $100 / 0.0238 = $4,200
    assert size == Decimal("4200")


def test_calculate_position_size_invalid_score():
    """Test position sizing with invalid weighted score"""
    config = RiskConfig()

    with pytest.raises(ValueError, match="weighted_score must be in \\[-1, 1\\]"):
        calculate_position_size(
            mode=PositionSizeMode.FIXED,
            config=config,
            weighted_score=1.5,  # Invalid
            current_price=Decimal("42000"),
            total_capital=Decimal("10000")
        )


def test_calculate_position_size_invalid_price():
    """Test position sizing with invalid price"""
    config = RiskConfig()

    with pytest.raises(ValueError, match="current_price must be > 0"):
        calculate_position_size(
            mode=PositionSizeMode.FIXED,
            config=config,
            weighted_score=0.75,
            current_price=Decimal("-100"),  # Invalid
            total_capital=Decimal("10000")
        )


def test_calculate_position_size_invalid_capital():
    """Test position sizing with invalid capital"""
    config = RiskConfig()

    with pytest.raises(ValueError, match="total_capital must be > 0"):
        calculate_position_size(
            mode=PositionSizeMode.FIXED,
            config=config,
            weighted_score=0.75,
            current_price=Decimal("42000"),
            total_capital=Decimal("0")  # Invalid
        )


def test_calculate_position_size_risk_atr_missing_atr():
    """Test RISK_ATR mode without ATR value"""
    config = RiskConfig(position_size_mode=PositionSizeMode.RISK_ATR)

    with pytest.raises(ValueError, match="atr_value is required"):
        calculate_position_size(
            mode=PositionSizeMode.RISK_ATR,
            config=config,
            weighted_score=0.75,
            current_price=Decimal("42000"),
            total_capital=Decimal("10000"),
            atr_value=None  # Missing
        )


# --- _calculate_confidence_size tests ---

def test_confidence_size_at_entry_threshold():
    """Test confidence sizing at entry threshold (minimum exposure)"""
    config = RiskConfig(max_exposure_percent=30.0)

    # Score = 0.6 (entry threshold) → min exposure 10%
    size = _calculate_confidence_size(
        config=config,
        weighted_score=0.6,
        total_capital=Decimal("10000")
    )

    assert size == Decimal("1000")  # 10% of capital


def test_confidence_size_at_maximum():
    """Test confidence sizing at maximum score"""
    config = RiskConfig(max_exposure_percent=30.0)

    # Score = 1.0 → max exposure 30%
    size = _calculate_confidence_size(
        config=config,
        weighted_score=1.0,
        total_capital=Decimal("10000")
    )

    assert size == Decimal("3000")  # 30% of capital


def test_confidence_size_midpoint():
    """Test confidence sizing at midpoint"""
    config = RiskConfig(max_exposure_percent=30.0)

    # Score = 0.8 (midpoint between 0.6 and 1.0) → 20% exposure
    size = _calculate_confidence_size(
        config=config,
        weighted_score=0.8,
        total_capital=Decimal("10000")
    )

    assert size == Decimal("2000")  # 20% of capital


# --- _calculate_risk_atr_size tests ---

def test_risk_atr_size_calculation():
    """Test risk-based ATR sizing calculation"""
    config = RiskConfig(
        atr_multiplier=2.0,
        capital_risk_percent=1.0
    )

    size = _calculate_risk_atr_size(
        config=config,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000"),
        atr_value=Decimal("500")
    )

    # Risk: $100, Stop: $1000, Result: $4200
    assert size == Decimal("4200")


def test_risk_atr_size_higher_risk():
    """Test risk-based ATR sizing with higher risk percentage"""
    config = RiskConfig(
        atr_multiplier=2.0,
        capital_risk_percent=2.0  # 2% risk
    )

    size = _calculate_risk_atr_size(
        config=config,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000"),
        atr_value=Decimal("500")
    )

    # Risk: $200, Stop: $1000, Result: $8400
    assert size == Decimal("8400")


def test_risk_atr_size_larger_atr():
    """Test risk-based ATR sizing with larger ATR (wider stops)"""
    config = RiskConfig(
        atr_multiplier=2.0,
        capital_risk_percent=1.0
    )

    size = _calculate_risk_atr_size(
        config=config,
        current_price=Decimal("42000"),
        total_capital=Decimal("10000"),
        atr_value=Decimal("1000")  # Larger ATR
    )

    # Risk: $100, Stop: $2000, Result: $2100
    assert size == Decimal("2100")


# --- calculate_position_quantity tests ---

def test_calculate_position_quantity():
    """Test position quantity calculation"""
    qty = calculate_position_quantity(
        position_size_usdt=Decimal("4200"),
        current_price=Decimal("42000")
    )

    assert qty == Decimal("0.10000")  # 5 decimal places


def test_calculate_position_quantity_precision():
    """Test position quantity with different precision"""
    qty = calculate_position_quantity(
        position_size_usdt=Decimal("4250.50"),
        current_price=Decimal("42000"),
        quantity_precision=8
    )

    assert qty == Decimal("0.10120238")  # 8 decimal places


def test_calculate_position_quantity_below_minimum():
    """Test position quantity below minimum"""
    with pytest.raises(ValueError, match="below minimum"):
        calculate_position_quantity(
            position_size_usdt=Decimal("0.0001"),  # Very small
            current_price=Decimal("42000"),
            min_quantity=Decimal("0.001")
        )


def test_calculate_position_quantity_invalid_size():
    """Test position quantity with invalid size"""
    with pytest.raises(ValueError, match="position_size_usdt must be > 0"):
        calculate_position_quantity(
            position_size_usdt=Decimal("-100"),
            current_price=Decimal("42000")
        )


def test_calculate_position_quantity_invalid_price():
    """Test position quantity with invalid price"""
    with pytest.raises(ValueError, match="current_price must be > 0"):
        calculate_position_quantity(
            position_size_usdt=Decimal("1000"),
            current_price=Decimal("0")
        )
