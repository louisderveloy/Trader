"""Tests for ATR indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import atr
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestATRCompute:
    """Tests for ATR compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test ATR computation with default parameters."""
        params = {}  # Use default: period=14
        result = atr.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['atr', 'atr_percent', 'trend'])
        assert result.values['atr'] is not None
        assert result.values['atr'] > 0  # ATR should always be positive

    def test_compute_with_custom_params(self, sample_candles):
        """Test ATR computation with custom parameters."""
        params = {'period': 10}
        result = atr.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['period'] == 10

    def test_compute_atr_is_positive(self, sample_candles):
        """Test that ATR is always positive."""
        params = {'period': 14}
        result = atr.compute(sample_candles, params)

        assert result.values['atr'] > 0
        assert result.values['atr_percent'] >= 0

    def test_compute_volatile_has_higher_atr(self, sample_candles, volatile_candles):
        """Test that volatile candles have higher ATR."""
        params = {'period': 14}

        result_normal = atr.compute(sample_candles, params)
        result_volatile = atr.compute(volatile_candles, params)

        # Volatile candles should have higher ATR percentage
        assert result_volatile.values['atr_percent'] > result_normal.values['atr_percent']

    def test_compute_trend_classification(self, sample_candles):
        """Test ATR trend classification."""
        params = {'period': 14}
        result = atr.compute(sample_candles, params)

        assert result.values['trend'] in ['rising', 'falling', 'stable']

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'period': 14}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            atr.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Negative period
        with pytest.raises(ValueError, match="ATR period must be a positive integer"):
            atr.compute(sample_candles, {'period': -14})


class TestATRToSignal:
    """Tests for ATR to_signal function."""

    def test_to_signal_is_weak(self, sample_candles):
        """Test that ATR signal is weak (not directional)."""
        params = {'period': 14}
        result = atr.compute(sample_candles, params)
        signal = atr.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # ATR signal should be weak (between -0.3 and 0.3)
        assert -0.3 <= signal.value <= 0.3

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'period': 14}
        result = atr.compute(sample_candles, params)
        signal = atr.to_signal(result)

        assert signal.metadata is not None
        assert 'atr' in signal.metadata
        assert 'atr_percent' in signal.metadata
        assert 'trend' in signal.metadata
        assert 'note' in signal.metadata  # ATR note about being for risk management

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'period': 14}
        result = atr.compute(volatile_candles, params)
        signal = atr.to_signal(result)

        assert -1.0 <= signal.value <= 1.0

    def test_to_signal_high_volatility_slightly_bullish(self, volatile_candles):
        """Test that high volatility produces slightly positive signal."""
        params = {'period': 14}
        result = atr.compute(volatile_candles, params)

        # Mock high percentile rank
        result.metadata['percentile_rank'] = 0.85

        signal = atr.to_signal(result)

        # High volatility should be slightly bullish (momentum/breakout)
        assert signal.value >= 0
