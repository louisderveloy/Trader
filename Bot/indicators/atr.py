"""
ATR (Average True Range) indicator.

ATR measures market volatility by calculating the average of true ranges over
a specified period. The true range is the greatest of:
1. Current high minus current low
2. Absolute value of current high minus previous close
3. Absolute value of current low minus previous close

ATR is primarily used for:
- Position sizing (higher ATR = smaller position)
- Stop-loss placement (e.g., 2 × ATR below entry)
- Take-profit placement (e.g., 3 × ATR above entry)
- Volatility assessment for signal strength

As a signal, high ATR can indicate:
- Potential trend reversals (extreme volatility)
- Breakout confirmation (increasing ATR)
- Consolidation ending (ATR rising from low levels)
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import normalize_percentile, safe_divide

logger = logging.getLogger(__name__)


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate ATR raw values for every bar (vectorized).

    This is the single source of truth for ATR raw values: ``compute()`` (live, scalar)
    slices the last row, and ``signal_series()`` (vectorbt backtest) consumes the full
    series, so both paths can never drift from each other.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): ATR period (default: 14)

    Returns:
        DataFrame indexed like ``candles`` with columns ``close``, ``atr``, ``atr_percent``
        (NaN for the warm-up bars before ATR has enough history).

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 14)

    # Validate parameters
    if period <= 0:
        raise ValueError("ATR period must be a positive integer")

    # Validate sufficient data (need period + 1 for previous close)
    validate_candles(candles, min_periods=period + 1)

    # Calculate True Range components
    high = candles['high'].astype(float)
    low = candles['low'].astype(float)
    close = candles['close'].astype(float)
    prev_close = close.shift(1)

    # True Range is the greatest of:
    # 1. high - low
    # 2. abs(high - prev_close)
    # 3. abs(low - prev_close)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate ATR using Wilder's smoothing (EMA with alpha = 1/period)
    atr = true_range.ewm(alpha=1/period, adjust=False).mean()

    # Vectorized equivalent of safe_divide(current_atr, current_price, 0.0) * 100
    atr_percent = (atr / close.replace(0, np.nan) * 100).fillna(0.0)

    return pd.DataFrame(
        {'close': close, 'atr': atr, 'atr_percent': atr_percent},
        index=candles.index,
    )


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized ATR signal for every bar (vectorized equivalent of
    ``to_signal()``), including the volatility-percentile base signal and the
    rising/falling trend adjustment.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    series = compute_series(candles, params)
    atr = series['atr']

    # Rolling percentile rank over a trailing 100-bar window, matching compute()'s
    # `(recent_atr_history < current_atr).sum() / len(recent_atr_history)` exactly:
    # counts how many of the past 100 values are strictly LESS than the current value.
    # min_periods=100 matches the scalar's `if len(atr) >= 100` gate (no partial windows).
    percentile_rank = atr.rolling(100, min_periods=100).apply(
        lambda x: (x.iloc[-1] > x).sum() / len(x), raw=False
    )

    # Base signal from percentile_rank (NaN -> 0.0 fallback, matching to_signal()'s
    # "no percentile data" branch).
    signal = pd.Series(0.0, index=atr.index)
    low_vol = percentile_rank < 0.3
    high_vol = percentile_rank > 0.7
    signal = signal.where(~low_vol.fillna(False), -0.3 * (0.3 - percentile_rank) / 0.3)
    signal = signal.where(~high_vol.fillna(False), 0.3 * (percentile_rank - 0.7) / 0.3)

    # Trend detection: rising if at least 4 of the last 4 diffs are positive, falling if
    # at least 4 are negative, else stable (no adjustment). Matches compute()'s
    # `recent_atr.diff().dropna()` over `atr.tail(5)` (4 diffs), applied per-bar.
    diffs = atr.diff()
    rising = (diffs > 0).rolling(4, min_periods=4).sum() >= 4
    falling = (diffs < 0).rolling(4, min_periods=4).sum() >= 4

    signal = signal.where(~rising, (signal * 1.1).clip(upper=0.3))
    signal = signal.where(~falling, (signal * 1.1).clip(lower=-0.3))

    # Insufficient data (warm-up, atr is NaN) -> neutral, matching to_signal()'s
    # `if atr is None: return 0.0` check.
    signal = signal.where(atr.notna(), 0.0)

    return signal


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate ATR indicator values.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): ATR period (default: 14)

    Returns:
        IndicatorResult containing:
            - atr: Current ATR value
            - atr_percent: ATR as percentage of current price
            - trend: ATR trend ('rising' | 'falling' | 'stable')

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 14)

    series = compute_series(candles, params)
    atr = series['atr']
    close = series['close']

    # Get current values
    current_atr = atr.iloc[-1]
    current_price = close.iloc[-1]

    # Calculate ATR as percentage of price
    atr_percent = safe_divide(current_atr, current_price, 0.0) * 100

    # Determine ATR trend (compare recent ATR values)
    trend = 'stable'
    if len(atr) >= 5:
        recent_atr = atr.tail(5)
        if not recent_atr.isna().any():
            # Check if ATR is consistently rising or falling
            diffs = recent_atr.diff().dropna()
            if (diffs > 0).sum() >= 4:
                trend = 'rising'
            elif (diffs < 0).sum() >= 4:
                trend = 'falling'

    # Calculate percentile rank (how current ATR compares to recent history)
    percentile_rank = None
    if len(atr) >= 100:
        recent_atr_history = atr.tail(100)
        if not recent_atr_history.isna().any():
            percentile_rank = (recent_atr_history < current_atr).sum() / len(recent_atr_history)

    result = IndicatorResult(
        values={
            'atr': float(current_atr) if not pd.isna(current_atr) else None,
            'atr_percent': atr_percent,
            'trend': trend,
        },
        metadata={
            'period': period,
            'current_price': float(current_price),
            'percentile_rank': percentile_rank,
        }
    )

    logger.debug(
        "ATR computed",
        extra={
            'period': period,
            'atr': result.values['atr'],
            'atr_percent': atr_percent,
            'trend': trend,
            'percentile_rank': percentile_rank,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert ATR values to normalized signal.

    Signal logic:
    - High ATR (high volatility): Can indicate trend reversal or strong momentum
    - Rising ATR: Potential breakout or trend strengthening
    - Falling ATR: Consolidation, weakening momentum
    - ATR percentile rank determines signal strength

    Note: ATR is not directional (doesn't indicate buy/sell), but rather
    indicates volatility conditions. The signal interpretation depends on context:
    - In consolidation: Rising ATR → potential breakout (neutral to slightly bullish)
    - In trend: Rising ATR → trend continuation (slight boost to trend direction)
    - Very high ATR: Caution (potential exhaustion)

    For simplicity, we use a neutral interpretation focused on volatility regime:
    - Low volatility (ATR percentile < 30%): Slightly bearish (consolidation)
    - Normal volatility (30-70%): Neutral
    - High volatility (>70%): Slightly bullish (momentum/breakout)

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        The signal is relatively weak (-0.3 to +0.3) as ATR is primarily
        used for position sizing and risk management, not directional signals.
    """
    atr = values.values.get('atr')
    atr_percent = values.values.get('atr_percent', 0.0)
    trend = values.values.get('trend')
    percentile_rank = values.metadata.get('percentile_rank') if values.metadata else None

    # Handle missing data
    if atr is None:
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Base signal on percentile rank if available
    if percentile_rank is not None:
        # Low volatility (< 30th percentile): Slightly bearish (consolidation)
        # High volatility (> 70th percentile): Slightly bullish (momentum)
        # Scale to [-0.3, +0.3] to keep ATR signal weak
        if percentile_rank < 0.3:
            signal_value = -0.3 * (0.3 - percentile_rank) / 0.3
        elif percentile_rank > 0.7:
            signal_value = 0.3 * (percentile_rank - 0.7) / 0.3
        else:
            signal_value = 0.0
    else:
        # Fallback: neutral signal
        signal_value = 0.0

    # Build metadata
    metadata: Dict[str, Any] = {
        'atr': atr,
        'atr_percent': atr_percent,
        'trend': trend,
    }

    if percentile_rank is not None:
        metadata['percentile_rank'] = percentile_rank

    # Determine reason
    reason_parts = []

    # Factor 1: Volatility regime
    if percentile_rank is not None:
        if percentile_rank < 0.2:
            reason_parts.append('very_low_volatility')
        elif percentile_rank < 0.3:
            reason_parts.append('low_volatility')
        elif percentile_rank > 0.8:
            reason_parts.append('very_high_volatility')
        elif percentile_rank > 0.7:
            reason_parts.append('high_volatility')
        else:
            reason_parts.append('normal_volatility')

    # Factor 2: Trend
    if trend == 'rising':
        reason_parts.append('volatility_increasing')
        # Slight boost for rising volatility
        signal_value = min(0.3, signal_value * 1.1)
    elif trend == 'falling':
        reason_parts.append('volatility_decreasing')
        # Slight reduction for falling volatility
        signal_value = max(-0.3, signal_value * 1.1)

    metadata['reason'] = '_'.join(reason_parts) if reason_parts else 'neutral'

    # Add interpretation note
    metadata['note'] = 'ATR is primarily for risk management, not directional signals'

    logger.debug(
        "ATR signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'atr_percent': atr_percent,
            'trend': trend,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
