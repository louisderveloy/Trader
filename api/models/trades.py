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
    run_id: str = Field(..., description="Run ID (UUID)")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Trade side: long, short")
    environment: str = Field(..., description="Environment: testnet, live, paper, backtest")
    status: str = Field(..., description="Trade status: open, closed")

    entry_price: Decimal = Field(..., description="Entry price")
    exit_price: Optional[Decimal] = Field(None, description="Exit price (null if still open)")
    quantity: Decimal = Field(..., description="Position size")

    pnl: Optional[Decimal] = Field(None, description="Profit/Loss in USDT (null if still open)")
    pnl_percent: Optional[Decimal] = Field(None, description="P&L as percentage (null if still open)")

    commission_total: Decimal = Field(..., description="Total commission paid (entry + exit)")

    opened_at: datetime = Field(..., description="Entry timestamp")
    closed_at: Optional[datetime] = Field(None, description="Exit timestamp (null if still open)")
    duration_seconds: Optional[int] = Field(None, description="Trade duration in seconds (null if still open)")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class TradeFilter(BaseModel):
    """Trade filter query parameters."""

    run_id: Optional[str] = Field(None, description="Filter by run ID (UUID)")
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
