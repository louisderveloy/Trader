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

import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import normalize_oscillator, safe_divide

logger = logging.getLogger(__name__)


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
