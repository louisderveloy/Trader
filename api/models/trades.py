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
    direction: str = Field(..., description="Trade direction: long, short")

    entry_price: Decimal = Field(..., description="Entry price")
    entry_time: datetime = Field(..., description="Entry timestamp")
    entry_size: Decimal = Field(..., description="Position size")

    exit_price: Optional[Decimal] = Field(None, description="Exit price")
    exit_time: Optional[datetime] = Field(None, description="Exit timestamp")

    pnl: Optional[Decimal] = Field(None, description="Profit/Loss in USDT")
    pnl_percent: Optional[float] = Field(None, description="P&L as percentage")

    fees: Decimal = Field(..., description="Total fees paid")
    slippage: Optional[Decimal] = Field(None, description="Slippage amount")

    stop_loss_price: Optional[Decimal] = Field(None, description="Stop-loss price")
    take_profit_price: Optional[Decimal] = Field(None, description="Take-profit price")

    exit_reason: Optional[str] = Field(None, description="Exit reason: signal, stop_loss, take_profit")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class TradeFilter(BaseModel):
    """Trade filter query parameters."""

    run_id: Optional[int] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    direction: Optional[str] = Field(None, description="Filter by direction")

    min_pnl: Optional[Decimal] = Field(None, description="Minimum P&L")
    max_pnl: Optional[Decimal] = Field(None, description="Maximum P&L")

    date_from: Optional[datetime] = Field(None, description="Entry date from")
    date_to: Optional[datetime] = Field(None, description="Entry date to")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class TradeListResponse(BaseModel):
    """Trade list response with pagination."""

    total: int = Field(..., description="Total number of trades matching filter")
    items: list[TradeResponse] = Field(..., description="List of trades")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
