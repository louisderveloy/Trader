"""Tests for indicator types and utilities."""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators.types import (
    CandleData,
    IndicatorResult,
    IndicatorSignal,
    validate_candles,
)
from indicators.utils import (
    normalize_to_range,
    normalize_oscillator,
    normalize_crossover,
    calculate_ema,
    calculate_sma,
    safe_divide,
)


class TestIndicatorSignal:
    """Tests for IndicatorSignal validation."""

    def test_valid_signal_values(self):
        """Test that valid signal values are accepted."""
        # Boundary values
        assert IndicatorSignal(value=-1.0).value == -1.0
        assert IndicatorSignal(value=0.0).value == 0.0
        assert IndicatorSignal(value=1.0).value == 1.0

        # Middle values
        assert IndicatorSignal(value=0.5).value == 0.5
        assert IndicatorSignal(value=-0.5).value == -0.5

    def test_invalid_signal_values_raise_error(self):
        """Test that invalid signal values raise ValueError."""
        with pytest.raises(ValueError, match="Signal value must be in range"):
            IndicatorSignal(value=1.1)

        with pytest.raises(ValueError, match="Signal value must be in range"):
            IndicatorSignal(value=-1.1)

        with pytest.raises(ValueError, match="Signal value must be in range"):
            IndicatorSignal(value=2.0)

    def test_signal_with_metadata(self):
        """Test signal creation with metadata."""
        metadata = {'reason': 'test', 'value': 42}
        signal = IndicatorSignal(value=0.5, metadata=metadata)

        assert signal.metadata == metadata


class TestValidateCandles:
    """Tests for validate_candles function."""

    def test_valid_candles_pass(self, sample_candles):
        """Test that valid candles pass validation."""
        # Should not raise
        validate_candles(sample_candles, min_periods=10)

    def test_missing_columns_raise_error(self, sample_candles):
        """Test that missing columns raise ValueError."""
        incomplete = sample_candles.drop(columns=['volume'])

        with pytest.raises(ValueError, match="missing required columns"):
            validate_candles(incomplete)

    def test_insufficient_data_raises_error(self, sample_candles):
        """Test that insufficient data raises ValueError."""
        with pytest.raises(ValueError, match="Insufficient candle data"):
            validate_candles(sample_candles.head(5), min_periods=100)

    def test_nan_values_raise_error(self, sample_candles):
        """Test that NaN values in critical columns raise ValueError."""
        candles_with_nan = sample_candles.copy()
        candles_with_nan.loc[10, 'close'] = float('nan')

        with pytest.raises(ValueError, match="contains NaN values"):
            validate_candles(candles_with_nan)


class TestNormalizationUtils:
    """Tests for normalization utility functions."""

    def test_normalize_to_range(self):
        """Test linear normalization."""
        # Middle value
        assert normalize_to_range(50, 0, 100, -1, 1) == 0.0

        # Min value
        assert normalize_to_range(0, 0, 100, -1, 1) == -1.0

        # Max value
        assert normalize_to_range(100, 0, 100, -1, 1) == 1.0

        # Quarter
        assert normalize_to_range(25, 0, 100, -1, 1) == -0.5

        # Three quarters
        assert normalize_to_range(75, 0, 100, -1, 1) == 0.5

    def test_normalize_to_range_clamping(self):
        """Test that values outside range are clamped."""
        assert normalize_to_range(150, 0, 100, -1, 1) == 1.0
        assert normalize_to_range(-50, 0, 100, -1, 1) == -1.0

    def test_normalize_oscillator(self):
        """Test oscillator normalization (contrarian)."""
        # Oversold zone (30) should be bullish (positive)
        assert normalize_oscillator(30, neutral=50, overbought=70, oversold=30) > 0

        # Overbought zone (70) should be bearish (negative)
        assert normalize_oscillator(70, neutral=50, overbought=70, oversold=30) < 0

        # Neutral (50) should be near zero
        result = normalize_oscillator(50, neutral=50, overbought=70, oversold=30)
        assert abs(result) < 0.1

        # Extreme oversold should be strong bullish
        assert normalize_oscillator(10, neutral=50, overbought=70, oversold=30) >= 0.5

    def test_normalize_crossover(self):
        """Test crossover normalization."""
        # Fast above slow = positive
        assert normalize_crossover(110, 100) > 0

        # Fast below slow = negative
        assert normalize_crossover(90, 100) < 0

        # Equal = zero
        assert normalize_crossover(100, 100) == 0.0

    def test_safe_divide(self):
        """Test safe division."""
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(10, 0) == 0.0  # Default
        assert safe_divide(10, 0, default=99) == 99


class TestCalculationUtils:
    """Tests for calculation utility functions."""

    def test_calculate_ema(self):
        """Test EMA calculation."""
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        ema = calculate_ema(series, period=3)

        assert len(ema) == len(series)
        # EMA should smooth the series
        assert not ema.isna().all()
        # Last value should be influenced by recent values
        assert ema.iloc[-1] > series.iloc[0]

    def test_calculate_sma(self):
        """Test SMA calculation."""
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        sma = calculate_sma(series, period=3)

        assert len(sma) == len(series)
        # First period-1 values should be NaN
        assert sma.iloc[:2].isna().all()
        # SMA of [1,2,3] should be 2
        assert sma.iloc[2] == 2.0
        # SMA of [2,3,4] should be 3
        assert sma.iloc[3] == 3.0
