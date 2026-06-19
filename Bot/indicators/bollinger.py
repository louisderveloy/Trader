"""
Bollinger Bands indicator.

Bollinger Bands consist of three lines:
- Middle band: Simple Moving Average (SMA)
- Upper band: SMA + (standard deviation × multiplier)
- Lower band: SMA - (standard deviation × multiplier)

The bands expand and contract based on market volatility. Price position
relative to the bands provides trading signals:
- Price near lower band: Potentially oversold
- Price near upper band: Potentially overbought
- Price breaking out of bands: Strong momentum
- Band squeeze (narrow bands): Low volatility, potential breakout coming
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import calculate_sma, normalize_to_range, safe_divide

logger = logging.getLogger(__name__)


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate Bollinger Bands raw values for every bar (vectorized).

    This is the single source of truth for Bollinger Bands raw values: ``compute()``
    (live, scalar) slices the last row, and ``signal_series()`` (vectorbt backtest)
    consumes the full series, so both paths can never drift from each other.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): SMA period (default: 20)
            - std (float): Standard deviation multiplier (default: 2.0)

    Returns:
        DataFrame indexed like ``candles`` with columns ``close``, ``middle``, ``upper``,
        ``lower``, ``bandwidth`` (percentage) and ``position`` (0-1, NaN for warm-up bars).

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 20)
    std_multiplier = params.get('std', 2.0)

    # Validate parameters
    if period <= 0:
        raise ValueError("Bollinger Bands period must be a positive integer")

    if std_multiplier <= 0:
        raise ValueError("Standard deviation multiplier must be positive")

    # Validate sufficient data
    validate_candles(candles, min_periods=period)

    # Calculate middle band (SMA)
    close_prices = candles['close'].astype(float)
    middle_band = calculate_sma(close_prices, period)

    # Calculate standard deviation
    std_dev = close_prices.rolling(window=period).std()

    # Calculate upper and lower bands
    upper_band = middle_band + (std_dev * std_multiplier)
    lower_band = middle_band - (std_dev * std_multiplier)

    # Bandwidth = (upper - lower) / middle, as percentage (safe_divide default=0.0 equivalent)
    bandwidth = ((upper_band - lower_band) / middle_band.replace(0, np.nan)).fillna(0.0) * 100

    # Price position within bands (0 = lower band, 1 = upper band); 0.5 when band_range == 0
    band_range = upper_band - lower_band
    position = pd.Series(
        np.where(
            band_range > 0,
            (close_prices - lower_band) / band_range.replace(0, np.nan),
            0.5,
        ),
        index=candles.index,
    )
    # Warm-up bars (NaN bands) must stay NaN, not fall into the 0.5 "no range" case
    position = position.where(upper_band.notna() & lower_band.notna(), np.nan)

    return pd.DataFrame(
        {
            'close': close_prices,
            'middle': middle_band,
            'upper': upper_band,
            'lower': lower_band,
            'bandwidth': bandwidth,
            'position': position,
        },
        index=candles.index,
    )


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized Bollinger Bands signal for every bar (vectorized equivalent
    of ``to_signal()``), including the zone and squeeze adjustments.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    series = compute_series(candles, params)
    middle_band = series['middle']
    upper_band = series['upper']
    lower_band = series['lower']
    bandwidth = series['bandwidth']
    position = series['position']

    # Base signal: maps [0,1] to [1,-1], clamped
    signal_value = (1.0 - (position * 2.0)).clip(-1.0, 1.0)

    # Zone classification, vectorized from position thresholds (same order as compute())
    zone = pd.Series(
        np.select(
            [
                position >= 1.0,
                position >= 0.8,
                position <= 0.0,
                position <= 0.2,
            ],
            ['above_upper', 'near_upper', 'below_lower', 'near_lower'],
            default='middle',
        ),
        index=candles.index,
    )

    # Zone adjustment (step 1, sequential mutation of signal_value)
    signal_value = signal_value.where(
        zone != 'below_lower', (signal_value * 1.2).clip(upper=1.0)
    )
    signal_value = signal_value.where(
        zone != 'above_upper', (signal_value * 1.2).clip(lower=-1.0)
    )

    # Squeeze detection: requires at least 50 full trailing bars of bandwidth history,
    # matching compute()'s `if len(candles) >= period + 50` + `range(-50, 0)` loop.
    bw_ratio = bandwidth / 100  # convert back from percentage, matches current_bw_ratio
    avg_bw_ratio = bw_ratio.rolling(window=50, min_periods=50).mean()

    is_tight = (avg_bw_ratio > 0) & (bw_ratio < avg_bw_ratio * 0.7)
    is_wide = (avg_bw_ratio > 0) & (bw_ratio > avg_bw_ratio * 1.3)

    # Squeeze adjustment (step 2, applied after zone adjustment, same as to_signal())
    signal_value = signal_value.where(~is_tight, signal_value * 0.7)
    signal_value = signal_value.where(~is_wide, (signal_value * 1.1).clip(-1.0, 1.0))

    # Insufficient data (warm-up) -> neutral, matching to_signal()'s explicit check
    signal_value = signal_value.where(position.notna(), 0.0)

    return signal_value.clip(-1.0, 1.0)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate Bollinger Bands indicator values.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): SMA period (default: 20)
            - std (float): Standard deviation multiplier (default: 2.0)

    Returns:
        IndicatorResult containing:
            - middle: Middle band (SMA) value
            - upper: Upper band value
            - lower: Lower band value
            - bandwidth: Band width as percentage
            - position: Price position within bands (0-1)

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    period = params.get('period', 20)
    std_multiplier = params.get('std', 2.0)

    series = compute_series(candles, params)
    middle_band = series['middle']
    upper_band = series['upper']
    lower_band = series['lower']

    # Get current values
    current_close = series['close'].iloc[-1]
    current_middle = middle_band.iloc[-1]
    current_upper = upper_band.iloc[-1]
    current_lower = lower_band.iloc[-1]

    # Calculate bandwidth (volatility measure)
    # Bandwidth = (upper - lower) / middle
    bandwidth = safe_divide(
        current_upper - current_lower,
        current_middle,
        default=0.0
    ) * 100  # As percentage

    # Calculate price position within bands (0 = lower band, 1 = upper band)
    if not pd.isna(current_upper) and not pd.isna(current_lower):
        band_range = current_upper - current_lower
        if band_range > 0:
            position = (current_close - current_lower) / band_range
        else:
            position = 0.5  # Price at middle if no range
    else:
        position = None

    # Determine zone
    if position is None or pd.isna(current_middle):
        zone = 'insufficient_data'
    elif position >= 1.0:
        zone = 'above_upper'
    elif position >= 0.8:
        zone = 'near_upper'
    elif position <= 0.0:
        zone = 'below_lower'
    elif position <= 0.2:
        zone = 'near_lower'
    else:
        zone = 'middle'

    # Check for squeeze (narrow bands indicate low volatility)
    # Compare current bandwidth to its 50-period average
    squeeze = None
    if len(candles) >= period + 50:
        historical_bandwidth = []
        for i in range(-50, 0):
            hist_upper = upper_band.iloc[i]
            hist_lower = lower_band.iloc[i]
            hist_middle = middle_band.iloc[i]
            if not (pd.isna(hist_upper) or pd.isna(hist_lower) or pd.isna(hist_middle)):
                hist_bw = safe_divide(hist_upper - hist_lower, hist_middle, 0.0)
                historical_bandwidth.append(hist_bw)

        if historical_bandwidth:
            avg_bandwidth = sum(historical_bandwidth) / len(historical_bandwidth)
            current_bw_ratio = bandwidth / 100  # Convert back from percentage
            if avg_bandwidth > 0 and current_bw_ratio < avg_bandwidth * 0.7:
                squeeze = 'tight'
            elif avg_bandwidth > 0 and current_bw_ratio > avg_bandwidth * 1.3:
                squeeze = 'wide'

    result = IndicatorResult(
        values={
            'middle': float(current_middle) if not pd.isna(current_middle) else None,
            'upper': float(current_upper) if not pd.isna(current_upper) else None,
            'lower': float(current_lower) if not pd.isna(current_lower) else None,
            'bandwidth': bandwidth,
            'position': float(position) if position is not None else None,
            'zone': zone,
        },
        metadata={
            'period': period,
            'std_multiplier': std_multiplier,
            'current_price': float(current_close),
            'squeeze': squeeze,
        }
    )

    logger.debug(
        "Bollinger Bands computed",
        extra={
            'period': period,
            'middle': result.values['middle'],
            'upper': result.values['upper'],
            'lower': result.values['lower'],
            'bandwidth': bandwidth,
            'position': position,
            'zone': zone,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert Bollinger Bands values to normalized signal.

    Signal logic (mean reversion):
    - Price near lower band: Oversold, bullish signal
    - Price near upper band: Overbought, bearish signal
    - Price at middle: Neutral
    - Band squeeze: Reduced signal strength (consolidation)
    - Band expansion: Increased signal strength (trending)

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (price at or below lower band)
        - 0: Neutral (price at middle band)
        - -1: Strong bearish (price at or above upper band)
    """
    position = values.values.get('position')
    zone = values.values.get('zone')
    bandwidth = values.values.get('bandwidth', 0.0)
    squeeze = values.metadata.get('squeeze') if values.metadata else None

    # Handle missing data
    if position is None or zone == 'insufficient_data':
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Convert position to signal (contrarian/mean reversion)
    # position 0 (lower band) → +1 (bullish)
    # position 0.5 (middle) → 0 (neutral)
    # position 1 (upper band) → -1 (bearish)
    signal_value = 1.0 - (position * 2.0)  # Maps [0,1] to [1,-1]

    # Clamp to valid range (handles prices outside bands)
    signal_value = max(-1.0, min(1.0, signal_value))

    # Build metadata
    metadata: Dict[str, Any] = {
        'zone': zone,
        'position': position,
        'bandwidth': bandwidth,
    }

    # Determine reason
    reason_parts = []

    # Factor 1: Zone
    if zone == 'below_lower':
        reason_parts.append('below_lower_band_bullish')
        # Strong bullish signal
        signal_value = min(1.0, signal_value * 1.2)
    elif zone == 'near_lower':
        reason_parts.append('near_lower_band_bullish')
    elif zone == 'above_upper':
        reason_parts.append('above_upper_band_bearish')
        # Strong bearish signal
        signal_value = max(-1.0, signal_value * 1.2)
    elif zone == 'near_upper':
        reason_parts.append('near_upper_band_bearish')
    else:
        reason_parts.append('middle_zone')

    # Factor 2: Squeeze (low volatility reduces confidence)
    if squeeze:
        metadata['squeeze'] = squeeze
        if squeeze == 'tight':
            reason_parts.append('squeeze_consolidation')
            # Reduce signal strength during squeeze
            signal_value = signal_value * 0.7
        elif squeeze == 'wide':
            reason_parts.append('expansion_trending')
            # Increase signal strength during expansion
            signal_value = signal_value * 1.1
            signal_value = max(-1.0, min(1.0, signal_value))

    metadata['reason'] = '_'.join(reason_parts) if reason_parts else 'neutral'

    logger.debug(
        "Bollinger Bands signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'position': position,
            'zone': zone,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
