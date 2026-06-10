"""
Runs management endpoints.

REST API for querying and managing trading runs.
"""

import asyncio
import asyncpg
import json
import logging
import os
import pathlib
from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import Principal, get_principal, require_admin, require_viewer
from ..config import settings
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..limiter import limiter
from ..models.enums import RunStatus, TradeEnvironment
from ..models.run_control import (
    RunCommandResponse,
    RunLogsResponse,
    RunTypeStart,
    StartRunRequest,
    StartRunResponse,
)
from ..models.runs import RunFilter, RunListResponse, RunResponse, RunStatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

# Resolve the log directory once; per-run paths are confined under it.
_LOG_DIR = pathlib.Path(settings.bot_logs_dir).resolve()
_LOG_MAX_LINE_CHARS = 2000


def _tail_file(path: pathlib.Path, n: int, max_bytes: int = 262_144) -> tuple[list[str], bool]:
    """Return the last ``n`` lines of ``path`` plus a truncation flag.

    Pure-python tail (no shell): reads at most ``max_bytes`` from the end of the
    file, splits into lines, keeps the last ``n``, and truncates over-long lines.
    Blocking IO — call via ``asyncio.to_thread``.
    """
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        read_size = min(size, max_bytes)
        fh.seek(size - read_size)
        data = fh.read(read_size)

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    # If we started mid-file, the first (partial) line is unreliable — drop it.
    partial = read_size < size
    if partial and lines:
        lines = lines[1:]

    truncated = partial or len(lines) > n
    tail = lines[-n:]
    tail = [ln[:_LOG_MAX_LINE_CHARS] for ln in tail]
    return tail, truncated


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
    principal: Principal = Depends(require_viewer),
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
    principal: Principal = Depends(require_viewer),
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


@router.get("/symbols")
async def list_symbols(
    principal: Principal = Depends(require_viewer),
) -> dict:
    """
    List the trading symbols selectable when starting a run.

    Driven by the ``AVAILABLE_SYMBOLS`` env var (comma-separated, USDC quote).
    The first entry is the default. Defined before ``/{run_id}`` so the literal
    path wins over the integer path parameter.
    """
    symbols = settings.available_symbols_list
    return {"symbols": symbols, "default": symbols[0]}


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: int,
    principal: Principal = Depends(require_viewer),
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
    principal: Principal = Depends(require_admin),
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

        # SAFEGUARD: Prevent closing run with open positions
        if new_status in {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED}:
            # Check for open trades in database
            open_trades_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM trades
                WHERE run_id = $1 AND status = 'open'
                """,
                run_id,
            )

            if open_trades_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot close run: {open_trades_count} open trade(s) found. "
                           f"Please close all positions before ending the run.",
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


# ============================================================================
# Run control: start / stop / kill / logs
# ============================================================================

async def _queue_command(conn: asyncpg.Connection, run_id: int, kind: str,
                         params: dict | None = None) -> int:
    """Insert a run_commands row (the trigger fires the NOTIFY) and return its id.

    A pending command of the same kind for the same run violates the partial
    unique index and surfaces as a 409 instead of a duplicate.
    """
    try:
        return await conn.fetchval(
            "INSERT INTO run_commands (run_id, kind, params, status) "
            "VALUES ($1, $2, $3, 'pending') RETURNING id",
            run_id, kind, json.dumps(params) if params is not None else None,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A '{kind}' command is already pending for run {run_id}",
        )


@router.post("/start", response_model=StartRunResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: settings.rate_limit_expensive)
async def start_run(
    request: Request,
    payload: StartRunRequest,
    principal: Principal = Depends(require_admin),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> StartRunResponse:
    """
    Start a backtest, paper or live run.

    Admin only. Requires a CSRF token. Mainnet live additionally requires the
    ``confirm_phrase`` safety field (validated in :class:`StartRunRequest`).

    Creates a PENDING run row and queues a ``start`` command for the supervisor
    in a single transaction, so the run is visible before the NOTIFY fires.
    Parallelism mirrors the CLI: paper and live are single-instance (enforced by
    a DB unique index + this pre-check); backtests are capped by
    ``max_concurrent_backtests``.
    """
    await validate_csrf_token(request)

    rt = payload.run_type
    params = payload.to_command_params()
    environment = payload.environment()

    now = datetime.now(timezone.utc)
    if rt == RunTypeStart.BACKTEST:
        start_dt = datetime.combine(payload.start_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(payload.end_date, time.min, tzinfo=timezone.utc)
    else:
        # Live/paper are open-ended; end_date is updated on completion by the bot.
        start_dt = end_dt = now

    config_snapshot = {
        "source": "dashboard",
        "started_by": principal.username,
        "params": params,
    }

    async with db_pool.acquire() as conn:
        # UX pre-check (the DB unique index is the real guard against races).
        if rt in (RunTypeStart.PAPER, RunTypeStart.LIVE):
            existing = await conn.fetchval(
                "SELECT id FROM runs WHERE run_type = $1 AND status IN ('pending', 'running') LIMIT 1",
                rt.value,
            )
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A {rt.value} run is already active (run {existing})",
                )
        else:  # backtest concurrency cap (Finding #9)
            active_backtests = await conn.fetchval(
                "SELECT COUNT(*) FROM runs WHERE run_type = 'backtest' AND status IN ('pending', 'running')"
            )
            if active_backtests >= settings.max_concurrent_backtests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Max concurrent backtests ({settings.max_concurrent_backtests}) reached",
                )

        try:
            async with conn.transaction():
                run_id = await conn.fetchval(
                    """
                    INSERT INTO runs (
                        run_type, status, environment, symbol, timeframe,
                        start_date, end_date, config_snapshot, weights_set_id
                    ) VALUES ($1, 'pending', $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    rt.value, environment, payload.symbol, payload.timeframe,
                    start_dt, end_dt, json.dumps(config_snapshot), payload.weights_set_id,
                )
                command_id = await _queue_command(conn, run_id, "start", params)
        except asyncpg.UniqueViolationError:
            # Single-instance index tripped by a concurrent start of the same type.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {rt.value} run is already active",
            )

    logger.info(f"Queued start: run={run_id} type={rt.value} env={environment} by={principal.username}")
    return StartRunResponse(run_id=run_id, command_id=command_id)


@router.post("/{run_id}/stop", response_model=RunCommandResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def stop_run(
    request: Request,
    run_id: int,
    principal: Principal = Depends(require_admin),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunCommandResponse:
    """
    Request a graceful stop (SIGTERM) of a running/pending run.

    Admin only, CSRF-protected. The bot closes positions and writes a terminal
    status during graceful shutdown. Valid for all run types.
    """
    await validate_csrf_token(request)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, run_type FROM runs WHERE id = $1", run_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
        if row["status"] not in ("running", "pending"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {run_id} is {row['status']}; cannot stop",
            )
        command_id = await _queue_command(conn, run_id, "stop")

    logger.info(f"Queued stop: run={run_id} by={principal.username}")
    return RunCommandResponse(run_id=run_id, command_id=command_id, kind="stop",
                              message="Stop command queued (graceful shutdown)")


@router.post("/{run_id}/kill", response_model=RunCommandResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def kill_run(
    request: Request,
    run_id: int,
    principal: Principal = Depends(require_admin),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunCommandResponse:
    """
    Force-kill (SIGKILL) a run. **Backtest only.**

    Killing paper/live is rejected (409): SIGKILL bypasses position-close and
    would leave exchange positions open (security review Finding #3). Use stop
    for paper/live.
    """
    await validate_csrf_token(request)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, run_type FROM runs WHERE id = $1", run_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
        if row["run_type"] != "backtest":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Kill is only allowed for backtest runs; use stop for paper/live",
            )
        if row["status"] not in ("running", "pending"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {run_id} is {row['status']}; cannot kill",
            )
        command_id = await _queue_command(conn, run_id, "kill")

    logger.info(f"Queued kill: run={run_id} by={principal.username}")
    return RunCommandResponse(run_id=run_id, command_id=command_id, kind="kill",
                              message="Kill command queued")


@router.get("/{run_id}/logs", response_model=RunLogsResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_run_logs(
    request: Request,
    run_id: int,
    principal: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RunLogsResponse:
    """
    Return a snapshot of the last log lines for a run (not live-streamed).

    Viewer or admin. The file path is built solely from the integer ``run_id``
    and confined under the configured log directory (security review Finding #7).
    """
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM runs WHERE id = $1", run_id)
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")

    log_path = (_LOG_DIR / f"run_{run_id}.log").resolve()
    # Defense in depth: never read outside the log directory.
    if not log_path.is_relative_to(_LOG_DIR):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run id")

    if not log_path.exists():
        # Run exists but no log yet (e.g. just queued) — return an empty snapshot.
        return RunLogsResponse(run_id=run_id, lines=[], truncated=False)

    lines, truncated = await asyncio.to_thread(_tail_file, log_path, settings.run_logs_max_lines)
    return RunLogsResponse(run_id=run_id, lines=lines, truncated=truncated)
