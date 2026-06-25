"""
Position sizing calculations.

This module implements three position sizing modes:
1. Fixed: A fixed percentage of total capital per trade
2. Confidence: Size proportional to weighted score
3. Risk-based ATR: Size based on ATR and % capital to risk
"""

import logging
import json
from decimal import Decimal
from typing import Optional

from .types import PositionSizeMode
from .config import RiskConfig

# Structured logging
logger = logging.getLogger(__name__)


def calculate_position_size(
    mode: PositionSizeMode,
    config: RiskConfig,
    weighted_score: float,
    current_price: Decimal,
    total_capital: Decimal,
    atr_value: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate position size based on configured mode.

    Args:
        mode: Position sizing mode
        config: Risk configuration
        weighted_score: Current weighted score ∈ [-1, 1]
        current_price: Current market price
        total_capital: Total available capital in USDT
        atr_value: Current ATR value (required for RISK_ATR mode)

    Returns:
        Position size in USDT

    Raises:
        ValueError: If inputs are invalid or ATR is missing for RISK_ATR mode

    Example:
        >>> config = RiskConfig(position_size_mode=PositionSizeMode.CONFIDENCE)
        >>> size = calculate_position_size(
        ...     mode=PositionSizeMode.CONFIDENCE,
        ...     config=config,
        ...     weighted_score=0.75,
        ...     current_price=Decimal("42000"),
        ...     total_capital=Decimal("10000")
        ... )
        >>> print(f"Position size: {size:.2f} USDT")
    """
    # Validation
    if not -1.0 <= weighted_score <= 1.0:
        raise ValueError(f"weighted_score must be in [-1, 1], got {weighted_score}")
    if current_price <= 0:
        raise ValueError(f"current_price must be > 0, got {current_price}")
    if total_capital <= 0:
        raise ValueError(f"total_capital must be > 0, got {total_capital}")

    if mode == PositionSizeMode.FIXED:
        size = _calculate_fixed_size(config, total_capital)
    elif mode == PositionSizeMode.CONFIDENCE:
        size = _calculate_confidence_size(config, weighted_score, total_capital)
    elif mode == PositionSizeMode.RISK_ATR:
        if atr_value is None:
            raise ValueError("atr_value is required for RISK_ATR mode")
        if atr_value <= 0:
            raise ValueError(f"atr_value must be > 0, got {atr_value}")
        size = _calculate_risk_atr_size(config, current_price, total_capital, atr_value)
    else:
        raise ValueError(f"Unknown position size mode: {mode}")

    # Log sizing decision
    logger.info(
        "Position size calculated",
        extra={
            "mode": mode.value,
            "weighted_score": weighted_score,
            "current_price": float(current_price),
            "total_capital": float(total_capital),
            "atr_value": float(atr_value) if atr_value else None,
            "position_size_usdt": float(size)
        }
    )

    return size


def _calculate_fixed_size(config: RiskConfig, total_capital: Decimal) -> Decimal:
    """
    Calculate fixed position size as a percentage of total capital.

    The position uses a constant share of capital each trade (e.g. 10% of a
    10,000 USDT balance → 1,000 USDT), so the absolute amount scales with the
    account instead of being a hard-coded USDT figure.

    Args:
        config: Risk configuration
        total_capital: Total available capital in USDT

    Returns:
        Position size in USDT = total_capital × (fixed_size_percent / 100)
    """
    return total_capital * Decimal(str(config.fixed_size_percent / 100.0))


def _calculate_confidence_size(
    config: RiskConfig,
    weighted_score: float,
    total_capital: Decimal
) -> Decimal:
    """
    Calculate confidence-based position size.

    Size is proportional to the weighted score:
    - Score = 0.6 (minimum entry threshold) → minimum size
    - Score = 1.0 (maximum confidence) → maximum size

    The size scales linearly between min and max exposure.

    Args:
        config: Risk configuration
        weighted_score: Current weighted score ∈ [0, 1] (assuming entry signal)
        total_capital: Total available capital

    Returns:
        Position size in USDT
    """
    # Define min and max exposure as % of capital
    min_exposure_percent = 10.0  # Minimum exposure at entry threshold
    max_exposure_percent = config.max_exposure_percent  # Maximum exposure at score = 1.0

    # Map weighted score to exposure percentage
    # Assuming entry threshold is 0.6 (from StrategyConfig default)
    # Score 0.6 → min_exposure_percent
    # Score 1.0 → max_exposure_percent
    entry_threshold = 0.6  # TODO: Get from StrategyConfig
    score_range = 1.0 - entry_threshold
    score_normalized = (weighted_score - entry_threshold) / score_range

    # Clamp to [0, 1]
    score_normalized = max(0.0, min(1.0, score_normalized))

    # Calculate exposure percentage
    exposure_percent = min_exposure_percent + (
        score_normalized * (max_exposure_percent - min_exposure_percent)
    )

    # Calculate position size
    size = total_capital * Decimal(str(exposure_percent / 100.0))

    logger.debug(
        "Confidence-based sizing",
        extra={
            "weighted_score": weighted_score,
            "score_normalized": score_normalized,
            "exposure_percent": exposure_percent,
            "min_exposure_percent": min_exposure_percent,
            "max_exposure_percent": max_exposure_percent,
            "position_size_usdt": float(size)
        }
    )

    return size


def _calculate_risk_atr_size(
    config: RiskConfig,
    current_price: Decimal,
    total_capital: Decimal,
    atr_value: Decimal
) -> Decimal:
    """
    Calculate risk-based ATR position size.

    This method sizes positions based on the % of capital to risk and the ATR.
    The stop-loss is placed at entry_price - (ATR × atr_multiplier), and position
    size is calculated so that hitting the stop-loss loses exactly capital_risk_percent
    of total capital.

    Formula:
        risk_amount = total_capital × (capital_risk_percent / 100)
        stop_distance = ATR × atr_multiplier
        position_size_usdt = risk_amount / (stop_distance / current_price)

    Args:
        config: Risk configuration
        current_price: Current market price
        total_capital: Total available capital
        atr_value: Current ATR value

    Returns:
        Position size in USDT

    Example:
        Capital: $10,000
        Risk: 1% = $100
        Price: $42,000
        ATR: $500
        ATR multiplier: 2.0
        Stop distance: $500 × 2.0 = $1,000

        Position size = $100 / ($1,000 / $42,000)
                     = $100 / 0.0238
                     = $4,200 USDT
    """
    # Calculate risk amount in USDT
    risk_amount = total_capital * Decimal(str(config.capital_risk_percent / 100.0))

    # Calculate stop-loss distance
    stop_distance = atr_value * Decimal(str(config.atr_multiplier))

    # Calculate position size
    # If we lose stop_distance per unit, how many units can we buy with risk_amount?
    # position_size = risk_amount / (stop_distance / current_price)
    stop_distance_percent = stop_distance / current_price
    position_size = risk_amount / stop_distance_percent

    logger.debug(
        "Risk ATR sizing",
        extra={
            "total_capital": float(total_capital),
            "capital_risk_percent": config.capital_risk_percent,
            "risk_amount": float(risk_amount),
            "atr_value": float(atr_value),
            "atr_multiplier": config.atr_multiplier,
            "stop_distance": float(stop_distance),
            "stop_distance_percent": float(stop_distance_percent),
            "current_price": float(current_price),
            "position_size_usdt": float(position_size)
        }
    )

    return position_size


def calculate_position_quantity(
    position_size_usdt: Decimal,
    current_price: Decimal,
    min_quantity: Decimal = Decimal("0.00001"),
    quantity_precision: int = 5
) -> Decimal:
    """
    Convert position size from USDT to quantity (number of units).

    Args:
        position_size_usdt: Position size in USDT
        current_price: Current market price per unit
        min_quantity: Minimum allowed quantity (exchange-specific)
        quantity_precision: Number of decimal places for quantity

    Returns:
        Position quantity (number of units)

    Raises:
        ValueError: If calculated quantity is below minimum

    Example:
        >>> size_usdt = Decimal("4200")
        >>> price = Decimal("42000")
        >>> qty = calculate_position_quantity(size_usdt, price)
        >>> print(f"{qty:.5f} BTC")  # 0.10000 BTC
    """
    if position_size_usdt <= 0:
        raise ValueError(f"position_size_usdt must be > 0, got {position_size_usdt}")
    if current_price <= 0:
        raise ValueError(f"current_price must be > 0, got {current_price}")

    # Calculate quantity
    quantity = position_size_usdt / current_price

    # Round to exchange precision
    quantize_pattern = Decimal("0.1") ** quantity_precision
    quantity = quantity.quantize(quantize_pattern)

    # Check minimum
    if quantity < min_quantity:
        raise ValueError(
            f"Calculated quantity {quantity} is below minimum {min_quantity}. "
            f"Increase position size or check exchange limits."
        )

    logger.debug(
        "Position quantity calculated",
        extra={
            "position_size_usdt": float(position_size_usdt),
            "current_price": float(current_price),
            "quantity": float(quantity),
            "quantity_precision": quantity_precision
        }
    )

    return quantity
