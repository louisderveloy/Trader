"""
Common types and data structures for technical indicators.

This module defines the standard interfaces and types used across all indicators
to ensure consistency in the indicators engine.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol

import pandas as pd


@dataclass
class CandleData:
    """
    Standard OHLCV candle data structure.

    Attributes:
        timestamp: Candle opening timestamp (UTC)
        open: Opening price
        high: Highest price in period
        low: Lowest price in period
        close: Closing price
        volume: Trading volume in base currency
    """
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class IndicatorResult:
    """
    Result from an indicator's compute() function.

    Attributes:
        values: Dictionary of calculated indicator values (e.g., {"ema_50": 42000.5, "ema_200": 41000.2})
        metadata: Optional metadata about the calculation (e.g., {"insufficient_data": True})
    """
    values: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class IndicatorSignal:
    """
    Normalized signal from an indicator.

    Attributes:
        value: Signal strength in range [-1, 1] where:
              -1 = strong bearish signal
               0 = neutral signal
              +1 = strong bullish signal
        metadata: Optional metadata about the signal (e.g., {"reason": "overbought"})
    """
    value: float
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate that signal value is in valid range."""
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(
                f"Signal value must be in range [-1, 1], got {self.value}"
            )


class IndicatorProtocol(Protocol):
    """
    Protocol defining the standard interface for all indicators.

    All indicator modules must implement these two functions:
    - compute(candles, params): Calculate raw indicator values
    - to_signal(values): Convert raw values to normalized signal [-1, 1]
    """

    def compute(self, candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
        """
        Calculate indicator values from candle data.

        Args:
            candles: DataFrame with columns [timestamp, open, high, low, close, volume]
                    All price columns should be Decimal type
            params: Indicator-specific parameters (e.g., {"period": 14} for RSI)

        Returns:
            IndicatorResult with calculated values

        Raises:
            ValueError: If insufficient data or invalid parameters
        """
        ...

    def to_signal(self, values: IndicatorResult) -> IndicatorSignal:
        """
        Convert indicator values to normalized signal.

        Args:
            values: Result from compute() function

        Returns:
            IndicatorSignal with value in range [-1, 1]

        The normalization logic is indicator-specific:
        - Trend indicators (EMA): Use crossover direction
        - Oscillators (RSI): Use position relative to zones
        - Volatility (ATR): Use percentile-based normalization
        """
        ...


def validate_candles(candles: pd.DataFrame, min_periods: int = 1) -> None:
    """
    Validate that candle DataFrame has required structure and sufficient data.

    Args:
        candles: DataFrame to validate
        min_periods: Minimum number of candles required

    Raises:
        ValueError: If DataFrame is invalid or has insufficient data
    """
    required_columns = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
    missing_columns = required_columns - set(candles.columns)

    if missing_columns:
        raise ValueError(
            f"Candle DataFrame missing required columns: {missing_columns}"
        )

    if len(candles) < min_periods:
        raise ValueError(
            f"Insufficient candle data: need at least {min_periods} periods, got {len(candles)}"
        )

    # Check for NaN values in critical columns
    critical_columns = ['close', 'high', 'low']
    for col in critical_columns:
        if candles[col].isna().any():
            raise ValueError(f"Column '{col}' contains NaN values")
