"""
Optuna objective function.

This module provides the objective function that Optuna will optimize.
It integrates with the vectorbt backtester for fast evaluation of indicator weights.
"""

import logging
import os
from typing import Dict, Any, Optional
from decimal import Decimal
import asyncpg
import optuna

from .types import (
    OptimizationConfig,
    OptimizationObjective,
    WalkForwardSplit,
    WeightsSearchSpace
)
from backtesting.types import BacktestConfig
from backtesting.vectorbt_engine import VectorbtBacktester
from strategy.config import StrategyEngineConfig

# Structured logging
logger = logging.getLogger(__name__)

# Process-local connection pool cache
# With asyncio.run() creating fresh event loops per trial,
# we create fresh pools too. This is acceptable because:
# 1. asyncpg's internal connection pooling still provides benefit
# 2. Pool creation cost is ~50ms, but optimization gains from parallel trials dominate
# 3. Avoids complex event loop/pool lifecycle management
# 4. Simple and reliable - no task context mismatches
_process_pools: Dict[int, asyncpg.Pool] = {}


async def _get_or_create_pool(
    db_url: str,
    min_size: int = 1,
    max_size: int = 3
) -> asyncpg.Pool:
    """
    Create a database connection pool.

    With asyncio.run() creating fresh event loops per trial, we create
    fresh pools too. Each pool is properly cleaned up when the event loop
    exits, avoiding resource leaks.

    Args:
        db_url: Database connection string
        min_size: Minimum pool size
        max_size: Maximum pool size

    Returns:
        asyncpg.Pool for this trial's event loop
    """
    # Create pool in current event loop
    pool = await asyncpg.create_pool(
        dsn=db_url,
        min_size=min_size,
        max_size=max_size
    )

    logger.debug(
        "Created DB pool for trial",
        extra={"pool_size": max_size, "pid": os.getpid()}
    )

    return pool


async def _cleanup_process_pool():
    """
    Cleanup function (kept for backward compatibility with tests).
    Not needed with asyncio.run() since loops auto-cleanup.
    """
    # With asyncio.run(), cleanup happens automatically
    pass


class ObjectiveFunction:
    """
    Objective function for Optuna optimization.

    This class encapsulates the logic to evaluate a set of indicator weights
    using the vectorbt backtester and return a score to optimize.

    Attributes:
        config: Optimization configuration
        split: Walk-forward split (train or test)
        db_pool: Database connection pool
        search_space: Weights search space
        is_test: Whether this is test evaluation (if True, no pruning)
    """

    def __init__(
        self,
        config: OptimizationConfig,
        split: WalkForwardSplit,
        db_url: str,
        search_space: WeightsSearchSpace,
        strategy_config: StrategyEngineConfig,
        is_test: bool = False
    ):
        """
        Initialize objective function.

        Args:
            config: Optimization configuration
            split: Walk-forward split
            db_url: Database URL string (not pool - for multiprocessing compatibility)
            search_space: Weights search space configuration
            strategy_config: Strategy configuration from database
            is_test: Whether this is test phase (no pruning)
        """
        self.config = config
        self.split = split
        self.db_url = db_url
        self.search_space = search_space
        self.strategy_config = strategy_config
        self.is_test = is_test


        # Use train or test dates depending on phase
        if is_test:
            self.start_date = split.test_start
            self.end_date = split.test_end
            self.phase = "test"
        else:
            self.start_date = split.train_start
            self.end_date = split.train_end
            self.phase = "train"

        logger.debug(
            "ObjectiveFunction initialized",
            extra={
                "split_index": split.split_index,
                "phase": self.phase,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat()
            }
        )

    async def __call__(self, trial: optuna.Trial) -> float:
        """
        Evaluate objective function for a given trial.

        This is the main function called by Optuna for each trial.

        Args:
            trial: Optuna trial object

        Returns:
            Objective score to maximize (or minimize with direction="minimize")

        Raises:
            optuna.TrialPruned: If trial should be pruned
        """
        # Suggest weights using search space
        weights = self.search_space.suggest_weights(trial)

        logger.debug(
            f"Evaluating trial {trial.number}",
            extra={
                "trial_number": trial.number,
                "phase": self.phase,
                "split_index": self.split.split_index,
                "weights": weights
            }
        )

        try:
            # Run backtest with these weights
            score = await self._run_backtest(weights)

            logger.info(
                f"Trial {trial.number} completed",
                extra={
                    "trial_number": trial.number,
                    "phase": self.phase,
                    "split_index": self.split.split_index,
                    "score": score,
                    "weights": weights
                }
            )

            return score

        except Exception as e:
            logger.error(
                f"Trial {trial.number} failed",
                extra={
                    "trial_number": trial.number,
                    "phase": self.phase,
                    "split_index": self.split.split_index,
                    "error": str(e)
                },
                exc_info=True
            )
            # Return a very bad score instead of failing
            # This allows optimization to continue
            return float('-inf')

    async def _run_backtest(self, weights: Dict[str, float]) -> float:
        """
        Run backtest with given weights and return objective score.

        Creates a fresh database pool for each trial. With asyncio.run() creating
        fresh event loops per trial, pool creation cost (~50ms) is acceptable and
        avoids event loop context issues.

        Args:
            weights: Indicator weights dictionary

        Returns:
            Objective score (Sharpe, Sortino, etc.)

        Raises:
            Exception: If backtest fails
        """
        # Create fresh pool for this trial (asyncio.run ensures proper cleanup)
        db_pool = await _get_or_create_pool(
            db_url=self.db_url,
            min_size=1,
            max_size=3
        )

        try:
            # Create backtest configuration with thresholds from database config
            backtest_config = BacktestConfig(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.config.initial_capital,
                # Pass weights AND thresholds from database config
                strategy_params={
                    "weights": weights,
                    "entry_threshold": self.strategy_config.strategy.entry_threshold,
                    "exit_threshold": self.strategy_config.strategy.exit_threshold,
                    "confirmation_candles": self.strategy_config.strategy.confirmation_candles,
                }
            )

            # Create backtester with fresh pool
            backtester = VectorbtBacktester(
                config=backtest_config,
                db_pool=db_pool
            )

            # Run backtest
            result = await backtester.run()

            # Handle failed backtest or missing metrics
            if result is None or result.metrics is None:
                logger.warning("Backtest returned no metrics, returning -inf score")
                return float('-inf')

            # Extract score based on optimization objective
            score = self._extract_score(result.metrics)

            return score
        finally:
            # Properly close pool (asyncio.run ensures loop cleanup)
            await db_pool.close()

    def _extract_score(self, metrics) -> float:
        """
        Extract optimization score from backtest metrics.

        Args:
            metrics: BacktestMetrics object (not dict)

        Returns:
            Score based on optimization objective

        Raises:
            ValueError: If objective metric not found in metrics
        """
        # Safety check for None metrics
        if metrics is None:
            logger.warning("[OBJECTIVE] Metrics is None, returning -inf")
            return float('-inf')

        objective = self.config.objective

        # DEBUG: Log all available metrics (inline values for visibility)
        total_pnl = float(metrics.total_pnl) if metrics.total_pnl else 0
        total_return = float(metrics.total_return) if metrics.total_return else 0
        final_capital = float(metrics.final_capital) if metrics.final_capital else 0

        logger.info(
            f"[OBJECTIVE] Metrics: trades={metrics.total_trades} "
            f"(win={metrics.winning_trades}, lose={metrics.losing_trades}), "
            f"win_rate={metrics.win_rate:.2f}%"
        )
        logger.info(
            f"[OBJECTIVE] PnL: total_pnl={total_pnl:.2f}, total_return={total_return:.2f}%, "
            f"final_capital={final_capital:.2f}"
        )
        logger.info(
            f"[OBJECTIVE] Risk: sharpe={metrics.sharpe_ratio:.4f}, sortino={metrics.sortino_ratio:.4f}, "
            f"profit_factor={metrics.profit_factor:.4f}, max_dd={metrics.max_drawdown_pct:.2f}%"
        )

        if objective == OptimizationObjective.SHARPE_RATIO:
            score = metrics.sharpe_ratio if metrics.sharpe_ratio is not None else float('-inf')
        elif objective == OptimizationObjective.SORTINO_RATIO:
            score = metrics.sortino_ratio if metrics.sortino_ratio is not None else float('-inf')
        elif objective == OptimizationObjective.PROFIT_FACTOR:
            score = metrics.profit_factor if metrics.profit_factor is not None else float('-inf')
        elif objective == OptimizationObjective.WIN_RATE:
            score = metrics.win_rate if metrics.win_rate is not None else float('-inf')
        elif objective == OptimizationObjective.TOTAL_RETURN:
            score = float(metrics.total_return) if metrics.total_return is not None else float('-inf')
        else:
            raise ValueError(f"Unsupported optimization objective: {objective}")

        logger.info(f"[OBJECTIVE] Score for {objective.value}: {score}")

        # Flag if Sharpe is 0 - this is our bug
        if objective == OptimizationObjective.SHARPE_RATIO and score == 0.0:
            logger.warning(
                f"[OBJECTIVE] SHARPE IS ZERO despite {metrics.total_trades} trades "
                f"and {total_pnl:.2f} total PnL"
            )

        return score


def create_objective_function(
    config: OptimizationConfig,
    split: WalkForwardSplit,
    db_url: str,
    search_space: WeightsSearchSpace,
    strategy_config: StrategyEngineConfig,
    is_test: bool = False
) -> ObjectiveFunction:
    """
    Factory function to create an objective function.

    Args:
        config: Optimization configuration
        split: Walk-forward split
        db_url: Database URL string (not pool - for multiprocessing compatibility)
        search_space: Weights search space
        strategy_config: Strategy configuration from database
        is_test: Whether this is test evaluation

    Returns:
        ObjectiveFunction instance
    """
    return ObjectiveFunction(
        config=config,
        split=split,
        db_url=db_url,
        search_space=search_space,
        strategy_config=strategy_config,
        is_test=is_test
    )


async def evaluate_weights(
    weights: Dict[str, float],
    config: OptimizationConfig,
    split: WalkForwardSplit,
    db_url: str,
    strategy_config: StrategyEngineConfig,
    is_test: bool = False
) -> float:
    """
    Evaluate a specific set of weights (without Optuna trial).

    This is useful for evaluating the best weights found during training
    on the test set.

    Args:
        weights: Indicator weights dictionary
        config: Optimization configuration
        split: Walk-forward split
        db_url: Database URL string (not pool - for multiprocessing compatibility)
        strategy_config: Strategy configuration from database
        is_test: Whether this is test evaluation

    Returns:
        Objective score
    """
    # Create fresh pool for this evaluation
    db_pool = await _get_or_create_pool(
        db_url=db_url,
        min_size=1,
        max_size=2
    )

    try:
        # Use train or test dates
        start_date = split.test_start if is_test else split.train_start
        end_date = split.test_end if is_test else split.train_end

        # Create backtest configuration with thresholds from database config
        backtest_config = BacktestConfig(
            symbol=config.symbol,
            timeframe=config.timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=config.initial_capital,
            # Pass weights AND thresholds from database config
            strategy_params={
                "weights": weights,
                "entry_threshold": strategy_config.strategy.entry_threshold,
                "exit_threshold": strategy_config.strategy.exit_threshold,
                "confirmation_candles": strategy_config.strategy.confirmation_candles,
            }
        )

        # Create backtester
        backtester = VectorbtBacktester(
            config=backtest_config,
            db_pool=db_pool
        )

        # Run backtest
        result = await backtester.run()

        # Handle failed backtest
        if result is None or result.metrics is None:
            logger.error("Backtest failed or returned no metrics")
            return float('-inf')  # Return worst possible score

        # Extract score based on objective (metrics is BacktestMetrics object, not dict)
        if config.objective == OptimizationObjective.SHARPE_RATIO:
            score = result.metrics.sharpe_ratio
        elif config.objective == OptimizationObjective.SORTINO_RATIO:
            score = result.metrics.sortino_ratio
        elif config.objective == OptimizationObjective.PROFIT_FACTOR:
            score = result.metrics.profit_factor
        elif config.objective == OptimizationObjective.WIN_RATE:
            score = result.metrics.win_rate
        elif config.objective == OptimizationObjective.TOTAL_RETURN:
            score = float(result.metrics.total_return)
        else:
            raise ValueError(f"Unsupported optimization objective: {config.objective}")

        logger.info(
            "Weights evaluated",
            extra={
                "phase": "test" if is_test else "train",
                "split_index": split.split_index,
                "score": score,
                "weights": weights
            }
        )

        return score
    finally:
        # Properly close pool
        await db_pool.close()
