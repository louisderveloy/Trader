"""
Optimization configuration management.

This module provides configuration management for the Optuna optimization system,
including loading from environment variables and validation.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from .types import (
    OptimizationConfig,
    OptimizationObjective,
    WalkForwardMode,
    WeightsSearchSpace
)

# Structured logging
logger = logging.getLogger(__name__)


def load_config_from_env() -> OptimizationConfig:
    """
    Load optimization configuration from environment variables.

    This is a convenience wrapper around OptimizationConfig.from_env() that
    adds logging and error handling.

    Returns:
        OptimizationConfig: Loaded configuration

    Raises:
        ValueError: If configuration is invalid
    """
    logger.info("Loading optimization configuration from environment variables")

    try:
        config = OptimizationConfig.from_env()
        logger.info(
            "Optimization configuration loaded successfully",
            extra={
                "study_name": config.study_name,
                "objective": config.objective.value,
                "n_trials": config.n_trials,
                "n_splits": config.n_splits,
                "walk_forward_mode": config.walk_forward_mode.value
            }
        )
        return config
    except Exception as e:
        logger.error(
            "Failed to load optimization configuration",
            extra={"error": str(e)},
            exc_info=True
        )
        raise


def create_default_config(
    study_name: str,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> OptimizationConfig:
    """
    Create a default optimization configuration.

    Args:
        study_name: Name for the optimization study
        symbol: Trading symbol
        timeframe: Candle timeframe
        start_date: Optional start date for data
        end_date: Optional end date for data

    Returns:
        OptimizationConfig: Configuration with default values
    """
    logger.info(
        "Creating default optimization configuration",
        extra={
            "study_name": study_name,
            "symbol": symbol,
            "timeframe": timeframe
        }
    )

    return OptimizationConfig(
        study_name=study_name,
        objective=OptimizationObjective.SHARPE_RATIO,
        n_trials=100,
        walk_forward_mode=WalkForwardMode.SLIDING,
        n_splits=4,
        train_ratio=0.75,
        initial_capital=Decimal("10000.0"),
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        sampler="tpe",
        pruner="median"
    )


def validate_config(config: OptimizationConfig) -> None:
    """
    Validate optimization configuration.

    This performs additional validation beyond the __post_init__ checks,
    including checking for reasonable parameter ranges.

    Args:
        config: Configuration to validate

    Raises:
        ValueError: If configuration is invalid
    """
    logger.debug("Validating optimization configuration", extra={"study_name": config.study_name})

    # Check n_trials is reasonable (warn if too low)
    if config.n_trials < 50:
        logger.warning(
            "Low number of trials may not find optimal parameters",
            extra={"n_trials": config.n_trials, "recommended_min": 50}
        )

    # Check n_splits is reasonable
    if config.n_splits < 2:
        logger.warning(
            "Less than 2 splits reduces robustness of walk-forward validation",
            extra={"n_splits": config.n_splits, "recommended_min": 2}
        )

    # Check train_ratio is reasonable
    if config.train_ratio < 0.6:
        logger.warning(
            "Low training ratio may not provide enough data for optimization",
            extra={"train_ratio": config.train_ratio, "recommended_min": 0.6}
        )
    if config.train_ratio > 0.9:
        logger.warning(
            "High training ratio leaves little data for out-of-sample testing",
            extra={"train_ratio": config.train_ratio, "recommended_max": 0.9}
        )

    # Check sampler is supported
    supported_samplers = ["tpe", "random", "grid", "cmaes"]
    if config.sampler not in supported_samplers:
        logger.warning(
            "Unsupported sampler, using TPE as fallback",
            extra={"sampler": config.sampler, "supported": supported_samplers}
        )

    # Check pruner is supported
    supported_pruners = ["median", "hyperband", "none"]
    if config.pruner not in supported_pruners:
        logger.warning(
            "Unsupported pruner, using median as fallback",
            extra={"pruner": config.pruner, "supported": supported_pruners}
        )

    logger.debug("Configuration validation passed")


def create_search_space(
    indicators: Optional[list[str]] = None,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    normalize: bool = True
) -> WeightsSearchSpace:
    """
    Create indicator weights search space.

    Args:
        indicators: List of indicator names (defaults to all 9 indicators)
        min_weight: Minimum weight value
        max_weight: Maximum weight value
        normalize: Whether to normalize weights to sum to 1.0

    Returns:
        WeightsSearchSpace: Search space configuration
    """
    if indicators is None:
        # Default to all 9 indicators
        indicators = [
            "ema", "macd", "rsi", "stoch_rsi",
            "bollinger", "atr", "obv", "fear_greed",
            "user_indicator"
        ]

    logger.info(
        "Creating weights search space",
        extra={
            "n_indicators": len(indicators),
            "min_weight": min_weight,
            "max_weight": max_weight,
            "normalize": normalize
        }
    )

    return WeightsSearchSpace(
        indicators=indicators,
        min_weight=min_weight,
        max_weight=max_weight,
        normalize=normalize
    )
