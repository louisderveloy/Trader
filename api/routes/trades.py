"""
Trades management endpoints.

REST API for querying and analyzing completed trades.
"""

import logging
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import Principal, require_viewer
from ..database import get_db_pool
from ..models.enums import TradeSide, TradeEnvironment
from ..models.trades import TradeListResponse, TradeResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TradeListResponse)
async def list_trades(
        run_id: Annotated[str | None, Query(description="Filter by run ID (UUID)")] = None,
        symbol: Annotated[str | None, Query(max_length=20, description="Filter by symbol (max 20 chars)")] = None,
        side: Annotated[TradeSide | None, Query(description="Filter by side (buy/sell/long/short)")] = None,
        environment: Annotated[
            TradeEnvironment | None, Query(description="Filter by environment (testnet/live/paper/backtest)")] = None,
        min_pnl: Annotated[float | None, Query(description="Minimum P&L")] = None,
        max_pnl: Annotated[float | None, Query(description="Maximum P&L")] = None,
        limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
        offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
        user: Principal = Depends(require_viewer),
        db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> TradeListResponse:
    """
    List completed trades with filtering and pagination.

    Requires authentication.

    Returns:
        Paginated list of trades
    """
    try:
        # Build WHERE clause
        conditions = []
        param_values = []

        if run_id is not None:
            conditions.append(f"t.run_id = ${len(param_values) + 1}")
            param_values.append(run_id)

        if symbol:
            conditions.append(f"t.symbol = ${len(param_values) + 1}")
            param_values.append(symbol)

        if side:
            conditions.append(f"t.side = ${len(param_values) + 1}")
            param_values.append(side)

        if environment:
            conditions.append(f"r.environment = ${len(param_values) + 1}")
            param_values.append(environment)

        if min_pnl is not None:
            conditions.append(f"t.pnl >= ${len(param_values) + 1}")
            param_values.append(min_pnl)

        if max_pnl is not None:
            conditions.append(f"t.pnl <= ${len(param_values) + 1}")
            param_values.append(max_pnl)

        where_clause = "WHERE " + " AND ".join(
            conditions) if conditions else ""  # TODO: Check for dashboard data. For SQLInjection breach

        # Count total
        count_query = f"""
            SELECT COUNT(*) as count FROM trades t
            JOIN runs r ON t.run_id = r.id
            {where_clause}
        """

        # Get trades
        trades_query = f"""
            SELECT
                t.id::text, t.run_id::text, t.symbol, t.side, r.environment, t.status,
                t.entry_price, t.exit_price, t.quantity,
                t.pnl, t.pnl_percent, t.commission_total,
                t.opened_at, t.closed_at, t.duration_seconds,
                t.created_at
            FROM trades t
            JOIN runs r ON t.run_id = r.id
            {where_clause}
            ORDER BY t.opened_at DESC
            LIMIT ${len(param_values) + 1} OFFSET ${len(param_values) + 2}
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query, *param_values)
            total = count_row["count"] if count_row else 0

            # Fetch trades
            param_values.append(limit)
            param_values.append(offset)
            rows = await conn.fetch(trades_query, *param_values)

        # Convert to response models
        items = [TradeResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} trades (total={total})")

        return TradeListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Failed to query trades table: {e}")
        # Return empty list instead of mock data when table doesn't exist
        return TradeListResponse(total=0, items=[], limit=limit, offset=offset)


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
        trade_id: str,
        user: Principal = Depends(require_viewer),
        db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> TradeResponse:
    """
    Get trade details by ID.

    Requires authentication.

    Args:
        trade_id: Trade ID

    Returns:
        Trade details

    Raises:
        HTTPException: 404 if trade not found
    """
    try:
        query = """
            SELECT
                t.id::text, t.run_id::text, t.symbol, t.side, r.environment, t.status,
                t.entry_price, t.exit_price, t.quantity,
                t.pnl, t.pnl_percent, t.commission_total,
                t.opened_at, t.closed_at, t.duration_seconds,
                t.created_at
            FROM trades t
            JOIN runs r ON t.run_id = r.id
            WHERE t.id = $1
        """

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, trade_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trade {trade_id} not found",
            )

        return TradeResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query trade {trade_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade {trade_id} not found",
        )
