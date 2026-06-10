"""
Optimization runner.

This module provides the OptimizationRunner class that orchestrates the complete
optimization process including walk-forward analysis, Optuna study creation,
and result persistence.
"""

import logging
import os
import time
from typing import Optional
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
import asyncpg
import optuna
import nest_asyncio

# Apply nest_asyncio patch to allow asyncio.run() from within a running event loop
# This is required because the CLI wraps cmd_run() in asyncio.run() at the top level,
# and sync_objective (called by Optuna) needs to call asyncio.run() again for async code
nest_asyncio.apply()

from .types import (
    OptimizationConfig,
    StudyResult,
    WalkForwardResult,
    WeightsSearchSpace
)
from .config import validate_config, create_search_space
from .walk_forward import generate_splits_from_db
from .objective import create_objective_function, evaluate_weights
from .db import save_weights_set, save_study_result

from runs.types import RunConfig, RunType, RunEnvironment, RunResult
from runs.context import create_run, run_context
from runs.manager import RunManager
from runs.errors import log_exception, ErrorCategory, ErrorSeverity

from strategy.config import StrategyEngineConfig
from notifications.discord import DiscordNotifier

# Structured logging
logger = logging.getLogger(__name__)


class OptimizationRunner:
    """
    Orchestrates the complete optimization process.

    This class:
    1. Validates configuration
    2. Generates walk-forward splits
    3. Runs Optuna optimization on each split
    4. Evaluates best weights on test sets
    5. Saves results to database
    6. Generates comprehensive report

    Attributes:
        config: Optimization configuration
        db_pool: Database connection pool
        search_space: Weights search space
        run_id: Optional run ID for linking to a specific run
    """

    def __init__(
        self,
        config: OptimizationConfig,
        db_pool: asyncpg.Pool,
        search_space: Optional[WeightsSearchSpace] = None,
        run_id: Optional[UUID] = None
    ):
        """
        Initialize optimization runner.

        Args:
            config: Optimization configuration
            db_pool: Database connection pool
            search_space: Optional custom search space (uses defaults if not provided)
            run_id: Optional run ID to link results to
        """
        self.config = config
        self.db_pool = db_pool
        self.search_space = search_space or create_search_space()
        self.run_id = run_id
        self.strategy_config: Optional[StrategyEngineConfig] = None  # Loaded from DB

        # Validate configuration
        validate_config(config)

        logger.info(
            "OptimizationRunner initialized",
            extra={
                "study_name": config.study_name,
                "objective": config.objective.value,
                "n_trials": config.n_trials,
                "n_splits": config.n_splits,
                "run_id": str(run_id) if run_id else None
            }
        )

    async def run(self) -> StudyResult:
        """
        Run the complete optimization process.

        This is the main entry point that:
        1. Creates run record if not provided
        2. Generates walk-forward splits
        3. Optimizes on each training split
        4. Evaluates on each test split
        5. Aggregates results
        6. Saves to database
        7. Updates run status

        Returns:
            StudyResult with complete optimization results

        Raises:
            Exception: If optimization fails
        """
        logger.info(
            "Starting optimization",
            extra={"study_name": self.config.study_name}
        )

        # Create run record if not provided
        if self.run_id is None:
            run_config = RunConfig(
                run_type=RunType.OPTIMIZATION,
                environment=RunEnvironment.DEV,
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                initial_capital=Decimal("10000"),  # Default, not used in optimization
                strategy_config=self.config.to_snapshot(),
                optimization_config=self.config.to_snapshot(),
            )

            async with create_run(self.db_pool, run_config) as run:
                async with run_context(run):
                    self.run_id = run.id
                    logger.info(f"Created optimization run with ID: {run.id}")
                    return await self._run_optimization()
        else:
            # Run with provided run_id (don't create new run)
            return await self._run_optimization()

    async def _run_optimization(self) -> StudyResult:
        """Internal optimization logic."""
        start_time = time.time()
        started_at = datetime.now(timezone.utc)

        try:
            # Load strategy configuration from database
            await self._load_strategy_config()

            # Generate walk-forward splits
            splits = await self._generate_splits()

            # Run optimization on each split
            walk_forward_results = []
            best_overall_value = float('-inf')
            best_overall_params = {}

            for split in splits:
                logger.info(
                    f"Processing split {split.split_index + 1}/{len(splits)}",
                    extra={"split_index": split.split_index}
                )

                # Optimize on training set
                train_result = await self._optimize_split(split)

                # Get database URL for test evaluation
                db_url = os.getenv("DATABASE_URL", "")
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

                # Evaluate best params on test set
                test_score = await evaluate_weights(
                    weights=train_result["best_params"],
                    config=self.config,
                    split=split,
                    db_url=db_url,
                    strategy_config=self.strategy_config,
                    is_test=True
                )

                # Create walk-forward result
                wf_result = WalkForwardResult(
                    split=split,
                    train_score=train_result["best_value"],
                    test_score=test_score,
                    best_params=train_result["best_params"],
                    n_trials=train_result["n_trials"],
                    optimization_time_seconds=train_result["optimization_time"]
                )
                walk_forward_results.append(wf_result)

                # Track overall best
                if test_score > best_overall_value:
                    best_overall_value = test_score
                    best_overall_params = train_result["best_params"]

                logger.info(
                    f"Split {split.split_index + 1} completed",
                    extra={
                        "split_index": split.split_index,
                        "train_score": train_result["best_value"],
                        "test_score": test_score
                    }
                )

            # Calculate total optimization time
            end_time = time.time()
            completed_at = datetime.now(timezone.utc)
            optimization_time = end_time - start_time

            # Save best weights to database
            weights_set_name = f"{self.config.study_name} - {started_at.strftime('%Y-%m-%d %H:%M')}"
            weights_set_id = await save_weights_set(
                db_pool=self.db_pool,
                name=weights_set_name,
                weights=best_overall_params,
                optimization_score=best_overall_value,
                source="optuna",
                is_active=False  # Don't auto-activate, let user decide
            )

            # Create study result
            study_result = StudyResult(
                study_name=self.config.study_name,
                run_id=self.run_id,
                n_trials=sum(wf.n_trials for wf in walk_forward_results),
                best_value=best_overall_value,
                best_params=best_overall_params,
                best_weights=best_overall_params,  # Already normalized by search space
                weights_set_id=weights_set_id,
                started_at=started_at,
                completed_at=completed_at,
                optimization_time_seconds=optimization_time,
                walk_forward_results=walk_forward_results,
                metadata=self.config.to_snapshot()
            )

            # Save study result to database
            study_db_id = await save_study_result(self.db_pool, study_result)

            # Link run to optuna study if we have a run_id
            if self.run_id and study_db_id:
                try:
                    manager = RunManager(self.db_pool)
                    await manager.link_optuna_study(self.run_id, study_db_id)
                except Exception as e:
                    logger.warning(f"Failed to link run to optuna study: {e}")

            logger.info(
                "Optimization completed successfully",
                extra={
                    "study_name": self.config.study_name,
                    "best_value": best_overall_value,
                    "total_trials": study_result.n_trials,
                    "optimization_time": optimization_time,
                    "weights_set_id": str(weights_set_id)
                }
            )

            # Send Discord notification for optimization complete
            try:
                webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
                notify_enabled = os.getenv("NOTIFY_OPTIMIZATION_COMPLETE", "true").lower() == "true"

                if webhook_url and not webhook_url.startswith("https://discord.com/api/webhooks/YOUR_WEBHOOK") and notify_enabled:
                    rate_limit_seconds = int(os.getenv("DISCORD_RATE_LIMIT_PERIOD_SECONDS", "60"))
                    discord_notifier = DiscordNotifier(
                        webhook_url=webhook_url,
                        db_pool=self.db_pool,
                        rate_limit_seconds=rate_limit_seconds,
                        enabled=True,
                    )

                    await discord_notifier.notify_optimization_complete(
                        study_name=self.config.study_name,
                        best_value=float(best_overall_value),
                        best_params=best_overall_params,
                        n_trials=study_result.n_trials,
                        duration_seconds=optimization_time,
                    )

                    await discord_notifier.close()
            except Exception as e:
                logger.error(f"Failed to send optimization complete notification: {e}")

            return study_result

        except Exception as e:
            # Log error to database
            try:
                await log_exception(
                    self.db_pool,
                    e,
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.STRATEGY,
                    context={"study_name": self.config.study_name},
                    run_id=self.run_id,
                )
            except Exception as log_err:
                logger.warning(f"Failed to log exception: {log_err}")

            logger.error(
                "Optimization failed",
                extra={
                    "study_name": self.config.study_name,
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    async def _load_strategy_config(self):
        """Load strategy configuration from database."""
        try:
            self.strategy_config, _ = await StrategyEngineConfig.from_db(self.db_pool)
            logger.info(
                "Loaded strategy configuration from database",
                extra={
                    "entry_threshold": self.strategy_config.strategy.entry_threshold,
                    "exit_threshold": self.strategy_config.strategy.exit_threshold,
                    "confirmation_candles": self.strategy_config.strategy.confirmation_candles,
                }
            )
        except ValueError as e:
            logger.error(f"Failed to load configuration from database: {e}")
            logger.error("Please create a configuration first using: python -m main config create")
            raise

    async def _generate_splits(self):
        """Generate walk-forward splits from database."""
        logger.info("Generating walk-forward splits")

        splits = await generate_splits_from_db(
            db_pool=self.db_pool,
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            n_splits=self.config.n_splits,
            train_ratio=self.config.train_ratio,
            mode=self.config.walk_forward_mode,
            start_date=self.config.start_date,
            end_date=self.config.end_date
        )

        logger.info(
            "Splits generated",
            extra={"n_splits": len(splits)}
        )

        return splits

    async def _optimize_split(self, split):
        """
        Optimize weights on a single training split.

        Args:
            split: WalkForwardSplit object

        Returns:
            Dict with best_value, best_params, n_trials, optimization_time
        """
        logger.info(
            f"Starting optimization on split {split.split_index}",
            extra={
                "split_index": split.split_index,
                "train_start": split.train_start.isoformat(),
                "train_end": split.train_end.isoformat(),
                "n_jobs": self.config.n_jobs,
                "parallel": self.config.n_jobs != 1
            }
        )

        split_start_time = time.time()

        # Create Optuna study (unique per split to avoid trial contamination)
        study = self._create_study(split_index=split.split_index)

        # Get database URL from environment (not the pool object)
        db_url = os.getenv("DATABASE_URL", "")
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        # Create objective function for this split - pass URL, not pool
        objective_func = create_objective_function(
            config=self.config,
            split=split,
            db_url=db_url,
            search_space=self.search_space,
            strategy_config=self.strategy_config,
            is_test=False
        )

        # Define async wrapper for Optuna (Optuna expects sync functions)
        # Use asyncio.run() which properly creates/closes event loops per trial
        # This avoids task context mismatch errors when reusing event loops
        def sync_objective(trial: optuna.Trial) -> float:
            import asyncio

            # asyncio.run() creates a fresh event loop for this trial,
            # runs the async function, and properly cleans up.
            # This approach:
            # 1. Eliminates "different loop" errors (fresh loop per trial)
            # 2. Eliminates "task mismatch" errors (proper cleanup)
            # 3. Works with asyncpg pool caching (pools created fresh too)
            # 4. Simple and reliable
            return asyncio.run(objective_func(trial))

        # Run optimization
        study.optimize(
            sync_objective,
            n_trials=self.config.n_trials,
            n_jobs=self.config.n_jobs,
            show_progress_bar=True
        )

        split_end_time = time.time()
        split_optimization_time = split_end_time - split_start_time

        # Extract results
        best_value = study.best_value
        best_params = study.best_params

        logger.info(
            f"Split {split.split_index} optimization completed",
            extra={
                "split_index": split.split_index,
                "best_value": best_value,
                "n_trials": len(study.trials),
                "optimization_time": split_optimization_time
            }
        )

        return {
            "best_value": best_value,
            "best_params": best_params,
            "n_trials": len(study.trials),
            "optimization_time": split_optimization_time
        }

    def _create_study(self, split_index: int = 0) -> optuna.Study:
        """
        Create Optuna study with configured sampler and pruner.

        Each split gets a unique study name to prevent trial contamination
        between walk-forward splits.

        Args:
            split_index: Walk-forward split index (appended to study name)

        Returns:
            optuna.Study object
        """
        # Determine storage URL
        storage = None
        if self.config.n_jobs > 1:
            # Parallel optimization requires database storage
            if not self.config.storage:
                # Auto-configure database storage
                dsn = os.getenv("DATABASE_URL", "")
                dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

                # Use same database, different schema for Optuna
                # This keeps Optuna's internal tables separate from our application tables
                if "?" in dsn:
                    storage = f"{dsn}&options=-c%20search_path%3Doptuna,public"
                else:
                    storage = f"{dsn}?options=-c%20search_path%3Doptuna,public"

                logger.info(f"Parallel mode: using database storage (optuna schema)")
            else:
                storage = self.config.storage
        else:
            # Serial optimization can use in-memory storage or configured storage
            storage = self.config.storage

        # Create sampler
        if self.config.sampler == "tpe":
            sampler = optuna.samplers.TPESampler()
        elif self.config.sampler == "random":
            sampler = optuna.samplers.RandomSampler()
        elif self.config.sampler == "grid":
            # Grid sampler requires search space definition
            # For simplicity, fall back to TPE
            logger.warning("Grid sampler not fully supported, using TPE")
            sampler = optuna.samplers.TPESampler()
        elif self.config.sampler == "cmaes":
            sampler = optuna.samplers.CmaEsSampler()
        else:
            logger.warning(f"Unknown sampler {self.config.sampler}, using TPE")
            sampler = optuna.samplers.TPESampler()

        # Create pruner
        if self.config.pruner == "median":
            pruner = optuna.pruners.MedianPruner()
        elif self.config.pruner == "hyperband":
            pruner = optuna.pruners.HyperbandPruner()
        elif self.config.pruner == "none":
            pruner = optuna.pruners.NopPruner()
        else:
            logger.warning(f"Unknown pruner {self.config.pruner}, using median")
            pruner = optuna.pruners.MedianPruner()

        # Create study with unique name per split
        split_study_name = f"{self.config.study_name}_split_{split_index}"
        study = optuna.create_study(
            study_name=split_study_name,
            direction="maximize",  # Always maximize (Sharpe, Sortino, etc.)
            sampler=sampler,
            pruner=pruner,
            storage=storage,  # Use storage if provided for persistence
            load_if_exists=True  # Allow resuming existing studies
        )

        logger.info(
            "Optuna study created",
            extra={
                "study_name": split_study_name,
                "sampler": self.config.sampler,
                "pruner": self.config.pruner,
                "storage": storage or "in-memory",
                "n_jobs": self.config.n_jobs,
                "parallel_mode": self.config.n_jobs > 1
            }
        )

        return study


async def run_optimization(
    config: OptimizationConfig,
    db_pool: asyncpg.Pool,
    search_space: Optional[WeightsSearchSpace] = None,
    run_id: Optional[UUID] = None
) -> StudyResult:
    """
    Convenience function to run optimization.

    Args:
        config: Optimization configuration
        db_pool: Database connection pool
        search_space: Optional custom search space
        run_id: Optional run ID to link results to

    Returns:
        StudyResult with complete optimization results
    """
    runner = OptimizationRunner(
        config=config,
        db_pool=db_pool,
        search_space=search_space,
        run_id=run_id
    )
    return await runner.run()
