"""
Pytest fixtures for indicator tests.

Provides reusable test data and helper functions.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest


@pytest.fixture
def sample_candles():
    """
    Generate sample OHLCV candle data for testing.

    Creates 300 candles with a simple uptrend pattern.
    """
    base_price = 40000.0
    num_candles = 300

    timestamps = [
        datetime(2024, 1, 1) + timedelta(minutes=15 * i)
        for i in range(num_candles)
    ]

    data = {
        'timestamp': timestamps,
        'open': [Decimal(str(base_price + i * 10)) for i in range(num_candles)],
        'high': [Decimal(str(base_price + i * 10 + 20)) for i in range(num_candles)],
        'low': [Decimal(str(base_price + i * 10 - 20)) for i in range(num_candles)],
        'close': [Decimal(str(base_price + i * 10 + 5)) for i in range(num_candles)],
        'volume': [Decimal('100.5') for _ in range(num_candles)],
    }

    return pd.DataFrame(data)


@pytest.fixture
def downtrend_candles():
    """
    Generate sample OHLCV candle data with downtrend.
    """
    base_price = 50000.0
    num_candles = 300

    timestamps = [
        datetime(2024, 1, 1) + timedelta(minutes=15 * i)
        for i in range(num_candles)
    ]

    data = {
        'timestamp': timestamps,
        'open': [Decimal(str(base_price - i * 10)) for i in range(num_candles)],
        'high': [Decimal(str(base_price - i * 10 + 20)) for i in range(num_candles)],
        'low': [Decimal(str(base_price - i * 10 - 20)) for i in range(num_candles)],
        'close': [Decimal(str(base_price - i * 10 - 5)) for i in range(num_candles)],
        'volume': [Decimal('100.5') for _ in range(num_candles)],
    }

    return pd.DataFrame(data)


@pytest.fixture
def sideways_candles():
    """
    Generate sample OHLCV candle data with sideways movement.
    """
    import math

    base_price = 45000.0
    num_candles = 300

    timestamps = [
        datetime(2024, 1, 1) + timedelta(minutes=15 * i)
        for i in range(num_candles)
    ]

    # Add small oscillation
    prices = [base_price + math.sin(i / 10) * 100 for i in range(num_candles)]

    data = {
        'timestamp': timestamps,
        'open': [Decimal(str(p)) for p in prices],
        'high': [Decimal(str(p + 50)) for p in prices],
        'low': [Decimal(str(p - 50)) for p in prices],
        'close': [Decimal(str(p + 10)) for p in prices],
        'volume': [Decimal('100.5') for _ in range(num_candles)],
    }

    return pd.DataFrame(data)


@pytest.fixture
def volatile_candles():
    """
    Generate sample OHLCV candle data with high volatility.
    """
    import random

    random.seed(42)
    base_price = 45000.0
    num_candles = 300

    timestamps = [
        datetime(2024, 1, 1) + timedelta(minutes=15 * i)
        for i in range(num_candles)
    ]

    prices = []
    current_price = base_price
    for _ in range(num_candles):
        change_percent = random.uniform(-0.03, 0.03)  # ±3% per candle
        current_price = current_price * (1 + change_percent)
        prices.append(current_price)

    data = {
        'timestamp': timestamps,
        'open': [Decimal(str(p)) for p in prices],
        'high': [Decimal(str(p * 1.01)) for p in prices],
        'low': [Decimal(str(p * 0.99)) for p in prices],
        'close': [Decimal(str(p * 1.005)) for p in prices],
        'volume': [Decimal(str(random.uniform(50, 150))) for _ in range(num_candles)],
    }

    return pd.DataFrame(data)


@pytest.fixture
def insufficient_candles():
    """
    Generate insufficient candle data (only 10 candles).
    """
    base_price = 40000.0
    num_candles = 10

    timestamps = [
        datetime(2024, 1, 1) + timedelta(minutes=15 * i)
        for i in range(num_candles)
    ]

    data = {
        'timestamp': timestamps,
        'open': [Decimal(str(base_price + i * 10)) for i in range(num_candles)],
        'high': [Decimal(str(base_price + i * 10 + 20)) for i in range(num_candles)],
        'low': [Decimal(str(base_price + i * 10 - 20)) for i in range(num_candles)],
        'close': [Decimal(str(base_price + i * 10 + 5)) for i in range(num_candles)],
        'volume': [Decimal('100.5') for _ in range(num_candles)],
    }

    return pd.DataFrame(data)


def assert_signal_in_range(signal_value: float):
    """Helper to assert signal is in valid [-1, 1] range."""
    assert -1.0 <= signal_value <= 1.0, f"Signal {signal_value} out of range [-1, 1]"


def assert_result_has_values(result, expected_keys):
    """Helper to assert IndicatorResult has expected value keys."""
    assert result.values is not None
    for key in expected_keys:
        assert key in result.values, f"Expected key '{key}' not in result.values"
