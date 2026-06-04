"""Tests for EMA indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import ema
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestEMACompute:
    """Tests for EMA compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test EMA computation with default parameters."""
        params = {}  # Use defaults: fast=50, slow=200
        result = ema.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['ema_fast', 'ema_slow', 'crossover'])
        assert result.values['ema_fast'] is not None
        assert result.values['ema_slow'] is not None
        assert result.values['crossover'] in ['bullish', 'bearish', 'neutral', 'insufficient_data']

    def test_compute_with_custom_params(self, sample_candles):
        """Test EMA computation with custom parameters."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['fast_period'] == 20
        assert result.metadata['slow_period'] == 50
        assert result.values['ema_fast'] is not None
        assert result.values['ema_slow'] is not None

    def test_compute_uptrend_is_bullish(self, sample_candles):
        """Test that uptrend produces bullish crossover."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(sample_candles, params)

        # In uptrend, fast EMA should be above slow EMA
        assert result.values['ema_fast'] > result.values['ema_slow']
        assert result.values['crossover'] == 'bullish'

    def test_compute_downtrend_is_bearish(self, downtrend_candles):
        """Test that downtrend produces bearish crossover."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(downtrend_candles, params)

        # In downtrend, fast EMA should be below slow EMA
        assert result.values['ema_fast'] < result.values['ema_slow']
        assert result.values['crossover'] == 'bearish'

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'fast_period': 50, 'slow_period': 200}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            ema.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Fast period >= slow period
        with pytest.raises(ValueError, match="Fast period.*must be less than slow period"):
            ema.compute(sample_candles, {'fast_period': 200, 'slow_period': 50})

        # Negative periods
        with pytest.raises(ValueError, match="EMA periods must be positive"):
            ema.compute(sample_candles, {'fast_period': -10, 'slow_period': 50})


class TestEMAToSignal:
    """Tests for EMA to_signal function."""

    def test_to_signal_bullish_crossover(self, sample_candles):
        """Test signal generation for bullish crossover."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(sample_candles, params)
        signal = ema.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Uptrend should produce positive signal
        assert signal.value > 0

    def test_to_signal_bearish_crossover(self, downtrend_candles):
        """Test signal generation for bearish crossover."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(downtrend_candles, params)
        signal = ema.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Downtrend should produce negative signal
        assert signal.value < 0

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'fast_period': 20, 'slow_period': 50}
        result = ema.compute(sample_candles, params)
        signal = ema.to_signal(result)

        assert signal.metadata is not None
        assert 'crossover' in signal.metadata
        assert 'reason' in signal.metadata
        assert 'separation_percent' in signal.metadata

    def test_to_signal_range_clamped(self, sample_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'fast_period': 5, 'slow_period': 10}
        result = ema.compute(sample_candles, params)
        signal = ema.to_signal(result)

        assert -1.0 <= signal.value <= 1.0
