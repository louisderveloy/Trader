"""
Pydantic models for weights endpoints.

Request/response models for weight sets (strategy weights).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .enums import VALID_INDICATORS


class WeightsResponse(BaseModel):
    """Weights set response model (maps the ``weights_sets`` table 1:1)."""

    id: str = Field(..., description="Weights set ID (UUID)")
    name: str = Field(..., description="Human-readable name")

    # The actual weights
    weights: dict[str, Decimal] = Field(
        ..., description="Indicator weights (indicator_name -> weight)"
    )

    # Source: "manual" or "optuna"
    source: str = Field(..., description="Source: manual, optuna")

    # Score achieved by the optimization that produced this set (if any)
    optimization_score: Optional[Decimal] = Field(
        None, description="Optimization score achieved with these weights"
    )

    # Status
    is_active: bool = Field(default=False, description="Whether this weights set is currently active")

    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class WeightsCreateRequest(BaseModel):
    """Request to create new weights set."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable name (1-100 characters)"
    )
    weights: dict[str, Decimal] = Field(
        ...,
        description="Indicator weights (must use valid indicator names)"
    )

    @field_validator('weights')
    @classmethod
    def validate_weights_keys(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        """Validate that all weight keys are valid indicator names."""
        invalid_keys = set(v.keys()) - VALID_INDICATORS
        if invalid_keys:
            raise ValueError(
                f"Invalid indicator names: {invalid_keys}. "
                f"Valid indicators: {sorted(VALID_INDICATORS)}"
            )
        return v


class WeightsActivateRequest(BaseModel):
    """Request to activate a weights set."""

    pass  # Just the endpoint trigger, no body needed


class WeightsListResponse(BaseModel):
    """Weights list response."""

    total: int = Field(..., description="Total number of weights sets")
    items: list[WeightsResponse] = Field(..., description="List of weights sets")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
