"""
Indicator values logging utilities.

This module provides functions for logging indicator values to the database
during backtest and live trading runs.
"""

import asyncpg
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def save_indicator_value(
    db_pool: asyncpg.Pool,
    run_id: int,
    time: datetime,
    symbol: str,
    indicator_name: str,
    values: dict[str, Any],
    signal: float,
) -> UUID:
    """
    Save a single indicator value to the database.

    Args:
        db_pool: Database connection pool
        run_id: Run ID this indicator belongs to
        time: Candle timestamp
        symbol: Trading symbol
        indicator_name: Name of the indicator
        values: Raw indicator values (stored as JSONB)
        signal: Normalized signal [-1, 1]

    Returns:
        UUID of the created record

    Raises:
        asyncpg.PostgresError: Database error
        ValueError: Invalid signal value
    """
    if signal < -1 or signal > 1:
        raise ValueError(f"Signal must be in [-1, 1], got {signal}")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO indicators_values (
                run_id, time, symbol, indicator_name, values, signal
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            run_id,
            time,
            symbol,
            indicator_name,
            values,
            Decimal(str(signal)),
        )

    return row["id"]


async def save_indicators_batch(
    db_pool: asyncpg.Pool,
    run_id: int,
    time: datetime,
    symbol: str,
    indicators: dict[str, dict[str, Any]],
) -> int:
    """
    Batch insert indicator values for a single candle.

    This is more efficient than calling save_indicator_value multiple times.

    Args:
        db_pool: Database connection pool
        run_id: Run ID this indicator belongs to
        time: Candle timestamp
        symbol: Trading symbol
        indicators: Dict of indicator data, e.g.:
            {
                "ema": {"values": {"ema_fast": 50000, "ema_slow": 49500}, "signal": 0.2},
                "macd": {"values": {"macd": 100, "signal": 80, "hist": 20}, "signal": 0.15},
                ...
            }

    Returns:
        Number of records inserted

    Raises:
        asyncpg.PostgresError: Database error
    """
    if not indicators:
        return 0

    # Prepare batch data
    records = []
    for indicator_name, data in indicators.items():
        values = data.get("values", {})
        signal = data.get("signal", 0.0)

        # Clamp signal to valid range
        signal = max(-1.0, min(1.0, signal))

        records.append((
            run_id,
            time,
            symbol,
            indicator_name,
            values,
            Decimal(str(signal)),
        ))

    async with db_pool.acquire() as conn:
        # Use copy_records_to_table for efficient batch insert
        # Note: This is more efficient than multiple INSERT statements
        result = await conn.executemany(
            """
            INSERT INTO indicators_values (
                run_id, time, symbol, indicator_name, values, signal
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            records,
        )

    logger.debug(
        f"Saved {len(records)} indicator values for {symbol} at {time}",
        extra={"run_id": run_id, "symbol": symbol, "n_indicators": len(records)},
    )

    return len(records)


async def get_indicator_values(
    db_pool: asyncpg.Pool,
    run_id: int,
    indicator_name: Optional[str] = None,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    Get indicator values with filtering.

    Args:
        db_pool: Database connection pool
        run_id: Run ID
        indicator_name: Optional filter by indicator name
        symbol: Optional filter by symbol
        start_time: Optional start time filter
        end_time: Optional end time filter
        limit: Maximum number of records

    Returns:
        List of indicator value dicts

    Raises:
        asyncpg.PostgresError: Database error
    """
    conditions = ["run_id = $1"]
    params = [run_id]
    param_idx = 2

    if indicator_name:
        conditions.append(f"indicator_name = ${param_idx}")
        params.append(indicator_name)
        param_idx += 1

    if symbol:
        conditions.append(f"symbol = ${param_idx}")
        params.append(symbol)
        param_idx += 1

    if start_time:
        conditions.append(f"time >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"time <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    params.append(limit)

    query = f"""
        SELECT
            id, run_id, time, symbol, indicator_name, values, signal, created_at
        FROM indicators_values
        WHERE {' AND '.join(conditions)}
        ORDER BY time ASC
        LIMIT ${param_idx}
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [dict(row) for row in rows]


async def get_latest_indicator_values(
    db_pool: asyncpg.Pool,
    run_id: int,
    symbol: str,
) -> dict[str, dict[str, Any]]:
    """
    Get the most recent indicator values for all indicators.

    Args:
        db_pool: Database connection pool
        run_id: Run ID
        symbol: Trading symbol

    Returns:
        Dict mapping indicator_name to {values, signal, time}

    Raises:
        asyncpg.PostgresError: Database error
    """
    query = """
        SELECT DISTINCT ON (indicator_name)
            indicator_name, values, signal, time
        FROM indicators_values
        WHERE run_id = $1 AND symbol = $2
        ORDER BY indicator_name, time DESC
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, run_id, symbol)

    return {
        row["indicator_name"]: {
            "values": row["values"],
            "signal": float(row["signal"]),
            "time": row["time"],
        }
        for row in rows
    }


class IndicatorLogger:
    """
    Context-aware indicator logger for a specific run.

    This class provides a convenient interface for logging indicator values
    within a specific run context, with optional rate limiting.

    Attributes:
        db_pool: Database connection pool
        run_id: Run ID to log to
        symbol: Trading symbol
        enabled: Whether logging is enabled
        log_every_n: Only log every N candles (default: 1 = log all)
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        run_id: int,
        symbol: str,
        enabled: bool = True,
        log_every_n: int = 1,
    ):
        """
        Initialize indicator logger.

        Args:
            db_pool: Database connection pool
            run_id: Run ID to log to
            symbol: Trading symbol
            enabled: Whether logging is enabled (default: True)
            log_every_n: Only log every N candles (default: 1)
        """
        self.db_pool = db_pool
        self.run_id = run_id
        self.symbol = symbol
        self.enabled = enabled
        self.log_every_n = log_every_n

        self._candle_count = 0

    async def log(
        self,
        time: datetime,
        indicators: dict[str, dict[str, Any]],
    ) -> bool:
        """
        Log indicator values for a candle.

        Args:
            time: Candle timestamp
            indicators: Dict of indicator data

        Returns:
            True if logged, False if skipped
        """
        if not self.enabled:
            return False

        self._candle_count += 1

        # Check if we should log this candle
        if self._candle_count % self.log_every_n != 0:
            return False

        await save_indicators_batch(
            db_pool=self.db_pool,
            run_id=self.run_id,
            time=time,
            symbol=self.symbol,
            indicators=indicators,
        )

        return True
