"""
Error logging utilities for runs.

This module provides utilities for logging errors to the errors_log table
with run context and structured data.
"""

import asyncpg
import json
import logging
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from .context import get_current_run_id

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Severity level for errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Category of error."""

    DATABASE = "database"
    EXCHANGE_API = "exchange_api"
    STRATEGY = "strategy"
    INDICATOR = "indicator"
    ORDER = "order"
    NETWORK = "network"
    VALIDATION = "validation"
    SYSTEM = "system"
    UNKNOWN = "unknown"


async def log_error(
    db_pool: asyncpg.Pool,
    error_message: str,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    exception: Optional[Exception] = None,
    context: Optional[dict[str, Any]] = None,
    run_id: Optional[int] = None,
) -> int:
    """
    Log an error to the errors_log table.

    Args:
        db_pool: Database connection pool
        error_message: Human-readable error message
        severity: Error severity level
        category: Error category
        exception: Optional exception object (will extract traceback)
        context: Optional context data (stored as JSONB)
        run_id: Optional run ID (auto-detected from context if not provided)

    Returns:
        ID of created error log entry

    Raises:
        asyncpg.PostgresError: Database error
    """
    # Auto-detect run_id from context if not provided
    if run_id is None:
        run_id = get_current_run_id()

    # Extract traceback from exception
    error_traceback = None
    if exception:
        error_traceback = "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )

    # Prepare context data
    context_data = context or {}
    if exception:
        context_data["exception_type"] = type(exception).__name__
        context_data["exception_str"] = str(exception)

    now = datetime.now(timezone.utc)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO errors_log (
                run_id, severity, category,
                error_message, error_traceback, context,
                timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            run_id,
            severity.value,
            category.value,
            error_message,
            error_traceback,
            json.dumps(context_data),
            now,
        )

    error_id = row["id"]

    logger.error(
        f"Error logged: id={error_id}, severity={severity.value}, "
        f"category={category.value}, message={error_message}",
        extra={
            "error_id": error_id,
            "run_id": run_id,
            "severity": severity.value,
            "category": category.value,
        },
    )

    return error_id


async def log_exception(
    db_pool: asyncpg.Pool,
    exception: Exception,
    severity: ErrorSeverity = ErrorSeverity.HIGH,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    context: Optional[dict[str, Any]] = None,
    run_id: Optional[int] = None,
) -> int:
    """
    Log an exception to the errors_log table.

    Convenience wrapper around log_error for exceptions.

    Args:
        db_pool: Database connection pool
        exception: Exception to log
        severity: Error severity level
        category: Error category
        context: Optional context data
        run_id: Optional run ID

    Returns:
        ID of created error log entry

    Raises:
        asyncpg.PostgresError: Database error
    """
    error_message = f"{type(exception).__name__}: {str(exception)}"

    return await log_error(
        db_pool=db_pool,
        error_message=error_message,
        severity=severity,
        category=category,
        exception=exception,
        context=context,
        run_id=run_id,
    )


async def get_recent_errors(
    db_pool: asyncpg.Pool,
    run_id: Optional[int] = None,
    severity: Optional[ErrorSeverity] = None,
    category: Optional[ErrorCategory] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Get recent errors from errors_log table.

    Args:
        db_pool: Database connection pool
        run_id: Optional filter by run ID
        severity: Optional filter by severity
        category: Optional filter by category
        limit: Maximum number of errors to return

    Returns:
        List of error dictionaries

    Raises:
        asyncpg.PostgresError: Database error
    """
    conditions = []
    params = []
    param_idx = 1

    if run_id is not None:
        conditions.append(f"run_id = ${param_idx}")
        params.append(run_id)
        param_idx += 1

    if severity is not None:
        conditions.append(f"severity = ${param_idx}")
        params.append(severity.value)
        param_idx += 1

    if category is not None:
        conditions.append(f"category = ${param_idx}")
        params.append(category.value)
        param_idx += 1

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    query = f"""
        SELECT
            id, run_id, severity, category,
            error_message, error_traceback, context,
            timestamp
        FROM errors_log
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    errors = [dict(row) for row in rows]
    logger.debug(f"Retrieved {len(errors)} recent errors")
    return errors


async def count_errors(
    db_pool: asyncpg.Pool,
    run_id: Optional[int] = None,
    severity: Optional[ErrorSeverity] = None,
    category: Optional[ErrorCategory] = None,
) -> int:
    """
    Count errors matching criteria.

    Args:
        db_pool: Database connection pool
        run_id: Optional filter by run ID
        severity: Optional filter by severity
        category: Optional filter by category

    Returns:
        Number of matching errors

    Raises:
        asyncpg.PostgresError: Database error
    """
    conditions = []
    params = []
    param_idx = 1

    if run_id is not None:
        conditions.append(f"run_id = ${param_idx}")
        params.append(run_id)
        param_idx += 1

    if severity is not None:
        conditions.append(f"severity = ${param_idx}")
        params.append(severity.value)
        param_idx += 1

    if category is not None:
        conditions.append(f"category = ${param_idx}")
        params.append(category.value)
        param_idx += 1

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    query = f"""
        SELECT COUNT(*) as count
        FROM errors_log
        {where_clause}
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)

    count = row["count"]
    return count
