"""
Orders management endpoints.

REST API for querying exchange orders and their status.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.enums import OrderStatus, TradeSide
from ..models.orders import OrderFilter, OrderListResponse, OrderResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=OrderListResponse)
async def list_orders(
    run_id: Annotated[int | None, Query(description="Filter by run ID")] = None,
    symbol: Annotated[str | None, Query(max_length=20, description="Filter by symbol (max 20 chars)")] = None,
    side: Annotated[TradeSide | None, Query(description="Filter by side (buy/sell/long/short)")] = None,
    status_filter: Annotated[OrderStatus | None, Query(alias="status", description="Filter by status (pending/open/filled/cancelled/rejected)")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OrderListResponse:
    """
    List exchange orders with filtering and pagination.

    Requires authentication.

    Returns:
        Paginated list of orders
    """
    try:
        # Build WHERE clause
        conditions = []
        param_values = []

        if run_id is not None:
            conditions.append(f"run_id = ${len(param_values) + 1}")
            param_values.append(run_id)

        if symbol:
            conditions.append(f"symbol = ${len(param_values) + 1}")
            param_values.append(symbol)

        if side:
            conditions.append(f"side = ${len(param_values) + 1}")
            param_values.append(side)

        if status_filter:
            conditions.append(f"status = ${len(param_values) + 1}")
            param_values.append(status_filter)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Count total
        count_query = f"SELECT COUNT(*) as count FROM orders {where_clause}"

        # Get orders
        orders_query = f"""
            SELECT
                id, run_id, exchange_order_id,
                symbol, side, order_type,
                quantity, price,
                status, filled_quantity, filled_price,
                commission, placed_at, filled_at,
                cancelled_at, metadata
            FROM orders
            {where_clause}
            ORDER BY placed_at DESC
            LIMIT ${len(param_values) + 1} OFFSET ${len(param_values) + 2}
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query, *param_values)
            total = count_row["count"] if count_row else 0

            # Fetch orders
            param_values.append(limit)
            param_values.append(offset)
            rows = await conn.fetch(orders_query, *param_values)

        # Convert to response models
        items = [OrderResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} orders (total={total})")

        return OrderListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Failed to query orders table: {e}")
        # Return empty list instead of mock data when table doesn't exist
        return OrderListResponse(total=0, items=[], limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> OrderResponse:
    """
    Get order details by ID.

    Requires authentication.

    Args:
        order_id: Order ID

    Returns:
        Order details

    Raises:
        HTTPException: 404 if order not found
    """
    try:
        query = """
            SELECT
                id, run_id, exchange_order_id,
                symbol, side, order_type,
                quantity, price,
                status, filled_quantity, filled_price,
                commission, placed_at, filled_at,
                cancelled_at, metadata
            FROM orders
            WHERE id = $1
        """

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, order_id)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )

        return OrderResponse(**dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )
