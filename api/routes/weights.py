"""
Weights management endpoints.

REST API for managing strategy weight sets (manual and from optimization).
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import User, get_current_user
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..models.weights import (
    WeightsActivateRequest,
    WeightsCreateRequest,
    WeightsListResponse,
    WeightsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=WeightsListResponse)
async def list_weights(
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsListResponse:
    """
    List all weights sets with pagination.

    Requires authentication.

    Returns:
        Paginated list of weights sets
    """
    # Count total
    count_query = "SELECT COUNT(*) as count FROM weights_sets"

    # Get weights
    weights_query = """
        SELECT
            id, name, description,
            weights, source, optuna_study_id,
            metrics, is_active, activated_at,
            created_at, updated_at
        FROM weights_sets
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
    """

    async with db_pool.acquire() as conn:
        # Count
        count_row = await conn.fetchrow(count_query)
        total = count_row["count"]

        # Fetch weights
        rows = await conn.fetch(weights_query, limit, offset)

    # Convert to response models
    items = [WeightsResponse(**dict(row)) for row in rows]

    logger.info(f"Listed {len(items)} weights sets (total={total})")

    return WeightsListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/{weights_id}", response_model=WeightsResponse)
async def get_weights(
    weights_id: int,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """
    Get weights set details by ID.

    Requires authentication.

    Args:
        weights_id: Weights set ID

    Returns:
        Weights set details

    Raises:
        HTTPException: 404 if weights set not found
    """
    query = """
        SELECT
            id, name, description,
            weights, source, optuna_study_id,
            metrics, is_active, activated_at,
            created_at, updated_at
        FROM weights_sets
        WHERE id = $1
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, weights_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weights set {weights_id} not found",
        )

    return WeightsResponse(**dict(row))


@router.post("", response_model=WeightsResponse, status_code=status.HTTP_201_CREATED)
async def create_weights(
    http_request: Request,
    request: WeightsCreateRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """
    Create a new weights set.

    Requires authentication and CSRF token.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        request: Weights creation request

    Returns:
        Created weights set

    Raises:
        HTTPException: 400 if invalid request
        HTTPException: 403 if CSRF validation fails
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    query = """
        INSERT INTO weights_sets (name, description, weights, source, is_active)
        VALUES ($1, $2, $3, $4, false)
        RETURNING
            id, name, description,
            weights, source, optuna_study_id,
            metrics, is_active, activated_at,
            created_at, updated_at
    """

    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                request.name,
                request.description,
                request.weights,
                "manual",
            )

        logger.info(f"Created weights set: {row['id']} - {row['name']}")

        return WeightsResponse(**dict(row))
    except Exception as e:
        logger.error(f"Failed to create weights set: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create weights set: {str(e)}",
        )


@router.patch("/{weights_id}/activate", response_model=WeightsResponse)
async def activate_weights(
    http_request: Request,
    weights_id: int,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """
    Activate a weights set (deactivate current, activate new).

    Requires authentication and CSRF token.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        weights_id: Weights set ID to activate

    Returns:
        Activated weights set

    Raises:
        HTTPException: 404 if weights set not found
        HTTPException: 403 if CSRF validation fails
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    async with db_pool.acquire() as conn:
        # Verify weights set exists
        verify_query = "SELECT id FROM weights_sets WHERE id = $1"
        if not await conn.fetchrow(verify_query, weights_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Weights set {weights_id} not found",
            )

        # Deactivate all other weights sets
        deactivate_query = "UPDATE weights_sets SET is_active = false WHERE id != $1"
        await conn.execute(deactivate_query, weights_id)

        # Activate this weights set
        activate_query = """
            UPDATE weights_sets
            SET is_active = true, activated_at = NOW()
            WHERE id = $1
            RETURNING
                id, name, description,
                weights, source, optuna_study_id,
                metrics, is_active, activated_at,
                created_at, updated_at
        """
        row = await conn.fetchrow(activate_query, weights_id)

    logger.info(f"Activated weights set: {weights_id}")

    return WeightsResponse(**dict(row))
