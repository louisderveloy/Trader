"""
Signals management endpoints.

REST API for querying bot decision signals and their metadata.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.signals import SignalFilter, SignalListResponse, SignalResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=SignalListResponse)
async def list_signals(
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    symbol: Annotated[str | None, Query(description="Filter by symbol")] = None,
    decision: Annotated[str | None, Query(description="Filter by decision (buy/sell/hold)")] = None,
    min_score: Annotated[float | None, Query(description="Minimum score [-1, 1]")] = None,
    max_score: Annotated[float | None, Query(description="Maximum score [-1, 1]")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
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
    params = {}

    if run_id:
        conditions.append(f"run_id = ${len(params) + 1}")
        params["run_id"] = run_id

    if symbol:
        conditions.append(f"symbol = ${len(params) + 1}")
        params["symbol"] = symbol

    if decision:
        conditions.append(f"decision = ${len(params) + 1}")
        params["decision"] = decision

    if min_score is not None:
        conditions.append(f"score >= ${len(params) + 1}")
        params["min_score"] = min_score

    if max_score is not None:
        conditions.append(f"score <= ${len(params) + 1}")
        params["max_score"] = max_score

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count total
    count_query = f"SELECT COUNT(*) as count FROM signals {where_clause}"

    # Get signals
    signals_query = f"""
        SELECT
            id, run_id, timestamp, symbol, timeframe,
            decision, score, confidence,
            weights_snapshot, indicators_snapshot, reason,
            position_size, estimated_sl_price, estimated_tp_price,
            created_at
        FROM signals
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """

    async with db_pool.acquire() as conn:
        # Count
        count_row = await conn.fetchrow(count_query, *params.values())
        total = count_row["count"]

        # Fetch signals
        params["limit"] = limit
        params["offset"] = offset
        rows = await conn.fetch(signals_query, *params.values())

    # Convert to response models
    items = [SignalResponse(**dict(row)) for row in rows]

    logger.info(f"Listed {len(items)} signals (total={total})")

    return SignalListResponse(total=total, items=items, limit=limit, offset=offset)


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: str,
    user: User = Depends(get_current_user),
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
            id, run_id, timestamp, symbol, timeframe,
            decision, score, confidence,
            weights_snapshot, indicators_snapshot, reason,
            position_size, estimated_sl_price, estimated_tp_price,
            created_at
        FROM signals
        WHERE id = $1
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, signal_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal {signal_id} not found",
        )

    return SignalResponse(**dict(row))
