"""
Health check endpoint.

Provides system health status for monitoring.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from ..database import check_database_health
from ..redis.client import check_redis_health

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns system health status including database and Redis connectivity.
    No authentication required.

    Returns:
        Health status dict
    """
    # Check database
    db_health = await check_database_health()

    # Check Redis
    redis_health = await check_redis_health()

    # Overall status
    overall_status = "healthy"
    if db_health.get("status") != "connected" or redis_health.get("status") != "connected":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_health,
        "redis": redis_health,
    }
