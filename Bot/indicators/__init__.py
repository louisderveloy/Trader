"""
Technical indicators module for crypto trading bot.

This module provides a collection of technical indicators for market analysis.
All indicators follow a standard interface:

- compute(candles, params) -> IndicatorResult: Calculate raw indicator values
- to_signal(values) -> IndicatorSignal: Convert to normalized signal [-1, 1]

Available indicators:
- EMA: Exponential Moving Average crossover
- MACD: Moving Average Convergence Divergence
- RSI: Relative Strength Index
- Stochastic RSI: Stochastic version of RSI
- Bollinger Bands: Price volatility bands
- ATR: Average True Range (volatility)
- OBV: On Balance Volume
- Fear & Greed Index: Market sentiment from alternative.me
- User Indicator: Manual user input from database

Example usage:
    >>> import pandas as pd
    >>> from indicators import ema, types
    >>>
    >>> # Prepare candle data
    >>> candles = pd.DataFrame({
    ...     'timestamp': [...],
    ...     'open': [...],
    ...     'close': [...],
    ...     # ... more columns
    ... })
    >>>
    >>> # Calculate indicator
    >>> params = {'fast_period': 50, 'slow_period': 200}
    >>> result = ema.compute(candles, params)
    >>> signal = ema.to_signal(result)
    >>>
    >>> print(f"Signal: {signal.value}")  # Value in [-1, 1]
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from indicators.types import (
    CandleData,
    IndicatorProtocol,
    IndicatorResult,
    IndicatorSignal,
    validate_candles,
)
from indicators import ema, macd, rsi, stoch_rsi, bollinger, atr, obv

logger = logging.getLogger(__name__)

# Price/volume indicators computed synchronously from candle data.
# Order is irrelevant (weighted score is commutative). Defaults inside each
# module already match CLAUDE.md (EMA 50/200, MACD 12/26/9, RSI 14, ...), so an
# empty params dict yields the canonical configuration.
_PRICE_INDICATORS = (
    ("ema", ema),
    ("macd", macd),
    ("rsi", rsi),
    ("stoch_rsi", stoch_rsi),
    ("bollinger", bollinger),
    ("atr", atr),
    ("obv", obv),
)

# Sentiment / manual indicators that require external I/O (alternative.me API,
# DB lookup). They cannot be fetched synchronously from inside a running async
# loop, so compute_all_indicators() emits neutral placeholders by default; the
# caller may inject pre-fetched signal values via ``extra_signals``.
_PLACEHOLDER_INDICATORS = ("fear_greed", "user_indicator")


def compute_all_indicators(
    candles: pd.DataFrame,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    extra_signals: Optional[Dict[str, float]] = None,
) -> Dict[str, IndicatorResult]:
    """Compute every indicator and attach its normalized signal.

    Produces the ``indicator_results`` dict consumed by
    ``strategy.StrategyEngine.make_decision`` (each value exposes ``.values`` and
    ``.signal``). This is the single shared entry point for the live trading loop
    and the event-driven backtester, replacing their divergent inline calculations.

    Args:
        candles: DataFrame with columns [timestamp, open, high, low, close, volume].
        params: Optional per-indicator parameter overrides, keyed by indicator name
            (e.g. ``{"ema": {"fast_period": 20}}``). Missing keys fall back to each
            module's defaults.
        extra_signals: Optional pre-fetched signal values in [-1, 1] for the
            placeholder indicators (``fear_greed``, ``user_indicator``). Defaults to
            neutral (0.0) when absent.

    Returns:
        Dict mapping indicator name to an :class:`IndicatorResult` with ``.signal`` set.
        An indicator that fails (e.g. insufficient data) yields a neutral result rather
        than raising, so a single bad indicator never aborts a decision.
    """
    params = params or {}
    extra_signals = extra_signals or {}
    results: Dict[str, IndicatorResult] = {}

    for name, module in _PRICE_INDICATORS:
        try:
            result = module.compute(candles, params.get(name, {}))
            result.signal = module.to_signal(result)
        except Exception as exc:  # noqa: BLE001 - one bad indicator must not abort the decision
            logger.warning(
                "Indicator computation failed; using neutral signal",
                extra={"indicator": name, "error": str(exc)},
            )
            result = IndicatorResult(
                values={},
                metadata={"error": str(exc)},
                signal=IndicatorSignal(value=0.0, metadata={"reason": "compute_failed"}),
            )
        results[name] = result

    for name in _PLACEHOLDER_INDICATORS:
        signal_value = float(extra_signals.get(name, 0.0))
        results[name] = IndicatorResult(
            values={},
            metadata={"placeholder": name not in extra_signals},
            signal=IndicatorSignal(value=signal_value),
        )

    return results


__all__ = [
    # Core types
    "CandleData",
    "IndicatorProtocol",
    "IndicatorResult",
    "IndicatorSignal",
    "validate_candles",
    # Aggregation helper
    "compute_all_indicators",
    # Indicators (import modules, not functions, for cleaner API)
    "ema",
    "macd",
    "rsi",
    "stoch_rsi",
    "bollinger",
    "atr",
    "obv",
    "fear_greed",
    "user_indicator",
]
