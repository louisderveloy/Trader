"""
Predictive features pipeline and candle memory buffer for ML trading engine.

Computes 11 normalized technical indicators matching the training pipeline:
- open_norm, high_norm, low_norm, close_norm, volume_norm, vwap_norm
- rsi_norm, atr_norm, obv_norm, macd_norm, macd_hist_norm

The CandleMemoryBuffer maintains the previous 59 candles in RAM to form the
(1, 60, 11) input tensor on each new closed candle without re-fetching or
recalculating the entire historical dataset from scratch.
"""

import logging
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "open_norm",
    "high_norm",
    "low_norm",
    "close_norm",
    "volume_norm",
    "vwap_norm",
    "rsi_norm",
    "atr_norm",
    "obv_norm",
    "macd_norm",
    "macd_hist_norm",
]

DEFAULT_NORM_WINDOW = 200
DEFAULT_WINDOW_SIZE = 60
MIN_REQUIRED_CANDLES = DEFAULT_NORM_WINDOW + DEFAULT_WINDOW_SIZE  # 260 candles


def _compute_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price with daily grouping anchor."""
    tp = (high + low + close) / 3.0
    wp = tp * volume
    if isinstance(wp.index, pd.DatetimeIndex):
        vwap = wp.groupby(wp.index.to_period("D")).cumsum() / volume.groupby(volume.index.to_period("D")).cumsum()
    else:
        vwap = wp.cumsum() / volume.cumsum()
    return vwap


def _compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index."""
    delta = close.diff()
    positive = delta.clip(lower=0)
    negative = (-delta).clip(lower=0)
    alpha = 1.0 / length
    pos_avg = positive.ewm(alpha=alpha, adjust=False).mean()
    neg_avg = negative.ewm(alpha=alpha, adjust=False).mean()
    denom = pos_avg + neg_avg
    return (100.0 * pos_avg / denom.replace(0, np.nan)).fillna(50.0)


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff()).fillna(0)
    if len(direction) > 0:
        direction.iloc[0] = 1.0
    return (direction * volume).cumsum()


def _compute_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[pd.Series, pd.Series]:
    """Moving Average Convergence Divergence line and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, macd_hist


def compute_predictive_features(
    df: pd.DataFrame,
    norm_window: int = DEFAULT_NORM_WINDOW,
) -> pd.DataFrame:
    """
    Compute causal rolling normalized features for the predictive ML model.

    Args:
        df: DataFrame containing at minimum [open, high, low, close, volume]
            and optionally [time] or datetime index.
        norm_window: Rolling window mean length for price and volume normalization.

    Returns:
        DataFrame containing the 11 normalized feature columns in exact model order.
    """
    df = df.copy()

    # Ensure numeric columns
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = df[col].astype(float)

    # Ensure datetime index for VWAP calculation
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.date_range("2024-01-01", periods=len(df), freq="15min")

    # 1. Base technical indicators (pure pandas/numpy vectorization)
    df["vwap"] = _compute_vwap(df["high"], df["low"], df["close"], df["volume"])
    df["rsi"] = _compute_rsi(df["close"], length=14)
    df["atr"] = _compute_atr(df["high"], df["low"], df["close"], length=14)
    df["obv"] = _compute_obv(df["close"], df["volume"])

    # Backfill initial NaN values from indicator warm-up
    df = df.bfill()

    # 2. Causal rolling window normalization (strictly backward-looking)
    for col in ["open", "high", "low", "close", "vwap"]:
        df[col + "_norm"] = df[col] / df[col].rolling(window=norm_window, min_periods=1).mean()

    df["volume_norm"] = df["volume"] / df["volume"].rolling(window=norm_window, min_periods=1).mean()
    df["rsi_norm"] = df["rsi"] / 100.0
    df["atr_norm"] = df["atr"] / df["close"]
    df["obv_norm"] = df["obv"] / df["obv"].rolling(window=norm_window, min_periods=1).mean()

    # MACD calculated on already normalized close price to maintain scale
    macd_line, macd_hist = _compute_macd(df["close_norm"], fast=12, slow=26, signal=9)
    df["macd_norm"] = macd_line
    df["macd_hist_norm"] = macd_hist

    # Replace any potential inf or nan resulting from zero-divisions
    df = df.replace([np.inf, -np.inf], np.nan).bfill().fillna(0.0)

    return df[FEATURE_COLUMNS]


class CandleMemoryBuffer:
    """
    In-memory ring buffer for market candles and precalculated features.

    Avoids fetching hundreds of historical candles on every trading loop iteration.
    Holds the required history in RAM (norm_window + window_size candles), caches
    the normalized features of previous candles, and produces the (1, window_size, 11)
    tensor instantaneously on each new closed candle.
    """

    def __init__(
        self,
        norm_window: int = DEFAULT_NORM_WINDOW,
        window_size: int = DEFAULT_WINDOW_SIZE,
        max_buffer_len: int = 350,
    ):
        self.norm_window = norm_window
        self.window_size = window_size
        self.max_buffer_len = max(max_buffer_len, norm_window + window_size + 20)

        # Buffer of raw candle dicts
        self._candles: List[Dict[str, Any]] = []
        # Cached normalized feature rows: shape (N, 11)
        self._cached_features: Optional[np.ndarray] = None
        self._last_candle_time: Optional[Any] = None

    @property
    def is_warmed_up(self) -> bool:
        """Check if buffer has reached the minimum warm-up size."""
        return len(self._candles) >= (self.window_size + 10)

    @property
    def candle_count(self) -> int:
        """Total candles currently stored in buffer."""
        return len(self._candles)

    def warm_up(self, candles: List[Dict[str, Any]]) -> None:
        """
        Initialize buffer with historical candles.

        Args:
            candles: List of candle dicts with keys [time, open, high, low, close, volume].
        """
        if not candles:
            return

        # Keep at most max_buffer_len recent candles
        self._candles = list(candles[-self.max_buffer_len:])
        self._last_candle_time = self._candles[-1].get("time")

        # Compute full features for the buffer
        df = pd.DataFrame(self._candles)
        feats_df = compute_predictive_features(df, norm_window=self.norm_window)
        self._cached_features = feats_df.values.astype(np.float32)

        logger.info(
            f"CandleMemoryBuffer warmed up with {len(self._candles)} candles. "
            f"Cached features shape: {self._cached_features.shape}"
        )

    def add_candle(self, candle: Dict[str, Any]) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Add a new candle or update the latest in-progress candle.

        Returns:
            (is_new_closed_candle, input_tensor):
            - is_new_closed_candle: True if a new candle time was detected.
            - input_tensor: ndarray of shape (1, window_size, 11) ready for model,
              or None if buffer is not yet warmed up.
        """
        candle_time = candle.get("time")

        if not self._candles:
            self.warm_up([candle])
            return True, self.get_latest_sequence()

        # Check if updating the current forming candle or appending a new one
        if candle_time == self._last_candle_time:
            # Update the latest candle in-place
            self._candles[-1] = candle
            is_new = False
        else:
            # New closed candle arrived!
            self._candles.append(candle)
            self._last_candle_time = candle_time
            if len(self._candles) > self.max_buffer_len:
                self._candles.pop(0)
            is_new = True

        # Recompute features on the rolling buffer
        df = pd.DataFrame(self._candles)
        feats_df = compute_predictive_features(df, norm_window=self.norm_window)
        self._cached_features = feats_df.values.astype(np.float32)

        tensor = self.get_latest_sequence()
        return is_new, tensor

    def get_latest_sequence(self) -> Optional[np.ndarray]:
        """
        Extract the latest (1, window_size, 11) tensor for model inference.

        Returns:
            np.ndarray of shape (1, 60, 11) with float32 dtype, or None if insufficient history.
        """
        if self._cached_features is None or len(self._cached_features) < self.window_size:
            return None

        # Take exactly the last window_size (e.g. 60) feature vectors
        seq = self._cached_features[-self.window_size:]
        return np.expand_dims(seq, axis=0)  # shape (1, 60, 11)
