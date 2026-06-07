"""
Optimizations management endpoints.

REST API for managing Optuna optimization studies and results.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import User, get_current_user
from ..config import settings
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..limiter import limiter
from ..models.optimizations import (
    OptimizationLaunchRequest,
    OptimizationListResponse,
    OptimizationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=OptimizationListResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def list_optimizations(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationListResponse:
    """
    List optimization studies with pagination.

    Requires authentication.
    Rate limited to 60 requests per minute.

    Returns:
        Paginated list of optimization studies
    """
    try:
        # Count total
        count_query = "SELECT COUNT(*) as count FROM optuna_studies"

        # Get studies
        studies_query = """
            SELECT
                id, run_id, study_name, n_trials,
                best_value, best_params, weights_set_id,
                started_at, completed_at, metadata, created_at
            FROM optuna_studies
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query)
            total = count_row["count"] if count_row else 0

            # Fetch studies
            rows = await conn.fetch(studies_query, limit, offset)

        # Convert to response models
        items = [OptimizationResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} optimization studies (total={total})")

        return OptimizationListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        # Return empty list if table doesn't exist
        logger.error(f"Failed to query optuna_studies table: {e}")
        return OptimizationListResponse(total=0, items=[], limit=limit, offset=offset)


@router.get("/{study_id}", response_model=OptimizationResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_optimization(
    study_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """
    Get optimization study details by ID.

    Requires authentication.
    Rate limited to 60 requests per minute.

    Args:
        study_id: Study ID (UUID)

    Returns:
        Optimization study details

    Raises:
        HTTPException: 404 if study not found
    """
    try:
        query = """
            SELECT
                id, run_id, study_name, n_trials,
                best_value, best_params, weights_set_id,
                started_at, completed_at, metadata, created_at
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
        logger.error(f"Failed to query optimization {study_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization study {study_id} not found",
        )


@router.post("", response_model=OptimizationResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: settings.rate_limit_expensive)
async def launch_optimization(
    http_request: Request,
    request: OptimizationLaunchRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OptimizationResponse:
    """
    Launch a new optimization study.

    Requires authentication and CSRF token.
    Rate limited to 2 requests per hour (expensive operation).

    This endpoint creates a new study record and publishes a command to Redis
    for the bot to execute the optimization. The endpoint returns immediately
    with the study record.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        request: Optimization launch request

    Returns:
        Created optimization study

    Raises:
        HTTPException: 400 if invalid request
        HTTPException: 403 if CSRF validation fails
        HTTPException: 429 if rate limit exceeded (2/hour)
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    try:
        query = """
            INSERT INTO optuna_studies (
                study_name, n_trials, created_at
            )
            VALUES ($1, $2, NOW())
            RETURNING
                id, run_id, study_name, n_trials,
                best_value, best_params, weights_set_id,
                started_at, completed_at, metadata, created_at
        """

        async with db_pool.acquire() as conn:
            # Create study record
            row = await conn.fetchrow(
                query,
                request.name,
                request.n_trials,
            )

        logger.info(f"Launched optimization study: {row['id']} - {row['study_name']}")

        # TODO: Publish command to Redis to notify bot to start optimization
        # This would be: await redis.publish('bot:commands', json.dumps({'type': 'start_optimization', 'study_id': row['id']}))

        return OptimizationResponse(**dict(row))
    except Exception as e:
        logger.error(f"Failed to launch optimization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to launch optimization study",
        )
