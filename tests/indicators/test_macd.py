"""Tests for MACD indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import macd
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestMACDCompute:
    """Tests for MACD compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test MACD computation with default parameters."""
        params = {}  # Use defaults: fast=12, slow=26, signal=9
        result = macd.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['macd', 'signal', 'histogram', 'crossover'])
        assert result.values['macd'] is not None
        assert result.values['signal'] is not None
        assert result.values['histogram'] is not None

    def test_compute_with_custom_params(self, sample_candles):
        """Test MACD computation with custom parameters."""
        params = {'fast': 5, 'slow': 13, 'signal': 5}
        result = macd.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['fast_period'] == 5
        assert result.metadata['slow_period'] == 13
        assert result.metadata['signal_period'] == 5

    def test_compute_uptrend_is_bullish(self, sample_candles):
        """Test that uptrend produces bullish MACD."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(sample_candles, params)

        # In uptrend, MACD should be above signal line
        assert result.values['macd'] > result.values['signal']
        assert result.values['crossover'] == 'bullish'
        assert result.values['histogram'] > 0

    def test_compute_downtrend_is_bearish(self, downtrend_candles):
        """Test that downtrend produces bearish MACD."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(downtrend_candles, params)

        # In downtrend, MACD should be below signal line
        assert result.values['macd'] < result.values['signal']
        assert result.values['crossover'] == 'bearish'
        assert result.values['histogram'] < 0

    def test_compute_histogram_is_difference(self, sample_candles):
        """Test that histogram equals MACD - signal."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(sample_candles, params)

        # Histogram should be MACD - signal
        expected_histogram = result.values['macd'] - result.values['signal']
        assert abs(result.values['histogram'] - expected_histogram) < 0.0001

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            macd.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Fast >= slow
        with pytest.raises(ValueError, match="Fast period.*must be less than slow period"):
            macd.compute(sample_candles, {'fast': 26, 'slow': 12, 'signal': 9})

        # Negative periods
        with pytest.raises(ValueError, match="MACD periods must be positive"):
            macd.compute(sample_candles, {'fast': -12, 'slow': 26, 'signal': 9})


class TestMACDToSignal:
    """Tests for MACD to_signal function."""

    def test_to_signal_bullish_crossover(self, sample_candles):
        """Test signal generation for bullish crossover."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(sample_candles, params)
        signal = macd.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Uptrend should produce positive signal
        assert signal.value > 0

    def test_to_signal_bearish_crossover(self, downtrend_candles):
        """Test signal generation for bearish crossover."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(downtrend_candles, params)
        signal = macd.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Downtrend should produce negative signal
        assert signal.value < 0

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(sample_candles, params)
        signal = macd.to_signal(result)

        assert signal.metadata is not None
        assert 'crossover' in signal.metadata
        assert 'reason' in signal.metadata
        assert 'histogram' in signal.metadata

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'fast': 5, 'slow': 10, 'signal': 3}
        result = macd.compute(volatile_candles, params)
        signal = macd.to_signal(result)

        assert -1.0 <= signal.value <= 1.0

    def test_to_signal_recent_crossover_boost(self, sample_candles):
        """Test that recent crossovers boost signal strength."""
        params = {'fast': 12, 'slow': 26, 'signal': 9}
        result = macd.compute(sample_candles, params)

        # Mock a recent crossover in metadata
        result.metadata['recent_crossover'] = {'type': 'bullish', 'candles_ago': 1}

        signal = macd.to_signal(result)

        # Signal should mention crossover
        assert 'crossover' in signal.metadata.get('reason', '')
