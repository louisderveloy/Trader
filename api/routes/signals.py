"""
Signals management endpoints.

REST API for querying bot decision signals and their metadata.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import Principal, require_viewer
from ..database import get_db_pool
from ..models.enums import SignalDecision
from ..models.signals import SignalFilter, SignalListResponse, SignalResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=SignalListResponse)
async def list_signals(
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    symbol: Annotated[str | None, Query(max_length=20, description="Filter by symbol (max 20 chars)")] = None,
    decision: Annotated[SignalDecision | None, Query(description="Filter by decision (entry_long/entry_short/exit/skip)")] = None,
    min_score: Annotated[float | None, Query(ge=-1.0, le=1.0, description="Minimum score [-1, 1]")] = None,
    max_score: Annotated[float | None, Query(ge=-1.0, le=1.0, description="Maximum score [-1, 1]")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> SignalListResponse:
    """
    List signals (bot decisions) with filtering and pagination.

    Requires authentication.

    Returns:
        Paginated list of signals
    """
    # Build WHERE clause
    conditions = []
    param_values = []

    if run_id:
        conditions.append(f"run_id = ${len(param_values) + 1}")
        param_values.append(run_id)

    if symbol:
        conditions.append(f"symbol = ${len(param_values) + 1}")
        param_values.append(symbol)

    if decision:
        conditions.append(f"signal_type = ${len(param_values) + 1}")
        param_values.append(decision)

    if min_score is not None:
        conditions.append(f"weighted_score >= ${len(param_values) + 1}")
        param_values.append(min_score)

    if max_score is not None:
        conditions.append(f"weighted_score <= ${len(param_values) + 1}")
        param_values.append(max_score)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count total
    count_query = f"SELECT COUNT(*) as count FROM signals {where_clause}"

    # Get signals
    signals_query = f"""
        SELECT
            id, run_id, time, symbol,
            signal_type, weighted_score,
            weights_snapshot, indicators_snapshot, decision_reason,
            created_at
        FROM signals
        {where_clause}
        ORDER BY time DESC
        LIMIT ${len(param_values) + 1} OFFSET ${len(param_values) + 2}
    """

    async with db_pool.acquire() as conn:
        try:
            # Count
            count_row = await conn.fetchrow(count_query, *param_values)
            total = count_row["count"] if count_row else 0

            # Fetch signals
            param_values.append(limit)
            param_values.append(offset)
            rows = await conn.fetch(signals_query, *param_values)

            # Convert to response models
            items = [SignalResponse(**dict(row)) for row in rows]

            logger.info(f"Listed {len(items)} signals (total={total})")

            return SignalListResponse(total=total, items=items, limit=limit, offset=offset)
        except Exception as e:
            logger.error(f"Failed to query signals table: {e}")
            # Return empty list if table doesn't exist
            return SignalListResponse(total=0, items=[], limit=limit, offset=offset)


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: str,
    user: Principal = Depends(require_viewer),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> SignalResponse:
    """
    Get signal details by ID.

    Requires authentication.

    Args:
        signal_id: Signal ID

    Returns:
        Signal details

    Raises:
        HTTPException: 404 if signal not found
    """
    query = """
        SELECT
            id, run_id, time, symbol,
            signal_type, weighted_score,
            weights_snapshot, indicators_snapshot, decision_reason,
            created_at
        FROM signals
        WHERE id = $1
    """

    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, signal_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {signal_id} not found",
            )

        return SignalResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query signal {signal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal {signal_id} not found",
        )
