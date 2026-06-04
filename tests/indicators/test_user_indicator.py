"""Tests for User Indicator."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import user_indicator
from indicators.types import IndicatorResult, IndicatorSignal
from tests.indicators.conftest import assert_signal_in_range, assert_result_has_values

# Skip database-related tests if db.models not available (Phase 1 not complete)
try:
    import db.models  # noqa: F401
    DB_MODELS_AVAILABLE = True
except ImportError:
    DB_MODELS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not DB_MODELS_AVAILABLE,
    reason="db.models not available yet (will be created in later phase)"
)


class MockUserIndicator:
    """Mock UserIndicator model."""

    def __init__(self, symbol, value, note, expires_at=None, is_active=True):
        self.symbol = symbol
        self.value = value
        self.note = note
        self.expires_at = expires_at
        self.is_active = is_active
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class TestUserIndicatorComputeAsync:
    """Tests for User Indicator compute_async function."""

    @pytest.mark.asyncio
    async def test_compute_async_with_active_indicator(self, sample_candles):
        """Test computation with active user indicator."""
        mock_db = AsyncMock()
        mock_result = MagicMock()

        # Create mock user indicator
        mock_user_ind = MockUserIndicator(
            symbol='BTCUSDT',
            value=0.75,
            note='Strong bullish outlook',
            expires_at=None
        )

        mock_result.scalar_one_or_none.return_value = mock_user_ind
        mock_db.execute.return_value = mock_result

        result = await user_indicator.compute_async(mock_db, 'BTCUSDT')

        assert isinstance(result, IndicatorResult)
        assert result.values['value'] == 0.75
        assert result.values['note'] == 'Strong bullish outlook'
        assert result.values['is_active'] is True

    @pytest.mark.asyncio
    async def test_compute_async_no_indicator_set(self, sample_candles):
        """Test computation when no user indicator is set."""
        mock_db = AsyncMock()
        mock_result = MagicMock()

        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await user_indicator.compute_async(mock_db, 'BTCUSDT')

        assert isinstance(result, IndicatorResult)
        assert result.values['value'] is None
        assert result.values['is_active'] is False
        assert result.metadata['reason'] == 'no_indicator_set'

    @pytest.mark.asyncio
    async def test_compute_async_expired_indicator(self, sample_candles):
        """Test computation with expired user indicator."""
        mock_db = AsyncMock()
        mock_result = MagicMock()

        # Create expired indicator
        mock_user_ind = MockUserIndicator(
            symbol='BTCUSDT',
            value=0.5,
            note='Old analysis',
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        )

        mock_result.scalar_one_or_none.return_value = mock_user_ind
        mock_db.execute.return_value = mock_result

        result = await user_indicator.compute_async(mock_db, 'BTCUSDT')

        assert isinstance(result, IndicatorResult)
        assert result.values['value'] is None
        assert result.values['is_active'] is False
        assert result.metadata['reason'] == 'expired'

    @pytest.mark.asyncio
    async def test_compute_async_database_error(self, sample_candles):
        """Test computation handles database errors gracefully."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database connection error")

        result = await user_indicator.compute_async(mock_db, 'BTCUSDT')

        assert isinstance(result, IndicatorResult)
        assert result.values['value'] is None
        assert result.values['is_active'] is False
        assert result.metadata['reason'] == 'database_error'


class TestUserIndicatorToSignal:
    """Tests for User Indicator to_signal function."""

    def test_to_signal_active_bullish_indicator(self):
        """Test signal generation for active bullish indicator."""
        result = IndicatorResult(
            values={
                'value': 0.8,
                'note': 'Strong bullish trend',
                'is_active': True,
                'expires_at': None
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert_signal_in_range(signal.value)
        assert signal.value == 0.8
        assert signal.metadata['user_note'] == 'Strong bullish trend'
        assert 'bullish' in signal.metadata['interpretation']

    def test_to_signal_active_bearish_indicator(self):
        """Test signal generation for active bearish indicator."""
        result = IndicatorResult(
            values={
                'value': -0.6,
                'note': 'Bearish reversal expected',
                'is_active': True,
                'expires_at': None
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert signal.value == -0.6
        assert 'bearish' in signal.metadata['interpretation']

    def test_to_signal_inactive_returns_neutral(self):
        """Test that inactive indicator returns neutral signal."""
        result = IndicatorResult(
            values={
                'value': None,
                'note': None,
                'is_active': False,
                'expires_at': None
            },
            metadata={'reason': 'no_indicator_set'}
        )

        signal = user_indicator.to_signal(result)

        assert isinstance(signal, IndicatorSignal)
        assert signal.value == 0.0
        assert signal.metadata['is_active'] is False

    def test_to_signal_range_clamping(self):
        """Test that out-of-range values are clamped."""
        # Value > 1.0
        result = IndicatorResult(
            values={
                'value': 1.5,  # Invalid, should be clamped
                'note': 'Test',
                'is_active': True,
                'expires_at': None
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert signal.value == 1.0  # Clamped to max

        # Value < -1.0
        result = IndicatorResult(
            values={
                'value': -1.5,  # Invalid, should be clamped
                'note': 'Test',
                'is_active': True,
                'expires_at': None
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert signal.value == -1.0  # Clamped to min

    def test_to_signal_has_metadata(self):
        """Test that signal includes metadata."""
        result = IndicatorResult(
            values={
                'value': 0.5,
                'note': 'Moderate bullish',
                'is_active': True,
                'expires_at': '2024-12-31T23:59:59'
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert signal.metadata is not None
        assert 'reason' in signal.metadata
        assert 'is_active' in signal.metadata
        assert 'user_note' in signal.metadata
        assert 'interpretation' in signal.metadata
        assert 'expires_at' in signal.metadata

    def test_to_signal_neutral_value(self):
        """Test signal for neutral user input."""
        result = IndicatorResult(
            values={
                'value': 0.0,
                'note': 'No strong opinion',
                'is_active': True,
                'expires_at': None
            },
            metadata={'reason': 'active'}
        )

        signal = user_indicator.to_signal(result)

        assert signal.value == 0.0
        assert 'neutral' in signal.metadata['interpretation']
