"""
Runs management module.

This module provides comprehensive run lifecycle management, logging, and error tracking
for backtests, optimizations, paper trading, and live trading runs.
"""

from .context import (
    RunContext,
    create_run,
    get_current_run_id,
    get_run_context,
    run_context,
    set_run_context,
    update_run_result,
)
from .errors import (
    ErrorCategory,
    ErrorSeverity,
    count_errors,
    get_recent_errors,
    log_error,
    log_exception,
)
from .logger import (
    JSONFormatter,
    PerformanceLogger,
    RunContextFormatter,
    get_logger_with_context,
    setup_logging,
)
from .manager import RunManager
from .types import (
    Run,
    RunConfig,
    RunEnvironment,
    RunFilter,
    RunResult,
    RunStatus,
    RunType,
    is_terminal_status,
    is_valid_status_transition,
)

__all__ = [
    # Types
    "Run",
    "RunConfig",
    "RunEnvironment",
    "RunFilter",
    "RunResult",
    "RunStatus",
    "RunType",
    "is_terminal_status",
    "is_valid_status_transition",
    # Manager
    "RunManager",
    # Context
    "RunContext",
    "create_run",
    "run_context",
    "update_run_result",
    "get_run_context",
    "set_run_context",
    "get_current_run_id",
    # Logger
    "setup_logging",
    "get_logger_with_context",
    "RunContextFormatter",
    "JSONFormatter",
    "PerformanceLogger",
    # Errors
    "ErrorCategory",
    "ErrorSeverity",
    "log_error",
    "log_exception",
    "get_recent_errors",
    "count_errors",
]
