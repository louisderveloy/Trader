"""
Pydantic models for weights endpoints.

Request/response models for weight sets (strategy weights).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class WeightsResponse(BaseModel):
    """Weights set response model."""

    id: int = Field(..., description="Weights set ID")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Description of weights set")

    # The actual weights
    weights: dict[str, Decimal] = Field(
        ..., description="Indicator weights (indicator_name -> weight)"
    )

    # Source and status
    source: str = Field(..., description="Source: manual, optuna")
    optuna_study_id: Optional[int] = Field(None, description="Source Optuna study ID (if from optimization)")

    # Performance metrics
    metrics: Optional[dict[str, Any]] = Field(
        None, description="Performance metrics (Sharpe, Sortino, win_rate, etc.)"
    )

    # Status
    is_active: bool = Field(default=False, description="Whether this weights set is currently active")
    activated_at: Optional[datetime] = Field(None, description="When this set was activated")

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class WeightsCreateRequest(BaseModel):
    """Request to create new weights set."""

    name: str = Field(..., description="Human-readable name", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Optional description")
    weights: dict[str, Decimal] = Field(..., description="Indicator weights")


class WeightsUpdateRequest(BaseModel):
    """Request to update weights set."""

    name: Optional[str] = Field(None, description="New name")
    description: Optional[str] = Field(None, description="New description")
    weights: Optional[dict[str, Decimal]] = Field(None, description="New weights")


class WeightsActivateRequest(BaseModel):
    """Request to activate a weights set."""

    pass  # Just the endpoint trigger, no body needed


class WeightsListResponse(BaseModel):
    """Weights list response."""

    total: int = Field(..., description="Total number of weights sets")
    items: list[WeightsResponse] = Field(..., description="List of weights sets")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
