"""
Stochastic RSI indicator.

Stochastic RSI applies the Stochastic oscillator formula to RSI values instead of
price data. It's more sensitive than standard RSI and oscillates between 0 and 1.

The indicator produces two lines:
- %K: The Stochastic RSI value
- %D: SMA of %K (signal line)

Interpretation:
- Values near 1: Overbought
- Values near 0: Oversold
- %K crossing above %D: Bullish
- %K crossing below %D: Bearish
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from indicators.types import IndicatorResult, IndicatorSignal, validate_candles
from indicators.utils import calculate_sma, normalize_oscillator

logger = logging.getLogger(__name__)


def _calculate_rsi(close_prices: pd.Series, period: int) -> pd.Series:
    """Helper function to calculate RSI."""
    delta = close_prices.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Calculate Stochastic RSI %K/%D values for every bar (vectorized).

    This is the single source of truth for Stochastic RSI raw values: ``compute()``
    (live, scalar) slices the last row, and ``signal_series()`` (vectorbt backtest)
    consumes the full series, so both paths can never drift from each other.

    Stochastic RSI formula:
    1. Calculate RSI
    2. StochRSI = (RSI - RSI_min) / (RSI_max - RSI_min) over lookback period
    3. %K = SMA of StochRSI over K period
    4. %D = SMA of %K over D period

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): RSI period (default: 14)
            - k (int): %K smoothing period (default: 3)
            - d (int): %D smoothing period (default: 3)

    Returns:
        DataFrame indexed like ``candles`` with columns ``stoch_rsi``, ``k``, ``d``
        (NaN for the warm-up bars before each value has enough history).

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    # Get parameters with defaults
    rsi_period = params.get('period', 14)
    k_period = params.get('k', 3)
    d_period = params.get('d', 3)

    # Validate parameters
    if rsi_period <= 0 or k_period <= 0 or d_period <= 0:
        raise ValueError("Stochastic RSI periods must be positive integers")

    # Validate sufficient data
    min_periods = rsi_period * 2 + k_period + d_period
    validate_candles(candles, min_periods=min_periods)

    # Calculate RSI
    close_prices = candles['close'].astype(float)
    rsi = _calculate_rsi(close_prices, rsi_period)

    # Calculate Stochastic RSI
    # Use rolling window equal to RSI period
    rsi_min = rsi.rolling(window=rsi_period).min()
    rsi_max = rsi.rolling(window=rsi_period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-10)

    # Calculate %K (smoothed Stochastic RSI)
    k_line = calculate_sma(stoch_rsi, k_period)

    # Calculate %D (signal line - SMA of %K)
    d_line = calculate_sma(k_line, d_period)

    return pd.DataFrame(
        {'stoch_rsi': stoch_rsi, 'k': k_line, 'd': d_line}, index=candles.index
    )


def signal_series(candles: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Calculate the normalized Stochastic RSI signal for every bar (vectorized
    equivalent of ``to_signal()``), including the bullish/bearish crossover
    recency boost.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Same as ``compute_series()``

    Returns:
        Series indexed like ``candles`` with signal values in [-1, 1] (0.0 during warm-up).
    """
    series = compute_series(candles, params)
    k = series['k']
    d = series['d']

    # Same scaling as to_signal(): %K in [0, 1] -> [0, 100] for oscillator normalization.
    k_scaled = k * 100

    overbought = 80.0
    oversold = 20.0
    neutral = 50.0

    # Vectorized equivalent of normalize_oscillator(), replicating its piecewise-linear
    # branches and the normalize_to_range() clip(((v-a)/(b-a))*(d-c)+c, min(c,d), max(c,d)) formula.
    def _map(value: pd.Series, a: float, b: float, c: float, d_: float) -> pd.Series:
        normalized = (value - a) / (b - a) * (d_ - c) + c
        lo, hi = min(c, d_), max(c, d_)
        return normalized.clip(lower=lo, upper=hi)

    base_signal = pd.Series(
        np.select(
            [k_scaled <= oversold, k_scaled >= overbought],
            [
                _map(k_scaled, 0, oversold, 1.0, 0.5),
                _map(k_scaled, overbought, 100, -0.5, -1.0),
            ],
            default=np.where(
                k_scaled <= neutral,
                _map(k_scaled, oversold, neutral, 0.5, 0.0),
                _map(k_scaled, neutral, overbought, 0.0, -0.5),
            ),
        ),
        index=candles.index,
    )

    # Crossover detection (within last 3 transitions, matching compute()'s range(-3, 0) loop).
    bullish_cross = (k.shift(1) <= d.shift(1)) & (k > d)
    bearish_cross = (k.shift(1) >= d.shift(1)) & (k < d)
    recent_bullish = bullish_cross.rolling(3, min_periods=1).max().astype(bool)
    recent_bearish = bearish_cross.rolling(3, min_periods=1).max().astype(bool)

    # "in_oversold"/"in_overbought" are evaluated on the CURRENT bar's %K, matching
    # compute()'s `current_k` (always the latest bar) used inside the crossover dict.
    in_oversold = k <= 0.2
    in_overbought = k >= 0.8

    signal = base_signal.copy()

    # Bullish crossover boost: from_oversold -> x1.4 clamped to 1.0; elif base > 0 -> x1.2 clamped to 1.0.
    bullish_from_oversold = recent_bullish & in_oversold
    bullish_base_positive = recent_bullish & ~in_oversold & (base_signal > 0)
    signal = signal.where(~bullish_from_oversold, (base_signal * 1.4).clip(upper=1.0))
    signal = signal.where(~bullish_base_positive, (base_signal * 1.2).clip(upper=1.0))

    # Bearish crossover boost: from_overbought -> x1.4 clamped to -1.0; elif base < 0 -> x1.2 clamped to -1.0.
    bearish_from_overbought = recent_bearish & in_overbought
    bearish_base_negative = recent_bearish & ~in_overbought & (base_signal < 0)
    signal = signal.where(~bearish_from_overbought, (base_signal * 1.4).clip(lower=-1.0))
    signal = signal.where(~bearish_base_negative, (base_signal * 1.2).clip(lower=-1.0))

    # Insufficient data (warm-up) -> neutral, matching to_signal()'s explicit check.
    signal = signal.where(k.notna() & d.notna(), 0.0)

    return signal.clip(-1.0, 1.0)


def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """
    Calculate Stochastic RSI indicator values.

    Stochastic RSI formula:
    1. Calculate RSI
    2. StochRSI = (RSI - RSI_min) / (RSI_max - RSI_min) over lookback period
    3. %K = SMA of StochRSI over K period
    4. %D = SMA of %K over D period

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume]
        params: Dictionary with keys:
            - period (int): RSI period (default: 14)
            - k (int): %K smoothing period (default: 3)
            - d (int): %D smoothing period (default: 3)

    Returns:
        IndicatorResult containing:
            - stoch_rsi: Raw Stochastic RSI value (0-1)
            - k: %K line value (0-1)
            - d: %D line value (0-1)
            - crossover: Current state ('bullish' | 'bearish' | 'neutral')

    Raises:
        ValueError: If insufficient candle data or invalid parameters
    """
    rsi_period = params.get('period', 14)
    k_period = params.get('k', 3)
    d_period = params.get('d', 3)

    series = compute_series(candles, params)
    stoch_rsi = series['stoch_rsi']
    k_line = series['k']
    d_line = series['d']

    # Get current values
    current_stoch_rsi = stoch_rsi.iloc[-1]
    current_k = k_line.iloc[-1]
    current_d = d_line.iloc[-1]

    # Determine zone and crossover
    if pd.isna(current_k) or pd.isna(current_d):
        zone = 'insufficient_data'
        crossover = 'insufficient_data'
    else:
        # Determine zone based on %K
        if current_k >= 0.8:
            zone = 'overbought'
        elif current_k <= 0.2:
            zone = 'oversold'
        else:
            zone = 'neutral'

        # Determine crossover
        if current_k > current_d:
            crossover = 'bullish'
        elif current_k < current_d:
            crossover = 'bearish'
        else:
            crossover = 'neutral'

    # Check for recent crossover
    recent_crossover = None
    if len(k_line) >= 3 and len(d_line) >= 3:
        for i in range(-3, 0):
            if pd.isna(k_line.iloc[i]) or pd.isna(d_line.iloc[i]):
                continue
            if pd.isna(k_line.iloc[i-1]) or pd.isna(d_line.iloc[i-1]):
                continue

            # Bullish crossover
            if k_line.iloc[i-1] <= d_line.iloc[i-1] and k_line.iloc[i] > d_line.iloc[i]:
                recent_crossover = {
                    'type': 'bullish',
                    'candles_ago': abs(i),
                    'in_oversold': current_k <= 0.2
                }
                break
            # Bearish crossover
            elif k_line.iloc[i-1] >= d_line.iloc[i-1] and k_line.iloc[i] < d_line.iloc[i]:
                recent_crossover = {
                    'type': 'bearish',
                    'candles_ago': abs(i),
                    'in_overbought': current_k >= 0.8
                }
                break

    result = IndicatorResult(
        values={
            'stoch_rsi': float(current_stoch_rsi) if not pd.isna(current_stoch_rsi) else None,
            'k': float(current_k) if not pd.isna(current_k) else None,
            'd': float(current_d) if not pd.isna(current_d) else None,
            'zone': zone,
            'crossover': crossover,
        },
        metadata={
            'rsi_period': rsi_period,
            'k_period': k_period,
            'd_period': d_period,
            'recent_crossover': recent_crossover,
        }
    )

    logger.debug(
        "Stochastic RSI computed",
        extra={
            'rsi_period': rsi_period,
            'k': result.values['k'],
            'd': result.values['d'],
            'zone': zone,
            'crossover': crossover,
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert Stochastic RSI values to normalized signal.

    Signal logic (contrarian):
    - %K in oversold zone (<0.2): Bullish
    - %K in overbought zone (>0.8): Bearish
    - %K crossing above %D: Additional bullish confirmation
    - %K crossing below %D: Additional bearish confirmation
    - Crossovers in extreme zones are stronger signals

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Strong bullish (oversold with bullish crossover)
        - 0: Neutral
        - -1: Strong bearish (overbought with bearish crossover)
    """
    k = values.values.get('k')
    d = values.values.get('d')
    zone = values.values.get('zone')
    crossover = values.values.get('crossover')
    recent_crossover = values.metadata.get('recent_crossover') if values.metadata else None

    # Handle missing data
    if k is None or zone == 'insufficient_data':
        return IndicatorSignal(
            value=0.0,
            metadata={'reason': 'insufficient_data'}
        )

    # Convert %K from [0, 1] to [0, 100] for oscillator normalization
    k_scaled = k * 100

    # Normalize using contrarian logic
    signal_value = normalize_oscillator(
        value=k_scaled,
        neutral=50.0,
        overbought=80.0,
        oversold=20.0,
    )

    # Build metadata
    metadata: Dict[str, Any] = {
        'zone': zone,
        'crossover': crossover,
        'k': k,
        'd': d,
    }

    # Determine reason
    reason_parts = []

    # Factor 1: Zone
    if zone == 'oversold':
        reason_parts.append('oversold')
    elif zone == 'overbought':
        reason_parts.append('overbought')
    else:
        reason_parts.append('neutral_zone')

    # Factor 2: Recent crossover (strongest signal)
    if recent_crossover:
        metadata['recent_crossover'] = recent_crossover
        if recent_crossover['type'] == 'bullish':
            reason_parts.append('bullish_crossover')
            # Extra boost if crossover happened in oversold zone
            if recent_crossover.get('in_oversold'):
                reason_parts.append('from_oversold')
                signal_value = min(1.0, signal_value * 1.4)
            elif signal_value > 0:
                signal_value = min(1.0, signal_value * 1.2)
        elif recent_crossover['type'] == 'bearish':
            reason_parts.append('bearish_crossover')
            # Extra boost if crossover happened in overbought zone
            if recent_crossover.get('in_overbought'):
                reason_parts.append('from_overbought')
                signal_value = max(-1.0, signal_value * 1.4)
            elif signal_value < 0:
                signal_value = max(-1.0, signal_value * 1.2)

    # Factor 3: Current crossover state (if no recent crossover)
    elif crossover == 'bullish' and signal_value > 0:
        reason_parts.append('k_above_d')
    elif crossover == 'bearish' and signal_value < 0:
        reason_parts.append('k_below_d')

    metadata['reason'] = '_'.join(reason_parts) if reason_parts else 'neutral'

    logger.debug(
        "Stochastic RSI signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'k': k,
            'zone': zone,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
