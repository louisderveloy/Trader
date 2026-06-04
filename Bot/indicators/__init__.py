"""
Technical indicators module for crypto trading bot.

This module provides a collection of technical indicators for market analysis.
All indicators follow a standard interface:

- compute(candles, params) -> IndicatorResult: Calculate raw indicator values
- to_signal(values) -> IndicatorSignal: Convert to normalized signal [-1, 1]

Available indicators:
- EMA: Exponential Moving Average crossover
- MACD: Moving Average Convergence Divergence
- RSI: Relative Strength Index
- Stochastic RSI: Stochastic version of RSI
- Bollinger Bands: Price volatility bands
- ATR: Average True Range (volatility)
- OBV: On Balance Volume
- Fear & Greed Index: Market sentiment from alternative.me
- User Indicator: Manual user input from database

Example usage:
    >>> import pandas as pd
    >>> from indicators import ema, types
    >>>
    >>> # Prepare candle data
    >>> candles = pd.DataFrame({
    ...     'timestamp': [...],
    ...     'open': [...],
    ...     'close': [...],
    ...     # ... more columns
    ... })
    >>>
    >>> # Calculate indicator
    >>> params = {'fast_period': 50, 'slow_period': 200}
    >>> result = ema.compute(candles, params)
    >>> signal = ema.to_signal(result)
    >>>
    >>> print(f"Signal: {signal.value}")  # Value in [-1, 1]
"""

from indicators.types import (
    CandleData,
    IndicatorProtocol,
    IndicatorResult,
    IndicatorSignal,
    validate_candles,
)

__all__ = [
    # Core types
    "CandleData",
    "IndicatorProtocol",
    "IndicatorResult",
    "IndicatorSignal",
    "validate_candles",
    # Indicators (import modules, not functions, for cleaner API)
    "ema",
    "macd",
    "rsi",
    "stoch_rsi",
    "bollinger",
    "atr",
    "obv",
    "fear_greed",
    "user_indicator",
]
