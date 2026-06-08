"""
Pydantic models for errors_log endpoints.

Request/response models for error log management.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorLogResponse(BaseModel):
    """Error log response model."""

    id: UUID = Field(..., description="Error log ID")
    run_id: Optional[int] = Field(None, description="Associated run ID")
    category: str = Field(..., description="Error category/type")
    severity: str = Field(..., description="Error severity: low, medium, high, critical")
    error_message: str = Field(..., description="Error message")
    error_traceback: Optional[str] = Field(None, description="Stack trace")
    timestamp: datetime = Field(..., description="When the error occurred")
    context: Optional[dict[str, Any]] = Field(None, description="Additional context metadata")

    class Config:
        """Pydantic config."""

        from_attributes = True


class ErrorLogListResponse(BaseModel):
    """Error log list response with pagination."""

    total: int = Field(..., description="Total number of errors matching filter")
    items: list[ErrorLogResponse] = Field(..., description="List of errors")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")


class ErrorStatsResponse(BaseModel):
    """Error statistics response."""

    total_errors: int = Field(..., description="Total error count")
    by_severity: dict[str, int] = Field(..., description="Count by severity level")
    by_category: dict[str, int] = Field(..., description="Count by category")
    recent_24h: int = Field(..., description="Errors in last 24 hours")
