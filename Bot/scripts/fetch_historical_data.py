"""
Fetch historical candle data from exchange and store in database.

This script fetches historical OHLCV candle data from a configured exchange
(Binance by default) and stores it in the PostgreSQL/TimescaleDB database.

Usage:
    python -m scripts.fetch_historical_data --symbol BTCUSDT --timeframe 15m \
        --start-date 2023-01-01 --end-date 2024-12-31

    # Or with docker:
    docker compose exec bot python -m scripts.fetch_historical_data \
        --symbol BTCUSDT --timeframe 15m \
        --start-date 2023-01-01 --end-date 2024-12-31
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any

import asyncpg
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges import BinanceExchange

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_db_pool() -> asyncpg.Pool:
    """
    Create database connection pool.

    Returns:
        asyncpg.Pool: Database connection pool

    Raises:
        Exception: If connection fails
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL environment variable not set")

    # Asyncpg requires "postgresql" or "postgres" scheme (not "postgresql+asyncpg")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    logger.info("Database connection established")
    return pool


async def insert_candles_batch(
    pool: asyncpg.Pool,
    candles: List[Dict[str, Any]],
    symbol: str,
    timeframe: str
) -> int:
    """
    Insert a batch of candles into the database.

    Uses ON CONFLICT DO NOTHING to handle duplicates gracefully (idempotent).

    Args:
        pool: Database connection pool
        candles: List of candle dictionaries
        symbol: Trading symbol
        timeframe: Timeframe string

    Returns:
        Number of candles inserted (excluding duplicates)
    """
    if not candles:
        return 0

    query = """
        INSERT INTO candles (
            time, symbol, timeframe, open, high, low, close, volume
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (time, symbol, timeframe) DO NOTHING
    """

    async with pool.acquire() as conn:
        # Prepare data for batch insert
        rows = [
            (
                candle["time"],
                symbol,
                timeframe,
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"]
            )
            for candle in candles
        ]

        # Execute batch insert
        result = await conn.executemany(query, rows)

    # Count successful inserts (executemany returns list of statuses)
    # For ON CONFLICT DO NOTHING, we can't easily count, so we return total attempted
    logger.debug(f"Inserted batch of {len(candles)} candles")
    return len(candles)


async def fetch_and_store_historical_data(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    exchange_name: str = "binance",
    testnet: bool = False
) -> Dict[str, Any]:
    """
    Fetch historical candle data from exchange and store in database.

    This function handles pagination automatically, fetching data in batches
    and storing it incrementally.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe: Candle timeframe (e.g., "15m", "1h")
        start_date: Start date for historical data
        end_date: End date for historical data
        exchange_name: Exchange name (default: "binance")
        testnet: Whether to use testnet (default: False)

    Returns:
        Dict with statistics (total_candles, batches, time_taken)

    Raises:
        ValueError: If exchange not supported or parameters invalid
        Exception: If fetching or storing fails
    """
    logger.info("=" * 80)
    logger.info("FETCHING HISTORICAL DATA")
    logger.info("=" * 80)
    logger.info(f"Exchange: {exchange_name} {'(testnet)' if testnet else '(mainnet)'}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe}")
    logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
    logger.info("=" * 80)

    # Validate dates
    if start_date >= end_date:
        raise ValueError(f"start_date must be before end_date: {start_date} >= {end_date}")

    # Initialize exchange
    if exchange_name.lower() != "binance":
        raise ValueError(f"Unsupported exchange: {exchange_name}. Only 'binance' is supported.")

    # Load API credentials from environment
    api_key = os.getenv("BINANCE_TESTNET_API_KEY" if testnet else "BINANCE_MAINNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET" if testnet else "BINANCE_MAINNET_API_SECRET")

    if not api_key or not api_secret:
        env_prefix = "BINANCE_TESTNET" if testnet else "BINANCE_MAINNET"
        raise ValueError(
            f"Missing API credentials. Please set {env_prefix}_API_KEY and {env_prefix}_API_SECRET "
            "environment variables."
        )

    exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, testnet=testnet)
    await exchange.connect()

    # Initialize database
    db_pool = await get_db_pool()

    try:
        total_candles = 0
        total_batches = 0
        start_time = asyncio.get_event_loop().time()

        # Binance returns max 1000 candles per request
        # We'll fetch in chunks and move the start date forward
        current_start = start_date

        while current_start < end_date:
            # Fetch candles from current_start
            logger.info(f"Fetching candles from {current_start.strftime('%Y-%m-%d %H:%M:%S')}...")

            candles = await exchange.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                start_time=current_start,
                end_time=end_date,
                limit=1000  # Binance max
            )

            if not candles:
                logger.warning(f"No candles returned for {current_start}. Moving forward...")
                # Move forward by a reasonable amount to avoid infinite loop
                current_start += timedelta(days=1)
                continue

            logger.info(f"Received {len(candles)} candles")

            # Insert into database
            inserted = await insert_candles_batch(db_pool, candles, symbol, timeframe)
            total_candles += inserted
            total_batches += 1

            # Update progress
            last_candle_time = candles[-1]["time"]
            logger.info(f"Progress: {last_candle_time.strftime('%Y-%m-%d %H:%M:%S')} "
                       f"(Total: {total_candles} candles in {total_batches} batches)")

            # Move to next batch
            # Add 1 second to avoid fetching the same candle again
            current_start = last_candle_time + timedelta(seconds=1)

            # Stop if we've reached or passed the end date
            if current_start >= end_date:
                break

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)

        end_time = asyncio.get_event_loop().time()
        time_taken = end_time - start_time

        # Final statistics
        logger.info("=" * 80)
        logger.info("FETCH COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total candles fetched: {total_candles}")
        logger.info(f"Total batches: {total_batches}")
        logger.info(f"Time taken: {time_taken:.2f} seconds")
        logger.info(f"Average speed: {total_candles / time_taken:.2f} candles/second")
        logger.info("=" * 80)

        return {
            "total_candles": total_candles,
            "batches": total_batches,
            "time_taken": time_taken,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }

    finally:
        # Cleanup
        await exchange.disconnect()
        await db_pool.close()
        logger.info("Connections closed")


def parse_args():
    """
    Parse command-line arguments.

    Returns:
        Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Fetch historical candle data from exchange and store in database"
    )

    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Trading symbol (e.g., BTCUSDT)"
    )

    parser.add_argument(
        "--timeframe",
        type=str,
        default="15m",
        help="Candle timeframe (e.g., 1m, 5m, 15m, 1h, 4h, 1d)"
    )

    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date in ISO format (e.g., 2023-01-01 or 2023-01-01T00:00:00)"
    )

    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date in ISO format (e.g., 2024-12-31 or 2024-12-31T23:59:59)"
    )

    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        help="Exchange name (default: binance)"
    )

    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use exchange testnet instead of mainnet"
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()

    # Parse arguments
    args = parse_args()

    # Parse dates and make timezone-aware (UTC)
    try:
        start_date = datetime.fromisoformat(args.start_date)
        # Make timezone-aware if naive
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"Invalid start-date format: {args.start_date}")
        logger.error("Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
        sys.exit(1)

    try:
        end_date = datetime.fromisoformat(args.end_date)
        # Make timezone-aware if naive
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"Invalid end-date format: {args.end_date}")
        logger.error("Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
        sys.exit(1)

    # Run fetching
    try:
        result = await fetch_and_store_historical_data(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_date=start_date,
            end_date=end_date,
            exchange_name=args.exchange,
            testnet=args.testnet
        )

        logger.info("SUCCESS: Historical data fetched and stored successfully")
        sys.exit(0)

    except Exception as e:
        logger.error(f"FAILED: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
