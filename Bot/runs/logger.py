"""
Enhanced logging utilities with run context support.

This module provides logging utilities that automatically include run context
in log messages and support structured JSON logging.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from .context import get_run_context


class RunContextFormatter(logging.Formatter):
    """
    Custom formatter that adds run context to log records.

    Automatically includes run_id and run_type in logs when available.
    """

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        """
        Initialize formatter.

        Args:
            fmt: Log format string
            datefmt: Date format string
        """
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with run context.

        Args:
            record: Log record

        Returns:
            Formatted log message
        """
        # Add run context if available
        context = get_run_context()
        if context:
            record.run_id = context.run_id
            record.run_type = context.run_type
        else:
            record.run_id = None
            record.run_type = None

        return super().format(record)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs as JSON objects for easy parsing and analysis.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record

        Returns:
            JSON-formatted log message
        """
        # Build log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add run context if available
        context = get_run_context()
        if context:
            log_entry["run_id"] = context.run_id
            log_entry["run_type"] = context.run_type

        # Add extra fields
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_entry.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[str] = None,
) -> None:
    """
    Setup logging configuration for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json' or 'text')
        log_file: Optional file path for file logging
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Create formatter
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        # Text format with run context
        fmt = "[%(asctime)s] [%(levelname)s] [%(name)s]"
        if log_format == "text":
            fmt += " [RUN:%(run_id)s]" if "%(run_id)s" else ""
        fmt += " %(message)s"
        formatter = RunContextFormatter(fmt=fmt)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.info(f"Logging configured: level={level}, format={log_format}")


def get_logger_with_context(name: str) -> logging.Logger:
    """
    Get a logger that automatically includes run context.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)

    # Add custom log method with automatic context
    def log_with_context(level: int, msg: str, **kwargs: Any) -> None:
        """Log with automatic run context."""
        context = get_run_context()
        if context:
            extra = kwargs.get("extra", {})
            extra.update(context.get_log_extra())
            kwargs["extra"] = extra
        logger.log(level, msg, **kwargs)

    # Patch logger methods
    logger.debug_ctx = lambda msg, **kw: log_with_context(logging.DEBUG, msg, **kw)
    logger.info_ctx = lambda msg, **kw: log_with_context(logging.INFO, msg, **kw)
    logger.warning_ctx = lambda msg, **kw: log_with_context(logging.WARNING, msg, **kw)
    logger.error_ctx = lambda msg, **kw: log_with_context(logging.ERROR, msg, **kw)

    return logger


class PerformanceLogger:
    """
    Logger for tracking performance metrics.

    Used to log operation latency and throughput.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize performance logger.

        Args:
            logger: Base logger
        """
        self.logger = logger

    def log_latency(
        self,
        operation: str,
        latency_ms: float,
        success: bool = True,
        **extra: Any,
    ) -> None:
        """
        Log operation latency.

        Args:
            operation: Operation name
            latency_ms: Latency in milliseconds
            success: Whether operation succeeded
            **extra: Additional fields
        """
        log_data = {
            "operation": operation,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            **extra,
        }

        context = get_run_context()
        if context:
            log_data.update(context.get_log_extra())

        self.logger.info(
            f"[PERF] {operation}: {latency_ms:.2f}ms (success={success})",
            extra=log_data,
        )

    def log_throughput(
        self,
        operation: str,
        count: int,
        duration_seconds: float,
        **extra: Any,
    ) -> None:
        """
        Log operation throughput.

        Args:
            operation: Operation name
            count: Number of items processed
            duration_seconds: Duration in seconds
            **extra: Additional fields
        """
        rate = count / duration_seconds if duration_seconds > 0 else 0

        log_data = {
            "operation": operation,
            "count": count,
            "duration_seconds": round(duration_seconds, 2),
            "rate_per_second": round(rate, 2),
            **extra,
        }

        context = get_run_context()
        if context:
            log_data.update(context.get_log_extra())

        self.logger.info(
            f"[PERF] {operation}: {count} items in {duration_seconds:.2f}s ({rate:.2f}/s)",
            extra=log_data,
        )
