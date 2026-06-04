"""
Types and dataclasses for runs management.

This module defines all types used in the runs management system for tracking
backtest, optimization, paper trading, and live trading runs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class RunType(str, Enum):
    """Type of trading run."""

    BACKTEST = "backtest"
    OPTIMIZATION = "optimization"
    PAPER = "paper"
    LIVE = "live"


class RunStatus(str, Enum):
    """Status of a trading run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunEnvironment(str, Enum):
    """Environment where run is executed."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


# Valid status transitions
_VALID_TRANSITIONS = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),  # Terminal state
    RunStatus.FAILED: set(),  # Terminal state
    RunStatus.CANCELLED: set(),  # Terminal state
}


def is_valid_status_transition(from_status: RunStatus, to_status: RunStatus) -> bool:
    """
    Check if status transition is valid.

    Args:
        from_status: Current status
        to_status: Target status

    Returns:
        True if transition is allowed, False otherwise
    """
    if from_status == to_status:
        return True
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


def is_terminal_status(status: RunStatus) -> bool:
    """
    Check if status is terminal (no further transitions possible).

    Args:
        status: Status to check

    Returns:
        True if status is terminal
    """
    return len(_VALID_TRANSITIONS.get(status, set())) == 0


@dataclass
class RunConfig:
    """
    Configuration snapshot for a run.

    This captures all configuration at the time of run creation.
    Stored as JSONB in database.
    """

    # Run identification
    run_type: RunType
    environment: RunEnvironment

    # Trading parameters
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal

    # Strategy config (from strategy.config.StrategyConfig.to_snapshot())
    strategy_config: dict[str, Any]

    # Active weights (if applicable)
    weights_set_id: Optional[int] = None
    weights: Optional[dict[str, float]] = None

    # Optimization config (if run_type == OPTIMIZATION)
    optimization_config: Optional[dict[str, Any]] = None

    # Exchange config
    exchange: str = "binance"
    testnet: bool = True

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_type": self.run_type.value,
            "environment": self.environment.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": str(self.initial_capital),
            "strategy_config": self.strategy_config,
            "weights_set_id": self.weights_set_id,
            "weights": self.weights,
            "optimization_config": self.optimization_config,
            "exchange": self.exchange,
            "testnet": self.testnet,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunConfig":
        """Create from dictionary."""
        return cls(
            run_type=RunType(data["run_type"]),
            environment=RunEnvironment(data["environment"]),
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            start_date=datetime.fromisoformat(data["start_date"]),
            end_date=datetime.fromisoformat(data["end_date"]),
            initial_capital=Decimal(data["initial_capital"]),
            strategy_config=data["strategy_config"],
            weights_set_id=data.get("weights_set_id"),
            weights=data.get("weights"),
            optimization_config=data.get("optimization_config"),
            exchange=data.get("exchange", "binance"),
            testnet=data.get("testnet", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class RunResult:
    """
    Results from a completed run.

    Stored as JSONB in database.
    """

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    total_pnl: Decimal = Decimal("0")
    total_return_pct: float = 0.0
    final_capital: Decimal = Decimal("0")

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: float = 0.0

    profit_factor: float = 0.0
    exposure_time_pct: float = 0.0

    # Comparison to buy-and-hold
    buy_hold_return_pct: float = 0.0
    excess_return_pct: float = 0.0

    # Error information (if run failed)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    # Additional metrics
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": str(self.total_pnl),
            "total_return_pct": self.total_return_pct,
            "final_capital": str(self.final_capital),
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": str(self.max_drawdown),
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "exposure_time_pct": self.exposure_time_pct,
            "buy_hold_return_pct": self.buy_hold_return_pct,
            "excess_return_pct": self.excess_return_pct,
            "error_message": self.error_message,
            "error_traceback": self.error_traceback,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunResult":
        """Create from dictionary."""
        return cls(
            total_trades=data.get("total_trades", 0),
            winning_trades=data.get("winning_trades", 0),
            losing_trades=data.get("losing_trades", 0),
            win_rate=data.get("win_rate", 0.0),
            total_pnl=Decimal(str(data.get("total_pnl", "0"))),
            total_return_pct=data.get("total_return_pct", 0.0),
            final_capital=Decimal(str(data.get("final_capital", "0"))),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=Decimal(str(data.get("max_drawdown", "0"))),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            exposure_time_pct=data.get("exposure_time_pct", 0.0),
            buy_hold_return_pct=data.get("buy_hold_return_pct", 0.0),
            excess_return_pct=data.get("excess_return_pct", 0.0),
            error_message=data.get("error_message"),
            error_traceback=data.get("error_traceback"),
            metrics=data.get("metrics", {}),
        )


@dataclass
class Run:
    """
    Complete run information.

    Represents a row from the runs table.
    """

    id: int
    run_type: RunType
    status: RunStatus
    environment: RunEnvironment

    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime

    config_snapshot: dict[str, Any]
    result: Optional[dict[str, Any]]

    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Optional foreign keys
    weights_set_id: Optional[int] = None
    optuna_study_id: Optional[int] = None

    def __post_init__(self):
        """Validate and convert string enums if needed."""
        if isinstance(self.run_type, str):
            self.run_type = RunType(self.run_type)
        if isinstance(self.status, str):
            self.status = RunStatus(self.status)
        if isinstance(self.environment, str):
            self.environment = RunEnvironment(self.environment)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate run duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        """Check if run is in terminal status."""
        return is_terminal_status(self.status)

    def get_config(self) -> RunConfig:
        """Parse config snapshot as RunConfig."""
        return RunConfig.from_dict(self.config_snapshot)

    def get_result(self) -> Optional[RunResult]:
        """Parse result as RunResult."""
        if self.result:
            return RunResult.from_dict(self.result)
        return None


@dataclass
class RunFilter:
    """Filter criteria for querying runs."""

    run_type: Optional[RunType] = None
    status: Optional[RunStatus] = None
    environment: Optional[RunEnvironment] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None

    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None

    weights_set_id: Optional[int] = None
    optuna_study_id: Optional[int] = None

    limit: int = 100
    offset: int = 0

    def to_sql_conditions(self) -> tuple[list[str], dict[str, Any]]:
        """
        Convert filter to SQL WHERE conditions and parameters.

        Returns:
            Tuple of (conditions list, parameters dict)
        """
        conditions = []
        params = {}

        if self.run_type:
            conditions.append("run_type = :run_type")
            params["run_type"] = self.run_type.value

        if self.status:
            conditions.append("status = :status")
            params["status"] = self.status.value

        if self.environment:
            conditions.append("environment = :environment")
            params["environment"] = self.environment.value

        if self.symbol:
            conditions.append("symbol = :symbol")
            params["symbol"] = self.symbol

        if self.timeframe:
            conditions.append("timeframe = :timeframe")
            params["timeframe"] = self.timeframe

        if self.created_after:
            conditions.append("created_at >= :created_after")
            params["created_after"] = self.created_after

        if self.created_before:
            conditions.append("created_at <= :created_before")
            params["created_before"] = self.created_before

        if self.weights_set_id:
            conditions.append("weights_set_id = :weights_set_id")
            params["weights_set_id"] = self.weights_set_id

        if self.optuna_study_id:
            conditions.append("optuna_study_id = :optuna_study_id")
            params["optuna_study_id"] = self.optuna_study_id

        return conditions, params
