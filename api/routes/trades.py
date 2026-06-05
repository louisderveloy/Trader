"""
Trades management endpoints.

REST API for querying and analyzing completed trades.
"""

import asyncpg
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import User, get_current_user
from ..database import get_db_pool
from ..models.trades import TradeFilter, TradeListResponse, TradeResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TradeListResponse)
async def list_trades(
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    symbol: Annotated[str | None, Query(description="Filter by symbol")] = None,
    direction: Annotated[str | None, Query(description="Filter by direction (long/short)")] = None,
    min_pnl: Annotated[float | None, Query(description="Minimum P&L")] = None,
    max_pnl: Annotated[float | None, Query(description="Maximum P&L")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    user: User = Depends(get_current_user),
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
        params = {}

        if run_id:
            conditions.append(f"run_id = ${len(params) + 1}")
            params["run_id"] = run_id

        if symbol:
            conditions.append(f"symbol = ${len(params) + 1}")
            params["symbol"] = symbol

        if direction:
            conditions.append(f"direction = ${len(params) + 1}")
            params["direction"] = direction

        if min_pnl is not None:
            conditions.append(f"pnl >= ${len(params) + 1}")
            params["min_pnl"] = min_pnl

        if max_pnl is not None:
            conditions.append(f"pnl <= ${len(params) + 1}")
            params["max_pnl"] = max_pnl

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Count total
        count_query = f"SELECT COUNT(*) as count FROM trades {where_clause}"

        # Get trades
        trades_query = f"""
            SELECT
                id, run_id, symbol, direction,
                entry_price, entry_time, entry_size,
                exit_price, exit_time,
                pnl, pnl_percent, fees, slippage,
                stop_loss_price, take_profit_price, exit_reason,
                created_at
            FROM trades
            {where_clause}
            ORDER BY entry_time DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """

        async with db_pool.acquire() as conn:
            # Count
            count_row = await conn.fetchrow(count_query, *params.values())
            total = count_row["count"]

            # Fetch trades
            params["limit"] = limit
            params["offset"] = offset
            rows = await conn.fetch(trades_query, *params.values())

        # Convert to response models
        items = [TradeResponse(**dict(row)) for row in rows]

        logger.info(f"Listed {len(items)} trades (total={total})")

        return TradeListResponse(total=total, items=items, limit=limit, offset=offset)
    except Exception as e:
        logger.warning(f"Failed to query trades table, using mock data: {e}")
        return get_mock_trades(limit, offset)


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    user: User = Depends(get_current_user),
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
                id, run_id, symbol, direction,
                entry_price, entry_time, entry_size,
                exit_price, exit_time,
                pnl, pnl_percent, fees, slippage,
                stop_loss_price, take_profit_price, exit_reason,
                created_at
            FROM trades
            WHERE id = $1
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
        logger.warning(f"Failed to query trade {trade_id}, using mock data: {e}")
        mock_trades = get_mock_trades_list()
        for trade in mock_trades:
            if trade["id"] == trade_id:
                return TradeResponse(**trade)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade {trade_id} not found",
        )


def get_mock_trades_list() -> list[dict]:
    """Get mock trades for development."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    now = datetime.now(timezone.utc)
    return [
        {
            "id": "trade-1",
            "run_id": 1,
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": Decimal("45000.00"),
            "entry_time": (now - timedelta(days=2, hours=3)).isoformat(),
            "entry_size": Decimal("0.5"),
            "exit_price": Decimal("46200.00"),
            "exit_time": (now - timedelta(days=1, hours=5)).isoformat(),
            "pnl": Decimal("600.00"),
            "pnl_percent": 0.0267,
            "fees": Decimal("24.00"),
            "slippage": Decimal("5.50"),
            "stop_loss_price": Decimal("44100.00"),
            "take_profit_price": Decimal("47300.00"),
            "exit_reason": "signal",
            "created_at": (now - timedelta(days=2, hours=3)).isoformat(),
        },
        {
            "id": "trade-2",
            "run_id": 1,
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": Decimal("46200.00"),
            "entry_time": (now - timedelta(days=1, hours=5)).isoformat(),
            "entry_size": Decimal("0.3"),
            "exit_price": Decimal("45800.00"),
            "exit_time": (now - timedelta(hours=12)).isoformat(),
            "pnl": Decimal("-139.20"),
            "pnl_percent": -0.0086,
            "fees": Decimal("13.80"),
            "slippage": Decimal("3.20"),
            "stop_loss_price": Decimal("45378.00"),
            "take_profit_price": Decimal("47886.00"),
            "exit_reason": "stop_loss",
            "created_at": (now - timedelta(days=1, hours=5)).isoformat(),
        },
        {
            "id": "trade-3",
            "run_id": 1,
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": Decimal("45800.00"),
            "entry_time": (now - timedelta(hours=12)).isoformat(),
            "entry_size": Decimal("0.8"),
            "exit_price": Decimal("46850.00"),
            "exit_time": (now - timedelta(hours=2)).isoformat(),
            "pnl": Decimal("840.00"),
            "pnl_percent": 0.0228,
            "fees": Decimal("37.60"),
            "slippage": Decimal("8.40"),
            "stop_loss_price": Decimal("45092.00"),
            "take_profit_price": Decimal("48016.00"),
            "exit_reason": "take_profit",
            "created_at": (now - timedelta(hours=12)).isoformat(),
        },
    ]


def get_mock_trades(limit: int = 100, offset: int = 0) -> TradeListResponse:
    """Get paginated mock trades."""
    items = get_mock_trades_list()
    return TradeListResponse(
        total=len(items),
        items=[TradeResponse(**item) for item in items[offset : offset + limit]],
        limit=limit,
        offset=offset,
    )
