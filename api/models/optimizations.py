"""
Pydantic models for optimizations endpoints.

Response models for Optuna optimization studies. An optimization is a run
(``run_type='optimization'``): lifecycle/status comes from the ``runs`` row and
the results (``best_value``/``best_params``/...) from the linked ``optuna_studies``
row once the study completes. The launch request lives in ``models.run_control``
(:class:`StartOptimizationRequest`).
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class OptimizationResponse(BaseModel):
    """Optimization study merged from its run row and (if any) its study row."""

    # Run lifecycle (always present)
    run_id: int = Field(..., description="Run id (primary identifier; used for stop/kill/logs)")
    status: str = Field(..., description="pending / running / completed / failed / cancelled")
    symbol: Optional[str] = Field(None, description="Trading symbol")
    timeframe: Optional[str] = Field(None, description="Candle timeframe")
    created_at: datetime = Field(..., description="Run creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Run start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Run completion timestamp")

    # Launch parameters (from runs.config_snapshot)
    study_name: str = Field(..., description="Study name")
    objective: Optional[str] = Field(None, description="Optimization objective")
    n_trials: Optional[int] = Field(None, description="Trials per split")
    n_splits: Optional[int] = Field(None, description="Walk-forward splits")

    # Results (from optuna_studies; null until the study completes)
    study_id: Optional[str] = Field(None, description="optuna_studies id (UUID), null while running")
    best_value: Optional[float] = Field(None, description="Best objective value found")
    best_params: Optional[dict[str, Any]] = Field(None, description="Best parameters found")
    weights_set_id: Optional[str] = Field(None, description="Weights set produced by the study")
    weights_set_active: bool = Field(
        False, description="Whether the produced weights set is currently the active one"
    )


class OptimizationListResponse(BaseModel):
    """Optimization list response."""

    total: int = Field(..., description="Total studies")
    items: list[OptimizationResponse] = Field(..., description="List of studies")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")
