"""
Errors log endpoints.

REST API for querying error logs with filtering.
"""

import asyncpg
import json
import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.errors import ErrorLogListResponse, ErrorLogResponse, ErrorStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _row_to_error_response(row: asyncpg.Record) -> ErrorLogResponse:
    """
    Convert database row to ErrorLogResponse, parsing JSON fields.

    Args:
        row: Database row

    Returns:
        ErrorLogResponse model
    """
    data = dict(row)

    # Parse context field if it's a string
    if isinstance(data.get("context"), str):
        data["context"] = json.loads(data["context"])

    return ErrorLogResponse(**data)


@router.get("", response_model=ErrorLogListResponse)
async def list_errors(
    severity: Annotated[str | None, Query(description="Filter by severity")] = None,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    start_date: Annotated[datetime | None, Query(description="Filter from date")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter to date")] = None,
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> ErrorLogListResponse:
    """
    List error logs with filtering and pagination.

    Requires authentication.

    Returns:
        Paginated list of error logs
    """
    # Build WHERE clause
    conditions = []
    params = {}

    if severity:
        conditions.append(f"severity = ${len(params) + 1}")
        params["severity"] = severity

    if category:
        conditions.append(f"category = ${len(params) + 1}")
        params["category"] = category

    if start_date:
        conditions.append(f"timestamp >= ${len(params) + 1}")
        params["start_date"] = start_date

    if end_date:
        conditions.append(f"timestamp <= ${len(params) + 1}")
        params["end_date"] = end_date

    if run_id:
        conditions.append(f"run_id = ${len(params) + 1}")
        params["run_id"] = run_id

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count total
    count_query = f"SELECT COUNT(*) as count FROM errors_log {where_clause}"

    # Get errors
    errors_query = f"""
        SELECT
            id, run_id, category, severity,
            error_message, error_traceback, timestamp, context
        FROM errors_log
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """

    async with db_pool.acquire() as conn:
        # Count
        count_row = await conn.fetchrow(count_query, *params.values())
        total = count_row["count"]

        # Fetch errors
        params["limit"] = limit
        params["offset"] = offset
        rows = await conn.fetch(errors_query, *params.values())

    # Convert to response models
    items = [_row_to_error_response(row) for row in rows]

    logger.info(f"Listed {len(items)} errors (total={total})")

    return ErrorLogListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/stats", response_model=ErrorStatsResponse)
async def get_error_stats(
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> ErrorStatsResponse:
    """
    Get error statistics.

    Requires authentication.

    Returns:
        Error statistics including counts by severity and category
    """
    async with db_pool.acquire() as conn:
        # Total errors
        total_row = await conn.fetchrow("SELECT COUNT(*) as count FROM errors_log")
        total_errors = total_row["count"]

        # By severity
        severity_rows = await conn.fetch(
            "SELECT severity, COUNT(*) as count FROM errors_log GROUP BY severity ORDER BY count DESC"
        )
        by_severity = {row["severity"]: row["count"] for row in severity_rows}

        # By category
        category_rows = await conn.fetch(
            """
            SELECT category, COUNT(*) as count
            FROM errors_log
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
            """
        )
        by_category = {row["category"]: row["count"] for row in category_rows}

        # Recent 24h
        recent_row = await conn.fetchrow(
            "SELECT COUNT(*) as count FROM errors_log WHERE timestamp >= NOW() - INTERVAL '24 hours'"
        )
        recent_24h = recent_row["count"]

    logger.info("Retrieved error statistics")

    return ErrorStatsResponse(
        total_errors=total_errors,
        by_severity=by_severity,
        by_category=by_category,
        recent_24h=recent_24h,
    )


@router.get("/categories", response_model=list[str])
async def list_categories(
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[str]:
    """
    Get distinct error categories.

    Requires authentication.

    Returns:
        List of unique error categories
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT category FROM errors_log ORDER BY category"
        )

    categories = [row["category"] for row in rows]
    logger.info(f"Retrieved {len(categories)} error categories")

    return categories


@router.get("/{error_id}", response_model=ErrorLogResponse)
async def get_error(
    error_id: str,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> ErrorLogResponse:
    """
    Get error log details by ID.

    Requires authentication.

    Args:
        error_id: Error log ID (UUID)

    Returns:
        Error log details

    Raises:
        HTTPException: 404 if error not found
    """
    query = """
        SELECT
            id, run_id, category, severity,
            error_message, error_traceback, timestamp, context
        FROM errors_log
        WHERE id = $1
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, error_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Error {error_id} not found",
        )

    return _row_to_error_response(row)
