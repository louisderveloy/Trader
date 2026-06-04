"""
Walk-forward analysis logic.

This module provides functions to generate train/test splits for walk-forward
analysis, supporting both sliding and expanding window approaches.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
import asyncpg

from .types import WalkForwardSplit, WalkForwardMode

# Structured logging
logger = logging.getLogger(__name__)


async def get_data_date_range(
    db_pool: asyncpg.Pool,
    symbol: str,
    timeframe: str
) -> tuple[datetime, datetime]:
    """
    Get the date range of available candle data in the database.

    Args:
        db_pool: Database connection pool
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe: Candle timeframe (e.g., "15m")

    Returns:
        Tuple of (start_date, end_date)

    Raises:
        ValueError: If no data is found for the symbol/timeframe
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT MIN(time) as start_date, MAX(time) as end_date
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            """,
            symbol,
            timeframe
        )

        if not result or not result["start_date"]:
            raise ValueError(f"No candle data found for {symbol} {timeframe}")

        return result["start_date"], result["end_date"]


def generate_splits(
    start_date: datetime,
    end_date: datetime,
    n_splits: int,
    train_ratio: float,
    mode: WalkForwardMode
) -> List[WalkForwardSplit]:
    """
    Generate walk-forward train/test splits.

    Args:
        start_date: Start date of available data
        end_date: End date of available data
        n_splits: Number of splits to generate
        train_ratio: Ratio of data for training (rest for testing)
        mode: Walk-forward mode (SLIDING or EXPANDING)

    Returns:
        List of WalkForwardSplit objects

    Raises:
        ValueError: If parameters are invalid or insufficient data
    """
    logger.info(
        "Generating walk-forward splits",
        extra={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "n_splits": n_splits,
            "train_ratio": train_ratio,
            "mode": mode.value
        }
    )

    # Validate inputs
    if n_splits < 1:
        raise ValueError(f"n_splits must be at least 1: {n_splits}")
    if not (0.0 < train_ratio < 1.0):
        raise ValueError(f"train_ratio must be in (0, 1): {train_ratio}")
    if start_date >= end_date:
        raise ValueError(f"start_date must be before end_date: {start_date} >= {end_date}")

    # Calculate total duration
    total_duration = end_date - start_date
    total_days = total_duration.days

    if total_days < n_splits:
        raise ValueError(
            f"Insufficient data: {total_days} days for {n_splits} splits. "
            f"Need at least {n_splits} days."
        )

    logger.debug(
        "Total data duration",
        extra={"total_days": total_days, "total_seconds": total_duration.total_seconds()}
    )

    splits = []

    if mode == WalkForwardMode.SLIDING:
        splits = _generate_sliding_splits(
            start_date, end_date, n_splits, train_ratio, total_duration
        )
    elif mode == WalkForwardMode.EXPANDING:
        splits = _generate_expanding_splits(
            start_date, end_date, n_splits, train_ratio, total_duration
        )
    else:
        raise ValueError(f"Unsupported walk-forward mode: {mode}")

    logger.info(
        "Walk-forward splits generated successfully",
        extra={"n_splits": len(splits), "mode": mode.value}
    )

    # Log each split for debugging
    for split in splits:
        logger.debug(
            "Split generated",
            extra={
                "split_index": split.split_index,
                "train_start": split.train_start.isoformat(),
                "train_end": split.train_end.isoformat(),
                "test_start": split.test_start.isoformat(),
                "test_end": split.test_end.isoformat(),
                "train_days": (split.train_end - split.train_start).days,
                "test_days": (split.test_end - split.test_start).days
            }
        )

    return splits


def _generate_sliding_splits(
    start_date: datetime,
    end_date: datetime,
    n_splits: int,
    train_ratio: float,
    total_duration: timedelta
) -> List[WalkForwardSplit]:
    """
    Generate sliding window walk-forward splits.

    In sliding window mode, both train and test windows have fixed sizes and
    slide forward in time together.

    Example with 4 splits, train_ratio=0.75:
    Split 1: [Train: Jan-Sep] [Test: Oct-Dec]
    Split 2:         [Train: Apr-Dec] [Test: Jan-Mar]
    Split 3:                 [Train: Jul-Mar] [Test: Apr-Jun]
    Split 4:                         [Train: Oct-Jun] [Test: Jul-Sep]

    Args:
        start_date: Start date of data
        end_date: End date of data
        n_splits: Number of splits
        train_ratio: Training data ratio
        total_duration: Total duration of data

    Returns:
        List of WalkForwardSplit objects
    """
    # Calculate period duration (one complete train+test cycle)
    period_duration = total_duration / n_splits

    # Calculate train and test durations
    train_duration = period_duration * train_ratio
    test_duration = period_duration * (1 - train_ratio)

    # Ensure minimum durations (at least 1 day each)
    min_duration = timedelta(days=1)
    if train_duration < min_duration:
        raise ValueError(
            f"Training period too short: {train_duration.days} days. "
            f"Increase total data range or reduce n_splits."
        )
    if test_duration < min_duration:
        raise ValueError(
            f"Testing period too short: {test_duration.days} days. "
            f"Increase total data range, reduce n_splits, or adjust train_ratio."
        )

    logger.debug(
        "Sliding window parameters",
        extra={
            "period_days": period_duration.days,
            "train_days": train_duration.days,
            "test_days": test_duration.days
        }
    )

    splits = []
    for i in range(n_splits):
        # Calculate split dates
        split_start = start_date + (period_duration * i)

        train_start = split_start
        train_end = train_start + train_duration
        test_start = train_end
        test_end = test_start + test_duration

        # Ensure we don't exceed end_date
        if test_end > end_date:
            logger.warning(
                "Last split exceeds end_date, truncating",
                extra={
                    "split_index": i,
                    "original_test_end": test_end.isoformat(),
                    "truncated_test_end": end_date.isoformat()
                }
            )
            test_end = end_date

        # Skip if train/test periods are too small
        if train_end - train_start < min_duration:
            logger.warning(
                "Skipping split with insufficient training data",
                extra={"split_index": i, "train_duration_days": (train_end - train_start).days}
            )
            continue
        if test_end - test_start < min_duration:
            logger.warning(
                "Skipping split with insufficient testing data",
                extra={"split_index": i, "test_duration_days": (test_end - test_start).days}
            )
            continue

        split = WalkForwardSplit(
            split_index=i,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end
        )
        splits.append(split)

    return splits


def _generate_expanding_splits(
    start_date: datetime,
    end_date: datetime,
    n_splits: int,
    train_ratio: float,
    total_duration: timedelta
) -> List[WalkForwardSplit]:
    """
    Generate expanding window walk-forward splits.

    In expanding window mode, the training window grows over time while the
    test window remains a fixed size.

    Example with 4 splits, train_ratio=0.75:
    Split 1: [Train: Jan-Sep]                    [Test: Oct-Dec]
    Split 2: [Train: Jan-----Dec]                [Test: Jan-Mar]
    Split 3: [Train: Jan----------Mar]           [Test: Apr-Jun]
    Split 4: [Train: Jan---------------Jun]      [Test: Jul-Sep]

    Args:
        start_date: Start date of data
        end_date: End date of data
        n_splits: Number of splits
        train_ratio: Initial training data ratio
        total_duration: Total duration of data

    Returns:
        List of WalkForwardSplit objects
    """
    # In expanding mode, test size is fixed based on the first split
    first_split_duration = total_duration * (1.0 / n_splits)
    test_duration = first_split_duration * (1 - train_ratio)

    # Ensure minimum test duration
    min_duration = timedelta(days=1)
    if test_duration < min_duration:
        raise ValueError(
            f"Testing period too short: {test_duration.days} days. "
            f"Increase total data range, reduce n_splits, or adjust train_ratio."
        )

    logger.debug(
        "Expanding window parameters",
        extra={
            "test_days": test_duration.days,
            "first_split_days": first_split_duration.days
        }
    )

    splits = []
    current_date = start_date

    for i in range(n_splits):
        # Training always starts from the beginning
        train_start = start_date

        # Training ends just before this split's test period
        train_end = current_date

        # Test starts after training
        test_start = train_end
        test_end = test_start + test_duration

        # Ensure we don't exceed end_date
        if test_end > end_date:
            logger.warning(
                "Last split exceeds end_date, truncating",
                extra={
                    "split_index": i,
                    "original_test_end": test_end.isoformat(),
                    "truncated_test_end": end_date.isoformat()
                }
            )
            test_end = end_date

        # Ensure minimum training data
        if train_end - train_start < min_duration:
            logger.warning(
                "Skipping split with insufficient training data",
                extra={"split_index": i, "train_duration_days": (train_end - train_start).days}
            )
            current_date = test_end
            continue

        # Ensure minimum test data
        if test_end - test_start < min_duration:
            logger.warning(
                "Skipping split with insufficient testing data",
                extra={"split_index": i, "test_duration_days": (test_end - test_start).days}
            )
            break

        split = WalkForwardSplit(
            split_index=i,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end
        )
        splits.append(split)

        # Move to next split (start of next test period)
        current_date = test_end

    return splits


async def generate_splits_from_db(
    db_pool: asyncpg.Pool,
    symbol: str,
    timeframe: str,
    n_splits: int,
    train_ratio: float,
    mode: WalkForwardMode,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[WalkForwardSplit]:
    """
    Generate walk-forward splits using data from the database.

    This is a convenience function that queries the database for available
    data range and generates splits accordingly.

    Args:
        db_pool: Database connection pool
        symbol: Trading symbol
        timeframe: Candle timeframe
        n_splits: Number of splits
        train_ratio: Training data ratio
        mode: Walk-forward mode
        start_date: Optional override for start date (uses DB min if not provided)
        end_date: Optional override for end date (uses DB max if not provided)

    Returns:
        List of WalkForwardSplit objects

    Raises:
        ValueError: If no data found or parameters invalid
    """
    logger.info(
        "Generating splits from database",
        extra={
            "symbol": symbol,
            "timeframe": timeframe,
            "n_splits": n_splits,
            "mode": mode.value
        }
    )

    # Get date range from DB if not provided
    db_start, db_end = await get_data_date_range(db_pool, symbol, timeframe)

    # Use provided dates or fall back to DB range
    actual_start = start_date if start_date else db_start
    actual_end = end_date if end_date else db_end

    # Validate that requested dates are within DB range
    if start_date and start_date < db_start:
        logger.warning(
            "Requested start_date before available data, using DB start",
            extra={
                "requested": start_date.isoformat(),
                "db_start": db_start.isoformat()
            }
        )
        actual_start = db_start

    if end_date and end_date > db_end:
        logger.warning(
            "Requested end_date after available data, using DB end",
            extra={
                "requested": end_date.isoformat(),
                "db_end": db_end.isoformat()
            }
        )
        actual_end = db_end

    logger.info(
        "Using date range",
        extra={
            "start": actual_start.isoformat(),
            "end": actual_end.isoformat(),
            "days": (actual_end - actual_start).days
        }
    )

    # Generate splits
    return generate_splits(actual_start, actual_end, n_splits, train_ratio, mode)
