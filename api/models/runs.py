"""
Pydantic models for runs endpoints.

Request/response models for run management.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RunResponse(BaseModel):
    """Run response model."""

    id: int = Field(..., description="Run ID")
    run_type: str = Field(..., description="Run type: backtest, optimization, paper, live")
    status: str = Field(..., description="Status: pending, running, completed, failed, cancelled")
    environment: str = Field(..., description="Environment: dev, staging, prod")

    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")
    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")

    config_snapshot: dict[str, Any] = Field(..., description="Configuration snapshot")
    result: Optional[dict[str, Any]] = Field(None, description="Run result (if completed)")

    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")

    weights_set_id: Optional[int] = Field(None, description="Active weights set ID")
    optuna_study_id: Optional[int] = Field(None, description="Optuna study ID")

    class Config:
        """Pydantic config."""

        from_attributes = True


class RunFilter(BaseModel):
    """Run filter query parameters."""

    run_type: Optional[str] = Field(None, description="Filter by run type")
    status: Optional[str] = Field(None, description="Filter by status")
    environment: Optional[str] = Field(None, description="Filter by environment")
    symbol: Optional[str] = Field(None, description="Filter by symbol")
    timeframe: Optional[str] = Field(None, description="Filter by timeframe")

    created_after: Optional[datetime] = Field(None, description="Created after timestamp")
    created_before: Optional[datetime] = Field(None, description="Created before timestamp")

    weights_set_id: Optional[int] = Field(None, description="Filter by weights set ID")
    optuna_study_id: Optional[int] = Field(None, description="Filter by Optuna study ID")

    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class RunListResponse(BaseModel):
    """Run list response with pagination."""

    total: int = Field(..., description="Total number of runs matching filter")
    items: list[RunResponse] = Field(..., description="List of runs")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")


class RunStatusUpdate(BaseModel):
    """Run status update request."""

    status: str = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for status change")
