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
    _compute_vwap,
    _compute_rsi,
    _compute_atr,
    _compute_obv,
    _compute_macd,
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


# ==============================================================================
# Dedicated unit tests for standalone vectorized indicators
# ==============================================================================

def test_compute_rsi_monotonic_and_flat():
    """Verify RSI returns 100 for purely increasing, 0 for purely decreasing, 50 for flat."""
    # Purely increasing series
    close_up = pd.Series([10.0 + i for i in range(30)])
    rsi_up = _compute_rsi(close_up, length=14)
    assert rsi_up.iloc[-1] == 100.0
    assert not rsi_up.isna().any()

    # Purely decreasing series
    close_down = pd.Series([100.0 - i for i in range(30)])
    rsi_down = _compute_rsi(close_down, length=14)
    assert rsi_down.iloc[-1] == 0.0
    assert not rsi_down.isna().any()

    # Purely flat series
    close_flat = pd.Series([50.0] * 30)
    rsi_flat = _compute_rsi(close_flat, length=14)
    assert (rsi_flat == 50.0).all()


def test_compute_rsi_bounds_and_oscillations(sample_candles_df):
    """Verify RSI is strictly bounded in [0, 100] on realistic series."""
    rsi = _compute_rsi(sample_candles_df["close"], length=14)
    assert (rsi >= 0.0).all() and (rsi <= 100.0).all()
    assert not rsi.isna().any()


def test_compute_atr_constant_range_and_gap():
    """Verify ATR accurately computes True Range with Wilder's exponential smoothing."""
    # Flat price bar with constant high-low of 20.0
    n = 40
    highs = pd.Series([110.0] * n)
    lows = pd.Series([90.0] * n)
    closes = pd.Series([100.0] * n)

    atr = _compute_atr(highs, lows, closes, length=14)
    # TR is 20 on every bar, so ATR must be 20
    assert np.isclose(atr.iloc[-1], 20.0, atol=1e-4)

    # Test Gap Up: previous close = 100, next low = 110, next high = 120
    h_gap = pd.Series([100.0, 120.0])
    l_gap = pd.Series([95.0, 110.0])
    c_gap = pd.Series([100.0, 115.0])
    atr_gap = _compute_atr(h_gap, l_gap, c_gap, length=14)
    # For bar 1: TR = max(120 - 110, |120 - 100|, |110 - 100|) = 20.0
    assert atr_gap.iloc[1] > 0.0
    assert not atr_gap.isna().any()


def test_compute_vwap_weighted_calculation():
    """Verify VWAP equals sum(Typical Price * Volume) / sum(Volume)."""
    # Hand-crafted 2-bar case
    highs = pd.Series([110.0, 210.0])
    lows = pd.Series([90.0, 190.0])
    closes = pd.Series([100.0, 200.0])
    volumes = pd.Series([10.0, 30.0])

    # Bar 0: tp = 100.0, wp = 1000.0, cum_v = 10.0 -> vwap = 100.0
    # Bar 1: tp = 200.0, wp = 6000.0, cum_wp = 7000.0, cum_v = 40.0 -> vwap = 175.0
    vwap = _compute_vwap(highs, lows, closes, volumes)
    assert np.isclose(vwap.iloc[0], 100.0)
    assert np.isclose(vwap.iloc[1], 175.0)


def test_compute_vwap_with_daily_anchor():
    """Verify VWAP resets across midnight when DatetimeIndex is present."""
    times = pd.to_datetime([
        "2024-01-01 10:00:00",
        "2024-01-01 14:00:00",
        "2024-01-02 08:00:00",  # New day
        "2024-01-02 12:00:00",
    ])
    highs = pd.Series([105.0, 115.0, 205.0, 215.0], index=times)
    lows = pd.Series([95.0, 105.0, 195.0, 205.0], index=times)
    closes = pd.Series([100.0, 110.0, 200.0, 210.0], index=times)
    volumes = pd.Series([10.0, 10.0, 5.0, 15.0], index=times)

    vwap = _compute_vwap(highs, lows, closes, volumes)
    # Day 1: tp=[100, 110], wp=[1000, 1100], vol=[10, 10] -> cum_wp=2100, cum_v=20 -> vwap=105.0
    assert np.isclose(vwap.iloc[1], 105.0)
    # Day 2 resets: bar 2 tp=200, vol=5 -> vwap starts at 200.0
    assert np.isclose(vwap.iloc[2], 200.0)
    # Day 2 bar 3: tp=210, vol=15 -> cum_wp=1000 + 3150 = 4150, cum_v=20 -> vwap = 207.5
    assert np.isclose(vwap.iloc[3], 207.5)


def test_compute_obv_signed_volume_accumulation():
    """Verify On-Balance Volume accumulates volume based on price delta sign."""
    # Bar 0: initial 1.0 * 10 = 10
    # Bar 1: close 100 -> 105 (+5) -> add 20 -> 30
    # Bar 2: close 105 -> 102 (-3) -> sub 15 -> 15
    # Bar 3: close 102 -> 102 ( 0) -> unchanged -> 15
    # Bar 4: close 102 -> 110 (+8) -> add 30 -> 45
    closes = pd.Series([100.0, 105.0, 102.0, 102.0, 110.0])
    volumes = pd.Series([10.0, 20.0, 15.0, 5.0, 30.0])

    obv = _compute_obv(closes, volumes)
    assert obv.tolist() == [10.0, 30.0, 15.0, 15.0, 45.0]


def test_compute_macd_trend_and_flat():
    """Verify MACD line, signal line and histogram behavior on trend and flat data."""
    # Flat data -> EMA_fast == EMA_slow -> all lines 0
    close_flat = pd.Series([100.0] * 50)
    macd_line, macd_hist = _compute_macd(close_flat, fast=12, slow=26, signal=9)
    assert np.isclose(macd_line.iloc[-1], 0.0, atol=1e-5)
    assert np.isclose(macd_hist.iloc[-1], 0.0, atol=1e-5)

    # Monotonic uptrend -> EMA12 > EMA26 -> MACD line > 0
    close_up = pd.Series([50.0 + i * 2.0 for i in range(50)])
    macd_line_up, macd_hist_up = _compute_macd(close_up, fast=12, slow=26, signal=9)
    assert macd_line_up.iloc[-1] > 0.0
    assert not macd_line_up.isna().any()
    assert not macd_hist_up.isna().any()

