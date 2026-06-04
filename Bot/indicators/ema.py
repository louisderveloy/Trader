"""
EMA (Exponential Moving Average) crossover indicator.

This indicator uses two EMAs (fast and slow) to identify trend direction.
When the fast EMA crosses above the slow EMA, it generates a bullish signal.
When it crosses below, it generates a bearish signal.

The EMA gives more weight to recent prices compared to SMA, making it more
responsive to new information.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import calculate_ema, normalize_crossover

logger = logging.getLogger(__name__)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate EMA indicator values.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - fast_period (int): Fast EMA period (default: 50)
            - slow_period (int): Slow EMA period (default: 200)

    Returns:
        IndicatorResult containing:
            - ema_fast: Fast EMA values
            - ema_slow: Slow EMA values
            - crossover: Current crossover state ('bullish' | 'bearish' | 'neutral')

    Raises:
        ValueError: If insufficient candle data for calculation
    """
    # Get parameters with defaults
    fast_period = params.get('fast_period', 50)
    slow_period = params.get('slow_period', 200)

    # Validate parameters
    if fast_period <= 0 or slow_period <= 0:
        raise ValueError("EMA periods must be positive integers")

    if fast_period >= slow_period:
        raise ValueError(
            f"Fast period ({fast_period}) must be less than slow period ({slow_period})"
        )

    # Validate sufficient data
    min_periods = max(fast_period, slow_period)
    validate_candles(candles, min_periods=min_periods)

    # Calculate EMAs
    close_prices = candles['close'].astype(float)
    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)

    # Get current values (most recent)
    current_fast = ema_fast.iloc[-1]
    current_slow = ema_slow.iloc[-1]

    # Determine crossover state
    if pd.isna(current_fast) or pd.isna(current_slow):
        crossover = 'insufficient_data'
    elif current_fast > current_slow:
        crossover = 'bullish'
    elif current_fast < current_slow:
        crossover = 'bearish'
    else:
        crossover = 'neutral'

    # Check for recent crossover (within last 5 candles)
    recent_crossover = None
    if len(ema_fast) >= 5 and len(ema_slow) >= 5:
        for i in range(-5, 0):
            if pd.isna(ema_fast.iloc[i]) or pd.isna(ema_slow.iloc[i]):
                continue
            if pd.isna(ema_fast.iloc[i-1]) or pd.isna(ema_slow.iloc[i-1]):
                continue

            # Check for crossover
            if (ema_fast.iloc[i-1] <= ema_slow.iloc[i-1] and
                    ema_fast.iloc[i] > ema_slow.iloc[i]):
                recent_crossover = {
                    'type': 'golden_cross',
                    'candles_ago': abs(i)
                }
                break
            elif (ema_fast.iloc[i-1] >= ema_slow.iloc[i-1] and
                  ema_fast.iloc[i] < ema_slow.iloc[i]):
                recent_crossover = {
                    'type': 'death_cross',
                    'candles_ago': abs(i)
                }
                break

    result = IndicatorResult(
        values={
            'ema_fast': float(current_fast) if not pd.isna(current_fast) else None,
            'ema_slow': float(current_slow) if not pd.isna(current_slow) else None,
            'crossover': crossover,
        },
        metadata={
            'fast_period': fast_period,
            'slow_period': slow_period,
            'recent_crossover': recent_crossover,
        }
    )

    logger.debug(
        "EMA computed",
        extra={
            'fast_period': fast_period,
            'slow_period': slow_period,
            'ema_fast': result.values['ema_fast'],
            'ema_slow': result.values['ema_slow'],
            'crossover': crossover,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert EMA values to normalized signal.

    Signal logic:
    - Fast EMA > Slow EMA: Bullish signal (positive)
    - Fast EMA < Slow EMA: Bearish signal (negative)
    - Magnitude based on percentage separation between EMAs
    - Recent crossovers boost signal strength

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (fast well above slow)
        - 0: Neutral (EMAs very close)
        - -1: Strong bearish (fast well below slow)
    """
    ema_fast = values.values.get('ema_fast')
    ema_slow = values.values.get('ema_slow')
    crossover = values.values.get('crossover')
    recent_crossover = values.metadata.get('recent_crossover') if values.metadata else None

    # Handle missing data
    if ema_fast is None or ema_slow is None or crossover == 'insufficient_data':
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Calculate signal based on crossover
    # Use 1% threshold for normalization
    signal_value = normalize_crossover(
        fast_value=ema_fast,
        slow_value=ema_slow,
        threshold_percent=0.01  # 1% separation = max signal
    )

    # Build metadata
    metadata: Dict[str, Any] = {
        'crossover': crossover,
        'separation_percent': ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow != 0 else 0,
    }

    # Boost signal if recent crossover detected
    if recent_crossover:
        metadata['recent_crossover'] = recent_crossover
        # Boost signal strength for recent crossovers
        if recent_crossover['type'] == 'golden_cross' and signal_value > 0:
            signal_value = min(1.0, signal_value * 1.2)
            metadata['reason'] = 'golden_cross_bullish'
        elif recent_crossover['type'] == 'death_cross' and signal_value < 0:
            signal_value = max(-1.0, signal_value * 1.2)
            metadata['reason'] = 'death_cross_bearish'
    else:
        # No recent crossover, base reason on current state
        if signal_value > 0.3:
            metadata['reason'] = 'fast_above_slow_bullish'
        elif signal_value < -0.3:
            metadata['reason'] = 'fast_below_slow_bearish'
        else:
            metadata['reason'] = 'emas_close_neutral'

    logger.debug(
        "EMA signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata.get('reason'),
            'separation_percent': metadata.get('separation_percent'),
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
