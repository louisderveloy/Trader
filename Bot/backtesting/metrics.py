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
        "Calculating backtest metrics",
        extra={
            "total_trades": len(trades),
            "initial_capital": float(config.initial_capital)
        }
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

    # Profit factor
    total_wins = sum(t.net_pnl for t in winning_trades) if winning_trades else Decimal("0")
    total_losses = abs(sum(t.net_pnl for t in losing_trades)) if losing_trades else Decimal("0")
    metrics.profit_factor = float(total_wins / total_losses) if total_losses > 0 else 0.0

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
        return pd.Series(dtype=float)

    # Calculate percentage change
    returns = equity_curve['capital'].pct_change()

    # Remove NaN (first row) and infinite values
    returns = returns.replace([np.inf, -np.inf], 0.0).fillna(0.0)

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
        return 0.0

    mean_return = returns.mean()
    std_return = returns.std()

    # Check for zero or near-zero standard deviation (use small epsilon for floating point comparison)
    if std_return == 0 or np.isclose(std_return, 0.0, atol=1e-10):
        return 0.0

    # Annualize
    sharpe = (mean_return - RISK_FREE_RATE) / std_return * np.sqrt(periods_per_year)

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

    if not trades:
        return equity_curve

    # Build map of realized P&L by timestamp
    pnl_map = {}
    current_capital = float(initial_capital)

    for trade in sorted(trades, key=lambda t: t.exit_time):
        # Add cumulative capital at exit time
        current_capital += float(trade.net_pnl)
        pnl_map[trade.exit_time] = current_capital

    # Apply realized P&L to equity curve
    for i, row in equity_curve.iterrows():
        timestamp = row['timestamp']

        # Find the latest trade exit before or at this timestamp
        applicable_pnl = initial_capital
        for exit_time, capital in pnl_map.items():
            if exit_time <= timestamp:
                applicable_pnl = capital
            else:
                break

        equity_curve.at[i, 'capital'] = applicable_pnl

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
