"""
Backtesting module for crypto trading bot.

This module provides two backtesting implementations:
1. vectorbt: Fast, vectorized backtesting for Optuna optimization
2. event-driven: Custom event-driven backtesting for exact live simulation

Both implementations share common types and produce standardized metrics
for coherence validation.
"""

from .types import (
    BacktestMode,
    OrderType,
    TradeDirection,
    BacktestConfig,
    BacktestTrade,
    BacktestMetrics,
    BacktestResult,
    CoherenceResult
)
from .base import BacktesterBase
from .vectorbt_engine import VectorbtBacktester
from .event_driven import EventDrivenBacktester
from .metrics import (
    calculate_metrics,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    build_equity_curve,
    calculate_trade_statistics
)
from .coherence import (
    validate_coherence,
    generate_coherence_report,
    compare_trades,
    COHERENCE_TOLERANCE_PCT
)

__all__ = [
    # Enums
    "BacktestMode",
    "OrderType",
    "TradeDirection",

    # Configuration and results
    "BacktestConfig",
    "BacktestTrade",
    "BacktestMetrics",
    "BacktestResult",
    "CoherenceResult",

    # Base class
    "BacktesterBase",

    # Implementations
    "VectorbtBacktester",
    "EventDrivenBacktester",

    # Metrics utilities
    "calculate_metrics",
    "calculate_returns",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_max_drawdown",
    "build_equity_curve",
    "calculate_trade_statistics",

    # Coherence utilities
    "validate_coherence",
    "generate_coherence_report",
    "compare_trades",
    "COHERENCE_TOLERANCE_PCT",
]
