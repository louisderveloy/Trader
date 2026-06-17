"""
Tests for vectorbt backtester stop-loss / take-profit support (issue #17).

The vectorbt engine previously ran Portfolio.from_signals with no sl_stop/tp_stop,
so backtests ignored stop-loss entirely. These verify the fraction arrays are built
correctly (FIXED and ATR modes) and that vectorbt actually applies an sl_stop.
"""

import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

import vectorbt as vbt
from backtesting.types import BacktestConfig
from backtesting.vectorbt_engine import VectorbtBacktester


def _config(strategy_params=None):
    return BacktestConfig(
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
        initial_capital=Decimal("10000"),
        strategy_params=strategy_params or {},
    )


def _engine(strategy_params=None):
    eng = VectorbtBacktester(config=_config(strategy_params), db_pool=None)
    close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    eng.signals_df = pd.DataFrame({"atr": [2.0, 2.0, 2.0, 2.0, 2.0]})
    return eng, close


def test_atr_mode_builds_per_bar_fraction_array():
    eng, close = _engine()  # defaults: SL atr x2, TP atr x3
    sl_stop, tp_stop = eng._compute_stop_arrays(close)
    # SL fraction = atr * 2 / close ; TP fraction = atr * 3 / close
    np.testing.assert_allclose(sl_stop, (2.0 * 2.0) / close.to_numpy())
    np.testing.assert_allclose(tp_stop, (2.0 * 3.0) / close.to_numpy())


def test_fixed_mode_builds_flat_fraction():
    eng, close = _engine({
        "stop_loss": {"mode": "fixed", "fixed_percent": 2.0},
        "take_profit": {"mode": "fixed", "fixed_percent": 4.0},
    })
    sl_stop, tp_stop = eng._compute_stop_arrays(close)
    assert sl_stop == pytest.approx(0.02)
    assert tp_stop == pytest.approx(0.04)


def test_atr_warmup_nan_becomes_no_stop():
    eng, close = _engine()
    eng.signals_df = pd.DataFrame({"atr": [np.nan, np.nan, 2.0, 2.0, 2.0]})
    sl_stop, _ = eng._compute_stop_arrays(close)
    assert np.isinf(sl_stop[0]) and np.isinf(sl_stop[1])  # warm-up → no stop
    assert sl_stop[2] == pytest.approx((2.0 * 2.0) / 102.0)


def test_vectorbt_applies_sl_stop():
    """A fixed 5% sl_stop must produce a stop-loss exit on a sharp drop."""
    # Rise, enter, then a -10% drop → 5% stop should trigger.
    close = pd.Series([100, 100, 100, 90, 80, 80], dtype=float)
    entries = pd.Series([True, False, False, False, False, False])
    exits = pd.Series([False] * 6)
    pf = vbt.Portfolio.from_signals(
        close=close, entries=entries, exits=exits,
        init_cash=10000.0, sl_stop=0.05, freq="15T",
    )
    trades = pf.trades.records_readable
    assert len(trades) >= 1
    # The realized return must reflect the ~5% stop, not the full -20% drawdown.
    assert float(trades.iloc[0]["Return"]) < 0
    assert float(trades.iloc[0]["Return"]) > -0.15
