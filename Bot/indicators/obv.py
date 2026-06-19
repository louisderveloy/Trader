"""
OBV (On Balance Volume) indicator.

OBV is a cumulative volume-based indicator that tracks buying and selling pressure.
The principle is:
- When price closes higher than previous close: Add volume to OBV
- When price closes lower than previous close: Subtract volume from OBV
- When price closes unchanged: OBV unchanged

OBV is used to confirm trends:
- Rising OBV + rising price: Bullish trend confirmed
- Falling OBV + falling price: Bearish trend confirmed
- Divergence between price and OBV: Potential trend reversal

Since OBV is a cumulative value without absolute meaning, we normalize
it using its trend (EMA-based) and recent range.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import calculate_ema, normalize_percentile

logger = logging.getLogger(__name__)


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate OBV and its smoothed EMA for every bar (vectorized).

    This is the single source of truth for OBV raw values: ``compute()`` (live, scalar)
    slices the last row, and ``signal_series()`` (vectorbt backtest) consumes the full
    series, so both paths can never drift from each other.

    OBV is a cumulative sum: starting from the first bar's volume, each subsequent bar
    adds volume if price rose, subtracts volume if price fell, and leaves OBV unchanged
    if price was flat. This is equivalent to
    ``volume.iloc[0] + (sign(close.diff()) * volume).cumsum()`` once the first (NaN-diff)
    bar's contribution is zeroed out.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary (no parameters for OBV, but accepts optional smoothing period)
            - smoothing_period (int): EMA period for OBV smoothing (default: 20)

    Returns:
        DataFrame indexed like ``candles`` with columns ``obv``, ``obv_ema``
        (``obv_ema`` is NaN for the warm-up bars before it has enough history).

    Raises:
        ValueError: If insufficient candle data
    """
    # Get parameters with defaults
    smoothing_period = params.get('smoothing_period', 20)

    # Validate sufficient data
    min_periods = smoothing_period + 1
    validate_candles(candles, min_periods=min_periods)

    # Calculate OBV
    close = candles['close'].astype(float)
    volume = candles['volume'].astype(float)

    # Price change direction
    price_change = close.diff()

    # OBV calculation (vectorized cumulative sum, equivalent to the original
    # sequential loop: obv[0] = volume[0], then obv[i] = obv[i-1] +/- volume[i]
    # depending on the sign of price_change[i] (unchanged if flat).
    signed_volume = np.sign(price_change) * volume
    signed_volume.iloc[0] = 0.0  # price_change.iloc[0] is NaN/unused; baseline is volume[0]
    obv = volume.iloc[0] + signed_volume.cumsum()

    # Calculate smoothed OBV (EMA)
    obv_ema = calculate_ema(obv, smoothing_period)

    return pd.DataFrame({'obv': obv, 'obv_ema': obv_ema}, index=candles.index)


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized OBV signal for every bar (vectorized equivalent of
    ``to_signal()``), including the divergence boost.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    smoothing_period = params.get('smoothing_period', 20)

    series = compute_series(candles, params)
    obv = series['obv']
    obv_ema = series['obv_ema']

    # Same formula as to_signal()'s base signal, vectorized: pct diff / 5% threshold, clipped.
    percent_diff = (obv - obv_ema) / obv_ema.abs().replace(0, np.nan)
    base_signal = (percent_diff / 0.05).clip(-1.0, 1.0).fillna(0.0)

    # Divergence detection, vectorized equivalent of compute()'s rolling-window scan.
    window = smoothing_period * 2
    high = candles['high'].astype(float)
    low = candles['low'].astype(float)

    # Relative position (0..window-1) of the rolling max/min within each trailing window.
    high_argmax_rel = high.rolling(window).apply(np.argmax, raw=True)
    obv_argmax_rel = obv.rolling(window).apply(np.argmax, raw=True)
    low_argmin_rel = low.rolling(window).apply(np.argmin, raw=True)
    obv_argmin_rel = obv.rolling(window).apply(np.argmin, raw=True)

    window_high_max = high.rolling(window).max()
    window_low_min = low.rolling(window).min()

    enough_data = candles['high'].expanding().count() >= window

    bearish_divergence = (
        enough_data
        & (high_argmax_rel > obv_argmax_rel)
        & (high >= window_high_max * 0.99)
    )
    bullish_divergence = (
        enough_data
        & (low_argmin_rel > obv_argmin_rel)
        & (low <= window_low_min * 1.01)
    )

    # Boost logic from to_signal(): unconditional additive offset (no sign gate),
    # applied whenever that divergence type is detected.
    signal = base_signal.where(~bullish_divergence, (base_signal * 1.5 + 0.3).clip(-1.0, 1.0))
    signal = signal.where(~bearish_divergence, (signal * 1.5 - 0.3).clip(-1.0, 1.0))

    # Insufficient data (warm-up) -> neutral, matching to_signal()'s explicit check.
    signal = signal.where(obv_ema.notna(), 0.0)

    return signal.clip(-1.0, 1.0)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate OBV indicator values.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary (no parameters for OBV, but accepts optional smoothing period)
            - smoothing_period (int): EMA period for OBV smoothing (default: 20)

    Returns:
        IndicatorResult containing:
            - obv: Current OBV value
            - obv_ema: Smoothed OBV (EMA)
            - trend: OBV trend ('rising' | 'falling' | 'flat')
            - divergence: Price/OBV divergence if detected

    Raises:
        ValueError: If insufficient candle data
    """
    # Get parameters with defaults
    smoothing_period = params.get('smoothing_period', 20)

    series = compute_series(candles, params)
    obv = series['obv']
    obv_ema = series['obv_ema']

    # Get current values
    current_obv = obv.iloc[-1]
    current_obv_ema = obv_ema.iloc[-1]

    # Determine trend (compare OBV to its EMA)
    if pd.isna(current_obv_ema):
        trend = 'insufficient_data'
    elif current_obv > current_obv_ema * 1.01:  # 1% above EMA
        trend = 'rising'
    elif current_obv < current_obv_ema * 0.99:  # 1% below EMA
        trend = 'falling'
    else:
        trend = 'flat'

    # Check for divergence (price and OBV moving in opposite directions)
    divergence = None
    if len(candles) >= smoothing_period * 2:
        recent_candles = candles.tail(smoothing_period * 2)
        recent_obv = obv.tail(smoothing_period * 2)

        # Find price and OBV peaks
        price_peak_idx = recent_candles['high'].idxmax()
        obv_peak_idx = recent_obv.idxmax()
        price_trough_idx = recent_candles['low'].idxmin()
        obv_trough_idx = recent_obv.idxmin()

        # Bearish divergence: price makes higher high, OBV makes lower high
        # Convert Decimal to float for comparison
        if (price_peak_idx > obv_peak_idx and
                float(recent_candles['high'].iloc[-1]) >= float(recent_candles['high'].max()) * 0.99):
            divergence = 'bearish'

        # Bullish divergence: price makes lower low, OBV makes higher low
        # Convert Decimal to float for comparison
        elif (price_trough_idx > obv_trough_idx and
              float(recent_candles['low'].iloc[-1]) <= float(recent_candles['low'].min()) * 1.01):
            divergence = 'bullish'

    result = IndicatorResult(
        values={
            'obv': float(current_obv),
            'obv_ema': float(current_obv_ema) if not pd.isna(current_obv_ema) else None,
            'trend': trend,
        },
        metadata={
            'smoothing_period': smoothing_period,
            'divergence': divergence,
        }
    )

    logger.debug(
        "OBV computed",
        extra={
            'smoothing_period': smoothing_period,
            'obv': current_obv,
            'obv_ema': current_obv_ema,
            'trend': trend,
            'divergence': divergence,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert OBV values to normalized signal.

    Signal logic:
    - Rising OBV (above EMA): Bullish (accumulation)
    - Falling OBV (below EMA): Bearish (distribution)
    - Divergences strengthen signals
    - Signal strength based on OBV's position relative to recent range

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (rising OBV, bullish divergence)
        - 0: Neutral (flat OBV)
        - -1: Strong bearish (falling OBV, bearish divergence)
    """
    obv = values.values.get('obv')
    obv_ema = values.values.get('obv_ema')
    trend = values.values.get('trend')
    divergence = values.metadata.get('divergence') if values.metadata else None

    # Handle missing data
    if obv is None or trend == 'insufficient_data' or obv_ema is None:
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Calculate base signal from OBV position relative to EMA
    # OBV > EMA: positive (accumulation)
    # OBV < EMA: negative (distribution)
    if obv_ema != 0:
        percent_diff = (obv - obv_ema) / abs(obv_ema)
        # Normalize using 5% threshold (OBV 5% above EMA = strong signal)
        signal_value = percent_diff / 0.05
        signal_value = max(-1.0, min(1.0, signal_value))
    else:
        signal_value = 0.0

    # Build metadata
    metadata: Dict[str, Any] = {
        'trend': trend,
        'obv_to_ema_ratio': (obv / obv_ema) if obv_ema != 0 else 1.0,
    }

    # Determine reason
    reason_parts = []

    # Factor 1: Trend
    if trend == 'rising':
        reason_parts.append('accumulation')
    elif trend == 'falling':
        reason_parts.append('distribution')
    else:
        reason_parts.append('flat')

    # Factor 2: Divergence (strongest signal)
    if divergence:
        metadata['divergence'] = divergence
        if divergence == 'bullish':
            reason_parts.append('bullish_divergence')
            # Strong boost for bullish divergence. Clamp both bounds: a strongly
            # negative base (down to -1.0) would otherwise yield -1.2 here, which
            # violates the [-1, 1] IndicatorSignal contract.
            signal_value = max(-1.0, min(1.0, signal_value * 1.5 + 0.3))
        elif divergence == 'bearish':
            reason_parts.append('bearish_divergence')
            # Strong boost for bearish divergence. Clamp both bounds: a strongly
            # positive base (up to 1.0) would otherwise yield 1.2 here.
            signal_value = max(-1.0, min(1.0, signal_value * 1.5 - 0.3))

    metadata['reason'] = '_'.join(reason_parts) if reason_parts else 'neutral'

    logger.debug(
        "OBV signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'trend': trend,
            'divergence': divergence,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
