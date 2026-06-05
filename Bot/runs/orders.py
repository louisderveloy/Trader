"""
Order logging utilities for runs.

This module provides functions for logging order lifecycle events
to the orders table in the database.
"""

import asyncpg
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def create_order(
    db_pool: asyncpg.Pool,
    run_id: int,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    signal_id: Optional[UUID] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> UUID:
    """
    Create a pending order record in the database.

    Args:
        db_pool: Database connection pool
        run_id: Run ID this order belongs to
        symbol: Trading symbol (e.g., BTCUSDT)
        side: Order side ('buy' or 'sell')
        order_type: Order type ('limit' or 'market')
        quantity: Order quantity
        price: Order price (required for limit orders)
        signal_id: Optional signal ID that triggered this order
        metadata: Optional additional metadata

    Returns:
        UUID of the created order

    Raises:
        asyncpg.PostgresError: Database error
        ValueError: Invalid parameters
    """
    if side not in ('buy', 'sell'):
        raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'")

    if order_type not in ('limit', 'market'):
        raise ValueError(f"Invalid order_type: {order_type}. Must be 'limit' or 'market'")

    if order_type == 'limit' and price is None:
        raise ValueError("Price is required for limit orders")

    now = datetime.now(timezone.utc)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO orders (
                run_id, signal_id, symbol, side, order_type,
                status, quantity, price, placed_at, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            run_id,
            signal_id,
            symbol,
            side,
            order_type,
            'pending',
            quantity,
            price,
            now,
            metadata,
        )

    order_id = row["id"]
    logger.info(
        f"Created order: id={order_id}, symbol={symbol}, side={side}, "
        f"type={order_type}, quantity={quantity}, price={price}",
        extra={
            "order_id": str(order_id),
            "run_id": run_id,
            "symbol": symbol,
            "side": side,
        },
    )

    return order_id


async def update_order_submitted(
    db_pool: asyncpg.Pool,
    order_id: UUID,
    exchange_order_id: str,
) -> None:
    """
    Update order with exchange order ID after submission.

    Args:
        db_pool: Database connection pool
        order_id: Internal order ID
        exchange_order_id: Exchange-assigned order ID

    Raises:
        asyncpg.PostgresError: Database error
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET exchange_order_id = $2
            WHERE id = $1
            """,
            order_id,
            exchange_order_id,
        )

    logger.debug(
        f"Updated order {order_id} with exchange ID: {exchange_order_id}",
        extra={"order_id": str(order_id), "exchange_order_id": exchange_order_id},
    )


async def update_order_filled(
    db_pool: asyncpg.Pool,
    order_id: UUID,
    filled_quantity: Decimal,
    filled_price: Decimal,
    commission: Decimal,
    exchange_order_id: Optional[str] = None,
) -> None:
    """
    Update order when filled (fully or partially).

    Args:
        db_pool: Database connection pool
        order_id: Internal order ID
        filled_quantity: Quantity that was filled
        filled_price: Average fill price
        commission: Commission paid
        exchange_order_id: Optional exchange order ID if not set before

    Raises:
        asyncpg.PostgresError: Database error
    """
    now = datetime.now(timezone.utc)

    async with db_pool.acquire() as conn:
        if exchange_order_id:
            await conn.execute(
                """
                UPDATE orders
                SET
                    status = 'filled',
                    filled_quantity = $2,
                    filled_price = $3,
                    commission = $4,
                    filled_at = $5,
                    exchange_order_id = COALESCE($6, exchange_order_id)
                WHERE id = $1
                """,
                order_id,
                filled_quantity,
                filled_price,
                commission,
                now,
                exchange_order_id,
            )
        else:
            await conn.execute(
                """
                UPDATE orders
                SET
                    status = 'filled',
                    filled_quantity = $2,
                    filled_price = $3,
                    commission = $4,
                    filled_at = $5
                WHERE id = $1
                """,
                order_id,
                filled_quantity,
                filled_price,
                commission,
                now,
            )

    logger.info(
        f"Order {order_id} filled: qty={filled_quantity}, price={filled_price}, commission={commission}",
        extra={
            "order_id": str(order_id),
            "filled_quantity": str(filled_quantity),
            "filled_price": str(filled_price),
            "commission": str(commission),
        },
    )


async def update_order_cancelled(
    db_pool: asyncpg.Pool,
    order_id: UUID,
    reason: Optional[str] = None,
) -> None:
    """
    Update order when cancelled.

    Args:
        db_pool: Database connection pool
        order_id: Internal order ID
        reason: Optional cancellation reason

    Raises:
        asyncpg.PostgresError: Database error
    """
    now = datetime.now(timezone.utc)

    # Store reason in metadata
    metadata_update = {"cancellation_reason": reason} if reason else None

    async with db_pool.acquire() as conn:
        if metadata_update:
            await conn.execute(
                """
                UPDATE orders
                SET
                    status = 'cancelled',
                    cancelled_at = $2,
                    metadata = COALESCE(metadata, '{}'::jsonb) || $3::jsonb
                WHERE id = $1
                """,
                order_id,
                now,
                metadata_update,
            )
        else:
            await conn.execute(
                """
                UPDATE orders
                SET status = 'cancelled', cancelled_at = $2
                WHERE id = $1
                """,
                order_id,
                now,
            )

    logger.info(
        f"Order {order_id} cancelled: reason={reason}",
        extra={"order_id": str(order_id), "reason": reason},
    )


async def update_order_rejected(
    db_pool: asyncpg.Pool,
    order_id: UUID,
    reason: str,
) -> None:
    """
    Update order when rejected by exchange.

    Args:
        db_pool: Database connection pool
        order_id: Internal order ID
        reason: Rejection reason

    Raises:
        asyncpg.PostgresError: Database error
    """
    now = datetime.now(timezone.utc)
    metadata_update = {"rejection_reason": reason}

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET
                status = 'rejected',
                cancelled_at = $2,
                metadata = COALESCE(metadata, '{}'::jsonb) || $3::jsonb
            WHERE id = $1
            """,
            order_id,
            now,
            metadata_update,
        )

    logger.warning(
        f"Order {order_id} rejected: {reason}",
        extra={"order_id": str(order_id), "reason": reason},
    )


async def get_order(
    db_pool: asyncpg.Pool,
    order_id: UUID,
) -> Optional[dict[str, Any]]:
    """
    Get order by ID.

    Args:
        db_pool: Database connection pool
        order_id: Order ID

    Returns:
        Order dict if found, None otherwise

    Raises:
        asyncpg.PostgresError: Database error
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                id, run_id, signal_id, exchange_order_id,
                symbol, side, order_type, status,
                quantity, price, filled_quantity, filled_price,
                commission, placed_at, filled_at, cancelled_at,
                metadata, created_at
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )

    if row:
        return dict(row)
    return None


async def get_orders_by_run(
    db_pool: asyncpg.Pool,
    run_id: int,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Get orders for a run.

    Args:
        db_pool: Database connection pool
        run_id: Run ID
        status: Optional status filter
        limit: Maximum number of orders to return

    Returns:
        List of order dicts

    Raises:
        asyncpg.PostgresError: Database error
    """
    if status:
        query = """
            SELECT
                id, run_id, signal_id, exchange_order_id,
                symbol, side, order_type, status,
                quantity, price, filled_quantity, filled_price,
                commission, placed_at, filled_at, cancelled_at,
                metadata, created_at
            FROM orders
            WHERE run_id = $1 AND status = $2
            ORDER BY placed_at DESC
            LIMIT $3
        """
        params = [run_id, status, limit]
    else:
        query = """
            SELECT
                id, run_id, signal_id, exchange_order_id,
                symbol, side, order_type, status,
                quantity, price, filled_quantity, filled_price,
                commission, placed_at, filled_at, cancelled_at,
                metadata, created_at
            FROM orders
            WHERE run_id = $1
            ORDER BY placed_at DESC
            LIMIT $2
        """
        params = [run_id, limit]

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [dict(row) for row in rows]
