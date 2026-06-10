#!/usr/bin/env python3
"""
Trading Bot - Main Entry Point

Unified CLI for all bot operations:
  - fetch     : Fetch historical candle data from exchange
  - backtest  : Run backtesting on historical data
  - optimize  : Run Optuna optimization for indicator weights
  - paper     : Run paper trading (simulated, no real orders)
  - live      : Run live trading (testnet or mainnet)

Usage:
    python -m main <command> [options]

Examples:
    # Fetch historical data
    python -m main fetch --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-12-31

    # Run backtest
    python -m main backtest --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-06-01

    # Run optimization
    python -m main optimize --study-name my_study --n-trials 100 --n-splits 4

    # Start paper trading
    python -m main paper --symbol BTCUSDT

    # Start live trading (testnet)
    python -m main live --symbol BTCUSDT --testnet

    # Start live trading (mainnet) - USE WITH CAUTION
    python -m main live --symbol BTCUSDT
"""

import argparse
import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import asyncpg
from dotenv import load_dotenv

# Add bot directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))
from utils.instance_lock import InstanceLockManager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger().setLevel(level)

    if verbose:
        # Set DEBUG for our modules
        for module in ['backtesting', 'optimization', 'strategy', 'exchanges', 'runs']:
            logging.getLogger(module).setLevel(logging.DEBUG)

        # Suppress verbose third-party loggers
        logging.getLogger('asyncpg').setLevel(logging.WARNING)
        logging.getLogger('optuna').setLevel(logging.INFO)
        logging.getLogger('urllib3').setLevel(logging.WARNING)


# ============================================================================
# FETCH Command
# ============================================================================

def cmd_fetch(args):
    """Fetch historical data command."""
    from scripts.fetch_historical_data import fetch_and_store_historical_data

    start_date = datetime.fromisoformat(args.start_date)
    end_date = datetime.fromisoformat(args.end_date)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    asyncio.run(fetch_and_store_historical_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start_date,
        end_date=end_date,
        exchange_name="binance",
        testnet=args.testnet
    ))


# ============================================================================
# BACKTEST Command
# ============================================================================

def cmd_backtest(args):
    """Run backtest command."""
    from scripts.backtest import run_backtest_cli

    asyncio.run(run_backtest_cli(args))


# ============================================================================
# OPTIMIZE Command
# ============================================================================

def cmd_optimize(args):
    """Run optimization command - delegates to optimization.cli."""
    from optimization.cli import main as optimization_main

    # Build sys.argv for optimization CLI
    opt_args = ['optimization', args.subcmd]

    if args.subcmd == 'run':
        opt_args.extend(['--study-name', args.study_name])
        if args.symbol:
            opt_args.extend(['--symbol', args.symbol])
        if args.timeframe:
            opt_args.extend(['--timeframe', args.timeframe])
        if args.start_date:
            opt_args.extend(['--start-date', args.start_date])
        if args.end_date:
            opt_args.extend(['--end-date', args.end_date])
        if args.objective:
            opt_args.extend(['--objective', args.objective])
        if args.n_trials:
            opt_args.extend(['--n-trials', str(args.n_trials)])
        if args.n_splits:
            opt_args.extend(['--n-splits', str(args.n_splits)])
        if args.multithread:
            opt_args.append('--multithread')
    elif args.subcmd == 'list':
        if args.limit:
            opt_args.extend(['--limit', str(args.limit)])
    elif args.subcmd == 'best':
        opt_args.extend(['--optimization-id', args.optimization_id])
    elif args.subcmd == 'weights':
        if args.limit:
            opt_args.extend(['--limit', str(args.limit)])
        if args.source:
            opt_args.extend(['--source', args.source])
        if args.show_weights:
            opt_args.append('--show-weights')
    elif args.subcmd == 'activate':
        opt_args.extend(['--weights-set-id', args.weights_set_id])

    if args.verbose:
        opt_args.insert(1, '-v')

    sys.argv = opt_args
    optimization_main()


# ============================================================================
# PAPER Command
# ============================================================================

def cmd_paper(args):
    """Run paper trading command."""
    from scripts.trading import run_trading_loop

    # Pre-flight instance check: use the advisory lock as source of truth.
    # The DB status (run.status='running') can be stale after a container crash/kill,
    # but the advisory lock is always released when the connection drops.
    async def check_instance():
        dsn = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            lock_held = await InstanceLockManager.is_lock_held(pool, 'paper')
            if lock_held:
                existing = await InstanceLockManager.check_existing_runs(pool, 'paper')
                print(f"\n❌ Cannot start paper trading: Another instance is already running")
                if existing:
                    print(f"   Active run_id: {existing['id']}")
                    print(f"   Started at: {existing['started_at']}")
                    print(f"   Symbol: {existing.get('symbol', 'unknown')}")
                    print(f"   Environment: {existing.get('environment', 'unknown')}")
                print("\n   To stop the existing instance:")
                print("   - Press Ctrl+C in the running instance")
                print("   - Or restart the bot container: docker compose restart bot")
                sys.exit(1)
        finally:
            await pool.close()

    asyncio.run(check_instance())

    # Proceed with trading loop
    asyncio.run(run_trading_loop(
        symbol=args.symbol,
        timeframe=args.timeframe,
        mode='paper',
        testnet=True,  # Paper always uses testnet for price data
        verbose=args.verbose
    ))


# ============================================================================
# LIVE Command
# ============================================================================

def cmd_live(args):
    """Run live trading command."""
    from scripts.trading import run_trading_loop

    # Pre-flight instance check: use the advisory lock as source of truth.
    # The DB status (run.status='running') can be stale after a container crash/kill,
    # but the advisory lock is always released when the connection drops.
    async def check_instance():
        dsn = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            lock_held = await InstanceLockManager.is_lock_held(pool, 'live')
            if lock_held:
                existing = await InstanceLockManager.check_existing_runs(pool, 'live')
                print(f"\n❌ Cannot start live trading: Another instance is already running")
                if existing:
                    print(f"   Active run_id: {existing['id']}")
                    print(f"   Started at: {existing['started_at']}")
                    print(f"   Symbol: {existing.get('symbol', 'unknown')}")
                    print(f"   Environment: {existing.get('environment', 'unknown')}")
                print("\n   To stop the existing instance:")
                print("   - Press Ctrl+C in the running instance")
                print("   - Or restart the bot container: docker compose restart bot")
                sys.exit(1)
        finally:
            await pool.close()

    asyncio.run(check_instance())

    # Safety confirmation for mainnet
    if not args.testnet:
        print("\n" + "=" * 80)
        print("WARNING: You are about to start LIVE TRADING on MAINNET!")
        print("This will execute REAL trades with REAL money.")
        print("=" * 80)

        if not args.confirm:
            confirm = input("\nType 'YES I UNDERSTAND' to continue: ")
            if confirm != "YES I UNDERSTAND":
                print("Aborted.")
                sys.exit(1)

    asyncio.run(run_trading_loop(
        symbol=args.symbol,
        timeframe=args.timeframe,
        mode='live',
        testnet=args.testnet,
        verbose=args.verbose
    ))


# ============================================================================
# STATUS Command
# ============================================================================

async def check_services():
    """
    Check health of all required services.

    Returns:
        dict: Status of each service
    """
    import asyncpg

    status = {
        "database": {"healthy": False, "message": ""},
        "environment": {"healthy": False, "message": ""}
    }

    # Check environment variables
    required_env_vars = ["DATABASE_URL"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        status["environment"]["message"] = f"Missing: {', '.join(missing_vars)}"
    else:
        status["environment"]["healthy"] = True
        status["environment"]["message"] = "All required variables present"

    # Check PostgreSQL
    try:
        dsn = os.getenv("DATABASE_URL", "")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(dsn=dsn, timeout=5)

        # Test query
        version = await conn.fetchval("SELECT version()")
        await conn.close()

        status["database"]["healthy"] = True
        status["database"]["message"] = "Connected"
    except Exception as e:
        status["database"]["message"] = f"Error: {str(e)[:100]}"

    return status


def cmd_status(args):
    """Display system status and exit."""
    async def _status():
        print("\n" + "=" * 80)
        print("TRADING BOT - SYSTEM STATUS")
        print("=" * 80)
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print(f"Environment: {os.getenv('ENVIRONMENT', 'unknown')}")
        print("=" * 80)

        status = await check_services()

        all_healthy = all(s["healthy"] for s in status.values())

        for service_name, service_status in status.items():
            icon = "✓" if service_status["healthy"] else "✗"
            health = "HEALTHY" if service_status["healthy"] else "UNHEALTHY"

            print(f"\n{service_name.upper()}: [{icon}] {health}")
            print(f"  Message: {service_status['message']}")

        print("\n" + "=" * 80)

        if all_healthy:
            print("STATUS: All services are healthy ✓")
            print("=" * 80 + "\n")
            return 0
        else:
            print("STATUS: Some services are unhealthy ✗")
            print("=" * 80 + "\n")
            return 1

    exit_code = asyncio.run(_status())
    sys.exit(exit_code)


def cmd_config(args):
    """Manage bot configuration."""
    if args.config_cmd == 'create':
        from scripts.configure import create_config_interactive
        asyncio.run(create_config_interactive())
    else:
        logger.error("Unknown config command. Use 'create' to create a new configuration.")
        sys.exit(1)


def cmd_docker_entry(args):
    """Display system status and keep container alive."""
    async def _docker_entry():
        print("\n" + "=" * 80)
        print("TRADING BOT - DOCKER ENTRY POINT")
        print("=" * 80)
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print(f"Environment: {os.getenv('ENVIRONMENT', 'unknown')}")
        print("=" * 80)

        status = await check_services()

        all_healthy = all(s["healthy"] for s in status.values())

        for service_name, service_status in status.items():
            icon = "✓" if service_status["healthy"] else "✗"
            health = "HEALTHY" if service_status["healthy"] else "UNHEALTHY"

            print(f"\n{service_name.upper()}: [{icon}] {health}")
            print(f"  Message: {service_status['message']}")

        print("\n" + "=" * 80)

        if all_healthy:
            print("STATUS: All services are healthy ✓")
            logger.info("All services are healthy. Container is ready.")
        else:
            print("STATUS: Some services are unhealthy ✗")
            logger.warning("Some services are unhealthy. Container is running but not fully ready.")

        print("=" * 80)
        print("\nContainer is running. Use 'docker compose exec bot python -m main <command>' to execute commands.")
        print("Available commands: fetch, backtest, optimize, paper, live, status")
        print("\nPress Ctrl+C to stop the container.")
        print("=" * 80 + "\n")

        # Keep container alive
        try:
            while True:
                pass
        except KeyboardInterrupt:
            logger.info("Received shutdown signal. Exiting gracefully.")
            print("\nShutting down gracefully...")

    asyncio.run(_docker_entry())


# ============================================================================
# Main CLI
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Trading Bot CLI - Automated crypto trading for Binance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Step 0: Create bot configuration (REQUIRED FIRST)
  python -m main config create

  # Step 1: Fetch historical data (required for backtest/optimize)
  python -m main fetch --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-12-31

  # Step 2: Run optimization to find best indicator weights
  python -m main optimize run --study-name btc_2024 --n-trials 100

  # Step 3: Run backtest to validate strategy
  python -m main backtest --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-06-01

  # Step 4: Paper trading to test in real-time (no real money)
  python -m main paper --symbol BTCUSDT

  # Step 5: Live trading on testnet (fake money, real exchange)
  python -m main live --symbol BTCUSDT --testnet

  # Step 6: Live trading on mainnet (REAL MONEY - use with caution!)
  python -m main live --symbol BTCUSDT
        """
    )

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose/debug logging')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # -------------------------------------------------------------------------
    # FETCH subcommand
    # -------------------------------------------------------------------------
    fetch_parser = subparsers.add_parser('fetch',
        help='Fetch historical candle data from Binance')
    fetch_parser.add_argument('--symbol', required=True,
        help='Trading symbol (e.g., BTCUSDT)')
    fetch_parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')
    fetch_parser.add_argument('--start-date', required=True,
        help='Start date (ISO format: YYYY-MM-DD)')
    fetch_parser.add_argument('--end-date', required=True,
        help='End date (ISO format: YYYY-MM-DD)')
    fetch_parser.add_argument('--testnet', action='store_true',
        help='Use Binance testnet (limited historical data)')

    # -------------------------------------------------------------------------
    # BACKTEST subcommand
    # -------------------------------------------------------------------------
    backtest_parser = subparsers.add_parser('backtest',
        help='Run backtesting on historical data')
    backtest_parser.add_argument('--symbol', default='BTCUSDT',
        help='Trading symbol (default: BTCUSDT)')
    backtest_parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')
    backtest_parser.add_argument('--start-date', required=True,
        help='Start date (ISO format: YYYY-MM-DD)')
    backtest_parser.add_argument('--end-date', required=True,
        help='End date (ISO format: YYYY-MM-DD)')
    backtest_parser.add_argument('--initial-capital', type=float, default=10000,
        help='Initial capital in USDT (default: 10000)')
    backtest_parser.add_argument('--weights-set-id',
        help='UUID of weights set to use (default: active set)')
    backtest_parser.add_argument('--engine', choices=['vectorbt', 'event_driven'],
        default='vectorbt', help='Backtesting engine (default: vectorbt)')
    backtest_parser.add_argument('--save', action='store_true',
        help='Save results to database')

    # -------------------------------------------------------------------------
    # OPTIMIZE subcommand
    # -------------------------------------------------------------------------
    opt_parser = subparsers.add_parser('optimize',
        help='Run Optuna optimization for indicator weights')
    opt_subparsers = opt_parser.add_subparsers(dest='subcmd', help='Optimization commands')

    # optimize run
    opt_run = opt_subparsers.add_parser('run', help='Run new optimization study')
    opt_run.add_argument('--study-name', required=True, help='Study name')
    opt_run.add_argument('--symbol', default='BTCUSDT', help='Trading symbol')
    opt_run.add_argument('--timeframe', default='15m', help='Candle timeframe')
    opt_run.add_argument('--start-date', help='Start date (ISO format)')
    opt_run.add_argument('--end-date', help='End date (ISO format)')
    opt_run.add_argument('--objective',
        choices=['sharpe_ratio', 'sortino_ratio', 'profit_factor', 'win_rate', 'total_return'],
        help='Optimization objective')
    opt_run.add_argument('--n-trials', type=int, help='Number of trials per split')
    opt_run.add_argument('--n-splits', type=int, help='Number of walk-forward splits')
    opt_run.add_argument('--multithread', action='store_true',
        help='Enable multithreaded optimization (use all CPU cores)')

    # optimize list
    opt_list = opt_subparsers.add_parser('list', help='List optimization studies')
    opt_list.add_argument('--limit', type=int, default=10, help='Max results')

    # optimize best
    opt_best = opt_subparsers.add_parser('best', help='Show best results for a study')
    opt_best.add_argument('--optimization-id', required=True, help='Optimization ID (UUID from list command)')

    # optimize weights
    opt_weights = opt_subparsers.add_parser('weights', help='List weights sets')
    opt_weights.add_argument('--limit', type=int, default=10, help='Max results')
    opt_weights.add_argument('--source', choices=['optuna', 'manual'], help='Filter by source')
    opt_weights.add_argument('--show-weights', action='store_true', help='Show full weights')

    # optimize activate
    opt_activate = opt_subparsers.add_parser('activate', help='Activate a weights set')
    opt_activate.add_argument('--weights-set-id', required=True, help='Weights set UUID')

    # -------------------------------------------------------------------------
    # PAPER subcommand
    # -------------------------------------------------------------------------
    paper_parser = subparsers.add_parser('paper',
        help='Run paper trading (simulated, no real orders)')
    paper_parser.add_argument('--symbol', default='BTCUSDT',
        help='Trading symbol (default: BTCUSDT)')
    paper_parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')

    # -------------------------------------------------------------------------
    # LIVE subcommand
    # -------------------------------------------------------------------------
    live_parser = subparsers.add_parser('live',
        help='Run live trading (testnet or mainnet)')
    live_parser.add_argument('--symbol', default='BTCUSDT',
        help='Trading symbol (default: BTCUSDT)')
    live_parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')
    live_parser.add_argument('--testnet', action='store_true',
        help='Use Binance testnet (recommended for testing)')
    live_parser.add_argument('--confirm', action='store_true',
        help='Skip mainnet confirmation prompt (dangerous!)')

    # -------------------------------------------------------------------------
    # CONFIG subcommand
    # -------------------------------------------------------------------------
    config_parser = subparsers.add_parser('config',
        help='Manage bot configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_cmd', help='Config commands')

    # config create
    config_create = config_subparsers.add_parser('create',
        help='Create new configuration interactively')

    # -------------------------------------------------------------------------
    # STATUS subcommand
    # -------------------------------------------------------------------------
    status_parser = subparsers.add_parser('status',
        help='Check system health (database, environment)')

    # -------------------------------------------------------------------------
    # DOCKER_ENTRY subcommand
    # -------------------------------------------------------------------------
    docker_entry_parser = subparsers.add_parser('docker_entry',
        help='Docker entry point - check health and keep container alive')

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Setup logging
    setup_logging(verbose=args.verbose)

    # Execute command
    if args.command == 'fetch':
        cmd_fetch(args)
    elif args.command == 'backtest':
        cmd_backtest(args)
    elif args.command == 'optimize':
        if not args.subcmd:
            opt_parser.print_help()
            sys.exit(1)
        cmd_optimize(args)
    elif args.command == 'paper':
        cmd_paper(args)
    elif args.command == 'live':
        cmd_live(args)
    elif args.command == 'config':
        if not args.config_cmd:
            config_parser.print_help()
            sys.exit(1)
        cmd_config(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'docker_entry':
        cmd_docker_entry(args)


if __name__ == '__main__':
    main()
