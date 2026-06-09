"""
Health check endpoint.

Provides system health status for monitoring.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from ..database import check_database_health

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns system health status including database connectivity.
    No authentication required.

    Returns:
        Health status dict
    """
    # Check database
    db_health = await check_database_health()

    # Overall status
    overall_status = "healthy"
    if db_health.get("status") != "connected":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_health,
    }
