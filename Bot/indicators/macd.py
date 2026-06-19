"""
MACD (Moving Average Convergence Divergence) indicator.

MACD is a trend-following momentum indicator that shows the relationship between
two exponential moving averages of prices. It consists of:
- MACD line: Difference between fast EMA and slow EMA
- Signal line: EMA of the MACD line
- Histogram: Difference between MACD line and signal line

Trading signals:
- MACD crosses above signal line: Bullish
- MACD crosses below signal line: Bearish
- Histogram increasing: Momentum strengthening
- Histogram decreasing: Momentum weakening
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import calculate_ema, normalize_crossover, safe_divide

logger = logging.getLogger(__name__)


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate MACD line/signal line/histogram for every bar (vectorized).

    This is the single source of truth for MACD raw values: ``compute()`` (live, scalar)
    slices the last row, and ``signal_series()`` (vectorbt backtest) consumes the full
    series, so both paths can never drift from each other.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - fast (int): Fast EMA period (default: 12)
            - slow (int): Slow EMA period (default: 26)
            - signal (int): Signal line EMA period (default: 9)

    Returns:
        DataFrame indexed like ``candles`` with columns ``macd_line``, ``signal_line``,
        ``histogram`` (NaN for the warm-up bars before each value has enough history).

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    fast_period = params.get('fast', 12)
    slow_period = params.get('slow', 26)
    signal_period = params.get('signal', 9)

    # Validate parameters
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        raise ValueError("MACD periods must be positive integers")

    if fast_period >= slow_period:
        raise ValueError(
            f"Fast period ({fast_period}) must be less than slow period ({slow_period})"
        )

    # Validate sufficient data (need slow_period + signal_period for signal line)
    min_periods = slow_period + signal_period
    validate_candles(candles, min_periods=min_periods)

    # Calculate EMAs
    close_prices = candles['close'].astype(float)
    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)

    # Calculate MACD line
    macd_line = ema_fast - ema_slow

    # Calculate signal line (EMA of MACD line)
    signal_line = calculate_ema(macd_line, signal_period)

    # Calculate histogram
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {'macd_line': macd_line, 'signal_line': signal_line, 'histogram': histogram},
        index=candles.index,
    )


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized MACD signal for every bar (vectorized equivalent of
    ``to_signal()``), including the recent-crossover boost and histogram-trend boost.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    series = compute_series(candles, params)
    macd_line = series['macd_line']
    signal_line = series['signal_line']
    histogram = series['histogram']

    # Factor 1 (base signal): histogram / typical_threshold, same formula as to_signal().
    # typical_threshold = abs(signal_line) * 0.005, with a 1.0 fallback when signal_line == 0.
    typical_threshold = (signal_line.abs() * 0.005).where(signal_line != 0, 1.0)
    base_signal = (histogram / typical_threshold.replace(0, np.nan)).fillna(0.0)
    signal = base_signal.clip(-1.0, 1.0)

    # Factor 2: recent crossover (within last 3 transitions, matching compute()'s
    # range(-3, 0) loop). The scalar loop iterates from the OLDEST transition (-3) to
    # the newest (-1) and breaks on the first crossover found, so only the oldest
    # crossover's type in the window matters. Bullish/bearish are mutually exclusive
    # per bar (macd>signal and macd<signal can't both hold), so a single signed event
    # series captures "which type, if any" per bar; rolling(3).apply with a generator
    # that returns the first nonzero value replicates "oldest event in window wins".
    bullish_cross = (macd_line.shift(1) <= signal_line.shift(1)) & (macd_line > signal_line)
    bearish_cross = (macd_line.shift(1) >= signal_line.shift(1)) & (macd_line < signal_line)
    cross_event = pd.Series(0, index=macd_line.index, dtype=float)
    cross_event[bullish_cross] = 1.0
    cross_event[bearish_cross] = -1.0
    oldest_event = cross_event.rolling(3, min_periods=1).apply(
        lambda x: next((v for v in x if v != 0), 0.0), raw=True
    )
    recent_bullish = oldest_event == 1.0
    recent_bearish = oldest_event == -1.0

    boost_bullish = recent_bullish & (signal > 0)
    boost_bearish = recent_bearish & (signal < 0)
    signal = signal.where(~boost_bullish, (signal * 1.3).clip(upper=1.0))
    signal = signal.where(~boost_bearish, (signal * 1.3).clip(lower=-1.0))

    # Factor 3: histogram trend over the last 5 candles (4 diffs), matching compute()'s
    # `recent_hist = histogram.tail(5)` / `diffs = recent_hist.diff().dropna()` /
    # `(diffs > 0).all()` / `(diffs < 0).all()` logic, requiring all 5 values be non-NaN
    # (mirrored here by min_periods=4 on the rolling diff window plus the histogram
    # NaN guard applied at the end).
    diffs = histogram.diff()
    strengthening = (diffs > 0).rolling(4, min_periods=4).apply(
        lambda x: x.all(), raw=True
    ).fillna(0.0).astype(bool)
    weakening = (diffs < 0).rolling(4, min_periods=4).apply(
        lambda x: x.all(), raw=True
    ).fillna(0.0).astype(bool)

    # Strengthening: boost signal in its current direction (positive -> *1.1 clamped to 1.0,
    # negative -> *0.9 i.e. reduce magnitude toward 0).
    strengthening_pos = strengthening & (signal > 0)
    strengthening_neg = strengthening & (signal < 0)
    signal = signal.where(~strengthening_pos, (signal * 1.1).clip(upper=1.0))
    signal = signal.where(~strengthening_neg, signal * 0.9)

    # Weakening: reduce signal magnitude by *0.9 regardless of direction.
    signal = signal.where(~weakening, signal * 0.9)

    # Insufficient data (warm-up) -> neutral, matching to_signal()'s explicit check.
    signal = signal.where(macd_line.notna() & signal_line.notna(), 0.0)

    return signal.clip(-1.0, 1.0)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate MACD indicator values.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - fast (int): Fast EMA period (default: 12)
            - slow (int): Slow EMA period (default: 26)
            - signal (int): Signal line EMA period (default: 9)

    Returns:
        IndicatorResult containing:
            - macd: MACD line value (fast EMA - slow EMA)
            - signal: Signal line value
            - histogram: Histogram value (macd - signal)
            - crossover: Current state ('bullish' | 'bearish' | 'neutral')

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    fast_period = params.get('fast', 12)
    slow_period = params.get('slow', 26)
    signal_period = params.get('signal', 9)

    series = compute_series(candles, params)
    macd_line = series['macd_line']
    signal_line = series['signal_line']
    histogram = series['histogram']

    # Get current values
    current_macd = macd_line.iloc[-1]
    current_signal = signal_line.iloc[-1]
    current_histogram = histogram.iloc[-1]

    # Determine crossover state
    if pd.isna(current_macd) or pd.isna(current_signal):
        crossover = 'insufficient_data'
    elif current_macd > current_signal:
        crossover = 'bullish'
    elif current_macd < current_signal:
        crossover = 'bearish'
    else:
        crossover = 'neutral'

    # Check for recent crossover (within last 3 candles)
    recent_crossover = None
    if len(macd_line) >= 3 and len(signal_line) >= 3:
        for i in range(-3, 0):
            if pd.isna(macd_line.iloc[i]) or pd.isna(signal_line.iloc[i]):
                continue
            if pd.isna(macd_line.iloc[i-1]) or pd.isna(signal_line.iloc[i-1]):
                continue

            # Check for bullish crossover
            if (macd_line.iloc[i-1] <= signal_line.iloc[i-1] and
                    macd_line.iloc[i] > signal_line.iloc[i]):
                recent_crossover = {
                    'type': 'bullish',
                    'candles_ago': abs(i)
                }
                break
            # Check for bearish crossover
            elif (macd_line.iloc[i-1] >= signal_line.iloc[i-1] and
                  macd_line.iloc[i] < signal_line.iloc[i]):
                recent_crossover = {
                    'type': 'bearish',
                    'candles_ago': abs(i)
                }
                break

    # Analyze histogram trend (increasing/decreasing momentum)
    histogram_trend = None
    if len(histogram) >= 5:
        recent_hist = histogram.tail(5)
        if not recent_hist.isna().any():
            # Check if histogram is consistently increasing or decreasing
            diffs = recent_hist.diff().dropna()
            if (diffs > 0).all():
                histogram_trend = 'strengthening'
            elif (diffs < 0).all():
                histogram_trend = 'weakening'

    result = IndicatorResult(
        values={
            'macd': float(current_macd) if not pd.isna(current_macd) else None,
            'signal': float(current_signal) if not pd.isna(current_signal) else None,
            'histogram': float(current_histogram) if not pd.isna(current_histogram) else None,
            'crossover': crossover,
        },
        metadata={
            'fast_period': fast_period,
            'slow_period': slow_period,
            'signal_period': signal_period,
            'recent_crossover': recent_crossover,
            'histogram_trend': histogram_trend,
        }
    )

    logger.debug(
        "MACD computed",
        extra={
            'fast_period': fast_period,
            'slow_period': slow_period,
            'signal_period': signal_period,
            'macd': result.values['macd'],
            'signal': result.values['signal'],
            'histogram': result.values['histogram'],
            'crossover': crossover,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert MACD values to normalized signal.

    Signal logic:
    - MACD > Signal: Bullish (positive)
    - MACD < Signal: Bearish (negative)
    - Magnitude based on histogram relative to typical values
    - Recent crossovers and histogram trends affect signal strength

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (MACD well above signal, histogram increasing)
        - 0: Neutral (MACD ≈ signal)
        - -1: Strong bearish (MACD well below signal, histogram decreasing)
    """
    macd = values.values.get('macd')
    signal_line = values.values.get('signal')
    histogram = values.values.get('histogram')
    crossover = values.values.get('crossover')
    recent_crossover = values.metadata.get('recent_crossover') if values.metadata else None
    histogram_trend = values.metadata.get('histogram_trend') if values.metadata else None

    # Handle missing data
    if macd is None or signal_line is None or crossover == 'insufficient_data':
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Base signal on crossover
    # Normalize using histogram as a proxy for strength
    # Typical histogram values are usually within 0.5% of price
    # Use this as normalization threshold
    if signal_line != 0:
        typical_threshold = abs(signal_line) * 0.005  # 0.5% of signal line
    else:
        typical_threshold = 1.0  # Fallback

    # Calculate raw signal from histogram
    if typical_threshold > 0:
        signal_value = histogram / typical_threshold
    else:
        signal_value = 0.0

    # Clamp to [-1, 1]
    signal_value = max(-1.0, min(1.0, signal_value))

    # Build metadata
    metadata: Dict[str, Any] = {
        'crossover': crossover,
        'histogram': histogram,
    }

    # Determine primary reason for signal
    reason_parts = []

    # Factor 1: Recent crossover
    if recent_crossover:
        metadata['recent_crossover'] = recent_crossover
        if recent_crossover['type'] == 'bullish':
            reason_parts.append('bullish_crossover')
            # Boost bullish signal
            if signal_value > 0:
                signal_value = min(1.0, signal_value * 1.3)
        elif recent_crossover['type'] == 'bearish':
            reason_parts.append('bearish_crossover')
            # Boost bearish signal
            if signal_value < 0:
                signal_value = max(-1.0, signal_value * 1.3)

    # Factor 2: Histogram trend
    if histogram_trend:
        metadata['histogram_trend'] = histogram_trend
        if histogram_trend == 'strengthening':
            reason_parts.append('momentum_strengthening')
            # Boost signal in current direction
            if signal_value > 0:
                signal_value = min(1.0, signal_value * 1.1)
            elif signal_value < 0:
                # Weakening bearish momentum
                signal_value = signal_value * 0.9
        elif histogram_trend == 'weakening':
            reason_parts.append('momentum_weakening')
            # Reduce signal strength
            signal_value = signal_value * 0.9

    # Factor 3: Base position
    if not reason_parts:
        if signal_value > 0.3:
            reason_parts.append('macd_above_signal')
        elif signal_value < -0.3:
            reason_parts.append('macd_below_signal')
        else:
            reason_parts.append('macd_near_signal')

    metadata['reason'] = '_'.join(reason_parts) if reason_parts else 'neutral'

    logger.debug(
        "MACD signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'histogram': histogram,
            'crossover': crossover,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
