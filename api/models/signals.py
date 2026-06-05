"""
Pydantic models for signals endpoints.

Request/response models for signal/decision data.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class SignalResponse(BaseModel):
    """Signal response model."""

    id: str = Field(..., description="Signal ID (UUID)")
    run_id: str = Field(..., description="Run ID")
    timestamp: datetime = Field(..., description="Signal timestamp")
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")

    # Decision details
    decision: str = Field(..., description="Decision: buy, sell, hold")
    score: Decimal = Field(..., description="Weighted score [-1, 1]")
    confidence: float = Field(..., description="Confidence level [0, 1]")

    # Weights snapshot at time of decision
    weights_snapshot: dict[str, Decimal] = Field(..., description="Active weights at signal time")

    # Indicators snapshot at time of decision
    indicators_snapshot: dict[str, dict[str, Any]] = Field(
        ..., description="All indicator values and signals at signal time"
    )

    # Reason for the decision or skip
    reason: Optional[str] = Field(None, description="Reason for decision or skip (e.g., quota reached)")

    # Risk info
    position_size: Optional[Decimal] = Field(None, description="Position size if entry signal")
    estimated_sl_price: Optional[Decimal] = Field(None, description="Estimated stop-loss price")
    estimated_tp_price: Optional[Decimal] = Field(None, description="Estimated take-profit price")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class SignalFilter(BaseModel):
    """Signal filter query parameters."""

    run_id: Optional[str] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    decision: Optional[str] = Field(None, description="Filter by decision (buy/sell/hold)")

    min_score: Optional[Decimal] = Field(None, description="Minimum score")
    max_score: Optional[Decimal] = Field(None, description="Maximum score")

    date_from: Optional[datetime] = Field(None, description="Signal from date")
    date_to: Optional[datetime] = Field(None, description="Signal to date")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class SignalListResponse(BaseModel):
    """Signal list response with pagination."""

    total: int = Field(..., description="Total number of signals matching filter")
    items: list[SignalResponse] = Field(..., description="List of signals")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
