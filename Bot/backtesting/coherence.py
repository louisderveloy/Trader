"""
Coherence validation between vectorbt and event-driven backtests.

This module validates that both backtesting engines produce consistent results
within acceptable tolerance (<2% P&L difference as per CLAUDE.md).
"""

import logging
from typing import Dict, Any
from decimal import Decimal

from .types import BacktestResult, CoherenceResult, BacktestMode

# Structured logging
logger = logging.getLogger(__name__)

# Tolerance threshold from CLAUDE.md
COHERENCE_TOLERANCE_PCT = 2.0


def validate_coherence(
    vectorbt_result: BacktestResult,
    event_driven_result: BacktestResult,
    tolerance_pct: float = COHERENCE_TOLERANCE_PCT
) -> CoherenceResult:
    """
    Validate coherence between two backtest results.

    Compares P&L and other metrics to ensure both engines produce
    consistent results within the specified tolerance.

    Args:
        vectorbt_result: Result from vectorbt backtester
        event_driven_result: Result from event-driven backtester
        tolerance_pct: Maximum acceptable P&L difference percentage (default: 2.0%)

    Returns:
        CoherenceResult: Coherence validation result with detailed comparison

    Raises:
        ValueError: If either result is invalid or from wrong engine
    """
    logger.info(
        "Validating coherence between backtests",
        extra={
            "tolerance_pct": tolerance_pct,
            "vectorbt_trades": len(vectorbt_result.trades),
            "event_driven_trades": len(event_driven_result.trades)
        }
    )

    # Validate inputs
    if vectorbt_result.mode != BacktestMode.VECTORBT:
        raise ValueError(f"First result must be VECTORBT mode, got {vectorbt_result.mode}")

    if event_driven_result.mode != BacktestMode.EVENT_DRIVEN:
        raise ValueError(f"Second result must be EVENT_DRIVEN mode, got {event_driven_result.mode}")

    if not vectorbt_result.success or not event_driven_result.success:
        logger.warning("One or both backtests failed, coherence validation skipped")
        return CoherenceResult(
            vectorbt_result=vectorbt_result,
            event_driven_result=event_driven_result,
            is_coherent=False,
            tolerance_pct=tolerance_pct,
            differences={"error": "One or both backtests failed"}
        )

    # Extract metrics
    vbt_metrics = vectorbt_result.metrics
    ed_metrics = event_driven_result.metrics

    if not vbt_metrics or not ed_metrics:
        logger.warning("Metrics missing from one or both results")
        return CoherenceResult(
            vectorbt_result=vectorbt_result,
            event_driven_result=event_driven_result,
            is_coherent=False,
            tolerance_pct=tolerance_pct,
            differences={"error": "Metrics missing"}
        )

    # Calculate P&L difference
    vbt_pnl = float(vbt_metrics.total_pnl)
    ed_pnl = float(ed_metrics.total_pnl)

    pnl_difference_pct = calculate_percentage_difference(vbt_pnl, ed_pnl)

    # Check if coherent
    is_coherent = abs(pnl_difference_pct) <= tolerance_pct

    # Detailed comparison
    differences = {
        "pnl": {
            "vectorbt": vbt_pnl,
            "event_driven": ed_pnl,
            "difference_pct": pnl_difference_pct
        },
        "total_return": {
            "vectorbt": float(vbt_metrics.total_return),
            "event_driven": float(ed_metrics.total_return),
            "difference_pct": calculate_percentage_difference(
                float(vbt_metrics.total_return),
                float(ed_metrics.total_return)
            )
        },
        "total_trades": {
            "vectorbt": vbt_metrics.total_trades,
            "event_driven": ed_metrics.total_trades,
            "difference": vbt_metrics.total_trades - ed_metrics.total_trades
        },
        "win_rate": {
            "vectorbt": vbt_metrics.win_rate,
            "event_driven": ed_metrics.win_rate,
            "difference_pct": calculate_percentage_difference(
                vbt_metrics.win_rate,
                ed_metrics.win_rate
            )
        },
        "sharpe_ratio": {
            "vectorbt": vbt_metrics.sharpe_ratio,
            "event_driven": ed_metrics.sharpe_ratio,
            "difference": vbt_metrics.sharpe_ratio - ed_metrics.sharpe_ratio
        },
        "max_drawdown_pct": {
            "vectorbt": vbt_metrics.max_drawdown_pct,
            "event_driven": ed_metrics.max_drawdown_pct,
            "difference": vbt_metrics.max_drawdown_pct - ed_metrics.max_drawdown_pct
        },
        "profit_factor": {
            "vectorbt": vbt_metrics.profit_factor,
            "event_driven": ed_metrics.profit_factor,
            "difference_pct": calculate_percentage_difference(
                vbt_metrics.profit_factor,
                ed_metrics.profit_factor
            ) if vbt_metrics.profit_factor > 0 and ed_metrics.profit_factor > 0 else None
        }
    }

    result = CoherenceResult(
        vectorbt_result=vectorbt_result,
        event_driven_result=event_driven_result,
        pnl_difference_pct=pnl_difference_pct,
        is_coherent=is_coherent,
        tolerance_pct=tolerance_pct,
        differences=differences
    )

    # Log result
    if is_coherent:
        logger.info(
            "✅ Backtests are COHERENT",
            extra={
                "pnl_difference_pct": pnl_difference_pct,
                "tolerance_pct": tolerance_pct,
                "vectorbt_pnl": vbt_pnl,
                "event_driven_pnl": ed_pnl
            }
        )
    else:
        logger.warning(
            "❌ Backtests are INCOHERENT - Investigation required",
            extra={
                "pnl_difference_pct": pnl_difference_pct,
                "tolerance_pct": tolerance_pct,
                "vectorbt_pnl": vbt_pnl,
                "event_driven_pnl": ed_pnl,
                "differences": differences
            }
        )

    return result


def calculate_percentage_difference(value1: float, value2: float) -> float:
    """
    Calculate percentage difference between two values.

    Formula: ((value2 - value1) / abs(value1)) * 100

    Args:
        value1: First value (baseline)
        value2: Second value (comparison)

    Returns:
        float: Percentage difference
    """
    if value1 == 0:
        if value2 == 0:
            return 0.0
        else:
            # If baseline is 0 but comparison isn't, return large number
            return 100.0 if value2 > 0 else -100.0

    return ((value2 - value1) / abs(value1)) * 100


def generate_coherence_report(coherence: CoherenceResult) -> str:
    """
    Generate a human-readable coherence report.

    Args:
        coherence: Coherence validation result

    Returns:
        str: Formatted report
    """
    report_lines = [
        "=" * 80,
        "COHERENCE VALIDATION REPORT",
        "=" * 80,
        "",
        f"Tolerance: {coherence.tolerance_pct}%",
        f"Result: {'✅ COHERENT' if coherence.is_coherent else '❌ INCOHERENT'}",
        "",
        "P&L COMPARISON",
        "-" * 80,
        f"vectorbt P&L:      {coherence.differences['pnl']['vectorbt']:>15.2f} USDT",
        f"event-driven P&L:  {coherence.differences['pnl']['event_driven']:>15.2f} USDT",
        f"Difference:        {coherence.pnl_difference_pct:>15.2f}%",
        "",
        "DETAILED COMPARISON",
        "-" * 80,
    ]

    # Add detailed metrics
    for metric_name, metric_data in coherence.differences.items():
        if metric_name == "pnl":
            continue  # Already shown above

        report_lines.append(f"\n{metric_name.upper().replace('_', ' ')}:")

        if isinstance(metric_data, dict):
            for key, value in metric_data.items():
                if value is None:
                    report_lines.append(f"  {key:20s} {'N/A':>15}")
                elif isinstance(value, float):
                    report_lines.append(f"  {key:20s} {value:>15.2f}")
                else:
                    report_lines.append(f"  {key:20s} {value:>15}")

    report_lines.append("")
    report_lines.append("=" * 80)

    if not coherence.is_coherent:
        report_lines.append("")
        report_lines.append("⚠️  INVESTIGATION REQUIRED")
        report_lines.append("")
        report_lines.append("The P&L difference exceeds the acceptable tolerance.")
        report_lines.append("Possible causes:")
        report_lines.append("  1. Different slippage calculation between engines")
        report_lines.append("  2. Limit order handling discrepancies")
        report_lines.append("  3. Stop-loss/take-profit execution timing differences")
        report_lines.append("  4. Indicator calculation differences")
        report_lines.append("  5. Fee calculation discrepancies")
        report_lines.append("")
        report_lines.append("Action: Review both backtests in detail and identify the source of divergence.")
        report_lines.append("=" * 80)

    return "\n".join(report_lines)


def compare_trades(
    vectorbt_result: BacktestResult,
    event_driven_result: BacktestResult
) -> Dict[str, Any]:
    """
    Compare individual trades between two backtest results.

    Useful for debugging when coherence validation fails.

    Args:
        vectorbt_result: Result from vectorbt backtester
        event_driven_result: Result from event-driven backtester

    Returns:
        Dict with trade-by-trade comparison
    """
    vbt_trades = vectorbt_result.trades
    ed_trades = event_driven_result.trades

    comparison = {
        "vectorbt_trade_count": len(vbt_trades),
        "event_driven_trade_count": len(ed_trades),
        "trade_count_match": len(vbt_trades) == len(ed_trades),
        "trades": []
    }

    # Compare trades pairwise
    max_trades = max(len(vbt_trades), len(ed_trades))

    for i in range(max_trades):
        trade_comparison = {
            "trade_number": i + 1,
            "vectorbt": None,
            "event_driven": None,
            "differences": {}
        }

        if i < len(vbt_trades):
            vbt_trade = vbt_trades[i]
            trade_comparison["vectorbt"] = {
                "entry_time": vbt_trade.entry_time.isoformat(),
                "exit_time": vbt_trade.exit_time.isoformat(),
                "entry_price": float(vbt_trade.entry_price),
                "exit_price": float(vbt_trade.exit_price),
                "net_pnl": float(vbt_trade.net_pnl)
            }

        if i < len(ed_trades):
            ed_trade = ed_trades[i]
            trade_comparison["event_driven"] = {
                "entry_time": ed_trade.entry_time.isoformat(),
                "exit_time": ed_trade.exit_time.isoformat(),
                "entry_price": float(ed_trade.entry_price),
                "exit_price": float(ed_trade.exit_price),
                "net_pnl": float(ed_trade.net_pnl)
            }

        # Calculate differences if both trades exist
        if trade_comparison["vectorbt"] and trade_comparison["event_driven"]:
            vbt_pnl = trade_comparison["vectorbt"]["net_pnl"]
            ed_pnl = trade_comparison["event_driven"]["net_pnl"]

            trade_comparison["differences"] = {
                "pnl_difference": ed_pnl - vbt_pnl,
                "pnl_difference_pct": calculate_percentage_difference(vbt_pnl, ed_pnl),
                "entry_price_difference": (
                    trade_comparison["event_driven"]["entry_price"] -
                    trade_comparison["vectorbt"]["entry_price"]
                ),
                "exit_price_difference": (
                    trade_comparison["event_driven"]["exit_price"] -
                    trade_comparison["vectorbt"]["exit_price"]
                )
            }

        comparison["trades"].append(trade_comparison)

    return comparison
