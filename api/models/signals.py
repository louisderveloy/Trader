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
    run_id: int = Field(..., description="Run ID")
    time: datetime = Field(..., description="Signal timestamp")
    symbol: str = Field(..., description="Trading symbol")

    # Decision details
    signal_type: str = Field(..., description="Signal type: entry_long, exit, skip")
    weighted_score: Decimal = Field(..., description="Weighted score [-1, 1]")

    # Weights snapshot at time of decision
    weights_snapshot: dict[str, Any] = Field(..., description="Active weights at signal time")

    # Indicators snapshot at time of decision
    indicators_snapshot: dict[str, Any] = Field(
        ..., description="All indicator values and signals at signal time"
    )

    # Reason for the decision or skip
    decision_reason: Optional[str] = Field(None, description="Reason for decision or skip")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class SignalFilter(BaseModel):
    """Signal filter query parameters."""

    run_id: Optional[int] = Field(None, description="Filter by run ID")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    decision: Optional[str] = Field(None, description="Filter by signal_type (entry_long/exit/skip)")

    min_score: Optional[Decimal] = Field(None, description="Minimum score")
    max_score: Optional[Decimal] = Field(None, description="Maximum score")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class SignalListResponse(BaseModel):
    """Signal list response with pagination."""

    total: int = Field(..., description="Total number of signals matching filter")
    items: list[SignalResponse] = Field(..., description="List of signals")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
