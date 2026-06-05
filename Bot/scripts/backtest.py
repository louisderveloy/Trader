#!/usr/bin/env python3
"""
Backtest CLI - Run backtesting on historical data.

This script runs backtests using either:
  - vectorbt: Fast vectorized backtest (for quick analysis)
  - event_driven: Exact simulation with slippage, fees, latency

Usage:
    python -m scripts.backtest --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-06-01

    # With docker:
    docker compose exec bot python -m scripts.backtest \
        --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-06-01
"""

import argparse
import asyncio
import logging
import os
import sys
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.types import BacktestConfig, BacktestMode
from backtesting.vectorbt_engine import VectorbtBacktester

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_db_pool() -> asyncpg.Pool:
    """Create database connection pool."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL environment variable not set")

    # Asyncpg requires "postgresql" scheme (not "postgresql+asyncpg")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    return pool


async def get_active_weights(pool: asyncpg.Pool) -> Optional[dict]:
    """Get currently active weights set from database."""
    query = """
        SELECT id, name, weights, optimization_score
        FROM weights_sets
        WHERE is_active = true
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
        if row:
            weights = row["weights"]
            # Parse JSON string if needed
            if isinstance(weights, str):
                weights = json.loads(weights)

            # Remove 'weight_' prefix from keys if present
            # Database stores as "weight_ema", but strategy expects "ema"
            weights = {
                k.replace('weight_', ''): v
                for k, v in weights.items()
            }

            return {
                "id": row["id"],
                "name": row["name"],
                "weights": weights,
                "score": row["optimization_score"]
            }
    return None


async def get_weights_by_id(pool: asyncpg.Pool, weights_set_id: UUID) -> Optional[dict]:
    """Get weights set by ID."""
    query = """
        SELECT id, name, weights, optimization_score
        FROM weights_sets
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, weights_set_id)
        if row:
            weights = row["weights"]
            # Parse JSON string if needed
            if isinstance(weights, str):
                weights = json.loads(weights)

            # Remove 'weight_' prefix from keys if present
            # Database stores as "weight_ema", but strategy expects "ema"
            weights = {
                k.replace('weight_', ''): v
                for k, v in weights.items()
            }

            return {
                "id": row["id"],
                "name": row["name"],
                "weights": weights,
                "score": row["optimization_score"]
            }
    return None


async def run_backtest(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: Decimal,
    weights: dict,
    engine: str = "vectorbt",
    save_results: bool = False
):
    """
    Run backtest with specified parameters.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe
        start_date: Start date
        end_date: End date
        initial_capital: Initial capital
        weights: Indicator weights dict
        engine: Backtesting engine ('vectorbt' or 'event_driven')
        save_results: Whether to save results to database

    Returns:
        BacktestResult: Complete backtest results
    """
    logger.info("=" * 80)
    logger.info("RUNNING BACKTEST")
    logger.info("=" * 80)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe}")
    logger.info(f"Period: {start_date.date()} to {end_date.date()}")
    logger.info(f"Initial capital: {initial_capital} USDT")
    logger.info(f"Engine: {engine}")
    logger.info(f"Weights: {json.dumps(weights, indent=2)}")
    logger.info("=" * 80)

    # Create database pool
    db_pool = await get_db_pool()

    try:
        # Create backtest configuration
        config = BacktestConfig(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            strategy_params={"weights": weights}
        )

        # Create backtester
        if engine == "vectorbt":
            backtester = VectorbtBacktester(config=config, db_pool=db_pool)
        else:
            # TODO: Implement event-driven backtester CLI integration
            from backtesting.event_driven import EventDrivenBacktester
            backtester = EventDrivenBacktester(config=config, db_pool=db_pool)

        # Run backtest
        result = await backtester.run()

        if not result.success:
            logger.error(f"Backtest failed: {result.error_message}")
            return result

        # Print results
        metrics = result.metrics
        print("\n" + "=" * 80)
        print("BACKTEST RESULTS")
        print("=" * 80)

        print(f"\n{'='*40}")
        print("PERFORMANCE SUMMARY")
        print(f"{'='*40}")
        print(f"Total Return:      {float(metrics.total_return):>10.2f}%")
        print(f"Total P&L:         {float(metrics.total_pnl):>10.2f} USDT")
        print(f"Final Capital:     {float(metrics.final_capital):>10.2f} USDT")
        print(f"Buy & Hold Return: {float(metrics.buy_and_hold_return):>10.2f}%")
        print(f"Excess Return:     {float(metrics.excess_return):>10.2f}%")

        print(f"\n{'='*40}")
        print("TRADE STATISTICS")
        print(f"{'='*40}")
        print(f"Total Trades:      {metrics.total_trades:>10}")
        print(f"Winning Trades:    {metrics.winning_trades:>10}")
        print(f"Losing Trades:     {metrics.losing_trades:>10}")
        print(f"Win Rate:          {metrics.win_rate:>10.2f}%")
        print(f"Profit Factor:     {metrics.profit_factor:>10.2f}")
        print(f"Avg Win:           {float(metrics.avg_win):>10.2f} USDT")
        print(f"Avg Loss:          {float(metrics.avg_loss):>10.2f} USDT")

        print(f"\n{'='*40}")
        print("RISK METRICS")
        print(f"{'='*40}")
        print(f"Sharpe Ratio:      {metrics.sharpe_ratio:>10.2f}")
        print(f"Sortino Ratio:     {metrics.sortino_ratio:>10.2f}")
        print(f"Max Drawdown:      {metrics.max_drawdown_pct:>10.2f}%")
        print(f"Exposure Time:     {metrics.exposure_time_pct:>10.2f}%")

        print(f"\n{'='*40}")
        print("EXECUTION")
        print(f"{'='*40}")
        print(f"Engine:            {engine:>10}")
        print(f"Candles Processed: {result.candles_processed:>10}")
        print(f"Execution Time:    {result.execution_time_seconds:>10.2f}s")

        print("\n" + "=" * 80)

        # Save results if requested
        if save_results:
            # TODO: Implement saving to runs table
            logger.info("Saving results to database (not implemented yet)")

        return result

    finally:
        await db_pool.close()


async def run_backtest_cli(args):
    """
    CLI entry point for backtest command.

    Args:
        args: Parsed argparse arguments
    """
    load_dotenv()

    # Parse dates
    start_date = datetime.fromisoformat(args.start_date)
    end_date = datetime.fromisoformat(args.end_date)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    initial_capital = Decimal(str(args.initial_capital))

    # Get weights
    db_pool = await get_db_pool()

    try:
        if args.weights_set_id:
            # Use specified weights set
            weights_data = await get_weights_by_id(db_pool, UUID(args.weights_set_id))
            if not weights_data:
                logger.error(f"Weights set not found: {args.weights_set_id}")
                sys.exit(1)
            weights = weights_data["weights"]
            logger.info(f"Using weights set: {weights_data['name']} (ID: {weights_data['id']})")
        else:
            # Use active weights set
            weights_data = await get_active_weights(db_pool)
            if weights_data:
                weights = weights_data["weights"]
                logger.info(f"Using active weights set: {weights_data['name']} (ID: {weights_data['id']})")
            else:
                # Use default equal weights
                logger.warning("No active weights set found, using default equal weights")
                weights = {
                    "ema": 0.125,
                    "macd": 0.125,
                    "rsi": 0.125,
                    "stoch_rsi": 0.125,
                    "bollinger": 0.125,
                    "atr": 0.125,
                    "obv": 0.10,
                    "fear_greed": 0.10,
                    "user_indicator": 0.05
                }
    finally:
        await db_pool.close()

    # Run backtest
    await run_backtest(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        weights=weights,
        engine=args.engine,
        save_results=args.save
    )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run backtesting on historical data"
    )

    parser.add_argument('--symbol', default='BTCUSDT',
        help='Trading symbol (default: BTCUSDT)')
    parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')
    parser.add_argument('--start-date', required=True,
        help='Start date (ISO format: YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True,
        help='End date (ISO format: YYYY-MM-DD)')
    parser.add_argument('--initial-capital', type=float, default=10000,
        help='Initial capital in USDT (default: 10000)')
    parser.add_argument('--weights-set-id',
        help='UUID of weights set to use (default: active set)')
    parser.add_argument('--engine', choices=['vectorbt', 'event_driven'],
        default='vectorbt', help='Backtesting engine (default: vectorbt)')
    parser.add_argument('--save', action='store_true',
        help='Save results to database')
    parser.add_argument('-v', '--verbose', action='store_true',
        help='Enable verbose logging')

    return parser.parse_args()


async def main():
    """Main entry point."""
    load_dotenv()
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    await run_backtest_cli(args)


if __name__ == "__main__":
    asyncio.run(main())
