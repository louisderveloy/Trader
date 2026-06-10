"""
Command-line interface for optimization.

This module provides CLI commands to run, list, resume, and inspect optimization studies.
"""

import argparse
import asyncio
import sys
import logging
from datetime import datetime
from typing import Optional
import asyncpg

from .config import load_config_from_env, create_default_config
from .runner import run_optimization
from .db import list_studies, list_weights_sets, get_study_by_name, activate_weights_set
from .types import OptimizationObjective, WalkForwardMode

# Logger placeholder - configured in main()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """
    Setup logging with appropriate level.

    Args:
        verbose: If True, set DEBUG level for detailed diagnostics
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing configuration
    )

    # Also set level for specific modules we care about
    if verbose:
        logging.getLogger('backtesting').setLevel(logging.DEBUG)
        logging.getLogger('backtesting.vectorbt_engine').setLevel(logging.DEBUG)
        logging.getLogger('backtesting.metrics').setLevel(logging.DEBUG)
        logging.getLogger('optimization').setLevel(logging.DEBUG)
        logging.getLogger('optimization.objective').setLevel(logging.DEBUG)
        logging.getLogger('optimization.runner').setLevel(logging.DEBUG)

        # Suppress verbose third-party loggers
        logging.getLogger('asyncpg').setLevel(logging.WARNING)
        logging.getLogger('optuna').setLevel(logging.INFO)

    logger.info(f"Logging configured: level={'DEBUG' if verbose else 'INFO'}")


async def get_db_pool() -> asyncpg.Pool:
    """
    Create database connection pool from environment.

    Returns:
        asyncpg.Pool: Database connection pool

    Raises:
        Exception: If connection fails
    """
    import os

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL environment variable not set")

    # Asyncpg requires "postgresql" or "postgres" scheme (not "postgresql+asyncpg")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    return pool


async def cmd_run(args):
    """Run optimization command."""
    logger.info(f"Starting optimization: {args.study_name}")

    # Parse dates and make timezone-aware (UTC)
    from datetime import timezone

    start_date = None
    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

    end_date = None
    if args.end_date:
        end_date = datetime.fromisoformat(args.end_date)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

    # Create config
    config = create_default_config(
        study_name=args.study_name,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start_date,
        end_date=end_date
    )

    # Override with CLI args
    if args.objective:
        config.objective = OptimizationObjective(args.objective)
    if args.n_trials:
        config.n_trials = args.n_trials
    if args.n_splits:
        config.n_splits = args.n_splits
    if args.train_ratio:
        config.train_ratio = args.train_ratio
    if args.walk_forward_mode:
        config.walk_forward_mode = WalkForwardMode(args.walk_forward_mode)
    if args.sampler:
        config.sampler = args.sampler
    if args.pruner:
        config.pruner = args.pruner
    if args.multithread:
        import multiprocessing
        config.n_jobs = -1  # Use all CPU cores
        logger.info(f"Multithreading enabled: will use all {multiprocessing.cpu_count()} CPU cores")

    # Connect to database
    db_pool = await get_db_pool()

    try:
        # Run optimization
        result = await run_optimization(config, db_pool)

        # Print results
        print("\n" + "=" * 80)
        print("OPTIMIZATION COMPLETED")
        print("=" * 80)
        print(f"Study name: {result.study_name}")
        print(f"Best {config.objective.value}: {result.best_value:.4f}")
        print(f"Total trials: {result.n_trials}")
        print(f"Optimization time: {result.optimization_time_seconds:.2f}s")
        print(f"Weights set ID: {result.weights_set_id}")
        print("\nBest weights:")
        for indicator, weight in sorted(result.best_weights.items()):
            print(f"  {indicator:20s}: {weight:.4f}")

        print("\nWalk-forward results:")
        for wf in result.walk_forward_results:
            print(f"  Split {wf.split.split_index + 1}: "
                  f"train={wf.train_score:.4f}, test={wf.test_score:.4f}")

        print("\n" + "=" * 80)

    finally:
        await db_pool.close()


async def cmd_list(args):
    """List studies command."""
    db_pool = await get_db_pool()

    try:
        studies = await list_studies(db_pool, limit=args.limit)

        if not studies:
            print("No optimization studies found.")
            return

        print("\n" + "=" * 80)
        print("OPTIMIZATION STUDIES")
        print("=" * 80)

        for study in studies:
            print(f"\nStudy: {study['study_name']}")
            print(f"  Optimization ID: {study['id']}")
            print(f"  Best value: {study['best_value'] if study['best_value'] is not None else 0}")
            print(f"  N trials: {study['n_trials']}")
            print(f"  Started: {study['started_at']}")
            print(f"  Completed: {study['completed_at']}")
            print(f"  Weights set ID: {study['weights_set_id']}")

        print("\n" + "=" * 80)

    finally:
        await db_pool.close()


async def cmd_best(args):
    """Show best results command."""
    from uuid import UUID

    db_pool = await get_db_pool()

    try:
        from .db import get_study_by_id

        study = await get_study_by_id(db_pool, UUID(args.optimization_id))

        if not study:
            print(f"Study not found: {args.optimization_id}")
            return

        print("\n" + "=" * 80)
        print(f"STUDY: {study['study_name']}")
        print("=" * 80)
        print(f"Optimization ID: {study['id']}")
        print(f"Best value: {study['best_value']:.4f}")
        print(f"N trials: {study['n_trials']}")
        print(f"Started: {study['started_at']}")
        print(f"Completed: {study['completed_at']}")
        print(f"Weights set ID: {study['weights_set_id']}")

        print("\nBest parameters:")
        for param, value in sorted(study['best_params'].items()):
            print(f"  {param:25s}: {value:.4f}")

        # Show metadata if available
        if study['metadata']:
            print("\nMetadata:")
            if 'walk_forward' in study['metadata']:
                wf = study['metadata']['walk_forward']
                print(f"  Walk-forward splits: {wf.get('n_splits', 'N/A')}")
                if 'split_results' in wf:
                    print("  Split results:")
                    for split_res in wf['split_results']:
                        print(f"    Split {split_res.get('split', '?')}: "
                              f"train={split_res.get('train_score', 0):.4f}, "
                              f"test={split_res.get('test_score', 0):.4f}")

        print("\n" + "=" * 80)

    finally:
        await db_pool.close()


async def cmd_weights(args):
    """List weights sets command."""
    db_pool = await get_db_pool()

    try:
        weights_sets = await list_weights_sets(
            db_pool,
            limit=args.limit,
            source=args.source
        )

        if not weights_sets:
            print("No weights sets found.")
            return

        print("\n" + "=" * 80)
        print("WEIGHTS SETS")
        print("=" * 80)

        for ws in weights_sets:
            active_marker = "[ACTIVE]" if ws['is_active'] else ""
            score_str = f"{ws['optimization_score']:.4f}" if ws['optimization_score'] else "N/A"
            print(f"\nName: {ws['name']} {active_marker}")
            print(f"  ID: {ws['id']}")
            print(f"  Source: {ws['source']}")
            print(f"  Score: {score_str}")
            print(f"  Created: {ws['created_at']}")

            if args.show_weights:
                print("  Weights:")
                for indicator, weight in sorted(ws['weights'].items()):
                    print(f"    {indicator:20s}: {weight:.4f}")

        print("\n" + "=" * 80)

    finally:
        await db_pool.close()


async def cmd_activate(args):
    """Activate weights set command."""
    db_pool = await get_db_pool()

    try:
        from uuid import UUID
        weights_set_id = UUID(args.weights_set_id)

        await activate_weights_set(db_pool, weights_set_id)

        print(f"Weights set {weights_set_id} activated successfully.")

    finally:
        await db_pool.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Optimization CLI for indicator weight optimization"
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Global verbose flag
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose/debug logging')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run optimization study')
    run_parser.add_argument('--study-name', required=True, help='Study name')
    run_parser.add_argument('--symbol', default='BTCUSDT', help='Trading symbol')
    run_parser.add_argument('--timeframe', default='15m', help='Candle timeframe')
    run_parser.add_argument('--start-date', help='Start date (ISO format)')
    run_parser.add_argument('--end-date', help='End date (ISO format)')
    run_parser.add_argument('--objective', choices=[obj.value for obj in OptimizationObjective],
                            help='Optimization objective')
    run_parser.add_argument('--n-trials', type=int, help='Number of trials per split')
    run_parser.add_argument('--n-splits', type=int, help='Number of walk-forward splits')
    run_parser.add_argument('--train-ratio', type=float, help='Training data ratio')
    run_parser.add_argument('--walk-forward-mode', choices=[mode.value for mode in WalkForwardMode],
                            help='Walk-forward mode')
    run_parser.add_argument('--sampler', choices=['tpe', 'random', 'grid', 'cmaes'],
                            help='Optuna sampler')
    run_parser.add_argument('--pruner', choices=['median', 'hyperband', 'none'],
                            help='Optuna pruner')
    run_parser.add_argument('--multithread', action='store_true',
                            help='Enable multithreaded optimization (use all CPU cores)')

    # List command
    list_parser = subparsers.add_parser('list', help='List optimization studies')
    list_parser.add_argument('--limit', type=int, default=10, help='Maximum number to show')

    # Best command
    best_parser = subparsers.add_parser('best', help='Show best results for a study')
    best_parser.add_argument('--optimization-id', required=True, help='Optimization ID (UUID)')

    # Weights command
    weights_parser = subparsers.add_parser('weights', help='List weights sets')
    weights_parser.add_argument('--limit', type=int, default=10, help='Maximum number to show')
    weights_parser.add_argument('--source', choices=['optuna', 'manual'], help='Filter by source')
    weights_parser.add_argument('--show-weights', action='store_true', help='Show full weights')

    # Activate command
    activate_parser = subparsers.add_parser('activate', help='Activate a weights set')
    activate_parser.add_argument('--weights-set-id', required=True, help='Weights set UUID')

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Setup logging based on verbose flag
    setup_logging(verbose=args.verbose)

    # Run command
    if args.command == 'run':
        asyncio.run(cmd_run(args))
    elif args.command == 'list':
        asyncio.run(cmd_list(args))
    elif args.command == 'best':
        asyncio.run(cmd_best(args))
    elif args.command == 'weights':
        asyncio.run(cmd_weights(args))
    elif args.command == 'activate':
        asyncio.run(cmd_activate(args))


if __name__ == '__main__':
    main()
