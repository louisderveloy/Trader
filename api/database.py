"""
Database connection pool management.

This module provides async PostgreSQL connection pool using asyncpg.
"""

import asyncpg
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Singleton database connection pool manager.

    Manages a single asyncpg connection pool for the application.
    """

    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def create_pool(cls) -> asyncpg.Pool:
        """
        Create database connection pool.

        Returns:
            AsyncPG connection pool

        Raises:
            asyncpg.PostgresError: Database connection error
        """
        if cls._pool is not None:
            logger.warning("Database pool already exists, returning existing pool")
            return cls._pool

        logger.info(
            f"Creating database pool: host={settings.postgres_host}, "
            f"port={settings.postgres_port}, db={settings.postgres_db}"
        )

        try:
            cls._pool = await asyncpg.create_pool(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                min_size=2,
                max_size=10,
                command_timeout=60,
                # Enable connection health checks
                setup=cls._setup_connection,
            )

            logger.info("Database pool created successfully")
            return cls._pool

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    @classmethod
    async def _setup_connection(cls, conn: asyncpg.Connection) -> None:
        """
        Setup function called for each new connection.

        Args:
            conn: Database connection
        """
        # Set connection-level settings if needed
        await conn.execute("SET TIME ZONE 'UTC'")

    @classmethod
    async def close_pool(cls) -> None:
        """Close database connection pool."""
        if cls._pool is not None:
            logger.info("Closing database pool")
            await cls._pool.close()
            cls._pool = None
            logger.info("Database pool closed")

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        """
        Get existing database pool.

        Returns:
            AsyncPG connection pool

        Raises:
            RuntimeError: Pool not initialized
        """
        if cls._pool is None:
            raise RuntimeError(
                "Database pool not initialized. Call create_pool() first."
            )
        return cls._pool


async def get_db_pool() -> asyncpg.Pool:
    """
    FastAPI dependency to get database pool.

    Returns:
        AsyncPG connection pool

    Usage:
        @app.get("/endpoint")
        async def endpoint(db_pool: asyncpg.Pool = Depends(get_db_pool)):
            async with db_pool.acquire() as conn:
                result = await conn.fetch("SELECT * FROM table")
    """
    return DatabasePool.get_pool()


async def check_database_health() -> dict[str, str]:
    """
    Check database connectivity and health.

    Returns:
        Health status dict with status and version

    Raises:
        Exception: Database health check failed
    """
    try:
        pool = DatabasePool.get_pool()
        async with pool.acquire() as conn:
            # Check basic connectivity
            version = await conn.fetchval("SELECT version()")
            # Check TimescaleDB extension
            timescale_version = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
            )

            return {
                "status": "connected",
                "postgres_version": version.split(",")[0],
                "timescaledb_version": timescale_version or "not installed",
            }

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "error", "error": str(e)}
