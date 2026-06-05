"""
Pydantic models for trades endpoints.

Request/response models for trade data.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class TradeResponse(BaseModel):
    """Trade response model."""

    id: str = Field(..., description="Trade ID (UUID)")
    run_id: int = Field(..., description="Run ID")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Trade side: long, short")
    environment: str = Field(..., description="Environment: testnet, live, paper, backtest")

    entry_price: Decimal = Field(..., description="Entry price")
    exit_price: Decimal = Field(..., description="Exit price")
    quantity: Decimal = Field(..., description="Position size")

    pnl: Decimal = Field(..., description="Profit/Loss in USDT")
    pnl_percent: Decimal = Field(..., description="P&L as percentage")

    commission_total: Decimal = Field(..., description="Total commission paid")

    opened_at: datetime = Field(..., description="Entry timestamp")
    closed_at: datetime = Field(..., description="Exit timestamp")
    duration_seconds: int = Field(..., description="Trade duration in seconds")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class TradeFilter(BaseModel):
    """Trade filter query parameters."""

    run_id: Optional[int] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    side: Optional[str] = Field(None, description="Filter by side (long/short)")
    environment: Optional[str] = Field(None, description="Filter by environment (testnet/live/paper/backtest)")

    min_pnl: Optional[Decimal] = Field(None, description="Minimum P&L")
    max_pnl: Optional[Decimal] = Field(None, description="Maximum P&L")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class TradeListResponse(BaseModel):
    """Trade list response with pagination."""

    total: int = Field(..., description="Total number of trades matching filter")
    items: list[TradeResponse] = Field(..., description="List of trades")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
