"""
Utility functions for indicator calculations and signal normalization.

This module provides common helpers used across multiple indicators for:
- Signal normalization to [-1, 1] range
- Data validation
- Common calculations
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def normalize_to_range(
    value: float,
    min_val: float,
    max_val: float,
    target_min: float = -1.0,
    target_max: float = 1.0,
) -> float:
    """
    Normalize a value from [min_val, max_val] to [target_min, target_max].

    Args:
        value: Value to normalize
        min_val: Minimum value of input range
        max_val: Maximum value of input range
        target_min: Minimum value of output range (default: -1.0)
        target_max: Maximum value of output range (default: 1.0)

    Returns:
        Normalized value clamped to [target_min, target_max]

    Examples:
        >>> normalize_to_range(50, 0, 100, -1, 1)
        0.0
        >>> normalize_to_range(75, 0, 100, -1, 1)
        0.5
    """
    # Handle edge case where min == max
    if max_val == min_val:
        return (target_min + target_max) / 2.0

    # Linear normalization
    normalized = (value - min_val) / (max_val - min_val)
    normalized = normalized * (target_max - target_min) + target_min

    # Clamp to target range. np.clip requires its bounds in ascending order — callers
    # like normalize_oscillator() pass (target_min, target_max) pairs where target_min
    # is numerically greater than target_max (e.g. (1.0, 0.5) for a descending output
    # range), which would otherwise make np.clip collapse every input to target_max.
    lo, hi = (target_min, target_max) if target_min <= target_max else (target_max, target_min)
    return float(np.clip(normalized, lo, hi))


def normalize_oscillator(
    value: float,
    neutral: float = 50.0,
    overbought: float = 70.0,
    oversold: float = 30.0,
) -> float:
    """
    Normalize oscillator values (like RSI) to [-1, 1] signal.

    Maps oscillator zones to signals:
    - oversold zone (< oversold) → negative signal
    - neutral zone (oversold to overbought) → near zero
    - overbought zone (> overbought) → positive signal (reversed for contrarian)

    Args:
        value: Oscillator value (typically 0-100)
        neutral: Neutral zone center (default: 50)
        overbought: Overbought threshold (default: 70)
        oversold: Oversold threshold (default: 30)

    Returns:
        Signal in range [-1, 1]

    Note:
        Uses contrarian logic: overbought → negative (sell signal)
                                oversold → positive (buy signal)
    """
    if value <= oversold:
        # Oversold: strong buy signal
        # Map [0, oversold] to [1, 0.5]
        return normalize_to_range(value, 0, oversold, 1.0, 0.5)
    elif value >= overbought:
        # Overbought: strong sell signal
        # Map [overbought, 100] to [-0.5, -1]
        return normalize_to_range(value, overbought, 100, -0.5, -1.0)
    else:
        # Neutral zone: weak signal
        # Map [oversold, neutral, overbought] to [0.5, 0, -0.5]
        if value <= neutral:
            return normalize_to_range(value, oversold, neutral, 0.5, 0.0)
        else:
            return normalize_to_range(value, neutral, overbought, 0.0, -0.5)


def normalize_crossover(
    fast_value: float,
    slow_value: float,
    threshold_percent: float = 0.01,
) -> float:
    """
    Normalize crossover signal based on relative position.

    Args:
        fast_value: Fast line value (e.g., fast EMA)
        slow_value: Slow line value (e.g., slow EMA)
        threshold_percent: Threshold for significant separation (default: 1%)

    Returns:
        Signal in range [-1, 1]:
        - +1: fast >> slow (strong bullish)
        - 0: fast ≈ slow (neutral)
        - -1: fast << slow (strong bearish)
    """
    if slow_value == 0:
        return 0.0

    # Calculate percentage difference
    percent_diff = (fast_value - slow_value) / slow_value

    # Normalize using threshold
    # If diff > threshold%, map to +1
    # If diff < -threshold%, map to -1
    # Otherwise, linear interpolation
    signal = percent_diff / threshold_percent

    return float(np.clip(signal, -1.0, 1.0))


def normalize_percentile(
    current_value: float,
    historical_values: pd.Series,
    lookback_periods: int = 100,
) -> float:
    """
    Normalize value based on its percentile in recent history.

    Args:
        current_value: Current value to normalize
        historical_values: Series of historical values
        lookback_periods: Number of periods to consider for percentile calculation

    Returns:
        Signal in range [-1, 1]:
        - +1: current value at 100th percentile (highest in history)
        - 0: current value at 50th percentile (median)
        - -1: current value at 0th percentile (lowest in history)
    """
    if len(historical_values) < 2:
        return 0.0

    # Get recent history
    recent = historical_values.tail(lookback_periods)

    # Calculate percentile rank (0 to 1)
    percentile_rank = (recent < current_value).sum() / len(recent)

    # Convert to [-1, 1] range
    # percentile 0 → -1, percentile 0.5 → 0, percentile 1 → +1
    signal = (percentile_rank - 0.5) * 2.0

    return float(np.clip(signal, -1.0, 1.0))


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.

    Args:
        series: Input series (typically close prices)
        period: EMA period

    Returns:
        Series of EMA values (same length as input, initial values are NaN)
    """
    return series.ewm(span=period, adjust=False).mean()


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average.

    Args:
        series: Input series
        period: SMA period

    Returns:
        Series of SMA values (same length as input, initial values are NaN)
    """
    return series.rolling(window=period).mean()


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Value to return if denominator is zero (default: 0.0)

    Returns:
        Result of division or default value
    """
    if denominator == 0 or np.isnan(denominator) or np.isinf(denominator):
        return default
    return numerator / denominator
