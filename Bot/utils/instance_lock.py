#!/usr/bin/env python3
"""
Instance Lock Manager - PostgreSQL Advisory Lock Implementation

Ensures only ONE instance of each trading mode can run at a time:
- Only one paper trading instance globally
- Only one live trading instance globally (testnet and mainnet share the same lock)

Uses PostgreSQL advisory locks for reliable, crash-safe instance locking.
Locks are automatically released when the database connection closes.
"""

import logging
from typing import Optional, Dict, Any

import asyncpg

logger = logging.getLogger(__name__)


class InstanceLockManager:
    """
    Manages single-instance enforcement using PostgreSQL advisory locks.

    Advisory locks are session-scoped and automatically released when:
    - The connection closes normally
    - The process crashes
    - The database connection is terminated

    Lock keys are deterministic integers derived from mode names:
    - 'paper': 1827364950
    - 'live': 1923847563

    IMPORTANT: This class requires a persistent connection to be held for the
    duration of the lock. Use acquire_lock_connection() to get a connection
    that holds the lock, and release it with release_lock_connection().
    """

    # Lock keys (hashed to int32 for pg_advisory_lock)
    # These must be positive integers in the range [0, 2^31-1]
    LOCK_KEYS = {
        'paper': 1827364950,  # hash('paper_trading') & 0x7FFFFFFF
        'live': 1923847563,  # hash('live_trading') & 0x7FFFFFFF
    }

    @staticmethod
    def get_lock_key(mode: str) -> int:
        """
        Get the integer lock key for a mode.

        Args:
            mode: Trading mode ('paper' or 'live')

        Returns:
            Integer lock key

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in InstanceLockManager.LOCK_KEYS:
            raise ValueError(f"Invalid mode: {mode}. Must be 'paper' or 'live'")
        return InstanceLockManager.LOCK_KEYS[mode]

    @staticmethod
    async def acquire_lock_connection(db_pool: asyncpg.Pool, mode: str) -> Optional[asyncpg.Connection]:
        """
        Acquire advisory lock and return the connection holding the lock.

        CRITICAL: The returned connection must be kept open for the duration
        of the lock. Close it with release_lock_connection() when done.

        Args:
            db_pool: Database connection pool
            mode: Trading mode ('paper' or 'live')

        Returns:
            Connection object if lock acquired, None if lock already held

        Raises:
            ValueError: If mode is invalid
            asyncpg.PostgresError: If database query fails
        """
        lock_key = InstanceLockManager.get_lock_key(mode)

        # Acquire a connection from the pool
        conn = await db_pool.acquire()

        try:
            # Try to acquire the advisory lock on this connection
            result = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)",
                lock_key
            )

            if result:
                logger.info(f"✓ Instance lock acquired for mode '{mode}' (key={lock_key})")
                return conn
            else:
                logger.warning(f"✗ Failed to acquire instance lock for mode '{mode}' (key={lock_key}) - already held")
                # Release the connection back to the pool since we didn't get the lock
                await db_pool.release(conn)
                return None

        except Exception as e:
            # If anything goes wrong, release the connection
            await db_pool.release(conn)
            raise

    @staticmethod
    async def release_lock_connection(db_pool: asyncpg.Pool, conn: asyncpg.Connection, mode: str):
        """
        Release advisory lock and return connection to pool.

        Args:
            db_pool: Database connection pool
            conn: Connection holding the lock
            mode: Trading mode ('paper' or 'live')

        Raises:
            ValueError: If mode is invalid
        """
        if conn is None:
            return

        lock_key = InstanceLockManager.get_lock_key(mode)

        try:
            # Release the advisory lock
            result = await conn.fetchval(
                "SELECT pg_advisory_unlock($1)",
                lock_key
            )

            if result:
                logger.info(f"✓ Instance lock released for mode '{mode}' (key={lock_key})")
            else:
                logger.warning(f"⚠ Lock for mode '{mode}' (key={lock_key}) was not held during release")

        finally:
            # Always return the connection to the pool
            await db_pool.release(conn)

    @staticmethod
    async def check_existing_runs(db_pool: asyncpg.Pool, mode: str) -> Optional[Dict[str, Any]]:
        """
        Check for existing running instances in the database.

        This is a secondary safety check in addition to advisory locks.
        Provides visibility into which run is currently active.

        Args:
            db_pool: Database connection pool
            mode: Trading mode ('paper' or 'live')

        Returns:
            Dict with run info if found (id, started_at, symbol), None otherwise

        Raises:
            ValueError: If mode is invalid
            asyncpg.PostgresError: If database query fails
        """
        if mode not in ['paper', 'live']:
            raise ValueError(f"Invalid mode: {mode}. Must be 'paper' or 'live'")

        # Query for runs with matching run_type and status='running'
        # run_type is 'paper' for paper mode, 'live' for live mode
        query = """
            SELECT
                id,
                started_at,
                config_snapshot->>'symbol' as symbol,
                environment
            FROM runs
            WHERE run_type = $1 AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        """

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, mode)

        if row:
            result = {
                'id': row['id'],
                'started_at': row['started_at'],
                'symbol': row['symbol'] or 'unknown',
                'environment': row['environment']
            }
            logger.debug(f"Found existing running instance for mode '{mode}': {result}")
            return result

        logger.debug(f"No existing running instances found for mode '{mode}'")
        return None
