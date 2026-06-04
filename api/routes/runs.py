"""
Runs management endpoints.

REST API for querying and managing trading runs.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.runs import RunFilter, RunListResponse, RunResponse, RunStatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=RunListResponse)
async def list_runs(
    run_type: Annotated[str | None, Query(description="Filter by run type")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by status")] = None,
    environment: Annotated[str | None, Query(description="Filter by environment")] = None,
    symbol: Annotated[str | None, Query(description="Filter by symbol")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunListResponse:
    """
    List runs with filtering and pagination.

    Requires authentication.

    Returns:
        Paginated list of runs
    """
    # Build WHERE clause
    conditions = []
    params = {}

    if run_type:
        conditions.append(f"run_type = ${ len(params) + 1}")
        params["run_type"] = run_type

    if status_filter:
        conditions.append(f"status = ${len(params) + 1}")
        params["status"] = status_filter

    if environment:
        conditions.append(f"environment = ${len(params) + 1}")
        params["environment"] = environment

    if symbol:
        conditions.append(f"symbol = ${len(params) + 1}")
        params["symbol"] = symbol

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count total
    count_query = f"SELECT COUNT(*) as count FROM runs {where_clause}"

    # Get runs
    runs_query = f"""
        SELECT
            id, run_type, status, environment,
            symbol, timeframe, start_date, end_date,
            config_snapshot, result,
            created_at, started_at, completed_at,
            weights_set_id, optuna_study_id
        FROM runs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """

    async with db_pool.acquire() as conn:
        # Count
        count_row = await conn.fetchrow(count_query, *params.values())
        total = count_row["count"]

        # Fetch runs
        params["limit"] = limit
        params["offset"] = offset
        rows = await conn.fetch(runs_query, *params.values())

    # Convert to response models
    items = [RunResponse(**dict(row)) for row in rows]

    logger.info(f"Listed {len(items)} runs (total={total})")

    return RunListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/active", response_model=list[RunResponse])
async def get_active_runs(
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[RunResponse]:
    """
    Get currently active (running or pending) runs.

    Requires authentication.

    Returns:
        List of active runs
    """
    query = """
        SELECT
            id, run_type, status, environment,
            symbol, timeframe, start_date, end_date,
            config_snapshot, result,
            created_at, started_at, completed_at,
            weights_set_id, optuna_study_id
        FROM runs
        WHERE status IN ('pending', 'running')
        ORDER BY created_at DESC
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query)

    items = [RunResponse(**dict(row)) for row in rows]
    logger.info(f"Found {len(items)} active runs")

    return items


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunResponse:
    """
    Get run details by ID.

    Requires authentication.

    Args:
        run_id: Run ID

    Returns:
        Run details

    Raises:
        HTTPException: 404 if run not found
    """
    query = """
        SELECT
            id, run_type, status, environment,
            symbol, timeframe, start_date, end_date,
            config_snapshot, result,
            created_at, started_at, completed_at,
            weights_set_id, optuna_study_id
        FROM runs
        WHERE id = $1
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, run_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )

    return RunResponse(**dict(row))


@router.patch("/{run_id}/status", response_model=RunResponse)
async def update_run_status(
    run_id: int,
    update: RunStatusUpdate,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunResponse:
    """
    Update run status.

    Admin only endpoint. Validates status transitions.

    Args:
        run_id: Run ID
        update: Status update request

    Returns:
        Updated run

    Raises:
        HTTPException: 404 if run not found, 400 if invalid transition
    """
    # Import for status validation
    from bot.runs.types import RunStatus, is_valid_status_transition

    # Get current run
    get_query = "SELECT status FROM runs WHERE id = $1"

    async with db_pool.acquire() as conn:
        current_row = await conn.fetchrow(get_query, run_id)

        if not current_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )

        # Validate transition
        current_status = RunStatus(current_row["status"])
        new_status = RunStatus(update.status)

        if not is_valid_status_transition(current_status, new_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition: {current_status.value} -> {new_status.value}",
            )

        # Update status
        update_query = """
            UPDATE runs
            SET status = $2
            WHERE id = $1
            RETURNING
                id, run_type, status, environment,
                symbol, timeframe, start_date, end_date,
                config_snapshot, result,
                created_at, started_at, completed_at,
                weights_set_id, optuna_study_id
        """

        row = await conn.fetchrow(update_query, run_id, new_status.value)

    logger.info(
        f"Updated run {run_id} status: {current_status.value} -> {new_status.value}"
        + (f" (reason: {update.reason})" if update.reason else "")
    )

    return RunResponse(**dict(row))
