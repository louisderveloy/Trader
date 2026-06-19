"""
Parity tests: vectorized compute_series()/signal_series() must agree with the
scalar compute()/to_signal() for the same candles.

This is the regression guard for GitHub issue #9 (backtest weighted scores
diverging from live/paper trading): bot/backtesting/vectorbt_engine.py now calls
signal_series() directly instead of re-implementing each indicator's formula, so
if a future edit makes the scalar and vectorized paths disagree, it fails here
instead of being discovered as a silent live/backtest score discrepancy.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'bot'))

from indicators import ema, macd, rsi, stoch_rsi, bollinger, atr, obv

MODULES = [ema, macd, rsi, stoch_rsi, bollinger, atr, obv]

FIXTURE_NAMES = ['sample_candles', 'downtrend_candles', 'sideways_candles', 'volatile_candles']


@pytest.mark.parametrize('module', MODULES, ids=[m.__name__.rsplit('.', 1)[-1] for m in MODULES])
@pytest.mark.parametrize('fixture_name', FIXTURE_NAMES)
class TestSeriesParity:
    """Last value of the vectorized series must equal the scalar result."""

    def test_compute_series_matches_compute(self, module, fixture_name, request):
        candles = request.getfixturevalue(fixture_name)
        params = {}

        scalar_result = module.compute(candles, params)
        series_df = module.compute_series(candles, params)

        assert series_df.index.equals(candles.index)

        for key, scalar_value in scalar_result.values.items():
            if key not in series_df.columns:
                continue
            if not isinstance(scalar_value, (int, float)):
                continue
            series_last = series_df[key].iloc[-1]
            if scalar_value is None:
                assert series_last is None or series_last != series_last  # NaN check
            else:
                assert series_last == pytest.approx(scalar_value, abs=1e-6), (
                    f"{module.__name__}.compute_series()['{key}'] last value "
                    f"{series_last} != compute().values['{key}'] {scalar_value}"
                )

    def test_signal_series_matches_to_signal(self, module, fixture_name, request):
        candles = request.getfixturevalue(fixture_name)
        params = {}

        scalar_result = module.compute(candles, params)
        scalar_signal = module.to_signal(scalar_result)

        series = module.signal_series(candles, params)

        assert series.index.equals(candles.index)
        assert -1.0 <= series.iloc[-1] <= 1.0

        series_last = series.iloc[-1]
        assert series_last == pytest.approx(scalar_signal.value, abs=1e-6), (
            f"{module.__name__}.signal_series() last value {series_last} != "
            f"to_signal().value {scalar_signal.value}"
        )
