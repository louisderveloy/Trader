"""
Runs management endpoints.

REST API for querying and managing trading runs.
"""

import asyncpg
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import User, get_current_user
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..models.enums import RunStatus, TradeEnvironment
from ..models.runs import RunFilter, RunListResponse, RunResponse, RunStatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


def _row_to_run_response(row: asyncpg.Record) -> RunResponse:
    """
    Convert database row to RunResponse, parsing JSON fields.

    PostgreSQL JSONB columns are returned as strings by asyncpg,
    so we need to parse them manually.

    Args:
        row: Database row

    Returns:
        RunResponse model
    """
    data = dict(row)

    # Parse JSON fields if they're strings
    if isinstance(data.get("config_snapshot"), str):
        data["config_snapshot"] = json.loads(data["config_snapshot"])

    if isinstance(data.get("result"), str):
        data["result"] = json.loads(data["result"])

    return RunResponse(**data)


@router.get("", response_model=RunListResponse)
async def list_runs(
    run_type: Annotated[str | None, Query(max_length=50, description="Filter by run type (max 50 chars)")] = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status", description="Filter by status (pending/running/completed/failed/cancelled)")] = None,
    environment: Annotated[TradeEnvironment | None, Query(description="Filter by environment (testnet/live/paper/backtest)")] = None,
    symbol: Annotated[str | None, Query(max_length=20, description="Filter by symbol (max 20 chars)")] = None,
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
    items = [_row_to_run_response(row) for row in rows]

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

    items = [_row_to_run_response(row) for row in rows]
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

    return _row_to_run_response(row)


@router.patch("/{run_id}/status", response_model=RunResponse)
async def update_run_status(
    http_request: Request,
    run_id: int,
    update: RunStatusUpdate,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunResponse:
    """
    Update run status.

    Admin only endpoint. Validates status transitions.
    Requires authentication and CSRF token.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        run_id: Run ID
        update: Status update request

    Returns:
        Updated run

    Raises:
        HTTPException: 404 if run not found, 400 if invalid transition, 403 if CSRF validation fails
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
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

    return _row_to_run_response(row)
