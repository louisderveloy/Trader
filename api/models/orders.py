"""
Pydantic models for orders endpoints.

Request/response models for exchange order data.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class OrderResponse(BaseModel):
    """Order response model."""

    id: str = Field(..., description="Order ID (UUID)")
    run_id: str = Field(..., description="Run ID")
    exchange_order_id: str = Field(..., description="Exchange order ID (from Binance)")

    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side: BUY, SELL")
    order_type: str = Field(..., description="Order type: LIMIT, MARKET")

    # Quantities
    quantity: Decimal = Field(..., description="Order quantity")
    price: Optional[Decimal] = Field(None, description="Limit price (if LIMIT order)")

    # Execution
    status: str = Field(..., description="Order status: pending, filled, partial, cancelled, rejected")
    filled_quantity: Decimal = Field(..., description="Filled quantity")
    filled_price: Optional[Decimal] = Field(None, description="Average filled price")

    # Fees and costs
    commission: Decimal = Field(..., description="Commission paid")
    commission_asset: str = Field(default="USDT", description="Commission asset")

    # Timestamps
    created_at: datetime = Field(..., description="Order creation timestamp")
    submitted_at: Optional[datetime] = Field(None, description="Order submission to exchange")
    filled_at: Optional[datetime] = Field(None, description="Order fill timestamp")

    # Additional data
    rejected_reason: Optional[str] = Field(None, description="Reason if order was rejected")
    metadata: Optional[dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        """Pydantic config."""

        from_attributes = True


class OrderFilter(BaseModel):
    """Order filter query parameters."""

    run_id: Optional[str] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    side: Optional[str] = Field(None, description="Filter by side (BUY/SELL)")
    status: Optional[str] = Field(None, description="Filter by status")

    date_from: Optional[datetime] = Field(None, description="Order from date")
    date_to: Optional[datetime] = Field(None, description="Order to date")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class OrderListResponse(BaseModel):
    """Order list response with pagination."""

    total: int = Field(..., description="Total number of orders matching filter")
    items: list[OrderResponse] = Field(..., description="List of orders")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
