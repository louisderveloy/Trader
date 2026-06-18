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
from enum import Enum
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


# --- Allowed filter / sort values (whitelists; never interpolate raw user input) ---

class OptStatusFilter(str, Enum):
    """Allowed values for the ``status`` filter."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class OptObjectiveFilter(str, Enum):
    """Allowed values for the ``objective`` filter."""

    sharpe_ratio = "sharpe_ratio"
    sortino_ratio = "sortino_ratio"
    profit_factor = "profit_factor"
    win_rate = "win_rate"
    total_return = "total_return"


class OptSortField(str, Enum):
    """Allowed sort fields."""

    completed_at = "completed_at"
    best_value = "best_value"
    started_at = "started_at"


class SortDirection(str, Enum):
    """Allowed sort directions."""

    asc = "asc"
    desc = "desc"


# Map the (validated) sort field enum to a trusted SQL column expression. Only these
# expressions are ever placed into ORDER BY — the user never supplies a column name.
_SORT_COLUMNS: dict[OptSortField, str] = {
    OptSortField.completed_at: "r.completed_at",
    OptSortField.best_value: "s.best_value",
    OptSortField.started_at: "r.started_at",
}

# The objective lives in the JSONB config snapshot (dashboard launches store it under
# "params", CLI launches under "optimization_config"); read whichever is present.
_OBJECTIVE_EXPR = (
    "COALESCE("
    "r.config_snapshot -> 'params' ->> 'objective', "
    "r.config_snapshot -> 'optimization_config' ->> 'objective')"
)


def _build_filter_clause(
    symbol: str | None,
    objective: OptObjectiveFilter | None,
    status: OptStatusFilter | None,
    active_only: bool,
) -> tuple[str, list[Any]]:
    """
    Build the dynamic ``AND ...`` filter SQL plus its positional params.

    Values are always bound as parameters ($1, $2, ...); column/expression names and
    the enum-validated values are the only things ever embedded in the SQL string.
    Returns a fragment to append after the base ``WHERE r.run_type = 'optimization'``.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if symbol is not None:
        params.append(symbol)
        clauses.append(f"r.symbol = ${len(params)}")
    if objective is not None:
        params.append(objective.value)
        clauses.append(f"{_OBJECTIVE_EXPR} = ${len(params)}")
    if status is not None:
        params.append(status.value)
        clauses.append(f"r.status = ${len(params)}")
    if active_only:
        clauses.append("COALESCE(w.is_active, false) = true")

    return "".join(f" AND {c}" for c in clauses), params


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
    symbol: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=30,
            pattern=r"^[A-Za-z0-9._-]+$",
            description="Filter by trading symbol",
        ),
    ] = None,
    objective: Annotated[
        OptObjectiveFilter | None, Query(description="Filter by optimization objective")
    ] = None,
    status_filter: Annotated[
        OptStatusFilter | None, Query(alias="status", description="Filter by run status")
    ] = None,
    active_only: Annotated[
        bool, Query(description="Only the run whose weights set is active")
    ] = False,
    sort_by: Annotated[
        OptSortField, Query(description="Sort field")
    ] = OptSortField.completed_at,
    sort_dir: Annotated[
        SortDirection, Query(description="Sort direction")
    ] = SortDirection.desc,
    principal: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationListResponse:
    """
    List optimization runs with server-side filtering, sorting and pagination.

    All filter/sort inputs are validated (enums + a symbol pattern) and bound as query
    parameters or mapped through whitelists, so nothing user-supplied is interpolated
    into the SQL. Sorting puts NULLs last and breaks ties on ``r.id`` for stable paging.
    """
    filter_sql, filter_params = _build_filter_clause(
        symbol, objective, status_filter, active_only
    )
    order_col = _SORT_COLUMNS[sort_by]
    direction = "ASC" if sort_dir is SortDirection.asc else "DESC"
    order_sql = f" ORDER BY {order_col} {direction} NULLS LAST, r.id DESC"

    # COUNT(DISTINCT r.id): the joins (needed for the objective/active filters) could
    # otherwise fan out a run across multiple studies and inflate the total.
    count_query = (
        "SELECT COUNT(DISTINCT r.id) AS count FROM runs r "
        "LEFT JOIN optuna_studies s ON s.run_id = r.id "
        "LEFT JOIN weights_sets w ON w.id = COALESCE(r.weights_set_id, s.weights_set_id) "
        "WHERE r.run_type = 'optimization'" + filter_sql
    )
    list_query = (
        _OPTIMIZATION_SELECT
        + filter_sql
        + order_sql
        + f" LIMIT ${len(filter_params) + 1} OFFSET ${len(filter_params) + 2}"
    )

    async with db_pool.acquire() as conn:
        count_row = await conn.fetchrow(count_query, *filter_params)
        total = count_row["count"] if count_row else 0
        rows = await conn.fetch(list_query, *filter_params, limit, offset)

    items = [_row_to_optimization(row) for row in rows]
    logger.info(f"Listed {len(items)} optimizations (total={total})")
    return OptimizationListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/symbols")
@limiter.limit(lambda: settings.rate_limit_api_read)
async def list_optimization_symbols(
    request: Request,
    principal: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict[str, list[str]]:
    """
    Distinct symbols that appear in optimization runs (for the filter dropdown).

    Declared before ``/{run_id}`` so the literal path wins over the int converter.
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT symbol FROM runs "
            "WHERE run_type = 'optimization' AND symbol IS NOT NULL "
            "ORDER BY symbol"
        )
    return {"symbols": [row["symbol"] for row in rows]}


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
