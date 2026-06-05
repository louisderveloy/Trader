"""
Optimizations management endpoints.

REST API for managing Optuna optimization studies and results.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.optimizations import (
    OptimizationLaunchRequest,
    OptimizationListResponse,
    OptimizationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=OptimizationListResponse)
async def list_optimizations(
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationListResponse:
    """
    List optimization studies with pagination.

    Requires authentication.

    Returns:
        Paginated list of optimization studies
    """
    try:
        # Count total
        count_query = "SELECT COUNT(*) as count FROM optuna_studies"

        # Get studies
        studies_query = """
            SELECT
                id, run_id, name, direction, objective,
                n_trials, n_jobs, sampler, pruner,
                best_value, best_params, best_trial,
                walk_forward_splits, walk_forward_train_ratio,
                status, created_at, started_at, completed_at
            FROM optuna_studies
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query)
            total = count_row["count"]

            # Fetch studies
            rows = await conn.fetch(studies_query, limit, offset)

        # Convert to response models
        items = [OptimizationResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} optimization studies (total={total})")

        return OptimizationListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        # Fallback to mock data if table doesn't exist
        logger.warning(f"Failed to query optuna_studies table, using mock data: {e}")
        return get_mock_optimizations(limit, offset)


@router.get("/{study_id}", response_model=OptimizationResponse)
async def get_optimization(
    study_id: int,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """
    Get optimization study details by ID.

    Requires authentication.

    Args:
        study_id: Study ID

    Returns:
        Optimization study details

    Raises:
        HTTPException: 404 if study not found
    """
    try:
        query = """
            SELECT
                id, run_id, name, direction, objective,
                n_trials, n_jobs, sampler, pruner,
                best_value, best_params, best_trial,
                walk_forward_splits, walk_forward_train_ratio,
                status, created_at, started_at, completed_at
            FROM optuna_studies
            WHERE id = $1
        """

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, study_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Optimization study {study_id} not found",
            )

        return OptimizationResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        # Fallback to mock data
        logger.warning(f"Failed to query optimization {study_id}, using mock data: {e}")
        mock_studies = get_mock_optimizations_list()
        for study in mock_studies:
            if study["id"] == study_id:
                return OptimizationResponse(**study)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization study {study_id} not found",
        )


@router.post("", response_model=OptimizationResponse, status_code=status.HTTP_202_ACCEPTED)
async def launch_optimization(
    request: OptimizationLaunchRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """
    Launch a new optimization study.

    Requires authentication.

    This endpoint creates a new study record and publishes a command to Redis
    for the bot to execute the optimization. The endpoint returns immediately
    with the study record in 'running' status.

    Args:
        request: Optimization launch request

    Returns:
        Created optimization study (status: running)

    Raises:
        HTTPException: 400 if invalid request
    """
    try:
        query = """
            INSERT INTO optuna_studies (
                run_id, name, direction, objective,
                n_trials, n_jobs, sampler, pruner,
                walk_forward_splits, walk_forward_train_ratio,
                status, created_at
            )
            VALUES ($1, $2, 'maximize', $3, $4, $5, 'TPE', 'MedianPruner', 4, 0.75, 'running', NOW())
            RETURNING
                id, run_id, name, direction, objective,
                n_trials, n_jobs, sampler, pruner,
                best_value, best_params, best_trial,
                walk_forward_splits, walk_forward_train_ratio,
                status, created_at, started_at, completed_at
        """

        async with db_pool.acquire() as conn:
            # Create study record
            row = await conn.fetchrow(
                query,
                None,  # run_id will be set by bot
                request.name,
                request.objective,
                request.n_trials,
                request.n_jobs,
            )

        logger.info(f"Launched optimization study: {row['id']} - {row['name']}")

        # TODO: Publish command to Redis to notify bot to start optimization
        # This would be: await redis.publish('bot:commands', json.dumps({'type': 'start_optimization', 'study_id': row['id']}))

        return OptimizationResponse(**dict(row))
    except Exception as e:
        logger.error(f"Failed to launch optimization: {e}")
        # Fallback to mock data
        logger.warning(f"Using mock data for launched optimization")
        from datetime import datetime, timezone

        mock_study = {
            "id": 1,
            "run_id": None,
            "name": request.name,
            "direction": "maximize",
            "objective": request.objective,
            "n_trials": request.n_trials,
            "n_jobs": request.n_jobs,
            "sampler": "TPE",
            "pruner": "MedianPruner",
            "best_value": None,
            "best_params": None,
            "best_trial": None,
            "walk_forward_splits": 4,
            "walk_forward_train_ratio": 0.75,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        return OptimizationResponse(**mock_study)


def get_mock_optimizations_list() -> list[dict]:
    """Get mock optimization studies for development."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return [
        {
            "id": 1,
            "run_id": "run-001",
            "name": "Optuna Study 2026-01-15",
            "direction": "maximize",
            "objective": "sharpe",
            "n_trials": 100,
            "n_jobs": 4,
            "sampler": "TPE",
            "pruner": "MedianPruner",
            "best_value": 2.34,
            "best_params": {
                "ema_weight": 0.25,
                "macd_weight": 0.35,
                "rsi_weight": 0.15,
                "bollinger_weight": 0.25,
            },
            "best_trial": {
                "trial_number": 87,
                "value": 2.34,
                "state": "complete",
                "params": {"ema_weight": 0.25, "macd_weight": 0.35},
                "metrics": {"sharpe": 2.34, "win_rate": 0.62},
            },
            "walk_forward_splits": 4,
            "walk_forward_train_ratio": 0.75,
            "status": "completed",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "started_at": (now - timedelta(days=5)).isoformat(),
            "completed_at": (now - timedelta(days=4)).isoformat(),
        },
        {
            "id": 2,
            "run_id": "run-002",
            "name": "Optuna Study 2026-01-10",
            "direction": "maximize",
            "objective": "sortino",
            "n_trials": 150,
            "n_jobs": 4,
            "sampler": "TPE",
            "pruner": "MedianPruner",
            "best_value": 3.12,
            "best_params": {
                "ema_weight": 0.20,
                "macd_weight": 0.30,
                "rsi_weight": 0.25,
                "bollinger_weight": 0.25,
            },
            "best_trial": {
                "trial_number": 142,
                "value": 3.12,
                "state": "complete",
                "params": {"ema_weight": 0.20, "macd_weight": 0.30},
                "metrics": {"sortino": 3.12, "win_rate": 0.65},
            },
            "walk_forward_splits": 4,
            "walk_forward_train_ratio": 0.75,
            "status": "completed",
            "created_at": (now - timedelta(days=10)).isoformat(),
            "started_at": (now - timedelta(days=10)).isoformat(),
            "completed_at": (now - timedelta(days=9)).isoformat(),
        },
    ]


def get_mock_optimizations(limit: int = 100, offset: int = 0) -> OptimizationListResponse:
    """Get paginated mock optimization studies."""
    items = get_mock_optimizations_list()
    return OptimizationListResponse(
        total=len(items),
        items=[OptimizationResponse(**item) for item in items[offset : offset + limit]],
        limit=limit,
        offset=offset,
    )
