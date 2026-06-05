"""
Optimization module type definitions.

This module defines all core types, enums, and dataclasses used by the Optuna
optimization system for walk-forward analysis and indicator weight optimization.
"""

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from uuid import UUID


class OptimizationObjective(str, Enum):
    """Optimization objective metric."""

    SHARPE_RATIO = "sharpe_ratio"  # Maximize Sharpe ratio (default)
    SORTINO_RATIO = "sortino_ratio"  # Maximize Sortino ratio
    PROFIT_FACTOR = "profit_factor"  # Maximize profit factor
    WIN_RATE = "win_rate"  # Maximize win rate
    TOTAL_RETURN = "total_return"  # Maximize total return


class WalkForwardMode(str, Enum):
    """Walk-forward analysis mode."""

    SLIDING = "sliding"  # Sliding window (fixed size train/test)
    EXPANDING = "expanding"  # Expanding window (growing train, fixed test)


@dataclass
class WalkForwardSplit:
    """
    Single walk-forward train/test split.

    Attributes:
        split_index: Split number (0-indexed)
        train_start: Start date of training period
        train_end: End date of training period
        test_start: Start date of testing period
        test_end: End date of testing period
    """

    split_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        return {
            "split_index": self.split_index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat()
        }

    def __post_init__(self):
        """Validate split dates."""
        if self.train_start >= self.train_end:
            raise ValueError(f"train_start must be before train_end: {self.train_start} >= {self.train_end}")
        if self.test_start >= self.test_end:
            raise ValueError(f"test_start must be before test_end: {self.test_start} >= {self.test_end}")
        if self.train_end > self.test_start:
            raise ValueError(f"train_end must not be after test_start: {self.train_end} > {self.test_start}")


@dataclass
class WalkForwardResult:
    """
    Result from one walk-forward split optimization.

    Attributes:
        split: The split configuration
        train_score: Optimization score on training data
        test_score: Optimization score on test data (out-of-sample)
        best_params: Best parameters found in this split
        n_trials: Number of trials completed
        optimization_time_seconds: Time spent optimizing this split
    """

    split: WalkForwardSplit
    train_score: float
    test_score: float
    best_params: Dict[str, float]
    n_trials: int
    optimization_time_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        return {
            "split": self.split.to_dict(),
            "train_score": self.train_score,
            "test_score": self.test_score,
            "best_params": self.best_params,
            "n_trials": self.n_trials,
            "optimization_time_seconds": self.optimization_time_seconds
        }


@dataclass
class OptimizationConfig:
    """
    Configuration for Optuna optimization.

    Attributes:
        study_name: Name of the Optuna study
        objective: Optimization objective (Sharpe ratio by default)
        n_trials: Number of trials to run per split
        walk_forward_mode: Walk-forward analysis mode
        n_splits: Number of walk-forward splits
        train_ratio: Ratio of data for training (rest is for testing)
        initial_capital: Initial capital for backtesting (USDT)
        symbol: Trading symbol
        timeframe: Candle timeframe
        start_date: Start date for optimization data
        end_date: End date for optimization data
        sampler: Optuna sampler name ('tpe', 'random', 'grid')
        pruner: Optuna pruner name ('median', 'hyperband', 'none')
        db_url: Optional database URL for Optuna storage
        storage: Optuna storage URL (if using persistent storage)
    """

    study_name: str
    objective: OptimizationObjective = OptimizationObjective.SHARPE_RATIO
    n_trials: int = 100
    walk_forward_mode: WalkForwardMode = WalkForwardMode.SLIDING
    n_splits: int = 4
    train_ratio: float = 0.75
    initial_capital: Decimal = Decimal("10000.0")
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sampler: str = "tpe"  # Tree-structured Parzen Estimator (best for continuous params)
    pruner: str = "median"  # Median pruner (good default)
    storage: Optional[str] = None  # Optuna storage URL (e.g., postgresql://...)

    def __post_init__(self):
        """Validate configuration."""
        if self.n_trials <= 0:
            raise ValueError(f"n_trials must be positive: {self.n_trials}")
        if self.n_splits <= 0:
            raise ValueError(f"n_splits must be positive: {self.n_splits}")
        if not (0.0 < self.train_ratio < 1.0):
            raise ValueError(f"train_ratio must be in (0, 1): {self.train_ratio}")
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be positive: {self.initial_capital}")
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValueError(f"start_date must be before end_date: {self.start_date} >= {self.end_date}")

    @classmethod
    def from_env(cls) -> "OptimizationConfig":
        """
        Load optimization configuration from environment variables.

        Environment variables:
            OPTIMIZATION_STUDY_NAME: Study name
            OPTIMIZATION_OBJECTIVE: Optimization objective
            OPTIMIZATION_N_TRIALS: Number of trials per split
            OPTIMIZATION_WF_MODE: Walk-forward mode
            OPTIMIZATION_N_SPLITS: Number of splits
            OPTIMIZATION_TRAIN_RATIO: Training data ratio
            OPTIMIZATION_INITIAL_CAPITAL: Initial capital
            OPTIMIZATION_SYMBOL: Trading symbol
            OPTIMIZATION_TIMEFRAME: Candle timeframe
            OPTIMIZATION_START_DATE: Start date (ISO format)
            OPTIMIZATION_END_DATE: End date (ISO format)
            OPTIMIZATION_SAMPLER: Optuna sampler
            OPTIMIZATION_PRUNER: Optuna pruner
            OPTIMIZATION_STORAGE: Optuna storage URL

        Returns:
            OptimizationConfig: Configuration loaded from environment
        """
        import os

        # Parse dates if provided
        start_date = None
        end_date = None
        if start_str := os.getenv("OPTIMIZATION_START_DATE"):
            start_date = datetime.fromisoformat(start_str)
        if end_str := os.getenv("OPTIMIZATION_END_DATE"):
            end_date = datetime.fromisoformat(end_str)

        return cls(
            study_name=os.getenv("OPTIMIZATION_STUDY_NAME", "default_study"),
            objective=OptimizationObjective(
                os.getenv("OPTIMIZATION_OBJECTIVE", "sharpe_ratio")
            ),
            n_trials=int(os.getenv("OPTIMIZATION_N_TRIALS", "100")),
            walk_forward_mode=WalkForwardMode(
                os.getenv("OPTIMIZATION_WF_MODE", "sliding")
            ),
            n_splits=int(os.getenv("OPTIMIZATION_N_SPLITS", "4")),
            train_ratio=float(os.getenv("OPTIMIZATION_TRAIN_RATIO", "0.75")),
            initial_capital=Decimal(os.getenv("OPTIMIZATION_INITIAL_CAPITAL", "10000.0")),
            symbol=os.getenv("OPTIMIZATION_SYMBOL", "BTCUSDT"),
            timeframe=os.getenv("OPTIMIZATION_TIMEFRAME", "15m"),
            start_date=start_date,
            end_date=end_date,
            sampler=os.getenv("OPTIMIZATION_SAMPLER", "tpe"),
            pruner=os.getenv("OPTIMIZATION_PRUNER", "median"),
            storage=os.getenv("OPTIMIZATION_STORAGE")
        )

    def to_snapshot(self) -> Dict[str, Any]:
        """
        Convert configuration to snapshot dictionary for database storage.

        Returns:
            Dict: Configuration snapshot for JSONB column
        """
        return {
            "study_name": self.study_name,
            "objective": self.objective.value,
            "n_trials": self.n_trials,
            "walk_forward_mode": self.walk_forward_mode.value,
            "n_splits": self.n_splits,
            "train_ratio": self.train_ratio,
            "initial_capital": float(self.initial_capital),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "sampler": self.sampler,
            "pruner": self.pruner,
            "storage": self.storage
        }


@dataclass
class StudyResult:
    """
    Complete result from an Optuna optimization study.

    Attributes:
        study_name: Name of the study
        run_id: Associated run ID (if linked to a run)
        n_trials: Total number of trials across all splits
        best_value: Best objective value achieved
        best_params: Best parameters (indicator weights)
        best_weights: Best indicator weights (normalized)
        weights_set_id: UUID of saved weights_set in database
        started_at: Study start timestamp
        completed_at: Study completion timestamp
        optimization_time_seconds: Total optimization time
        walk_forward_results: Results from each walk-forward split
        metadata: Additional metadata (study configuration, etc.)
    """

    study_name: str
    run_id: Optional[UUID]
    n_trials: int
    best_value: float
    best_params: Dict[str, float]
    best_weights: Dict[str, float]
    weights_set_id: Optional[UUID]
    started_at: datetime
    completed_at: Optional[datetime]
    optimization_time_seconds: float
    walk_forward_results: List[WalkForwardResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata_dict(self) -> Dict[str, Any]:
        """
        Convert to metadata dictionary for optuna_studies.metadata column.

        Returns:
            Dict: Metadata for JSONB storage
        """
        return {
            "study_name": self.study_name,
            "n_trials": self.n_trials,
            "n_completed": self.n_trials,
            "optimization_time_seconds": self.optimization_time_seconds,
            "objective": self.metadata.get("objective", "sharpe_ratio"),
            "best_trial": {
                "value": self.best_value,
                "params": self.best_params,
                "datetime_start": self.started_at.isoformat(),
                "datetime_complete": self.completed_at.isoformat() if self.completed_at else None
            },
            "walk_forward": {
                "n_splits": len(self.walk_forward_results),
                "split_results": [wf.to_dict() for wf in self.walk_forward_results]
            },
            **self.metadata
        }


@dataclass
class WeightsSearchSpace:
    """
    Search space configuration for indicator weights.

    Attributes:
        indicators: List of indicator names to optimize
        min_weight: Minimum weight value
        max_weight: Maximum weight value
        normalize: Whether to normalize weights to sum to 1.0
        fixed_weights: Dict of indicator names to fixed weight values (not optimized)
    """

    indicators: List[str] = field(default_factory=lambda: [
        "ema", "macd", "rsi", "stoch_rsi", "bollinger", "atr", "obv", "fear_greed", "user_indicator"
    ])
    min_weight: float = 0.0
    max_weight: float = 1.0
    normalize: bool = True
    fixed_weights: Dict[str, float] = field(default_factory=lambda: {
        "user_indicator": 0.05  # Fixed to 5% - only a boost, not main decision driver
    })

    def __post_init__(self):
        """Validate search space."""
        if not self.indicators:
            raise ValueError("indicators list cannot be empty")
        if self.min_weight < 0.0:
            raise ValueError(f"min_weight must be non-negative: {self.min_weight}")
        if self.max_weight <= self.min_weight:
            raise ValueError(f"max_weight must be greater than min_weight: {self.max_weight} <= {self.min_weight}")

    def suggest_weights(self, trial) -> Dict[str, float]:
        """
        Suggest indicator weights using Optuna trial.

        Fixed weights (from fixed_weights dict) are not optimized and keep their fixed values.
        The remaining weights are optimized and normalized together.

        Args:
            trial: Optuna trial object

        Returns:
            Dict mapping indicator names to weights
        """
        weights = {}

        # Separate indicators into fixed and optimizable
        optimizable_indicators = [
            ind for ind in self.indicators
            if ind not in self.fixed_weights
        ]

        # Suggest weights for optimizable indicators only
        for indicator in optimizable_indicators:
            weight = trial.suggest_float(
                f"weight_{indicator}",
                self.min_weight,
                self.max_weight
            )
            weights[indicator] = weight

        # Add fixed weights (these are not optimized)
        for indicator, fixed_value in self.fixed_weights.items():
            if indicator in self.indicators:
                weights[indicator] = fixed_value

        # Normalize if requested
        if self.normalize and weights:
            total = sum(weights.values())
            if total > 0:
                weights = {k: v / total for k, v in weights.items()}

        return weights
