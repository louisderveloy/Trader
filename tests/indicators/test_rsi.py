"""Tests for RSI indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import rsi
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestRSICompute:
    """Tests for RSI compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test RSI computation with default parameters."""
        params = {}  # Use defaults: period=14, overbought=70, oversold=30
        result = rsi.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['rsi', 'zone'])
        assert result.values['rsi'] is not None
        assert 0 <= result.values['rsi'] <= 100

    def test_compute_with_custom_params(self, sample_candles):
        """Test RSI computation with custom parameters."""
        params = {'period': 10, 'overbought': 75, 'oversold': 25}
        result = rsi.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['period'] == 10
        assert result.metadata['overbought'] == 75
        assert result.metadata['oversold'] == 25

    def test_compute_uptrend_overbought(self, sample_candles):
        """Test that strong uptrend produces high RSI."""
        params = {'period': 14}
        result = rsi.compute(sample_candles, params)

        # Strong uptrend should have high RSI (>50 at minimum)
        assert result.values['rsi'] > 50

    def test_compute_downtrend_oversold(self, downtrend_candles):
        """Test that strong downtrend produces low RSI."""
        params = {'period': 14}
        result = rsi.compute(downtrend_candles, params)

        # Strong downtrend should have low RSI (<50 at minimum)
        assert result.values['rsi'] < 50

    def test_compute_zone_classification(self, sample_candles):
        """Test RSI zone classification."""
        params = {'period': 14}
        result = rsi.compute(sample_candles, params)

        assert result.values['zone'] in ['overbought', 'oversold', 'neutral', 'insufficient_data']

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'period': 14}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            rsi.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Invalid thresholds
        with pytest.raises(ValueError, match="Thresholds must satisfy"):
            rsi.compute(sample_candles, {'period': 14, 'overbought': 50, 'oversold': 60})

        # Negative period
        with pytest.raises(ValueError, match="RSI period must be a positive integer"):
            rsi.compute(sample_candles, {'period': -14})


class TestRSIToSignal:
    """Tests for RSI to_signal function."""

    def test_to_signal_contrarian_logic(self, sample_candles):
        """Test that RSI uses contrarian logic (overbought = bearish)."""
        params = {'period': 14}
        result = rsi.compute(sample_candles, params)
        signal = rsi.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # If RSI is high (overbought), signal should be negative (bearish)
        # If RSI is low (oversold), signal should be positive (bullish)
        if result.values['rsi'] > 70:
            assert signal.value < 0, "Overbought RSI should produce bearish signal"
        elif result.values['rsi'] < 30:
            assert signal.value > 0, "Oversold RSI should produce bullish signal"

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'period': 14}
        result = rsi.compute(sample_candles, params)
        signal = rsi.to_signal(result)

        assert signal.metadata is not None
        assert 'zone' in signal.metadata
        assert 'reason' in signal.metadata
        assert 'rsi' in signal.metadata
        assert 'strength' in signal.metadata

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'period': 14}
        result = rsi.compute(volatile_candles, params)
        signal = rsi.to_signal(result)

        assert -1.0 <= signal.value <= 1.0
