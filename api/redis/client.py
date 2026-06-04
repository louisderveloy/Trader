"""
Redis connection pool management.

Provides Redis connection pool for pub/sub and caching.
"""

import logging
from typing import Optional

from redis import asyncio as aioredis

from ..config import settings

logger = logging.getLogger(__name__)


class RedisPool:
    """
    Singleton Redis connection pool manager.

    Manages Redis connections for pub/sub and caching.
    """

    _pool: Optional[aioredis.Redis] = None

    @classmethod
    async def create_pool(cls) -> aioredis.Redis:
        """
        Create Redis connection pool.

        Returns:
            Redis connection pool

        Raises:
            redis.RedisError: Redis connection error
        """
        if cls._pool is not None:
            logger.warning("Redis pool already exists, returning existing pool")
            return cls._pool

        logger.info(
            f"Creating Redis pool: host={settings.redis_host}, "
            f"port={settings.redis_port}, db={settings.redis_db}"
        )

        try:
            cls._pool = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )

            # Test connection
            await cls._pool.ping()
            logger.info("Redis pool created successfully")

            return cls._pool

        except Exception as e:
            logger.error(f"Failed to create Redis pool: {e}")
            raise

    @classmethod
    async def close_pool(cls) -> None:
        """Close Redis connection pool."""
        if cls._pool is not None:
            logger.info("Closing Redis pool")
            await cls._pool.close()
            cls._pool = None
            logger.info("Redis pool closed")

    @classmethod
    def get_pool(cls) -> aioredis.Redis:
        """
        Get existing Redis pool.

        Returns:
            Redis connection pool

        Raises:
            RuntimeError: Pool not initialized
        """
        if cls._pool is None:
            raise RuntimeError("Redis pool not initialized. Call create_pool() first.")
        return cls._pool


async def get_redis_pool() -> aioredis.Redis:
    """
    FastAPI dependency to get Redis pool.

    Returns:
        Redis connection pool

    Usage:
        @app.get("/endpoint")
        async def endpoint(redis: aioredis.Redis = Depends(get_redis_pool)):
            await redis.set("key", "value")
    """
    return RedisPool.get_pool()


async def check_redis_health() -> dict[str, str]:
    """
    Check Redis connectivity and health.

    Returns:
        Health status dict

    Raises:
        Exception: Redis health check failed
    """
    try:
        redis = RedisPool.get_pool()
        await redis.ping()
        info = await redis.info("server")

        return {
            "status": "connected",
            "version": info.get("redis_version", "unknown"),
        }

    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "error", "error": str(e)}
