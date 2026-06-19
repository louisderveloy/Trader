"""
RSI (Relative Strength Index) indicator.

RSI is a momentum oscillator that measures the speed and magnitude of price changes.
It oscillates between 0 and 100, with traditional interpretation:
- RSI > 70: Overbought (potential sell signal)
- RSI < 30: Oversold (potential buy signal)
- RSI ≈ 50: Neutral

The indicator uses a contrarian approach: overbought conditions suggest
bearish signals, while oversold conditions suggest bullish signals.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import normalize_oscillator, safe_divide

logger = logging.getLogger(__name__)


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate RSI (and intermediate avg gain/loss) for every bar (vectorized).

    This is the single source of truth for RSI raw values: ``compute()`` (live, scalar)
    slices the last row, and ``signal_series()`` (vectorbt backtest) consumes the full
    series, so both paths can never drift from each other.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): RSI period (default: 14)
            - overbought (float): Overbought threshold (default: 70)
            - oversold (float): Oversold threshold (default: 30)

    Returns:
        DataFrame indexed like ``candles`` with columns ``rsi``, ``avg_gain``, ``avg_loss``
        (NaN for the warm-up bars before RSI has enough history).

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 14)
    overbought = params.get('overbought', 70.0)
    oversold = params.get('oversold', 30.0)

    # Validate parameters
    if period <= 0:
        raise ValueError("RSI period must be a positive integer")

    if not 0 < oversold < overbought < 100:
        raise ValueError(
            f"Thresholds must satisfy: 0 < oversold ({oversold}) < "
            f"overbought ({overbought}) < 100"
        )

    # Validate sufficient data (need period + 1 for delta calculation)
    min_periods = period + 1
    validate_candles(candles, min_periods=min_periods)

    # Calculate price changes
    close_prices = candles['close'].astype(float)
    delta = close_prices.diff()

    # Separate gains and losses
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)

    # Calculate average gain and loss using EMA (Wilder's smoothing)
    # Wilder's EMA is equivalent to EMA with alpha = 1/period
    avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss.replace(0, 1e-10)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))

    return pd.DataFrame(
        {'rsi': rsi, 'avg_gain': avg_gain, 'avg_loss': avg_loss}, index=candles.index
    )


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized RSI signal for every bar (vectorized equivalent of
    ``to_signal()``), including the divergence boost.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    period = params.get('period', 14)
    overbought = params.get('overbought', 70.0)
    oversold = params.get('oversold', 30.0)
    neutral = 50.0

    series = compute_series(candles, params)
    rsi = series['rsi']

    # Same formula as normalize_oscillator(), vectorized over the branches.
    # Branch 1: value <= oversold -> map [0, oversold] to [1.0, 0.5]
    oversold_branch = ((rsi - 0) / (oversold - 0)) * (0.5 - 1.0) + 1.0
    # Branch 2: value >= overbought -> map [overbought, 100] to [-0.5, -1.0]
    overbought_branch = ((rsi - overbought) / (100 - overbought)) * (-1.0 - -0.5) + -0.5
    # Branch 3a: neutral zone, value <= neutral -> map [oversold, neutral] to [0.5, 0.0]
    neutral_low_branch = ((rsi - oversold) / (neutral - oversold)) * (0.0 - 0.5) + 0.5
    # Branch 3b: neutral zone, value > neutral -> map [neutral, overbought] to [0.0, -0.5]
    neutral_high_branch = ((rsi - neutral) / (overbought - neutral)) * (-0.5 - 0.0) + 0.0

    base_signal = np.select(
        condlist=[rsi <= oversold, rsi >= overbought, rsi <= neutral],
        choicelist=[
            oversold_branch.clip(0.5, 1.0),
            overbought_branch.clip(-1.0, -0.5),
            neutral_low_branch.clip(0.0, 0.5),
        ],
        default=neutral_high_branch.clip(-0.5, 0.0),
    )
    base_signal = pd.Series(base_signal, index=candles.index)

    # Divergence detection, vectorized equivalent of compute()'s rolling-window scan.
    window = period * 2
    high = candles['high'].astype(float)
    low = candles['low'].astype(float)

    # Relative position (0..window-1) of the rolling max/min within each trailing window.
    high_argmax_rel = high.rolling(window).apply(np.argmax, raw=True)
    rsi_argmax_rel = rsi.rolling(window).apply(np.argmax, raw=True)
    low_argmin_rel = low.rolling(window).apply(np.argmin, raw=True)
    rsi_argmin_rel = rsi.rolling(window).apply(np.argmin, raw=True)

    window_high_max = high.rolling(window).max()
    window_low_min = low.rolling(window).min()

    enough_data = candles['high'].expanding().count() >= window

    bearish_divergence = (
        enough_data
        & (high_argmax_rel > rsi_argmax_rel)
        & (high >= window_high_max * 0.98)
    )
    bullish_divergence_raw = (
        enough_data
        & (low_argmin_rel > rsi_argmin_rel)
        & (low <= window_low_min * 1.02)
    )
    # Scalar code is `if bearish ... elif bullish ...` on a single divergence value per
    # bar: bearish takes precedence when both conditions hold on the same bar.
    bullish_divergence = bullish_divergence_raw & ~bearish_divergence

    # Boost logic from to_signal(): bullish boosts positive signals, bearish boosts negative.
    signal = base_signal.where(
        ~(bullish_divergence & (base_signal > 0)), (base_signal * 1.3).clip(upper=1.0)
    )
    signal = signal.where(
        ~(bearish_divergence & (signal < 0)), (signal * 1.3).clip(lower=-1.0)
    )

    # Insufficient data (warm-up) -> neutral, matching to_signal()'s explicit check.
    signal = signal.where(rsi.notna(), 0.0)

    return signal.clip(-1.0, 1.0)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate RSI indicator values.

    RSI calculation:
    1. Calculate price changes (delta = close[i] - close[i-1])
    2. Separate gains (positive deltas) and losses (negative deltas)
    3. Calculate average gain and average loss using EMA
    4. Calculate RS = average gain / average loss
    5. Calculate RSI = 100 - (100 / (1 + RS))

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): RSI period (default: 14)
            - overbought (float): Overbought threshold (default: 70)
            - oversold (float): Oversold threshold (default: 30)

    Returns:
        IndicatorResult containing:
            - rsi: Current RSI value (0-100)
            - zone: Current zone ('overbought' | 'oversold' | 'neutral')
            - divergence: Optional divergence signal

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 14)
    overbought = params.get('overbought', 70.0)
    oversold = params.get('oversold', 30.0)

    series = compute_series(candles, params)
    rsi = series['rsi']
    avg_gain = series['avg_gain']
    avg_loss = series['avg_loss']

    # Get current RSI value
    current_rsi = rsi.iloc[-1]

    # Determine zone
    if pd.isna(current_rsi):
        zone = 'insufficient_data'
    elif current_rsi >= overbought:
        zone = 'overbought'
    elif current_rsi <= oversold:
        zone = 'oversold'
    else:
        zone = 'neutral'

    # Check for divergence (price makes new high/low but RSI doesn't)
    divergence = None
    if len(candles) >= period * 2 and not pd.isna(current_rsi):
        recent_candles = candles.tail(period * 2)
        recent_rsi = rsi.tail(period * 2)

        # Find price peaks and troughs
        price_high_idx = recent_candles['high'].idxmax()
        price_low_idx = recent_candles['low'].idxmin()
        rsi_high_idx = recent_rsi.idxmax()
        rsi_low_idx = recent_rsi.idxmin()

        # Check for bearish divergence (price higher high, RSI lower high)
        # Convert Decimal to float for comparison
        if (price_high_idx > rsi_high_idx and
                float(recent_candles['high'].iloc[-1]) >= float(recent_candles['high'].max()) * 0.98):
            divergence = 'bearish'

        # Check for bullish divergence (price lower low, RSI higher low)
        # Convert Decimal to float for comparison
        elif (price_low_idx > rsi_low_idx and
              float(recent_candles['low'].iloc[-1]) <= float(recent_candles['low'].min()) * 1.02):
            divergence = 'bullish'

    result = IndicatorResult(
        values={
            'rsi': float(current_rsi) if not pd.isna(current_rsi) else None,
            'zone': zone,
            'avg_gain': float(avg_gain.iloc[-1]) if not pd.isna(avg_gain.iloc[-1]) else None,
            'avg_loss': float(avg_loss.iloc[-1]) if not pd.isna(avg_loss.iloc[-1]) else None,
        },
        metadata={
            'period': period,
            'overbought': overbought,
            'oversold': oversold,
            'divergence': divergence,
        }
    )

    logger.debug(
        "RSI computed",
        extra={
            'period': period,
            'rsi': result.values['rsi'],
            'zone': zone,
            'divergence': divergence,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert RSI values to normalized signal.

    Signal logic (contrarian):
    - RSI in oversold zone (<30): Bullish signal (buy opportunity)
    - RSI in neutral zone (30-70): Weak signal near zero
    - RSI in overbought zone (>70): Bearish signal (sell opportunity)
    - Divergences strengthen signals

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (deeply oversold)
        - 0: Neutral (RSI ≈ 50)
        - -1: Strong bearish (deeply overbought)
    """
    rsi = values.values.get('rsi')
    zone = values.values.get('zone')
    divergence = values.metadata.get('divergence') if values.metadata else None
    overbought = values.metadata.get('overbought', 70.0) if values.metadata else 70.0
    oversold = values.metadata.get('oversold', 30.0) if values.metadata else 30.0

    # Handle missing data
    if rsi is None or zone == 'insufficient_data':
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Normalize using oscillator utility (contrarian interpretation)
    signal_value = normalize_oscillator(
        value=rsi,
        neutral=50.0,
        overbought=overbought,
        oversold=oversold,
    )

    # Build metadata
    metadata: Dict[str, Any] = {
        'zone': zone,
        'rsi': rsi,
    }

    # Determine reason
    reason_parts = []

    # Factor 1: Zone
    if zone == 'oversold':
        reason_parts.append('oversold_bullish')
    elif zone == 'overbought':
        reason_parts.append('overbought_bearish')
    else:
        reason_parts.append('neutral')

    # Factor 2: Divergence
    if divergence:
        metadata['divergence'] = divergence
        if divergence == 'bullish':
            reason_parts.append('bullish_divergence')
            # Boost bullish signal
            if signal_value > 0:
                signal_value = min(1.0, signal_value * 1.3)
        elif divergence == 'bearish':
            reason_parts.append('bearish_divergence')
            # Boost bearish signal
            if signal_value < 0:
                signal_value = max(-1.0, signal_value * 1.3)

    metadata['reason'] = '_'.join(reason_parts)

    # Add context about RSI value ranges
    if rsi < 20:
        metadata['strength'] = 'extremely_oversold'
    elif rsi < oversold:
        metadata['strength'] = 'oversold'
    elif rsi > 80:
        metadata['strength'] = 'extremely_overbought'
    elif rsi > overbought:
        metadata['strength'] = 'overbought'
    else:
        metadata['strength'] = 'normal'

    logger.debug(
        "RSI signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'rsi': rsi,
            'zone': zone,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
