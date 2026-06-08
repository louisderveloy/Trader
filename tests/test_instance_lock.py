#!/usr/bin/env python3
"""
Tests for Instance Lock Manager

Tests the PostgreSQL advisory lock implementation for single-instance enforcement.
"""

import pytest
import asyncpg
import asyncio
import os
from datetime import datetime, timezone

from utils.instance_lock import InstanceLockManager


@pytest.fixture
async def db_pool():
    """Create a database connection pool for testing."""
    dsn = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trading_bot")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)

    # Clean up any existing locks before tests
    async with pool.acquire() as conn:
        # Release all advisory locks on this connection
        await conn.execute("SELECT pg_advisory_unlock_all()")

        # Terminate any other backends holding advisory locks
        try:
            result = await conn.fetch("""
                SELECT pg_terminate_backend(pid)
                FROM pg_locks
                WHERE locktype = 'advisory'
                AND pid != pg_backend_pid()
            """)
            if result:
                # Wait a moment for connections to terminate
                await asyncio.sleep(0.5)
        except Exception as e:
            # Non-fatal if this fails
            print(f"Warning: Could not terminate backends: {e}")

    yield pool

    # Clean up after all tests
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_unlock_all()")

        # Terminate any backends still holding locks
        try:
            await conn.fetch("""
                SELECT pg_terminate_backend(pid)
                FROM pg_locks
                WHERE locktype = 'advisory'
                AND pid != pg_backend_pid()
            """)
        except Exception:
            pass

    await pool.close()


@pytest.fixture
async def clean_runs_table(db_pool):
    """Clean up runs table before and after tests."""
    # Clean up before test - mark as completed instead of deleting to avoid FK issues
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE runs
            SET status = 'test_cleanup', completed_at = NOW()
            WHERE run_type IN ('paper', 'live') AND status = 'running'
        """)

    yield

    # Clean up after test - mark as completed instead of deleting
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE runs
            SET status = 'test_cleanup', completed_at = NOW()
            WHERE run_type IN ('paper', 'live') AND status = 'running'
        """)


@pytest.fixture(autouse=True)
async def release_locks_between_tests(db_pool):
    """Automatically release all advisory locks before and after each test."""
    # Release locks before test
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_unlock_all()")

    yield

    # Release locks after test (critical for cleanup)
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_unlock_all()")


class TestInstanceLockManager:
    """Test suite for InstanceLockManager."""

    @pytest.mark.asyncio
    async def test_get_lock_key_paper(self):
        """Test getting lock key for paper mode."""
        key = InstanceLockManager.get_lock_key('paper')
        assert key == 1827364950
        assert isinstance(key, int)

    @pytest.mark.asyncio
    async def test_get_lock_key_live(self):
        """Test getting lock key for live mode."""
        key = InstanceLockManager.get_lock_key('live')
        assert key == 1923847563
        assert isinstance(key, int)

    @pytest.mark.asyncio
    async def test_get_lock_key_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            InstanceLockManager.get_lock_key('invalid')

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, db_pool):
        """Test successful lock acquisition."""
        conn = None
        try:
            # Acquire lock
            conn = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn is not None
        finally:
            # Always clean up
            if conn:
                await InstanceLockManager.release_lock_connection(db_pool, conn, 'paper')

    @pytest.mark.asyncio
    async def test_acquire_lock_blocks_second(self, db_pool):
        """Test that second acquire fails when lock is held."""
        # Create a second pool to simulate another process
        dsn = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trading_bot")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        pool2 = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=1)

        conn1 = None
        try:
            # First acquire with pool1
            conn1 = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn1 is not None

            # Second acquire should fail with pool2 (different pool = different session)
            conn2 = await InstanceLockManager.acquire_lock_connection(pool2, 'paper')
            assert conn2 is None

        finally:
            # Clean up with pool1 (the one holding the lock)
            if conn1:
                await InstanceLockManager.release_lock_connection(db_pool, conn1, 'paper')
            await pool2.close()

    @pytest.mark.asyncio
    async def test_release_lock(self, db_pool):
        """Test lock release."""
        conn = None
        conn2 = None
        try:
            # Acquire lock first
            conn = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn is not None

            # Release the lock
            await InstanceLockManager.release_lock_connection(db_pool, conn, 'paper')
            conn = None  # Mark as released

            # Verify lock is released by acquiring again
            conn2 = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn2 is not None

        finally:
            # Clean up any remaining locks
            if conn:
                await InstanceLockManager.release_lock_connection(db_pool, conn, 'paper')
            if conn2:
                await InstanceLockManager.release_lock_connection(db_pool, conn2, 'paper')

    @pytest.mark.asyncio
    async def test_release_lock_with_none(self, db_pool):
        """Test releasing a None connection (graceful handling)."""
        # Should not raise an error
        await InstanceLockManager.release_lock_connection(db_pool, None, 'paper')

    @pytest.mark.asyncio
    async def test_lock_auto_release_on_connection_close(self, db_pool):
        """Test that lock is automatically released when connection closes."""
        # Create a temporary pool
        dsn = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trading_bot")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        temp_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=1)

        conn2 = None
        try:
            # Acquire lock with temp pool
            temp_conn = await InstanceLockManager.acquire_lock_connection(temp_pool, 'paper')
            assert temp_conn is not None

            # Close the connection directly (simulates process crash)
            await temp_conn.close()
            await temp_pool.close()

            # Lock should be automatically released, so acquiring with main pool should succeed
            conn2 = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn2 is not None

        finally:
            # Clean up
            if conn2:
                await InstanceLockManager.release_lock_connection(db_pool, conn2, 'paper')

    @pytest.mark.asyncio
    async def test_check_existing_runs_found(self, db_pool, clean_runs_table):
        """Test check_existing_runs when a running instance exists."""
        # Insert a running instance
        started_at = datetime.now(timezone.utc)

        async with db_pool.acquire() as conn:
            # Note: runs.id is an auto-increment INTEGER, not UUID
            row = await conn.fetchrow(
                """
                INSERT INTO runs (
                    run_type, environment, status, symbol, timeframe,
                    start_date, end_date, config_snapshot, started_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                'paper', 'paper', 'running', 'BTCUSDT', '15m',
                started_at, started_at, '{"symbol": "BTCUSDT"}', started_at
            )
            run_id = row['id']

        # Check should find it
        result = await InstanceLockManager.check_existing_runs(db_pool, 'paper')

        assert result is not None
        assert result['id'] == run_id
        assert result['symbol'] == 'BTCUSDT'
        assert result['environment'] == 'paper'

    @pytest.mark.asyncio
    async def test_check_existing_runs_none(self, db_pool, clean_runs_table):
        """Test check_existing_runs when no running instance exists."""
        result = await InstanceLockManager.check_existing_runs(db_pool, 'paper')
        assert result is None

    @pytest.mark.asyncio
    async def test_check_existing_runs_invalid_mode(self, db_pool):
        """Test that invalid mode raises ValueError in check_existing_runs."""
        with pytest.raises(ValueError, match="Invalid mode"):
            await InstanceLockManager.check_existing_runs(db_pool, 'invalid')

    @pytest.mark.asyncio
    async def test_concurrent_different_modes(self, db_pool):
        """Test that paper and live locks don't conflict."""
        conn_paper = None
        conn_live = None
        try:
            # Acquire paper lock
            conn_paper = await InstanceLockManager.acquire_lock_connection(db_pool, 'paper')
            assert conn_paper is not None

            # Acquire live lock should succeed (different lock key)
            conn_live = await InstanceLockManager.acquire_lock_connection(db_pool, 'live')
            assert conn_live is not None

        finally:
            # Clean up
            if conn_paper:
                await InstanceLockManager.release_lock_connection(db_pool, conn_paper, 'paper')
            if conn_live:
                await InstanceLockManager.release_lock_connection(db_pool, conn_live, 'live')

    @pytest.mark.asyncio
    async def test_lock_keys_are_different(self):
        """Test that paper and live have different lock keys."""
        paper_key = InstanceLockManager.get_lock_key('paper')
        live_key = InstanceLockManager.get_lock_key('live')

        assert paper_key != live_key
        assert paper_key > 0
        assert live_key > 0
        # Ensure they're within int32 range
        assert paper_key < 2**31
        assert live_key < 2**31

    @pytest.mark.asyncio
    async def test_acquire_lock_with_invalid_mode(self, db_pool):
        """Test that acquire_lock_connection with invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            await InstanceLockManager.acquire_lock_connection(db_pool, 'invalid')

    @pytest.mark.asyncio
    async def test_release_lock_with_invalid_mode(self, db_pool):
        """Test that release_lock_connection with invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            # Create a dummy connection
            conn = await db_pool.acquire()
            try:
                await InstanceLockManager.release_lock_connection(db_pool, conn, 'invalid')
            finally:
                await db_pool.release(conn)

    @pytest.mark.asyncio
    async def test_check_existing_runs_multiple_runs_returns_latest(self, db_pool, clean_runs_table):
        """Test that check_existing_runs returns the most recent run when multiple exist."""
        # Insert two running instances with different timestamps
        started_at_1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        started_at_2 = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)  # Later

        async with db_pool.acquire() as conn:
            # Note: runs.id is an auto-increment INTEGER, not UUID
            row1 = await conn.fetchrow(
                """
                INSERT INTO runs (
                    run_type, environment, status, symbol, timeframe,
                    start_date, end_date, config_snapshot, started_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                'paper', 'paper', 'running', 'BTCUSDT', '15m',
                started_at_1, started_at_1, '{"symbol": "BTCUSDT"}', started_at_1
            )
            run_id_1 = row1['id']

            row2 = await conn.fetchrow(
                """
                INSERT INTO runs (
                    run_type, environment, status, symbol, timeframe,
                    start_date, end_date, config_snapshot, started_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                'paper', 'paper', 'running', 'ETHUSDT', '15m',
                started_at_2, started_at_2, '{"symbol": "ETHUSDT"}', started_at_2
            )
            run_id_2 = row2['id']

        # Check should return the most recent (run_id_2)
        result = await InstanceLockManager.check_existing_runs(db_pool, 'paper')

        assert result is not None
        assert result['id'] == run_id_2
        assert result['symbol'] == 'ETHUSDT'
