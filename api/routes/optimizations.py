"""
Optimizations management endpoints.

An optimization is a run (``run_type='optimization'``). Launching one goes through
the same ``run_commands`` control plane as ``POST /runs/start``: the API pre-creates
a PENDING ``runs`` row and queues a ``start`` command; the bot supervisor spawns
``python -m main optimize run ... --run-id <id>`` and the runner adopts the row,
driving it PENDING -> RUNNING -> COMPLETED/FAILED. Stop/kill/logs reuse the existing
``/runs/{id}/...`` endpoints (keyed by run id).

Listing reads the ``runs`` row (lifecycle/status) left-joined onto ``optuna_studies``
(results, present once the study completes).
"""

import asyncpg
import json
import logging
from datetime import datetime, time, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import Principal, require_admin, require_viewer
from ..config import settings
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..limiter import limiter
from ..models.optimizations import OptimizationListResponse, OptimizationResponse
from ..models.run_control import StartOptimizationRequest, StartRunResponse
from .runs import _queue_command

logger = logging.getLogger(__name__)

router = APIRouter()


# Columns selected for an optimization (runs row left-joined onto its study).
_OPTIMIZATION_SELECT = """
    SELECT
        r.id              AS run_id,
        r.status          AS status,
        r.symbol          AS symbol,
        r.timeframe       AS timeframe,
        r.created_at      AS created_at,
        r.started_at      AS started_at,
        r.completed_at    AS completed_at,
        r.config_snapshot AS config_snapshot,
        s.id              AS study_id,
        s.study_name      AS study_study_name,
        s.n_trials        AS study_n_trials,
        s.best_value      AS best_value,
        s.best_params     AS best_params,
        COALESCE(r.weights_set_id, s.weights_set_id) AS weights_set_id,
        w.is_active       AS weights_set_active
    FROM runs r
    LEFT JOIN optuna_studies s ON s.run_id = r.id
    LEFT JOIN weights_sets w   ON w.id = COALESCE(r.weights_set_id, s.weights_set_id)
    WHERE r.run_type = 'optimization'
"""


def _as_dict(value: Any) -> dict:
    """Parse a JSONB column (asyncpg returns it as a str) into a dict."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value or {}


def _row_to_optimization(row: asyncpg.Record) -> OptimizationResponse:
    """Merge a runs row and its (optional) optuna_studies row into a response."""
    snap = _as_dict(row["config_snapshot"])
    # Dashboard launches store the validated params under "params"; CLI launches
    # store an "optimization_config" snapshot. Read from whichever is present.
    params = snap.get("params") or {}
    opt_cfg = snap.get("optimization_config") or {}

    run_id = row["run_id"]
    study_name = (
        row["study_study_name"]
        or params.get("study_name")
        or opt_cfg.get("study_name")
        or f"run-{run_id}"
    )

    return OptimizationResponse(
        run_id=run_id,
        status=row["status"],
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        study_name=study_name,
        objective=params.get("objective") or opt_cfg.get("objective"),
        n_trials=row["study_n_trials"] or params.get("n_trials") or opt_cfg.get("n_trials"),
        n_splits=params.get("n_splits") or opt_cfg.get("n_splits"),
        study_id=str(row["study_id"]) if row["study_id"] is not None else None,
        best_value=row["best_value"],
        best_params=_as_dict(row["best_params"]) or None,
        weights_set_id=str(row["weights_set_id"]) if row["weights_set_id"] is not None else None,
        weights_set_active=bool(row["weights_set_active"]),
    )


@router.get("", response_model=OptimizationListResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def list_optimizations(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    principal: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationListResponse:
    """List optimization runs (running/failed/completed), newest first."""
    count_query = "SELECT COUNT(*) AS count FROM runs WHERE run_type = 'optimization'"
    list_query = _OPTIMIZATION_SELECT + " ORDER BY r.created_at DESC LIMIT $1 OFFSET $2"

    async with db_pool.acquire() as conn:
        count_row = await conn.fetchrow(count_query)
        total = count_row["count"] if count_row else 0
        rows = await conn.fetch(list_query, limit, offset)

    items = [_row_to_optimization(row) for row in rows]
    logger.info(f"Listed {len(items)} optimizations (total={total})")
    return OptimizationListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=OptimizationResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_optimization(
    run_id: int,
    request: Request,
    principal: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """Get a single optimization run (by run id)."""
    query = _OPTIMIZATION_SELECT + " AND r.id = $1"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, run_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization run {run_id} not found",
        )
    return _row_to_optimization(row)


@router.post("/{run_id}/activate-weights", response_model=OptimizationResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def activate_optimization_weights(
    run_id: int,
    request: Request,
    principal: Principal = Depends(require_admin),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """
    Activate the weights set produced by this optimization run.

    Admin only, CSRF-protected. Mirrors the CLI ``optimize activate`` command:
    deactivates every other set and activates this run's set (the bot reads the
    active set from the DB on demand, so no NOTIFY is needed). Returns the refreshed
    optimization so the dashboard can update the card in place.
    """
    await validate_csrf_token(request)

    async with db_pool.acquire() as conn:
        run_exists = await conn.fetchval(
            "SELECT 1 FROM runs WHERE id = $1 AND run_type = 'optimization'", run_id
        )
        if not run_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Optimization run {run_id} not found",
            )

        weights_set_id = await conn.fetchval(
            """
            SELECT COALESCE(
                r.weights_set_id,
                (
                    SELECT s.weights_set_id FROM optuna_studies s
                    WHERE s.run_id = r.id AND s.weights_set_id IS NOT NULL
                    ORDER BY s.created_at DESC LIMIT 1
                )
            )
            FROM runs r WHERE r.id = $1
            """,
            run_id,
        )
        if weights_set_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This optimization has not produced a weights set yet",
            )

        async with conn.transaction():
            await conn.execute("UPDATE weights_sets SET is_active = false WHERE is_active = true")
            await conn.execute(
                "UPDATE weights_sets SET is_active = true WHERE id = $1", weights_set_id
            )

        row = await conn.fetchrow(_OPTIMIZATION_SELECT + " AND r.id = $1", run_id)

    logger.info(
        f"Activated weights set {weights_set_id} from optimization run {run_id} "
        f"by={principal.username}"
    )
    return _row_to_optimization(row)


@router.post("", response_model=StartRunResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: settings.rate_limit_expensive)
async def launch_optimization(
    request: Request,
    payload: StartOptimizationRequest,
    principal: Principal = Depends(require_admin),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> StartRunResponse:
    """
    Launch a new optimization run.

    Admin only, CSRF-protected, rate limited (expensive). Creates a PENDING run
    and queues a ``start`` command in a single transaction. Single-instance is
    enforced by a PostgreSQL advisory lock in the bot (this pre-check is for UX);
    an optimization may run alongside a paper/live run.
    """
    await validate_csrf_token(request)

    params = payload.to_command_params()
    now = datetime.now(timezone.utc)
    start_dt = (
        datetime.combine(payload.start_date, time.min, tzinfo=timezone.utc)
        if payload.start_date else now
    )
    end_dt = (
        datetime.combine(payload.end_date, time.min, tzinfo=timezone.utc)
        if payload.end_date else now
    )

    config_snapshot = {
        "source": "dashboard",
        "started_by": principal.username,
        "params": params,
    }

    async with db_pool.acquire() as conn:
        # UX pre-check (the bot's advisory lock is the real single-instance guard).
        existing = await conn.fetchval(
            "SELECT id FROM runs WHERE run_type = 'optimization' "
            "AND status IN ('pending', 'running') LIMIT 1"
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An optimization is already active (run {existing})",
            )

        async with conn.transaction():
            run_id = await conn.fetchval(
                """
                INSERT INTO runs (
                    run_type, status, environment, symbol, timeframe,
                    start_date, end_date, config_snapshot
                ) VALUES ('optimization', 'pending', 'dev', $1, $2, $3, $4, $5)
                RETURNING id
                """,
                payload.symbol, payload.timeframe, start_dt, end_dt,
                json.dumps(config_snapshot),
            )
            command_id = await _queue_command(conn, run_id, "start", params)

    logger.info(
        f"Queued optimization start: run={run_id} study={payload.study_name!r} "
        f"by={principal.username}"
    )
    return StartRunResponse(run_id=run_id, command_id=command_id)
