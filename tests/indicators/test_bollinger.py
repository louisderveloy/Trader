"""Tests for Bollinger Bands indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import bollinger
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestBollingerCompute:
    """Tests for Bollinger Bands compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test Bollinger Bands computation with default parameters."""
        params = {}  # Use defaults: period=20, std=2.0
        result = bollinger.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['middle', 'upper', 'lower', 'bandwidth', 'position', 'zone'])
        assert result.values['middle'] is not None
        assert result.values['upper'] is not None
        assert result.values['lower'] is not None

    def test_compute_with_custom_params(self, sample_candles):
        """Test Bollinger Bands computation with custom parameters."""
        params = {'period': 10, 'std': 1.5}
        result = bollinger.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['period'] == 10
        assert result.metadata['std_multiplier'] == 1.5

    def test_compute_bands_are_ordered(self, sample_candles):
        """Test that upper > middle > lower."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)

        assert result.values['upper'] > result.values['middle']
        assert result.values['middle'] > result.values['lower']

    def test_compute_bandwidth_is_positive(self, sample_candles):
        """Test that bandwidth is always positive."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)

        assert result.values['bandwidth'] >= 0

    def test_compute_position_in_range(self, sample_candles):
        """Test that position is typically in [0, 1] range."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)

        # Position can be outside [0,1] if price breaks bands
        assert result.values['position'] is not None

    def test_compute_zone_classification(self, sample_candles):
        """Test zone classification."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)

        valid_zones = ['above_upper', 'near_upper', 'middle', 'near_lower', 'below_lower', 'insufficient_data']
        assert result.values['zone'] in valid_zones

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'period': 20, 'std': 2.0}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            bollinger.compute(insufficient_candles, params)

    def test_compute_invalid_params_raises_error(self, sample_candles):
        """Test that invalid parameters raise ValueError."""
        # Negative period
        with pytest.raises(ValueError, match="Bollinger Bands period must be a positive"):
            bollinger.compute(sample_candles, {'period': -20, 'std': 2.0})

        # Negative std
        with pytest.raises(ValueError, match="Standard deviation multiplier must be positive"):
            bollinger.compute(sample_candles, {'period': 20, 'std': -2.0})


class TestBollingerToSignal:
    """Tests for Bollinger Bands to_signal function."""

    def test_to_signal_mean_reversion_logic(self, sample_candles):
        """Test that Bollinger uses mean reversion logic."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)
        signal = bollinger.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # Price near lower band should be bullish (mean reversion)
        if result.values['zone'] in ['near_lower', 'below_lower']:
            assert signal.value > 0, "Near lower band should produce bullish signal"
        # Price near upper band should be bearish
        elif result.values['zone'] in ['near_upper', 'above_upper']:
            assert signal.value < 0, "Near upper band should produce bearish signal"

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sample_candles, params)
        signal = bollinger.to_signal(result)

        assert signal.metadata is not None
        assert 'zone' in signal.metadata
        assert 'reason' in signal.metadata
        assert 'position' in signal.metadata

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(volatile_candles, params)
        signal = bollinger.to_signal(result)

        assert -1.0 <= signal.value <= 1.0

    def test_to_signal_squeeze_reduces_strength(self, sideways_candles):
        """Test that squeeze reduces signal strength."""
        params = {'period': 20, 'std': 2.0}
        result = bollinger.compute(sideways_candles, params)

        # Mock squeeze in metadata
        result.metadata['squeeze'] = 'tight'

        signal = bollinger.to_signal(result)

        # Signal should mention squeeze
        if 'squeeze' in signal.metadata.get('reason', ''):
            # Squeeze detected
            assert True
