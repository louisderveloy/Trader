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
    run_id: int = Field(..., description="Run ID")
    exchange_order_id: Optional[str] = Field(None, description="Exchange order ID (from Binance)")

    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Order side: buy, sell")
    order_type: str = Field(..., description="Order type: limit, market")

    # Quantities
    quantity: Decimal = Field(..., description="Order quantity")
    price: Optional[Decimal] = Field(None, description="Limit price (if limit order)")

    # Execution
    status: str = Field(..., description="Order status: pending, filled, cancelled, rejected")
    filled_quantity: Decimal = Field(..., description="Filled quantity")
    filled_price: Optional[Decimal] = Field(None, description="Average filled price")

    # Fees
    commission: Optional[Decimal] = Field(None, description="Commission paid")

    # Timestamps
    placed_at: datetime = Field(..., description="Order placement timestamp")
    filled_at: Optional[datetime] = Field(None, description="Order fill timestamp")
    cancelled_at: Optional[datetime] = Field(None, description="Order cancellation timestamp")

    # Additional data
    metadata: Optional[dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        """Pydantic config."""

        from_attributes = True


class OrderFilter(BaseModel):
    """Order filter query parameters."""

    run_id: Optional[int] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    side: Optional[str] = Field(None, description="Filter by side (buy/sell)")
    status: Optional[str] = Field(None, description="Filter by status")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class OrderListResponse(BaseModel):
    """Order list response with pagination."""

    total: int = Field(..., description="Total number of orders matching filter")
    items: list[OrderResponse] = Field(..., description="List of orders")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
