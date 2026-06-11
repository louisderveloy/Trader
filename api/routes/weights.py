"""
Weights management endpoints.

REST API for managing strategy weight sets (manual and from optimization). Maps the
``weights_sets`` table, whose primary key is a UUID and whose columns are
``id, name, source, weights, optimization_score, is_active, created_at``.
"""

import asyncpg
import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import User, get_current_user
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..models.weights import (
    WeightsCreateRequest,
    WeightsListResponse,
    WeightsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Columns of a weights set (matches the real ``weights_sets`` schema).
_WEIGHTS_COLUMNS = "id, name, weights, source, optimization_score, is_active, created_at"
_WEIGHTS_SELECT = f"SELECT {_WEIGHTS_COLUMNS} FROM weights_sets"


def _row_to_weights(row: asyncpg.Record) -> WeightsResponse:
    """Build a response model from a row, coercing UUID/JSONB to plain types."""
    data = dict(row)
    data["id"] = str(data["id"])
    # asyncpg returns JSONB as a str; the model expects a dict.
    if isinstance(data.get("weights"), str):
        data["weights"] = json.loads(data["weights"])
    return WeightsResponse(**data)


@router.get("", response_model=WeightsListResponse)
async def list_weights(
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsListResponse:
    """List all weights sets with pagination. Requires authentication."""
    list_query = _WEIGHTS_SELECT + " ORDER BY created_at DESC LIMIT $1 OFFSET $2"

    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM weights_sets")
        rows = await conn.fetch(list_query, limit, offset)

    items = [_row_to_weights(row) for row in rows]
    logger.info(f"Listed {len(items)} weights sets (total={total})")
    return WeightsListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/{weights_id}", response_model=WeightsResponse)
async def get_weights(
    weights_id: UUID,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """Get weights set details by ID. Requires authentication."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(_WEIGHTS_SELECT + " WHERE id = $1", weights_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weights set {weights_id} not found",
        )
    return _row_to_weights(row)


@router.post("", response_model=WeightsResponse, status_code=status.HTTP_201_CREATED)
async def create_weights(
    http_request: Request,
    request: WeightsCreateRequest,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """
    Create a new (manual) weights set. Requires authentication and a CSRF token.
    """
    await validate_csrf_token(http_request)
    query = (
        "INSERT INTO weights_sets (name, source, weights, is_active) "
        "VALUES ($1, 'manual', $2, false) "
        f"RETURNING {_WEIGHTS_COLUMNS}"
    )

    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                request.name,
                json.dumps({k: float(v) for k, v in request.weights.items()}),
            )
        logger.info(f"Created weights set: {row['id']} - {row['name']}")
        return _row_to_weights(row)
    except Exception as e:
        logger.error(f"Failed to create weights set: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create weights set: {str(e)}",
        )


@router.patch("/{weights_id}/activate", response_model=WeightsResponse)
async def activate_weights(
    http_request: Request,
    weights_id: UUID,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> WeightsResponse:
    """
    Activate a weights set (deactivates the current one, activates this one).

    Requires authentication and a CSRF token. Mirrors the CLI ``optimize activate``
    command; the bot reads the active set from the DB on demand (no NOTIFY needed).
    """
    await validate_csrf_token(http_request)
    async with db_pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM weights_sets WHERE id = $1", weights_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Weights set {weights_id} not found",
            )

        async with conn.transaction():
            await conn.execute("UPDATE weights_sets SET is_active = false WHERE is_active = true")
            await conn.execute(
                "UPDATE weights_sets SET is_active = true WHERE id = $1", weights_id
            )
        row = await conn.fetchrow(_WEIGHTS_SELECT + " WHERE id = $1", weights_id)

    logger.info(f"Activated weights set: {weights_id}")
    return _row_to_weights(row)
