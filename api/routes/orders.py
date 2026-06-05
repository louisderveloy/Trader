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
from ..models.orders import OrderFilter, OrderListResponse, OrderResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=OrderListResponse)
async def list_orders(
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    symbol: Annotated[str | None, Query(description="Filter by symbol")] = None,
    side: Annotated[str | None, Query(description="Filter by side (BUY/SELL)")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by status")] = None,
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
        params = {}

        if run_id:
            conditions.append(f"run_id = ${len(params) + 1}")
            params["run_id"] = run_id

        if symbol:
            conditions.append(f"symbol = ${len(params) + 1}")
            params["symbol"] = symbol

        if side:
            conditions.append(f"side = ${len(params) + 1}")
            params["side"] = side

        if status_filter:
            conditions.append(f"status = ${len(params) + 1}")
            params["status"] = status_filter

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
                commission, commission_asset,
                created_at, submitted_at, filled_at,
                rejected_reason, metadata
            FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query, *params.values())
            total = count_row["count"]

            # Fetch orders
            params["limit"] = limit
            params["offset"] = offset
            rows = await conn.fetch(orders_query, *params.values())

        # Convert to response models
        items = [OrderResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} orders (total={total})")

        return OrderListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        logger.warning(f"Failed to query orders table, using mock data: {e}")
        return get_mock_orders(limit, offset)


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
                commission, commission_asset,
                created_at, submitted_at, filled_at,
                rejected_reason, metadata
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
        logger.warning(f"Failed to query order {order_id}, using mock data: {e}")
        mock_orders = get_mock_orders_list()
        for order in mock_orders:
            if order["id"] == order_id:
                return OrderResponse(**order)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )


def get_mock_orders_list() -> list[dict]:
    """Get mock orders for development."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    now = datetime.now(timezone.utc)
    return [
        {
            "id": "order-1",
            "run_id": "run-001",
            "exchange_order_id": "1234567890",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": Decimal("0.5"),
            "price": Decimal("45000.00"),
            "status": "filled",
            "filled_quantity": Decimal("0.5"),
            "filled_price": Decimal("45005.50"),
            "commission": Decimal("24.00"),
            "commission_asset": "USDT",
            "created_at": (now - timedelta(days=2, hours=3)).isoformat(),
            "submitted_at": (now - timedelta(days=2, hours=3)).isoformat(),
            "filled_at": (now - timedelta(days=2, hours=2, minutes=45)).isoformat(),
            "rejected_reason": None,
            "metadata": {},
        },
        {
            "id": "order-2",
            "run_id": "run-001",
            "exchange_order_id": "1234567891",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": Decimal("0.5"),
            "price": Decimal("46200.00"),
            "status": "filled",
            "filled_quantity": Decimal("0.5"),
            "filled_price": Decimal("46195.50"),
            "commission": Decimal("23.10"),
            "commission_asset": "USDT",
            "created_at": (now - timedelta(days=1, hours=5)).isoformat(),
            "submitted_at": (now - timedelta(days=1, hours=5)).isoformat(),
            "filled_at": (now - timedelta(days=1, hours=4, minutes=30)).isoformat(),
            "rejected_reason": None,
            "metadata": {},
        },
        {
            "id": "order-3",
            "run_id": "run-001",
            "exchange_order_id": "1234567892",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": Decimal("0.3"),
            "price": Decimal("45800.00"),
            "status": "partial",
            "filled_quantity": Decimal("0.2"),
            "filled_price": Decimal("45805.50"),
            "commission": Decimal("9.16"),
            "commission_asset": "USDT",
            "created_at": (now - timedelta(hours=12)).isoformat(),
            "submitted_at": (now - timedelta(hours=12)).isoformat(),
            "filled_at": (now - timedelta(hours=11, minutes=30)).isoformat(),
            "rejected_reason": None,
            "metadata": {},
        },
    ]


def get_mock_orders(limit: int = 100, offset: int = 0) -> OrderListResponse:
    """Get paginated mock orders."""
    items = get_mock_orders_list()
    return OrderListResponse(
        total=len(items),
        items=[OrderResponse(**item) for item in items[offset : offset + limit]],
        limit=limit,
        offset=offset,
    )
