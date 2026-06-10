"""
Metrics calculation for backtesting.

This module provides standardized metric calculations that are used by both
vectorbt and event-driven backtesting engines to ensure consistency.

All metrics follow industry-standard definitions and are annualized where appropriate.
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
import numpy as np
import pandas as pd

from .types import BacktestTrade, BacktestMetrics, BacktestConfig

# Structured logging
logger = logging.getLogger(__name__)

# Constants
TRADING_DAYS_PER_YEAR = 365  # Crypto markets trade 24/7
RISK_FREE_RATE = 0.0  # Assume 0% risk-free rate for crypto


def calculate_metrics(
    trades: List[BacktestTrade],
    config: BacktestConfig,
    equity_curve: pd.DataFrame
) -> BacktestMetrics:
    """
    Calculate all standardized metrics from backtest trades.

    Args:
        trades: List of completed backtest trades
        config: Backtest configuration
        equity_curve: DataFrame with columns ['timestamp', 'capital']

    Returns:
        BacktestMetrics: Complete metrics object with all calculated values
    """
    logger.info(
        f"[METRICS] Starting calculation: trades={len(trades)}, "
        f"initial_capital={float(config.initial_capital):.2f}, "
        f"equity_curve_rows={len(equity_curve)}"
    )

    # Log trade PnL summary
    if trades:
        all_pnl = [float(t.net_pnl) for t in trades]
        total_pnl = sum(all_pnl)
        positive = sum(1 for p in all_pnl if p > 0)
        negative = sum(1 for p in all_pnl if p < 0)
        logger.info(
            f"[METRICS] Trade PnL summary: total={total_pnl:.2f}, "
            f"positive={positive}, negative={negative}, "
            f"min={min(all_pnl):.4f}, max={max(all_pnl):.4f}"
        )

    metrics = BacktestMetrics()

    if not trades:
        logger.warning("No trades to calculate metrics from")
        metrics.final_capital = config.initial_capital
        metrics.equity_curve = equity_curve.to_dict('records') if not equity_curve.empty else []
        return metrics

    # Basic performance
    final_capital = equity_curve.iloc[-1]['capital'] if not equity_curve.empty else config.initial_capital
    metrics.final_capital = Decimal(str(final_capital))
    metrics.total_pnl = sum(t.net_pnl for t in trades)
    metrics.total_return = ((metrics.final_capital - config.initial_capital) / config.initial_capital) * 100

    # Trade statistics
    metrics.total_trades = len(trades)
    winning_trades = [t for t in trades if t.net_pnl > 0]
    losing_trades = [t for t in trades if t.net_pnl < 0]
    metrics.winning_trades = len(winning_trades)
    metrics.losing_trades = len(losing_trades)
    metrics.win_rate = (metrics.winning_trades / metrics.total_trades * 100) if metrics.total_trades > 0 else 0.0

    # Profit/Loss statistics
    if winning_trades:
        metrics.avg_win = sum(t.net_pnl for t in winning_trades) / len(winning_trades)
        metrics.largest_win = max(t.net_pnl for t in winning_trades)

    if losing_trades:
        metrics.avg_loss = sum(t.net_pnl for t in losing_trades) / len(losing_trades)
        metrics.largest_loss = min(t.net_pnl for t in losing_trades)

    # Profit factor = sum(wins) / abs(sum(losses))
    # Perfect strategy (only wins, no losses) should have high profit factor, not 0.0
    total_wins = sum(t.net_pnl for t in winning_trades) if winning_trades else Decimal("0")
    total_losses = abs(sum(t.net_pnl for t in losing_trades)) if losing_trades else Decimal("0")

    if total_losses > 0:
        # Normal case: some losses exist
        metrics.profit_factor = float(total_wins / total_losses)
    else:
        # No losses: return 999.0 if there are wins (perfect strategy), else 0.0
        metrics.profit_factor = 999.0 if total_wins > 0 else 0.0

    # Risk metrics from equity curve
    if not equity_curve.empty:
        returns = calculate_returns(equity_curve)
        metrics.sharpe_ratio = calculate_sharpe_ratio(returns)
        metrics.sortino_ratio = calculate_sortino_ratio(returns)

        max_dd, max_dd_pct = calculate_max_drawdown(equity_curve)
        metrics.max_drawdown = Decimal(str(max_dd))
        metrics.max_drawdown_pct = max_dd_pct

        # Calmar ratio
        if metrics.max_drawdown_pct > 0:
            metrics.calmar_ratio = float(metrics.total_return) / metrics.max_drawdown_pct
        else:
            metrics.calmar_ratio = 0.0

    # Exposure and duration
    total_duration = config.end_date - config.start_date
    total_minutes = total_duration.total_seconds() / 60

    trade_durations = [t.duration_minutes for t in trades if t.duration_minutes is not None]
    if trade_durations:
        in_position_minutes = sum(trade_durations)
        metrics.exposure_time_pct = (in_position_minutes / total_minutes * 100) if total_minutes > 0 else 0.0
        metrics.avg_trade_duration_minutes = int(np.mean(trade_durations))

    # Buy-and-hold comparison
    if not equity_curve.empty:
        first_price = equity_curve.iloc[0].get('price', None)
        last_price = equity_curve.iloc[-1].get('price', None)

        if first_price and last_price:
            bh_return = ((last_price - first_price) / first_price) * 100
            bh_pnl = (config.initial_capital * Decimal(str(bh_return))) / 100

            metrics.buy_and_hold_return = Decimal(str(bh_return))
            metrics.buy_and_hold_pnl = bh_pnl
            metrics.excess_return = metrics.total_return - metrics.buy_and_hold_return

    # Store equity curve
    metrics.equity_curve = equity_curve.to_dict('records') if not equity_curve.empty else []

    logger.info(
        "Metrics calculated",
        extra={
            "total_return": float(metrics.total_return),
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "win_rate": metrics.win_rate,
            "profit_factor": metrics.profit_factor
        }
    )

    return metrics


def calculate_returns(equity_curve: pd.DataFrame) -> pd.Series:
    """
    Calculate period returns from equity curve.

    Args:
        equity_curve: DataFrame with 'capital' column

    Returns:
        Series: Period returns (percentage change)
    """
    if equity_curve.empty or 'capital' not in equity_curve.columns:
        logger.warning("[RETURNS] Empty equity curve or missing 'capital' column")
        return pd.Series(dtype=float)

    # DEBUG: Log capital distribution before pct_change (inline values)
    capital = equity_curve['capital']
    capital_min = float(capital.min())
    capital_max = float(capital.max())
    capital_std = float(capital.std())
    capital_unique = int(capital.nunique())

    logger.info(
        f"[RETURNS] Capital: min={capital_min:.2f}, max={capital_max:.2f}, "
        f"std={capital_std:.6f}, unique={capital_unique}"
    )

    # Calculate percentage change
    returns = equity_curve['capital'].pct_change()

    # Remove NaN (first row) and infinite values
    returns = returns.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # DEBUG: Log returns distribution (inline values)
    non_zero_count = int((returns != 0).sum())
    zero_count = int((returns == 0).sum())
    returns_mean = float(returns.mean())
    returns_std = float(returns.std())
    returns_min = float(returns.min())
    returns_max = float(returns.max())

    logger.info(
        f"[RETURNS] Distribution: total={len(returns)}, non_zero={non_zero_count}, zero={zero_count}"
    )
    logger.info(
        f"[RETURNS] Stats: mean={returns_mean:.12f}, std={returns_std:.12f}, "
        f"min={returns_min:.12f}, max={returns_max:.12f}"
    )

    if non_zero_count == 0:
        logger.warning("[RETURNS] WARNING: ALL returns are ZERO! Capital never changed.")

    return returns


def calculate_sharpe_ratio(returns: pd.Series, periods_per_year: int = 365 * 96) -> float:
    """
    Calculate annualized Sharpe ratio.

    Sharpe = (Mean Return - Risk-Free Rate) / Std Dev of Returns

    For 15-minute timeframe:
    - 96 periods per day (24h * 4 periods/hour)
    - 365 * 96 = 35040 periods per year

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods in a year (default: 35040 for 15m)

    Returns:
        float: Annualized Sharpe ratio
    """
    if returns.empty or len(returns) < 2:
        logger.warning(f"[SHARPE] Returning 0: insufficient returns data (len={len(returns)})")
        return 0.0

    mean_return = float(returns.mean())
    std_return = float(returns.std())
    non_zero_count = int((returns != 0).sum())

    # DEBUG: Log Sharpe calculation inputs (inline values)
    logger.info(
        f"[SHARPE] Inputs: mean={mean_return:.15f}, std={std_return:.15f}, "
        f"non_zero_returns={non_zero_count}/{len(returns)}"
    )

    # Check for zero or near-zero standard deviation (use small epsilon for floating point comparison)
    std_is_zero = std_return == 0
    std_near_zero = bool(np.isclose(std_return, 0.0, atol=1e-10))

    if std_is_zero or std_near_zero:
        logger.warning(
            f"[SHARPE] RETURNING 0: std={std_return:.15f} is {'zero' if std_is_zero else 'near-zero'}, "
            f"mean={mean_return:.15f}"
        )
        logger.warning(
            f"[SHARPE] ROOT CAUSE: {'No variance in returns' if non_zero_count == 0 else 'Extremely low variance'}"
        )
        return 0.0

    # Annualize
    annualization_factor = np.sqrt(periods_per_year)
    sharpe = (mean_return - RISK_FREE_RATE) / std_return * annualization_factor

    logger.info(
        f"[SHARPE] Result: sharpe={sharpe:.4f} "
        f"(mean={mean_return:.12f}, std={std_return:.12f}, annualization={annualization_factor:.2f})"
    )

    return float(sharpe)


def calculate_sortino_ratio(returns: pd.Series, periods_per_year: int = 365 * 96) -> float:
    """
    Calculate annualized Sortino ratio.

    Sortino = (Mean Return - Risk-Free Rate) / Downside Deviation

    Only considers downside (negative) volatility, not penalizing upside.

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods in a year (default: 35040 for 15m)

    Returns:
        float: Annualized Sortino ratio
    """
    if returns.empty or len(returns) < 2:
        return 0.0

    mean_return = returns.mean()

    # Calculate downside deviation (only negative returns)
    downside_returns = returns[returns < 0]

    if downside_returns.empty:
        return 0.0  # No downside = perfect but unrealistic

    downside_std = downside_returns.std()

    if downside_std == 0:
        return 0.0

    # Annualize
    sortino = (mean_return - RISK_FREE_RATE) / downside_std * np.sqrt(periods_per_year)

    return float(sortino)


def calculate_max_drawdown(equity_curve: pd.DataFrame) -> Tuple[float, float]:
    """
    Calculate maximum drawdown in USDT and percentage.

    Max Drawdown = Maximum loss from peak to trough before new peak

    Args:
        equity_curve: DataFrame with 'capital' column

    Returns:
        Tuple[float, float]: (max_drawdown_usdt, max_drawdown_pct)
    """
    if equity_curve.empty or 'capital' not in equity_curve.columns:
        return 0.0, 0.0

    capital = equity_curve['capital'].values

    # Calculate running maximum (peak)
    running_max = np.maximum.accumulate(capital)

    # Calculate drawdown at each point
    drawdown = running_max - capital
    drawdown_pct = (drawdown / running_max) * 100

    # Maximum drawdown
    max_dd_usdt = float(np.max(drawdown))
    max_dd_pct = float(np.max(drawdown_pct))

    return max_dd_usdt, max_dd_pct


def build_equity_curve(
    trades: List[BacktestTrade],
    initial_capital: Decimal,
    candles: pd.DataFrame
) -> pd.DataFrame:
    """
    Build equity curve from trades and candles.

    The equity curve shows capital at each point in time, including
    unrealized P&L of open positions.

    Args:
        trades: List of completed trades
        initial_capital: Starting capital
        candles: DataFrame with candle data (must have 'timestamp' and 'close' columns)

    Returns:
        DataFrame: Equity curve with columns ['timestamp', 'capital', 'price']
    """
    if candles.empty:
        logger.warning("No candles provided for equity curve")
        return pd.DataFrame(columns=['timestamp', 'capital', 'price'])

    # Initialize equity curve with candle timestamps
    equity_curve = candles[['timestamp', 'close']].copy()
    equity_curve.rename(columns={'close': 'price'}, inplace=True)
    equity_curve['capital'] = float(initial_capital)

    # DEBUG: Log candle timestamp info (inline values for visibility)
    first_ts = candles['timestamp'].iloc[0]
    last_ts = candles['timestamp'].iloc[-1]
    logger.info(
        f"[EQUITY_CURVE] Candles: count={len(candles)}, "
        f"ts_type={type(first_ts).__name__}, first={first_ts}, last={last_ts}"
    )

    if not trades:
        logger.warning("[EQUITY_CURVE] No trades provided - capital will be constant")
        return equity_curve

    # Build map of realized P&L by timestamp
    pnl_map = {}
    current_capital = float(initial_capital)

    for trade in sorted(trades, key=lambda t: t.exit_time):
        # Add cumulative capital at exit time
        current_capital += float(trade.net_pnl)
        pnl_map[trade.exit_time] = current_capital

    # DEBUG: Log pnl_map info (inline values for visibility)
    if pnl_map:
        exit_times = list(pnl_map.keys())
        capitals = list(pnl_map.values())
        capital_change = capitals[-1] - float(initial_capital)
        logger.info(
            f"[EQUITY_CURVE] PnL map: {len(pnl_map)} trades, "
            f"initial={float(initial_capital):.2f}, final={capitals[-1]:.2f}, "
            f"change={capital_change:.2f} ({capital_change/float(initial_capital)*100:.2f}%)"
        )
        # Log first and last exits for debugging
        first_exit = exit_times[0]
        last_exit = exit_times[-1]
        logger.info(
            f"[EQUITY_CURVE] Exit timestamps: first={first_exit} ({type(first_exit).__name__}), "
            f"last={last_exit} ({type(last_exit).__name__})"
        )

    # Check if timestamps are comparable BEFORE applying
    if pnl_map and len(equity_curve) > 0:
        first_candle_ts = equity_curve['timestamp'].iloc[0]
        last_candle_ts = equity_curve['timestamp'].iloc[-1]
        first_exit_ts = list(pnl_map.keys())[0]
        last_exit_ts = list(pnl_map.keys())[-1]

        # Check if any exit falls within candle range
        try:
            exits_after_first_candle = first_exit_ts >= first_candle_ts
            exits_before_last_candle = last_exit_ts <= last_candle_ts
            logger.info(
                f"[EQUITY_CURVE] Range check: candles=[{first_candle_ts}, {last_candle_ts}], "
                f"exits=[{first_exit_ts}, {last_exit_ts}], "
                f"exits_after_first={exits_after_first_candle}, exits_before_last={exits_before_last_candle}"
            )
        except TypeError as e:
            logger.error(
                f"[EQUITY_CURVE] TIMESTAMP COMPARISON FAILED: {e}"
            )
            logger.error(
                f"[EQUITY_CURVE] Types: candle_ts={type(first_candle_ts).__name__}, "
                f"exit_ts={type(first_exit_ts).__name__}"
            )
            # Try to show actual values for debugging
            logger.error(f"[EQUITY_CURVE] candle_ts repr: {repr(first_candle_ts)}")
            logger.error(f"[EQUITY_CURVE] exit_ts repr: {repr(first_exit_ts)}")

    # Apply realized P&L to equity curve
    matches_found = 0
    last_applied_capital = float(initial_capital)

    for i, row in equity_curve.iterrows():
        timestamp = row['timestamp']

        # Find the latest trade exit before or at this timestamp
        applicable_pnl = float(initial_capital)
        for exit_time, capital in pnl_map.items():
            try:
                if exit_time <= timestamp:
                    applicable_pnl = capital
                    matches_found += 1
                else:
                    break
            except TypeError as e:
                # Comparison failed - log once and break
                if matches_found == 0:
                    logger.error(
                        f"[EQUITY_CURVE] Comparison failed at first attempt: {e}"
                    )
                break

        equity_curve.at[i, 'capital'] = applicable_pnl
        if applicable_pnl != last_applied_capital:
            last_applied_capital = applicable_pnl

    # DEBUG: Log final equity curve stats (inline values for visibility)
    capital_unique = int(equity_curve['capital'].nunique())
    capital_min = float(equity_curve['capital'].min())
    capital_max = float(equity_curve['capital'].max())
    capital_first = float(equity_curve['capital'].iloc[0])
    capital_last = float(equity_curve['capital'].iloc[-1])

    logger.info(
        f"[EQUITY_CURVE] RESULT: {len(equity_curve)} candles, {matches_found} match operations, "
        f"unique_capitals={capital_unique}"
    )
    logger.info(
        f"[EQUITY_CURVE] Capital: first={capital_first:.2f}, last={capital_last:.2f}, "
        f"min={capital_min:.2f}, max={capital_max:.2f}"
    )

    if capital_unique == 1:
        logger.warning(
            f"[EQUITY_CURVE] WARNING: Capital is CONSTANT at {capital_first:.2f}! "
            f"This will cause Sharpe=0 (zero returns variance)"
        )

    return equity_curve


def calculate_trade_statistics(trades: List[BacktestTrade]) -> Dict[str, Any]:
    """
    Calculate detailed trade statistics for analysis.

    Args:
        trades: List of completed trades

    Returns:
        Dict with detailed statistics
    """
    if not trades:
        return {
            "total": 0,
            "winning": 0,
            "losing": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_duration_minutes": 0
        }

    winning = [t for t in trades if t.net_pnl > 0]
    losing = [t for t in trades if t.net_pnl < 0]

    durations = [t.duration_minutes for t in trades if t.duration_minutes is not None]

    return {
        "total": len(trades),
        "winning": len(winning),
        "losing": len(losing),
        "win_rate": (len(winning) / len(trades) * 100) if trades else 0.0,
        "avg_win": float(sum(t.net_pnl for t in winning) / len(winning)) if winning else 0.0,
        "avg_loss": float(sum(t.net_pnl for t in losing) / len(losing)) if losing else 0.0,
        "largest_win": float(max(t.net_pnl for t in winning)) if winning else 0.0,
        "largest_loss": float(min(t.net_pnl for t in losing)) if losing else 0.0,
        "avg_duration_minutes": int(np.mean(durations)) if durations else 0,
        "median_duration_minutes": int(np.median(durations)) if durations else 0,
    }
