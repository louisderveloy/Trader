#!/usr/bin/env python3
"""
Instance Lock Manager - PostgreSQL Advisory Lock Implementation

Ensures only ONE instance of each mode can run at a time:
- Only one paper trading instance globally
- Only one live trading instance globally (testnet and mainnet share the same lock)
- Only one optimization instance globally (independent lock; may run alongside trading)

Uses PostgreSQL advisory locks for reliable, crash-safe instance locking.
Locks are automatically released when the database connection closes.
"""

import json
import logging
from datetime import datetime, timezone
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
    - 'optimization': 1456372819

    IMPORTANT: This class requires a persistent connection to be held for the
    duration of the lock. Use acquire_lock_connection() to get a connection
    that holds the lock, and release it with release_lock_connection().
    """

    # Lock keys (hashed to int32 for pg_advisory_lock)
    # These must be positive integers in the range [0, 2^31-1]
    LOCK_KEYS = {
        'paper': 1827364950,  # hash('paper_trading') & 0x7FFFFFFF
        'live': 1923847563,  # hash('live_trading') & 0x7FFFFFFF
        'optimization': 1456372819,  # hash('optimization') & 0x7FFFFFFF
    }

    @staticmethod
    def get_lock_key(mode: str) -> int:
        """
        Get the integer lock key for a mode.

        Args:
            mode: Mode ('paper', 'live' or 'optimization')

        Returns:
            Integer lock key

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in InstanceLockManager.LOCK_KEYS:
            raise ValueError(
                f"Invalid mode: {mode}. Must be 'paper', 'live' or 'optimization'"
            )
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
    async def is_lock_held(db_pool: asyncpg.Pool, mode: str) -> bool:
        """
        Check if the advisory lock for mode is currently held by any session.

        Queries pg_locks directly without acquiring the lock — safe for read-only checks.
        Returns True if another session holds the lock (i.e. a real instance is running).

        Args:
            db_pool: Database connection pool
            mode: Trading mode ('paper' or 'live')

        Returns:
            True if the lock is currently held, False otherwise
        """
        lock_key = InstanceLockManager.get_lock_key(mode)
        async with db_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_locks
                    WHERE locktype = 'advisory'
                    AND classid = 0
                    AND objid = $1::bigint
                    AND granted = true
                )
                """,
                lock_key,
            )
        held = bool(result)
        logger.debug(f"Advisory lock for mode '{mode}' (key={lock_key}) is {'held' if held else 'free'}")
        return held

    @staticmethod
    async def cleanup_stale_runs(
        db_pool: asyncpg.Pool, mode: str, exclude_run_id: Optional[int] = None
    ) -> int:
        """
        Mark stale 'running'/'pending' runs of the given mode as 'cancelled'.

        Call this AFTER acquiring the advisory lock so we know for certain no other
        instance is running. Any run still showing status='running'/'pending' at that
        point is a zombie left behind by a previous crash or container kill.

        Args:
            db_pool: Database connection pool
            mode: Trading mode ('paper' or 'live')
            exclude_run_id: A run id to NEVER cancel. In the supervisor flow the bot
                is launched to adopt a freshly pre-created PENDING run; that run must
                be excluded here, otherwise we would cancel the very run we are about
                to adopt (and _create_run_record would then fail to adopt it).

        Returns:
            Number of stale runs cleaned up
        """
        now = datetime.now(timezone.utc)
        interrupted_result = json.dumps({
            "interrupted_by": "container_restart",
            "cleanup_at": now.isoformat(),
            "reason": (
                "Run was in running/pending state but advisory lock was not held — "
                "marked cancelled on bot startup after container restart/crash."
            ),
        })

        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE runs
                SET
                    status = 'cancelled',
                    completed_at = $1,
                    result = COALESCE(result, $2::jsonb)
                WHERE run_type = $3
                  AND status IN ('running', 'pending')
                  AND ($4::int IS NULL OR id <> $4)
                """,
                now,
                interrupted_result,
                mode,
                exclude_run_id,
            )

        count = int(result.split()[-1]) if result else 0
        if count > 0:
            logger.warning(
                f"Cleaned up {count} stale run(s) for mode '{mode}': "
                f"were running/pending but no advisory lock was held"
            )
        return count

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
        if mode not in ['paper', 'live', 'optimization']:
            raise ValueError(
                f"Invalid mode: {mode}. Must be 'paper', 'live' or 'optimization'"
            )

        # Query for runs with matching run_type and status='running'
        # run_type matches the mode name ('paper'/'live'/'optimization')
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
