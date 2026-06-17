"""Tests for OBV indicator."""

import sys
from pathlib import Path

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import obv
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestOBVCompute:
    """Tests for OBV compute function."""

    def test_compute_with_default_params(self, sample_candles):
        """Test OBV computation with default parameters."""
        params = {}  # Use default: smoothing_period=20
        result = obv.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert_result_has_values(result, ['obv', 'obv_ema', 'trend'])
        assert result.values['obv'] is not None

    def test_compute_with_custom_params(self, sample_candles):
        """Test OBV computation with custom parameters."""
        params = {'smoothing_period': 10}
        result = obv.compute(sample_candles, params)

        assert isinstance(result, IndicatorResult)
        assert result.metadata['smoothing_period'] == 10

    def test_compute_uptrend_rising_obv(self, sample_candles):
        """Test that uptrend produces rising OBV."""
        params = {'smoothing_period': 20}
        result = obv.compute(sample_candles, params)

        # In uptrend, OBV should be rising (above EMA)
        if result.values['obv_ema'] is not None:
            # Strong uptrend should have OBV > OBV_EMA
            assert result.values['trend'] in ['rising', 'flat']

    def test_compute_downtrend_falling_obv(self, downtrend_candles):
        """Test that downtrend produces falling OBV."""
        params = {'smoothing_period': 20}
        result = obv.compute(downtrend_candles, params)

        # In downtrend, OBV should be falling (below EMA)
        if result.values['obv_ema'] is not None:
            assert result.values['trend'] in ['falling', 'flat']

    def test_compute_trend_classification(self, sample_candles):
        """Test OBV trend classification."""
        params = {'smoothing_period': 20}
        result = obv.compute(sample_candles, params)

        assert result.values['trend'] in ['rising', 'falling', 'flat', 'insufficient_data']

    def test_compute_insufficient_data_raises_error(self, insufficient_candles):
        """Test that insufficient data raises ValueError."""
        params = {'smoothing_period': 20}

        with pytest.raises(ValueError, match="Insufficient candle data"):
            obv.compute(insufficient_candles, params)


class TestOBVToSignal:
    """Tests for OBV to_signal function."""

    def test_to_signal_rising_obv_bullish(self, sample_candles):
        """Test that rising OBV produces bullish signal."""
        params = {'smoothing_period': 20}
        result = obv.compute(sample_candles, params)
        signal = obv.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # Rising OBV should be bullish
        if result.values['trend'] == 'rising':
            assert signal.value > 0

    def test_to_signal_falling_obv_bearish(self, downtrend_candles):
        """Test that falling OBV produces bearish signal."""
        params = {'smoothing_period': 20}
        result = obv.compute(downtrend_candles, params)
        signal = obv.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)

        # Falling OBV should be bearish
        if result.values['trend'] == 'falling':
            assert signal.value < 0

    def test_to_signal_has_metadata(self, sample_candles):
        """Test that signal includes metadata."""
        params = {'smoothing_period': 20}
        result = obv.compute(sample_candles, params)
        signal = obv.to_signal(result)

        assert signal.metadata is not None
        assert 'trend' in signal.metadata
        assert 'reason' in signal.metadata

    def test_to_signal_range_clamped(self, volatile_candles):
        """Test that signal value is always in [-1, 1] range."""
        params = {'smoothing_period': 20}
        result = obv.compute(volatile_candles, params)
        signal = obv.to_signal(result)

        assert -1.0 <= signal.value <= 1.0

    def test_to_signal_divergence_boost(self, sample_candles):
        """Test that divergence boosts signal strength."""
        params = {'smoothing_period': 20}
        result = obv.compute(sample_candles, params)

        # Mock a divergence
        result.metadata['divergence'] = 'bullish'

        signal = obv.to_signal(result)

        # Signal should be strongly bullish with bullish divergence
        assert signal.value > 0
        assert 'divergence' in signal.metadata.get('reason', '')

    def test_to_signal_divergence_boost_stays_clamped(self):
        """Regression: a strongly negative base + bullish divergence (and the
        symmetric positive + bearish case) must stay within [-1, 1].

        The divergence boost previously clamped only one bound, so a base signal
        of -1.0 with bullish divergence produced -1.2, which IndicatorSignal
        rejects (caught upstream as a spurious "compute failed" + neutral signal).
        """
        # Base signal_value = (obv - obv_ema) / abs(obv_ema) / 0.05, clamped.
        # obv far below ema → base clamps to -1.0; bullish divergence → -1.0*1.5+0.3.
        bullish_on_negative = IndicatorResult(
            values={'obv': -1000.0, 'obv_ema': 1000.0, 'trend': 'falling'},
            metadata={'divergence': 'bullish'},
        )
        signal = obv.to_signal(bullish_on_negative)
        assert -1.0 <= signal.value <= 1.0

        # Symmetric: obv far above ema → base +1.0; bearish divergence → 1.0*1.5-0.3.
        bearish_on_positive = IndicatorResult(
            values={'obv': 1000.0, 'obv_ema': 1.0, 'trend': 'rising'},
            metadata={'divergence': 'bearish'},
        )
        signal = obv.to_signal(bearish_on_positive)
        assert -1.0 <= signal.value <= 1.0
