"""
Context managers for run lifecycle management.

This module provides context managers for automatically managing run lifecycle,
including status transitions and error handling.
"""

import asyncpg
import logging
import os
import traceback
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterator, Optional

from .manager import RunManager
from .types import Run, RunConfig, RunResult, RunStatus
from notifications.discord import DiscordNotifier

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_run(
    db_pool: asyncpg.Pool,
    run_config: RunConfig,
    auto_start: bool = True,
) -> AsyncIterator[Run]:
    """
    Context manager for run lifecycle.

    Automatically manages status transitions:
    - Creates run in PENDING status
    - Transitions to RUNNING on entry (if auto_start=True)
    - Transitions to COMPLETED on normal exit
    - Transitions to FAILED on exception

    Usage:
        async with create_run(db_pool, config) as run:
            # Run is now in RUNNING status
            # Do work...
            # On normal exit: status -> COMPLETED
            # On exception: status -> FAILED with error details

    Args:
        db_pool: Database connection pool
        run_config: Run configuration
        auto_start: Automatically transition to RUNNING on entry (default: True)

    Yields:
        Run object (status RUNNING if auto_start=True, else PENDING)

    Raises:
        Any exception from the context block (after recording in run)
    """
    manager = RunManager(db_pool)

    # Create run in PENDING status
    run = await manager.create_run(run_config, status=RunStatus.PENDING)
    logger.info(f"[RUN {run.id}] Created run: {run.run_type.value}")

    # Initialize Discord notifier if configured
    discord_notifier = None
    try:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        notify_enabled = os.getenv("NOTIFY_OPTIMIZATION_COMPLETE", "true").lower() == "true"

        if webhook_url and not webhook_url.startswith("https://discord.com/api/webhooks/YOUR_WEBHOOK") and notify_enabled:
            rate_limit_seconds = int(os.getenv("DISCORD_RATE_LIMIT_PERIOD_SECONDS", "60"))
            discord_notifier = DiscordNotifier(
                webhook_url=webhook_url,
                db_pool=db_pool,
                rate_limit_seconds=rate_limit_seconds,
                enabled=True,
            )
    except Exception as e:
        logger.warning(f"Failed to initialize Discord notifier: {e}")

    try:
        # Transition to RUNNING if auto_start
        if auto_start:
            run = await manager.update_status(run.id, RunStatus.RUNNING)
            logger.info(f"[RUN {run.id}] Started run")

        # Yield control to context block
        yield run

        # Normal exit - transition to COMPLETED
        run = await manager.update_status(run.id, RunStatus.COMPLETED)
        logger.info(f"[RUN {run.id}] Completed run")

        # Send Discord notification for run completion
        if discord_notifier:
            try:
                win_rate = None
                total_pnl = None

                # Extract metrics from result if available
                if run.result and isinstance(run.result, dict):
                    metrics = run.result.get("metrics", {})
                    if "win_rate" in metrics:
                        win_rate = float(metrics["win_rate"]) * 100  # Convert to percentage
                    if "total_pnl" in metrics:
                        total_pnl = Decimal(str(metrics["total_pnl"]))

                await discord_notifier.notify_run_completed(
                    run_type=run.run_type.value,
                    symbol=run.symbol,
                    environment=run.environment.value,
                    start_date=run.started_at or run.created_at,
                    end_date=run.completed_at or run.created_at,
                    win_rate=win_rate,
                    total_pnl=total_pnl,
                )
            except Exception as e:
                logger.error(f"Failed to send run completion notification: {e}")

    except Exception as e:
        # Exception - transition to FAILED with error details
        error_msg = str(e)
        error_tb = traceback.format_exc()

        result = RunResult(
            error_message=error_msg,
            error_traceback=error_tb,
        )

        try:
            run = await manager.update_status(run.id, RunStatus.FAILED, result=result)
            logger.error(
                f"[RUN {run.id}] Failed run: {error_msg}",
                extra={"run_id": run.id, "error": error_msg},
            )
        except Exception as update_error:
            logger.exception(
                f"[RUN {run.id}] Failed to update run status to FAILED: {update_error}"
            )

        # Re-raise original exception
        raise

    finally:
        # Close Discord notifier
        if discord_notifier:
            try:
                await discord_notifier.close()
            except Exception as e:
                logger.warning(f"Failed to close Discord notifier: {e}")


@asynccontextmanager
async def update_run_result(
    db_pool: asyncpg.Pool,
    run_id: int,
) -> AsyncIterator[RunResult]:
    """
    Context manager for incrementally updating run results.

    Useful for long-running operations that want to periodically update
    metrics without completing the run.

    Usage:
        async with update_run_result(db_pool, run_id) as result:
            result.total_trades = 10
            result.total_pnl = Decimal("150.50")
            # Result is automatically saved on exit

    Args:
        db_pool: Database connection pool
        run_id: Run ID to update

    Yields:
        RunResult object (modify in place)
    """
    manager = RunManager(db_pool)

    # Get current run
    run = await manager.get_run(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    # Parse existing result or create new
    result = run.get_result() or RunResult()

    try:
        # Yield result for modification
        yield result

        # Save updated result on normal exit
        await manager.update_result(run_id, result)
        logger.debug(f"[RUN {run_id}] Updated run result")

    except Exception as e:
        logger.exception(f"[RUN {run_id}] Error updating run result: {e}")
        raise


class RunContext:
    """
    Run context for tracking current run in request/operation scope.

    This can be used to associate logs, trades, signals, etc. with a specific run.
    """

    def __init__(self, run_id: int, run_type: str):
        """
        Initialize run context.

        Args:
            run_id: Run ID
            run_type: Run type (for logging)
        """
        self.run_id = run_id
        self.run_type = run_type

    def get_log_extra(self) -> dict:
        """
        Get extra fields for structured logging.

        Returns:
            Dictionary with run_id and run_type
        """
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
        }


# Thread-local storage for current run context (for sync code)
# For async code, use contextvars instead
_current_run_context: Optional[RunContext] = None


def set_run_context(context: Optional[RunContext]) -> None:
    """
    Set the current run context.

    Args:
        context: Run context to set (or None to clear)
    """
    global _current_run_context
    _current_run_context = context


def get_run_context() -> Optional[RunContext]:
    """
    Get the current run context.

    Returns:
        Current run context, or None if not set
    """
    return _current_run_context


def get_current_run_id() -> Optional[int]:
    """
    Get the current run ID from context.

    Returns:
        Current run ID, or None if no context set
    """
    context = get_run_context()
    return context.run_id if context else None


@asynccontextmanager
async def run_context(run: Run) -> AsyncIterator[RunContext]:
    """
    Context manager for setting run context.

    Usage:
        async with run_context(run) as ctx:
            # All code here has access to ctx via get_run_context()
            logger.info("Working", extra=ctx.get_log_extra())

    Args:
        run: Run object

    Yields:
        RunContext object
    """
    context = RunContext(run.id, run.run_type.value)
    old_context = get_run_context()

    try:
        set_run_context(context)
        yield context
    finally:
        set_run_context(old_context)
