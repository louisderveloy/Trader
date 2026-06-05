"""
Pydantic models for optimizations endpoints.

Request/response models for Optuna optimization studies.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class OptimizationTrialResponse(BaseModel):
    """Single trial result from optimization."""

    trial_number: int = Field(..., description="Trial number")
    value: float = Field(..., description="Objective value achieved")
    state: str = Field(..., description="Trial state: complete, pruned, fail")
    params: dict[str, Any] = Field(..., description="Parameters tested")
    metrics: dict[str, Any] = Field(..., description="Calculated metrics")


class OptimizationResponse(BaseModel):
    """Optimization study response model."""

    id: str = Field(..., description="Study ID (UUID)")
    run_id: Optional[int] = Field(None, description="Associated run ID")
    study_name: str = Field(..., description="Study name")

    # Study configuration
    n_trials: int = Field(..., description="Number of trials")

    # Results
    best_value: Optional[float] = Field(None, description="Best objective value found")
    best_params: Optional[dict[str, Any]] = Field(None, description="Best parameters found")
    weights_set_id: Optional[str] = Field(None, description="Associated weights set ID")

    # Timestamps
    started_at: Optional[datetime] = Field(None, description="Study start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Study completion timestamp")
    created_at: datetime = Field(..., description="Study creation timestamp")

    # Additional data
    metadata: Optional[dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        """Pydantic config."""

        from_attributes = True


class OptimizationLaunchRequest(BaseModel):
    """Request to launch new optimization study."""

    name: str = Field(..., description="Study name", min_length=1, max_length=100)
    objective: str = Field(
        default="sharpe",
        description="Objective metric: sharpe, sortino, profit_factor",
    )
    n_trials: int = Field(default=100, ge=1, description="Number of trials")
    n_jobs: int = Field(default=1, ge=1, description="Parallel jobs")


class OptimizationListResponse(BaseModel):
    """Optimization list response."""

    total: int = Field(..., description="Total studies")
    items: list[OptimizationResponse] = Field(..., description="List of studies")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
