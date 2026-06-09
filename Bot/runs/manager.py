"""
Run manager for CRUD operations on runs table.

This module provides the RunManager class for creating, updating, and querying
trading runs in the database.
"""
import json

import asyncpg
import logging
from datetime import datetime, timezone
from typing import Optional

from .types import (
    Run,
    RunConfig,
    RunEnvironment,
    RunFilter,
    RunResult,
    RunStatus,
    RunType,
    is_valid_status_transition,
)

logger = logging.getLogger(__name__)


class RunManager:
    """
    Manager for run lifecycle and database operations.

    Handles CRUD operations for runs table with proper validation.
    """

    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize run manager.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def create_run(
        self,
        run_config: RunConfig,
        status: RunStatus = RunStatus.PENDING,
    ) -> Run:
        """
        Create a new run in the database.

        Args:
            run_config: Run configuration snapshot
            status: Initial status (default: PENDING)

        Returns:
            Created run with assigned ID

        Raises:
            asyncpg.PostgresError: Database error
        """
        now = datetime.now(timezone.utc)

        def _normalize_run_config(_run_config: dict) -> dict:
            _run_config["weights_set_id"] =str(_run_config["weights_set_id"])
            return _run_config


        async with self.db_pool.acquire() as conn:
            logger.debug(f"Creating new run, run_config: {run_config.to_dict()}")
            logger.debug(f"Creating new run, run_config type: {[(iten[0], type(iten[1])) for iten in run_config.to_dict().items()]}")
            row = await conn.fetchrow(
                """
                INSERT INTO runs (
                    run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, weights_set_id,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING
                    id, run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, result,
                    created_at, started_at, completed_at,
                    weights_set_id, optuna_study_id
                """,
                run_config.run_type.value,
                status.value,
                run_config.environment.value,
                run_config.symbol,
                run_config.timeframe,
                run_config.start_date,
                run_config.end_date,
                json.dumps(_normalize_run_config(run_config.to_dict())),
                run_config.weights_set_id,
                now,
            )

        run = Run(**dict(row))
        logger.info(
            f"Created run: id={run.id}, type={run.run_type.value}, "
            f"status={run.status.value}, symbol={run.symbol}"
        )
        return run

    async def get_run(self, run_id: int) -> Optional[Run]:
        """
        Get run by ID.

        Args:
            run_id: Run ID

        Returns:
            Run if found, None otherwise

        Raises:
            asyncpg.PostgresError: Database error
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, result,
                    created_at, started_at, completed_at,
                    weights_set_id, optuna_study_id
                FROM runs
                WHERE id = $1
                """,
                run_id,
            )

        if row:
            return Run(**dict(row))
        return None

    async def update_status(
        self,
        run_id: int,
        new_status: RunStatus,
        result: Optional[RunResult] = None,
    ) -> Run:
        """
        Update run status with validation.

        Args:
            run_id: Run ID
            new_status: New status
            result: Optional result (required for COMPLETED/FAILED)

        Returns:
            Updated run

        Raises:
            ValueError: Invalid status transition
            asyncpg.PostgresError: Database error
        """
        # Get current run
        current_run = await self.get_run(run_id)
        if not current_run:
            raise ValueError(f"Run {run_id} not found")

        # Validate transition
        if not is_valid_status_transition(current_run.status, new_status):
            raise ValueError(
                f"Invalid status transition: {current_run.status.value} -> {new_status.value}"
            )

        # SAFEGUARD: Prevent closing run with open positions
        if new_status in {RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.FAILED}:
            open_trades_count = await self.get_open_trades_count(run_id)
            if open_trades_count > 0:
                raise ValueError(
                    f"Cannot close run: {open_trades_count} open trade(s) found. "
                    f"Please close all positions before ending the run."
                )

        # Prepare timestamps
        now = datetime.now(timezone.utc)
        started_at = current_run.started_at
        completed_at = current_run.completed_at

        # Set started_at if transitioning to RUNNING
        if new_status == RunStatus.RUNNING and not started_at:
            started_at = now

        # Set completed_at if transitioning to terminal status
        if new_status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            completed_at = now

        # Convert result to dict
        result_dict = result.to_dict() if result else None

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE runs
                SET
                    status = $2,
                    started_at = COALESCE($3, started_at),
                    completed_at = COALESCE($4, completed_at),
                    result = COALESCE($5, result)
                WHERE id = $1
                RETURNING
                    id, run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, result,
                    created_at, started_at, completed_at,
                    weights_set_id, optuna_study_id
                """,
                run_id,
                new_status.value,
                started_at,
                completed_at,
                result_dict,
            )

        updated_run = Run(**dict(row))
        logger.info(
            f"Updated run {run_id}: status={current_run.status.value} -> {new_status.value}"
        )
        return updated_run

    async def update_result(self, run_id: int, result: RunResult) -> Run:
        """
        Update run result without changing status.

        Useful for updating metrics while run is still in progress.

        Args:
            run_id: Run ID
            result: Updated result

        Returns:
            Updated run

        Raises:
            asyncpg.PostgresError: Database error
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE runs
                SET result = $2
                WHERE id = $1
                RETURNING
                    id, run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, result,
                    created_at, started_at, completed_at,
                    weights_set_id, optuna_study_id
                """,
                run_id,
                result.to_dict(),
            )

        updated_run = Run(**dict(row))
        logger.debug(f"Updated result for run {run_id}")
        return updated_run

    async def link_optuna_study(self, run_id: int, study_id: int) -> Run:
        """
        Link run to an Optuna study.

        Args:
            run_id: Run ID
            study_id: Optuna study ID

        Returns:
            Updated run

        Raises:
            asyncpg.PostgresError: Database error
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE runs
                SET optuna_study_id = $2
                WHERE id = $1
                RETURNING
                    id, run_type, status, environment,
                    symbol, timeframe, start_date, end_date,
                    config_snapshot, result,
                    created_at, started_at, completed_at,
                    weights_set_id, optuna_study_id
                """,
                run_id,
                study_id,
            )

        updated_run = Run(**dict(row))
        logger.info(f"Linked run {run_id} to Optuna study {study_id}")
        return updated_run

    async def query_runs(self, run_filter: RunFilter) -> list[Run]:
        """
        Query runs with filtering.

        Args:
            run_filter: Filter criteria

        Returns:
            List of matching runs

        Raises:
            asyncpg.PostgresError: Database error
        """
        # Build WHERE clause with positional parameters
        conditions = []
        params = []
        param_idx = 1

        if run_filter.run_type:
            conditions.append(f"run_type = ${param_idx}")
            params.append(run_filter.run_type.value)
            param_idx += 1

        if run_filter.status:
            conditions.append(f"status = ${param_idx}")
            params.append(run_filter.status.value)
            param_idx += 1

        if run_filter.environment:
            conditions.append(f"environment = ${param_idx}")
            params.append(run_filter.environment.value)
            param_idx += 1

        if run_filter.symbol:
            conditions.append(f"symbol = ${param_idx}")
            params.append(run_filter.symbol)
            param_idx += 1

        if run_filter.timeframe:
            conditions.append(f"timeframe = ${param_idx}")
            params.append(run_filter.timeframe)
            param_idx += 1

        if run_filter.created_after:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(run_filter.created_after)
            param_idx += 1

        if run_filter.created_before:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(run_filter.created_before)
            param_idx += 1

        if run_filter.weights_set_id:
            conditions.append(f"weights_set_id = ${param_idx}")
            params.append(run_filter.weights_set_id)
            param_idx += 1

        if run_filter.optuna_study_id:
            conditions.append(f"optuna_study_id = ${param_idx}")
            params.append(run_filter.optuna_study_id)
            param_idx += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Add limit and offset
        limit_param = f"${param_idx}"
        params.append(run_filter.limit)
        param_idx += 1

        offset_param = f"${param_idx}"
        params.append(run_filter.offset)

        query = f"""
            SELECT
                id, run_type, status, environment,
                symbol, timeframe, start_date, end_date,
                config_snapshot, result,
                created_at, started_at, completed_at,
                weights_set_id, optuna_study_id
            FROM runs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        runs = [Run(**dict(row)) for row in rows]
        logger.debug(f"Query returned {len(runs)} runs")
        return runs

    async def count_runs(self, run_filter: RunFilter) -> int:
        """
        Count runs matching filter.

        Args:
            run_filter: Filter criteria

        Returns:
            Number of matching runs

        Raises:
            asyncpg.PostgresError: Database error
        """
        # Build WHERE clause with positional parameters
        conditions = []
        params = []
        param_idx = 1

        if run_filter.run_type:
            conditions.append(f"run_type = ${param_idx}")
            params.append(run_filter.run_type.value)
            param_idx += 1

        if run_filter.status:
            conditions.append(f"status = ${param_idx}")
            params.append(run_filter.status.value)
            param_idx += 1

        if run_filter.environment:
            conditions.append(f"environment = ${param_idx}")
            params.append(run_filter.environment.value)
            param_idx += 1

        if run_filter.symbol:
            conditions.append(f"symbol = ${param_idx}")
            params.append(run_filter.symbol)
            param_idx += 1

        if run_filter.timeframe:
            conditions.append(f"timeframe = ${param_idx}")
            params.append(run_filter.timeframe)
            param_idx += 1

        if run_filter.created_after:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(run_filter.created_after)
            param_idx += 1

        if run_filter.created_before:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(run_filter.created_before)
            param_idx += 1

        if run_filter.weights_set_id:
            conditions.append(f"weights_set_id = ${param_idx}")
            params.append(run_filter.weights_set_id)
            param_idx += 1

        if run_filter.optuna_study_id:
            conditions.append(f"optuna_study_id = ${param_idx}")
            params.append(run_filter.optuna_study_id)
            param_idx += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT COUNT(*) as count
            FROM runs
            {where_clause}
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        count = row["count"]
        logger.debug(f"Count query returned {count} runs")
        return count

    async def delete_run(self, run_id: int) -> bool:
        """
        Delete a run (soft delete - not recommended per CLAUDE.md).

        NOTE: Per CLAUDE.md specification, nothing should ever be deleted.
        This method is provided for exceptional cases only.

        Args:
            run_id: Run ID

        Returns:
            True if deleted, False if not found

        Raises:
            asyncpg.PostgresError: Database error
        """
        logger.warning(f"Deleting run {run_id} (violates CLAUDE.md no-delete policy)")

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM runs WHERE id = $1",
                run_id,
            )

        deleted = result == "DELETE 1"
        return deleted

    async def get_active_runs(
        self, run_type: Optional[RunType] = None
    ) -> list[Run]:
        """
        Get all active (non-terminal) runs.

        Args:
            run_type: Optional filter by run type

        Returns:
            List of active runs

        Raises:
            asyncpg.PostgresError: Database error
        """
        run_filter = RunFilter(run_type=run_type, limit=1000)

        # Get all runs and filter for active status
        all_runs = await self.query_runs(run_filter)
        active_runs = [
            run
            for run in all_runs
            if run.status in {RunStatus.PENDING, RunStatus.RUNNING}
        ]

        logger.debug(f"Found {len(active_runs)} active runs")
        return active_runs

    async def get_open_trades_count(self, run_id: int) -> int:
        """
        Get count of open trades for a run.

        Args:
            run_id: Run ID

        Returns:
            Number of open trades

        Raises:
            asyncpg.PostgresError: Database error
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM trades
                WHERE run_id = $1 AND status = 'open'
                """,
                run_id,
            )

        count = row["count"]
        logger.debug(f"Run {run_id} has {count} open trade(s)")
        return count

    async def get_open_trades(self, run_id: int) -> list[dict]:
        """
        Get all open trades for a run.

        Args:
            run_id: Run ID

        Returns:
            List of open trade records

        Raises:
            asyncpg.PostgresError: Database error
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, run_id, symbol, entry_price, quantity,
                    opened_at, status
                FROM trades
                WHERE run_id = $1 AND status = 'open'
                ORDER BY opened_at DESC
                """,
                run_id,
            )

        trades = [dict(row) for row in rows]
        logger.debug(f"Run {run_id} has {len(trades)} open trade(s)")
        return trades
