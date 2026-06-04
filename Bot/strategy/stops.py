"""
Stop-loss and take-profit calculations.

This module implements two calculation modes for both stop-loss and take-profit:
1. ATR-based: Uses ATR (Average True Range) as a volatility measure
2. Fixed percentage: Simple percentage from entry price

Currently supports LONG positions only (v1).
"""

import logging
from decimal import Decimal
from typing import Optional

from .types import StopLossMode, TakeProfitMode
from .config import StopLossConfig, TakeProfitConfig

# Structured logging
logger = logging.getLogger(__name__)


def calculate_stop_loss(
    mode: StopLossMode,
    config: StopLossConfig,
    entry_price: Decimal,
    atr_value: Optional[Decimal] = None,
    price_precision: int = 2
) -> Decimal:
    """
    Calculate stop-loss price for a LONG position.

    Args:
        mode: Stop-loss calculation mode (ATR or FIXED)
        config: Stop-loss configuration
        entry_price: Position entry price
        atr_value: Current ATR value (required for ATR mode)
        price_precision: Number of decimal places for price

    Returns:
        Stop-loss price

    Raises:
        ValueError: If inputs are invalid or ATR is missing for ATR mode

    Example (ATR mode):
        >>> config = StopLossConfig(mode=StopLossMode.ATR, atr_multiplier=2.0)
        >>> entry_price = Decimal("42000")
        >>> atr = Decimal("500")
        >>> sl = calculate_stop_loss(
        ...     mode=StopLossMode.ATR,
        ...     config=config,
        ...     entry_price=entry_price,
        ...     atr_value=atr
        ... )
        >>> print(f"Stop-loss: ${sl:.2f}")  # $41000.00

    Example (FIXED mode):
        >>> config = StopLossConfig(mode=StopLossMode.FIXED, fixed_percent=2.0)
        >>> entry_price = Decimal("42000")
        >>> sl = calculate_stop_loss(
        ...     mode=StopLossMode.FIXED,
        ...     config=config,
        ...     entry_price=entry_price
        ... )
        >>> print(f"Stop-loss: ${sl:.2f}")  # $41160.00 (2% below entry)
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")

    if mode == StopLossMode.ATR:
        if atr_value is None:
            raise ValueError("atr_value is required for ATR mode")
        if atr_value <= 0:
            raise ValueError(f"atr_value must be > 0, got {atr_value}")
        sl_price = _calculate_atr_stop_loss(entry_price, atr_value, config.atr_multiplier)
    elif mode == StopLossMode.FIXED:
        sl_price = _calculate_fixed_stop_loss(entry_price, config.fixed_percent)
    else:
        raise ValueError(f"Unknown stop-loss mode: {mode}")

    # Round to price precision
    quantize_pattern = Decimal("0.1") ** price_precision
    sl_price = sl_price.quantize(quantize_pattern)

    # Validate: stop-loss must be below entry for LONG
    if sl_price >= entry_price:
        raise ValueError(
            f"Invalid stop-loss: {sl_price} >= entry_price {entry_price}. "
            f"Stop-loss must be below entry for LONG positions."
        )

    logger.info(
        "Stop-loss calculated",
        extra={
            "mode": mode.value,
            "entry_price": float(entry_price),
            "atr_value": float(atr_value) if atr_value else None,
            "atr_multiplier": config.atr_multiplier if mode == StopLossMode.ATR else None,
            "fixed_percent": config.fixed_percent if mode == StopLossMode.FIXED else None,
            "stop_loss_price": float(sl_price),
            "distance_percent": float((entry_price - sl_price) / entry_price * 100)
        }
    )

    return sl_price


def _calculate_atr_stop_loss(
    entry_price: Decimal,
    atr_value: Decimal,
    atr_multiplier: float
) -> Decimal:
    """
    Calculate ATR-based stop-loss for LONG position.

    Formula:
        stop_loss = entry_price - (ATR × multiplier)

    Args:
        entry_price: Position entry price
        atr_value: Current ATR value
        atr_multiplier: ATR multiplier from config

    Returns:
        Stop-loss price
    """
    stop_distance = atr_value * Decimal(str(atr_multiplier))
    sl_price = entry_price - stop_distance

    logger.debug(
        "ATR stop-loss",
        extra={
            "entry_price": float(entry_price),
            "atr_value": float(atr_value),
            "atr_multiplier": atr_multiplier,
            "stop_distance": float(stop_distance),
            "stop_loss_price": float(sl_price)
        }
    )

    return sl_price


def _calculate_fixed_stop_loss(entry_price: Decimal, fixed_percent: float) -> Decimal:
    """
    Calculate fixed percentage stop-loss for LONG position.

    Formula:
        stop_loss = entry_price × (1 - percent/100)

    Args:
        entry_price: Position entry price
        fixed_percent: Stop-loss percentage (e.g., 2.0 for 2%)

    Returns:
        Stop-loss price
    """
    sl_price = entry_price * (Decimal("1") - Decimal(str(fixed_percent / 100.0)))

    logger.debug(
        "Fixed stop-loss",
        extra={
            "entry_price": float(entry_price),
            "fixed_percent": fixed_percent,
            "stop_loss_price": float(sl_price)
        }
    )

    return sl_price


def calculate_take_profit(
    mode: TakeProfitMode,
    config: TakeProfitConfig,
    entry_price: Decimal,
    atr_value: Optional[Decimal] = None,
    price_precision: int = 2
) -> Decimal:
    """
    Calculate take-profit price for a LONG position.

    Args:
        mode: Take-profit calculation mode (ATR or FIXED)
        config: Take-profit configuration
        entry_price: Position entry price
        atr_value: Current ATR value (required for ATR mode)
        price_precision: Number of decimal places for price

    Returns:
        Take-profit price

    Raises:
        ValueError: If inputs are invalid or ATR is missing for ATR mode

    Example (ATR mode):
        >>> config = TakeProfitConfig(mode=TakeProfitMode.ATR, atr_multiplier=3.0)
        >>> entry_price = Decimal("42000")
        >>> atr = Decimal("500")
        >>> tp = calculate_take_profit(
        ...     mode=TakeProfitMode.ATR,
        ...     config=config,
        ...     entry_price=entry_price,
        ...     atr_value=atr
        ... )
        >>> print(f"Take-profit: ${tp:.2f}")  # $43500.00

    Example (FIXED mode):
        >>> config = TakeProfitConfig(mode=TakeProfitMode.FIXED, fixed_percent=4.0)
        >>> entry_price = Decimal("42000")
        >>> tp = calculate_take_profit(
        ...     mode=TakeProfitMode.FIXED,
        ...     config=config,
        ...     entry_price=entry_price
        ... )
        >>> print(f"Take-profit: ${tp:.2f}")  # $43680.00 (4% above entry)
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")

    if mode == TakeProfitMode.ATR:
        if atr_value is None:
            raise ValueError("atr_value is required for ATR mode")
        if atr_value <= 0:
            raise ValueError(f"atr_value must be > 0, got {atr_value}")
        tp_price = _calculate_atr_take_profit(entry_price, atr_value, config.atr_multiplier)
    elif mode == TakeProfitMode.FIXED:
        tp_price = _calculate_fixed_take_profit(entry_price, config.fixed_percent)
    else:
        raise ValueError(f"Unknown take-profit mode: {mode}")

    # Round to price precision
    quantize_pattern = Decimal("0.1") ** price_precision
    tp_price = tp_price.quantize(quantize_pattern)

    # Validate: take-profit must be above entry for LONG
    if tp_price <= entry_price:
        raise ValueError(
            f"Invalid take-profit: {tp_price} <= entry_price {entry_price}. "
            f"Take-profit must be above entry for LONG positions."
        )

    logger.info(
        "Take-profit calculated",
        extra={
            "mode": mode.value,
            "entry_price": float(entry_price),
            "atr_value": float(atr_value) if atr_value else None,
            "atr_multiplier": config.atr_multiplier if mode == TakeProfitMode.ATR else None,
            "fixed_percent": config.fixed_percent if mode == TakeProfitMode.FIXED else None,
            "take_profit_price": float(tp_price),
            "distance_percent": float((tp_price - entry_price) / entry_price * 100)
        }
    )

    return tp_price


def _calculate_atr_take_profit(
    entry_price: Decimal,
    atr_value: Decimal,
    atr_multiplier: float
) -> Decimal:
    """
    Calculate ATR-based take-profit for LONG position.

    Formula:
        take_profit = entry_price + (ATR × multiplier)

    Args:
        entry_price: Position entry price
        atr_value: Current ATR value
        atr_multiplier: ATR multiplier from config

    Returns:
        Take-profit price
    """
    profit_distance = atr_value * Decimal(str(atr_multiplier))
    tp_price = entry_price + profit_distance

    logger.debug(
        "ATR take-profit",
        extra={
            "entry_price": float(entry_price),
            "atr_value": float(atr_value),
            "atr_multiplier": atr_multiplier,
            "profit_distance": float(profit_distance),
            "take_profit_price": float(tp_price)
        }
    )

    return tp_price


def _calculate_fixed_take_profit(entry_price: Decimal, fixed_percent: float) -> Decimal:
    """
    Calculate fixed percentage take-profit for LONG position.

    Formula:
        take_profit = entry_price × (1 + percent/100)

    Args:
        entry_price: Position entry price
        fixed_percent: Take-profit percentage (e.g., 4.0 for 4%)

    Returns:
        Take-profit price
    """
    tp_price = entry_price * (Decimal("1") + Decimal(str(fixed_percent / 100.0)))

    logger.debug(
        "Fixed take-profit",
        extra={
            "entry_price": float(entry_price),
            "fixed_percent": fixed_percent,
            "take_profit_price": float(tp_price)
        }
    )

    return tp_price


def calculate_risk_reward_ratio(
    entry_price: Decimal,
    stop_loss_price: Decimal,
    take_profit_price: Decimal
) -> Decimal:
    """
    Calculate risk/reward ratio for a trade.

    Formula:
        risk = entry_price - stop_loss_price
        reward = take_profit_price - entry_price
        ratio = reward / risk

    Args:
        entry_price: Position entry price
        stop_loss_price: Stop-loss price
        take_profit_price: Take-profit price

    Returns:
        Risk/reward ratio (e.g., 1.5 means 1.5:1 reward:risk)

    Raises:
        ValueError: If prices are invalid

    Example:
        >>> entry = Decimal("42000")
        >>> sl = Decimal("41000")  # Risk: $1000
        >>> tp = Decimal("43500")  # Reward: $1500
        >>> ratio = calculate_risk_reward_ratio(entry, sl, tp)
        >>> print(f"Risk/Reward: {ratio:.2f}:1")  # 1.50:1
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")
    if stop_loss_price >= entry_price:
        raise ValueError(
            f"stop_loss_price ({stop_loss_price}) must be < entry_price ({entry_price}) for LONG"
        )
    if take_profit_price <= entry_price:
        raise ValueError(
            f"take_profit_price ({take_profit_price}) must be > entry_price ({entry_price}) for LONG"
        )

    risk = entry_price - stop_loss_price
    reward = take_profit_price - entry_price
    ratio = reward / risk

    logger.debug(
        "Risk/reward ratio",
        extra={
            "entry_price": float(entry_price),
            "stop_loss_price": float(stop_loss_price),
            "take_profit_price": float(take_profit_price),
            "risk": float(risk),
            "reward": float(reward),
            "ratio": float(ratio)
        }
    )

    return ratio
