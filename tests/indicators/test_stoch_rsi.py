"""Tests for Stochastic RSI indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import stoch_rsi
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestStochRSICompute:
    """Tests for Stochastic RSI compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test Stochastic RSI computation with default parameters."""
        params = {}  # Use defaults: period=14, k=3, d=3
        result = stoch_rsi.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['stoch_rsi', 'k', 'd', 'zone', 'crossover'])
        # K and D values should be in [0, 1] range
        if result.values['k'] is not None:
            assert 0 <= result.values['k'] <= 1
        if result.values['d'] is not None:
            assert 0 <= result.values['d'] <= 1

    def test_compute_with_custom_params(self, sample_candles):
        """Test Stochastic RSI computation with custom parameters."""
        params = {'period': 10, 'k': 2, 'd': 2}
        result = stoch_rsi.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['rsi_period'] == 10
        assert result.metadata['k_period'] == 2
        assert result.metadata['d_period'] == 2

    def test_compute_zone_classification(self, sample_candles):
        """Test Stochastic RSI zone classification."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(sample_candles, params)

        valid_zones = ['overbought', 'oversold', 'neutral', 'insufficient_data']
        assert result.values['zone'] in valid_zones

    def test_compute_crossover_classification(self, sample_candles):
        """Test Stochastic RSI crossover classification."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(sample_candles, params)

        valid_crossovers = ['bullish', 'bearish', 'neutral', 'insufficient_data']
        assert result.values['crossover'] in valid_crossovers

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'period': 14, 'k': 3, 'd': 3}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            stoch_rsi.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Negative periods
        with pytest.raises(ValueError, match="Stochastic RSI periods must be positive"):
            stoch_rsi.compute(sample_candles, {'period': -14, 'k': 3, 'd': 3})


class TestStochRSIToSignal:
    """Tests for Stochastic RSI to_signal function."""

    def test_to_signal_contrarian_logic(self, sample_candles):
        """Test that Stochastic RSI uses contrarian logic."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(sample_candles, params)
        signal = stoch_rsi.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # Oversold should be bullish, overbought should be bearish
        if result.values['zone'] == 'oversold':
            assert signal.value > 0, "Oversold should produce bullish signal"
        elif result.values['zone'] == 'overbought':
            assert signal.value < 0, "Overbought should produce bearish signal"

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(sample_candles, params)
        signal = stoch_rsi.to_signal(result)

        assert signal.metadata is not None
        assert 'zone' in signal.metadata
        assert 'crossover' in signal.metadata
        assert 'reason' in signal.metadata

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(volatile_candles, params)
        signal = stoch_rsi.to_signal(result)

        assert -1.0 <= signal.value <= 1.0

    def test_to_signal_crossover_in_extreme_zone_boost(self, sample_candles):
        """Test that crossovers in extreme zones get extra boost."""
        params = {'period': 14, 'k': 3, 'd': 3}
        result = stoch_rsi.compute(sample_candles, params)

        # Mock a bullish crossover in oversold zone
        result.metadata['recent_crossover'] = {
            'type': 'bullish',
            'candles_ago': 1,
            'in_oversold': True
        }

        signal = stoch_rsi.to_signal(result)

        # Should have strong bullish signal
        assert signal.value > 0
        assert 'crossover' in signal.metadata.get('reason', '')
