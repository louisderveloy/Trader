"""
Unit tests for predictive features pipeline and CandleMemoryBuffer.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytest

from strategy.features import (
    compute_predictive_features,
    CandleMemoryBuffer,
    FEATURE_COLUMNS,
    DEFAULT_NORM_WINDOW,
    DEFAULT_WINDOW_SIZE,
)


@pytest.fixture
def sample_candles_df() -> pd.DataFrame:
    """Generate realistic sample candle DataFrame."""
    np.random.seed(42)
    n = 280
    base_time = datetime(2024, 1, 1, 0, 0)
    times = [base_time + timedelta(minutes=15 * i) for i in range(n)]

    closes = 50000.0 + np.cumsum(np.random.randn(n) * 20)
    highs = closes + np.random.uniform(5, 50, n)
    lows = closes - np.random.uniform(5, 50, n)
    opens = closes + np.random.uniform(-10, 10, n)
    volumes = np.random.uniform(10, 100, n)

    return pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def test_compute_predictive_features_shape_and_columns(sample_candles_df):
    """Verify feature calculation outputs exact 11 columns with no NaNs."""
    feats = compute_predictive_features(sample_candles_df, norm_window=200)

    assert isinstance(feats, pd.DataFrame)
    assert list(feats.columns) == FEATURE_COLUMNS
    assert len(feats) == len(sample_candles_df)
    assert not feats.isna().any().any(), "Features contain NaNs"
    assert not np.isinf(feats.values).any(), "Features contain Infs"


def test_candle_memory_buffer_lifecycle(sample_candles_df):
    """Test CandleMemoryBuffer warm-up, updating, and tensor extraction."""
    candles_list = sample_candles_df.to_dict("records")

    buffer = CandleMemoryBuffer(norm_window=200, window_size=60)
    assert not buffer.is_warmed_up
    assert buffer.candle_count == 0

    # Warm up with first 260 candles
    buffer.warm_up(candles_list[:260])
    assert buffer.is_warmed_up
    assert buffer.candle_count == 260

    seq = buffer.get_latest_sequence()
    assert seq is not None
    assert seq.shape == (1, 60, 11)

    # Add a new closed candle
    new_candle = candles_list[260]
    is_new, seq2 = buffer.add_candle(new_candle)
    assert is_new is True
    assert seq2 is not None
    assert seq2.shape == (1, 60, 11)
    assert buffer.candle_count == 261

    # Update in-progress candle with identical time
    updated_candle = dict(new_candle)
    updated_candle["close"] += 50.0
    is_new2, seq3 = buffer.add_candle(updated_candle)
    assert is_new2 is False
    assert seq3 is not None
    assert buffer.candle_count == 261
