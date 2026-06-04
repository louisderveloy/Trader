"""Tests for Fear & Greed Index indicator."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import fear_greed
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values


class TestFearGreedCompute:
    """Tests for Fear & Greed compute function."""

    @pytest.fixture
    def mock_api_response(self):
        """Mock API response."""
        return {
            'data': [{
                'value': '45',
                'value_classification': 'Fear',
                'timestamp': '1640000000'
            }]
        }

    @pytest.fixture
    def mock_extreme_fear_response(self):
        """Mock API response for extreme fear."""
        return {
            'data': [{
                'value': '15',
                'value_classification': 'Extreme Fear',
                'timestamp': '1640000000'
            }]
        }

    @pytest.fixture
    def mock_extreme_greed_response(self):
        """Mock API response for extreme greed."""
        return {
            'data': [{
                'value': '85',
                'value_classification': 'Extreme Greed',
                'timestamp': '1640000000'
            }]
        }

    def test_compute_with_mocked_api(self, sample_candles, mock_api_response):
        """Test Fear & Greed computation with mocked API."""
        with patch('indicators.fear_greed._fetch_fear_greed_index') as mock_fetch:
            mock_fetch.return_value = {
                'value': 45,
                'classification': 'Fear',
                'timestamp': 1640000000
            }

            params = {}
            result = fear_greed.compute(sample_candles, params)

            assert isinstance(result, IndicatorResult)
            assert_result_has_values(result, ['value', 'classification'])
            assert result.values['value'] == 45
            assert result.values['classification'] == 'Fear'
            assert result.metadata['fetch_failed'] is False

    def test_compute_api_failure_returns_neutral(self, sample_candles):
        """Test that API failure returns neutral value."""
        with patch('indicators.fear_greed._fetch_fear_greed_index') as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            params = {}
            result = fear_greed.compute(sample_candles, params)

            assert isinstance(result, IndicatorResult)
            # Should return neutral value (50) on error
            assert result.values['value'] == 50
            assert result.metadata['fetch_failed'] is True


class TestFearGreedToSignal:
    """Tests for Fear & Greed to_signal function."""

    def test_to_signal_extreme_fear_bullish(self):
        """Test that extreme fear produces bullish signal (contrarian)."""
        result = IndicatorResult(
            values={'value': 15, 'classification': 'Extreme Fear'},
            metadata={'fetch_failed': False, 'source': 'alternative.me'}
        )

        signal = fear_greed.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Extreme fear should be bullish (contrarian)
        assert signal.value > 0.5

    def test_to_signal_extreme_greed_bearish(self):
        """Test that extreme greed produces bearish signal (contrarian)."""
        result = IndicatorResult(
            values={'value': 85, 'classification': 'Extreme Greed'},
            metadata={'fetch_failed': False, 'source': 'alternative.me'}
        )

        signal = fear_greed.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        # Extreme greed should be bearish (contrarian)
        assert signal.value < -0.5

    def test_to_signal_neutral_is_zero(self):
        """Test that neutral value produces zero signal."""
        result = IndicatorResult(
            values={'value': 50, 'classification': 'Neutral'},
            metadata={'fetch_failed': False, 'source': 'alternative.me'}
        )

        signal = fear_greed.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert abs(signal.value) < 0.1  # Should be close to zero

    def test_to_signal_has_metadata(self):
        """Test that signal includes metadata."""
        result = IndicatorResult(
            values={'value': 45, 'classification': 'Fear'},
            metadata={'fetch_failed': False, 'source': 'alternative.me'}
        )

        signal = fear_greed.to_signal(result)

        assert signal.metadata is not None
        assert 'value' in signal.metadata
        assert 'classification' in signal.metadata
        assert 'reason' in signal.metadata
        assert 'interpretation' in signal.metadata

    def test_to_signal_range_clamped(self):
        """Test that signal value is always in [-1, 1] range."""
        # Test extreme values
        for value in [0, 25, 50, 75, 100]:
            result = IndicatorResult(
                values={'value': value, 'classification': 'Test'},
                metadata={'fetch_failed': False}
            )

            signal = fear_greed.to_signal(result)
            assert -1.0 <= signal.value <= 1.0

    def test_to_signal_api_failure_returns_neutral(self):
        """Test that API failure returns neutral signal."""
        result = IndicatorResult(
            values={'value': None, 'classification': 'unknown'},
            metadata={'fetch_failed': True}
        )

        signal = fear_greed.to_signal(result)

        assert signal.value == 0.0
        assert signal.metadata['reason'] == 'api_fetch_failed'
