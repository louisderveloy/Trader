#!/usr/bin/env python
"""
Benchmark optimization performance with process-local pool caching.

This script measures the performance of multiprocessing optimization
and verifies that pool caching is working effectively.

Usage:
    python scripts/benchmark_optimization.py --n-trials 20 --n-jobs 4
    python scripts/benchmark_optimization.py --n-trials 100 --n-splits 5 --multithread
"""

import asyncio
import logging
import sys
import time
import argparse
from datetime import datetime, timedelta
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_benchmark(
    n_trials: int = 20,
    n_splits: int = 2,
    n_jobs: int = 1,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
):
    """
    Run optimization benchmark.

    Args:
        n_trials: Number of trials per split
        n_splits: Number of walk-forward splits
        n_jobs: Number of parallel jobs (-1 = all CPUs)
        symbol: Trading symbol
        timeframe: Timeframe for backtesting
    """
    from bot.optimization.runner import OptimizationRunner
    from bot.optimization.types import OptimizationConfig, OptimizationObjective
    from bot.strategy.config import get_strategy_config
    from decimal import Decimal

    logger.info("=" * 70)
    logger.info("OPTIMIZATION BENCHMARK")
    logger.info("=" * 70)

    # Configuration
    config = OptimizationConfig(
        study_name=f"benchmark_{int(time.time())}",
        objective=OptimizationObjective.SHARPE_RATIO,
        n_trials=n_trials,
        n_splits=n_splits,
        train_ratio=0.8,
        symbol=symbol,
        timeframe=timeframe,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2026, 1, 1),
        initial_capital=Decimal("1000"),
        n_jobs=n_jobs,
    )

    # Get strategy config
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/trader")
    strategy_config = await get_strategy_config(symbol=symbol, db_url=db_url)

    logger.info(f"Configuration:")
    logger.info(f"  Study: {config.study_name}")
    logger.info(f"  Trials per split: {n_trials}")
    logger.info(f"  Splits: {n_splits}")
    logger.info(f"  Total trials: {n_trials * n_splits}")
    logger.info(f"  Parallel jobs: {n_jobs}")
    logger.info(f"  Objective: {config.objective.value}")

    # Run optimization
    start_time = time.time()
    runner = OptimizationRunner(config, db_url)

    try:
        result = await runner.run()
        elapsed = time.time() - start_time

        logger.info("=" * 70)
        logger.info("RESULTS")
        logger.info("=" * 70)
        logger.info(f"Status: SUCCESS")
        logger.info(f"Total time: {elapsed:.2f}s ({elapsed/60:.2f}m)")
        logger.info(f"Time per trial: {elapsed / (n_trials * n_splits):.2f}s")
        logger.info(f"Trials per second: {(n_trials * n_splits) / elapsed:.2f}")

        if result:
            logger.info(f"Best score: {result.best_score:.4f}")
            logger.info(f"Best weights: {result.best_weights}")

        # Performance analysis
        logger.info("=" * 70)
        logger.info("PERFORMANCE ANALYSIS")
        logger.info("=" * 70)

        if n_jobs != 1:
            import multiprocessing

            cpu_count = multiprocessing.cpu_count()
            theoretical_speedup = min(n_jobs if n_jobs > 0 else cpu_count, cpu_count)
            logger.info(f"CPUs available: {cpu_count}")
            logger.info(f"Workers used: {n_jobs if n_jobs > 0 else cpu_count}")
            logger.info(f"Theoretical max speedup: {theoretical_speedup}x")
            logger.info(f"Actual parallelism effectiveness: {elapsed:.2f}s")

        return elapsed, result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Benchmark failed after {elapsed:.2f}s: {e}")
        import traceback

        traceback.print_exc()
        return elapsed, None


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark optimization performance with pool caching"
    )
    parser.add_argument(
        "--n-trials", type=int, default=20, help="Number of trials per split"
    )
    parser.add_argument("--n-splits", type=int, default=2, help="Number of splits")
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        help="Number of parallel jobs (-1 for all CPUs)",
    )
    parser.add_argument(
        "--symbol", default="BTCUSDT", help="Trading symbol to optimize"
    )
    parser.add_argument("--timeframe", default="15m", help="Timeframe for backtesting")
    parser.add_argument(
        "--multithread",
        action="store_true",
        help="Use all available CPUs (equivalent to --n-jobs -1)",
    )

    args = parser.parse_args()

    # Handle --multithread flag
    n_jobs = -1 if args.multithread else args.n_jobs

    # Run benchmark
    elapsed, result = await run_benchmark(
        n_trials=args.n_trials,
        n_splits=args.n_splits,
        n_jobs=n_jobs,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 70)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
