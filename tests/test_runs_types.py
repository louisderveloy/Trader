"""
Unit tests for runs.types module.

Tests for run types, statuses, enums, and dataclasses.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from runs.types import (
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


# ==========================================
# Status Transitions
# ==========================================


def test_valid_status_transitions():
    """Test all valid status transitions."""
    # From PENDING
    assert is_valid_status_transition(RunStatus.PENDING, RunStatus.RUNNING)
    assert is_valid_status_transition(RunStatus.PENDING, RunStatus.CANCELLED)

    # From RUNNING
    assert is_valid_status_transition(RunStatus.RUNNING, RunStatus.COMPLETED)
    assert is_valid_status_transition(RunStatus.RUNNING, RunStatus.FAILED)
    assert is_valid_status_transition(RunStatus.RUNNING, RunStatus.CANCELLED)

    # Same status (always valid)
    assert is_valid_status_transition(RunStatus.PENDING, RunStatus.PENDING)
    assert is_valid_status_transition(RunStatus.RUNNING, RunStatus.RUNNING)


def test_invalid_status_transitions():
    """Test invalid status transitions."""
    # Cannot go from PENDING to COMPLETED
    assert not is_valid_status_transition(RunStatus.PENDING, RunStatus.COMPLETED)

    # Cannot transition from terminal states
    assert not is_valid_status_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    assert not is_valid_status_transition(RunStatus.FAILED, RunStatus.RUNNING)
    assert not is_valid_status_transition(RunStatus.CANCELLED, RunStatus.RUNNING)


def test_terminal_statuses():
    """Test terminal status detection."""
    assert is_terminal_status(RunStatus.COMPLETED)
    assert is_terminal_status(RunStatus.FAILED)
    assert is_terminal_status(RunStatus.CANCELLED)

    assert not is_terminal_status(RunStatus.PENDING)
    assert not is_terminal_status(RunStatus.RUNNING)


# ==========================================
# RunConfig
# ==========================================


def test_run_config_creation():
    """Test RunConfig creation."""
    config = RunConfig(
        run_type=RunType.BACKTEST,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        initial_capital=Decimal("10000"),
        strategy_config={"param1": "value1"},
        weights={"ema": 0.15, "macd": 0.20},
        weights_set_id=42,
        exchange="binance",
        testnet=True,
        metadata={"note": "test run"},
    )

    assert config.run_type == RunType.BACKTEST
    assert config.environment == RunEnvironment.DEV
    assert config.symbol == "BTCUSDT"
    assert config.timeframe == "15m"
    assert config.initial_capital == Decimal("10000")
    assert config.weights_set_id == 42
    assert config.testnet is True


def test_run_config_to_dict():
    """Test RunConfig serialization to dict."""
    config = RunConfig(
        run_type=RunType.OPTIMIZATION,
        environment=RunEnvironment.PROD,
        symbol="ETHUSDT",
        timeframe="1h",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
        initial_capital=Decimal("5000"),
        strategy_config={"entry_threshold": 0.6},
        weights={"rsi": 0.25, "macd": 0.30},
        optimization_config={"n_trials": 100},
    )

    config_dict = config.to_dict()

    assert config_dict["run_type"] == "optimization"
    assert config_dict["environment"] == "prod"
    assert config_dict["symbol"] == "ETHUSDT"
    assert config_dict["initial_capital"] == "5000"
    assert config_dict["weights"]["rsi"] == 0.25
    assert config_dict["optimization_config"]["n_trials"] == 100


def test_run_config_from_dict():
    """Test RunConfig deserialization from dict."""
    data = {
        "run_type": "backtest",
        "environment": "staging",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "start_date": "2024-01-01T00:00:00+00:00",
        "end_date": "2024-12-31T23:59:59+00:00",
        "initial_capital": "10000.00",
        "strategy_config": {"param": "value"},
        "weights_set_id": 42,
        "weights": {"ema": 0.15},
        "exchange": "binance",
        "testnet": False,
        "metadata": {"key": "value"},
    }

    config = RunConfig.from_dict(data)

    assert config.run_type == RunType.BACKTEST
    assert config.environment == RunEnvironment.STAGING
    assert config.symbol == "BTCUSDT"
    assert config.initial_capital == Decimal("10000.00")
    assert config.weights_set_id == 42
    assert config.testnet is False


def test_run_config_roundtrip():
    """Test RunConfig serialization roundtrip."""
    original = RunConfig(
        run_type=RunType.PAPER,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="5m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
        initial_capital=Decimal("25000.50"),
        strategy_config={"test": True},
        weights={"ema": 0.1, "macd": 0.2, "rsi": 0.3},
    )

    # Serialize and deserialize
    data = original.to_dict()
    restored = RunConfig.from_dict(data)

    assert restored.run_type == original.run_type
    assert restored.environment == original.environment
    assert restored.symbol == original.symbol
    assert restored.initial_capital == original.initial_capital
    assert restored.weights == original.weights


# ==========================================
# RunResult
# ==========================================


def test_run_result_creation():
    """Test RunResult creation."""
    result = RunResult(
        total_trades=150,
        winning_trades=90,
        losing_trades=60,
        win_rate=60.0,
        total_pnl=Decimal("1523.45"),
        total_return_pct=15.23,
        final_capital=Decimal("11523.45"),
        sharpe_ratio=1.85,
        sortino_ratio=2.20,
        max_drawdown=Decimal("450.00"),
        max_drawdown_pct=4.5,
        profit_factor=1.75,
        exposure_time_pct=65.5,
        buy_hold_return_pct=12.0,
        excess_return_pct=3.23,
        metrics={"custom_metric": 42},
    )

    assert result.total_trades == 150
    assert result.win_rate == 60.0
    assert result.total_pnl == Decimal("1523.45")
    assert result.sharpe_ratio == 1.85
    assert result.metrics["custom_metric"] == 42


def test_run_result_defaults():
    """Test RunResult default values."""
    result = RunResult()

    assert result.total_trades == 0
    assert result.win_rate == 0.0
    assert result.total_pnl == Decimal("0")
    assert result.sharpe_ratio == 0.0
    assert result.error_message is None
    assert result.metrics == {}


def test_run_result_with_error():
    """Test RunResult with error information."""
    result = RunResult(
        error_message="Division by zero",
        error_traceback="Traceback: ...",
    )

    assert result.error_message == "Division by zero"
    assert result.error_traceback is not None


def test_run_result_to_dict():
    """Test RunResult serialization."""
    result = RunResult(
        total_trades=50,
        total_pnl=Decimal("750.25"),
        sharpe_ratio=1.5,
        metrics={"test": "value"},
    )

    result_dict = result.to_dict()

    assert result_dict["total_trades"] == 50
    assert result_dict["total_pnl"] == "750.25"
    assert result_dict["sharpe_ratio"] == 1.5
    assert result_dict["metrics"]["test"] == "value"


def test_run_result_from_dict():
    """Test RunResult deserialization."""
    data = {
        "total_trades": 100,
        "winning_trades": 60,
        "losing_trades": 40,
        "win_rate": 60.0,
        "total_pnl": "1200.50",
        "total_return_pct": 12.0,
        "final_capital": "11200.50",
        "sharpe_ratio": 1.8,
        "sortino_ratio": 2.1,
        "max_drawdown": "300.00",
        "max_drawdown_pct": 3.0,
        "profit_factor": 1.6,
        "exposure_time_pct": 70.0,
        "buy_hold_return_pct": 10.0,
        "excess_return_pct": 2.0,
        "error_message": None,
        "error_traceback": None,
        "metrics": {"key": "value"},
    }

    result = RunResult.from_dict(data)

    assert result.total_trades == 100
    assert result.total_pnl == Decimal("1200.50")
    assert result.sharpe_ratio == 1.8


def test_run_result_roundtrip():
    """Test RunResult serialization roundtrip."""
    original = RunResult(
        total_trades=75,
        winning_trades=50,
        losing_trades=25,
        win_rate=66.67,
        total_pnl=Decimal("999.99"),
        sharpe_ratio=2.0,
    )

    data = original.to_dict()
    restored = RunResult.from_dict(data)

    assert restored.total_trades == original.total_trades
    assert restored.total_pnl == original.total_pnl
    assert restored.sharpe_ratio == original.sharpe_ratio


# ==========================================
# Run
# ==========================================


def test_run_creation():
    """Test Run dataclass creation."""
    now = datetime.now(timezone.utc)

    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.COMPLETED,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        config_snapshot={"test": "config"},
        result={"total_trades": 100},
        created_at=now,
        started_at=now,
        completed_at=now,
        weights_set_id=42,
        optuna_study_id=10,
    )

    assert run.id == 1
    assert run.run_type == RunType.BACKTEST
    assert run.status == RunStatus.COMPLETED
    assert run.weights_set_id == 42


def test_run_string_enum_conversion():
    """Test Run converts string enums to Enum instances."""
    now = datetime.now(timezone.utc)

    run = Run(
        id=1,
        run_type="backtest",  # String, not enum
        status="running",  # String, not enum
        environment="prod",  # String, not enum
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=now,
        end_date=now,
        config_snapshot={},
        result=None,
        created_at=now,
        started_at=now,
        completed_at=None,
    )

    # Should be converted to enums
    assert isinstance(run.run_type, RunType)
    assert isinstance(run.status, RunStatus)
    assert isinstance(run.environment, RunEnvironment)
    assert run.run_type == RunType.BACKTEST
    assert run.status == RunStatus.RUNNING
    assert run.environment == RunEnvironment.PROD


def test_run_duration_calculation():
    """Test run duration calculation."""
    started = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    completed = datetime(2024, 1, 1, 10, 5, 30, tzinfo=timezone.utc)

    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.COMPLETED,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=started,
        end_date=completed,
        config_snapshot={},
        result=None,
        created_at=started,
        started_at=started,
        completed_at=completed,
    )

    assert run.duration_seconds == 330.0  # 5 minutes 30 seconds


def test_run_duration_none_when_not_completed():
    """Test duration is None when run not completed."""
    now = datetime.now(timezone.utc)

    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.RUNNING,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=now,
        end_date=now,
        config_snapshot={},
        result=None,
        created_at=now,
        started_at=now,
        completed_at=None,  # Not completed yet
    )

    assert run.duration_seconds is None


def test_run_is_terminal():
    """Test terminal status detection."""
    now = datetime.now(timezone.utc)

    # Terminal statuses
    for status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]:
        run = Run(
            id=1,
            run_type=RunType.BACKTEST,
            status=status,
            environment=RunEnvironment.DEV,
            symbol="BTCUSDT",
            timeframe="15m",
            start_date=now,
            end_date=now,
            config_snapshot={},
            result=None,
            created_at=now,
            started_at=now,
            completed_at=now,
        )
        assert run.is_terminal

    # Non-terminal statuses
    for status in [RunStatus.PENDING, RunStatus.RUNNING]:
        run = Run(
            id=1,
            run_type=RunType.BACKTEST,
            status=status,
            environment=RunEnvironment.DEV,
            symbol="BTCUSDT",
            timeframe="15m",
            start_date=now,
            end_date=now,
            config_snapshot={},
            result=None,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        assert not run.is_terminal


def test_run_get_config():
    """Test parsing config snapshot."""
    config_dict = {
        "run_type": "backtest",
        "environment": "dev",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "start_date": "2024-01-01T00:00:00+00:00",
        "end_date": "2024-12-31T23:59:59+00:00",
        "initial_capital": "10000",
        "strategy_config": {},
        "exchange": "binance",
        "testnet": True,
        "metadata": {},
    }

    now = datetime.now(timezone.utc)
    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.COMPLETED,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=now,
        end_date=now,
        config_snapshot=config_dict,
        result=None,
        created_at=now,
        started_at=now,
        completed_at=now,
    )

    config = run.get_config()
    assert isinstance(config, RunConfig)
    assert config.symbol == "BTCUSDT"
    assert config.initial_capital == Decimal("10000")


def test_run_get_result():
    """Test parsing result."""
    result_dict = {
        "total_trades": 100,
        "winning_trades": 60,
        "losing_trades": 40,
        "win_rate": 60.0,
        "total_pnl": "500.00",
        "total_return_pct": 5.0,
        "final_capital": "10500.00",
        "sharpe_ratio": 1.5,
        "sortino_ratio": 1.8,
        "max_drawdown": "200.00",
        "max_drawdown_pct": 2.0,
        "profit_factor": 1.5,
        "exposure_time_pct": 60.0,
        "buy_hold_return_pct": 4.0,
        "excess_return_pct": 1.0,
        "metrics": {},
    }

    now = datetime.now(timezone.utc)
    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.COMPLETED,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=now,
        end_date=now,
        config_snapshot={},
        result=result_dict,
        created_at=now,
        started_at=now,
        completed_at=now,
    )

    result = run.get_result()
    assert isinstance(result, RunResult)
    assert result.total_trades == 100
    assert result.sharpe_ratio == 1.5


def test_run_get_result_none():
    """Test getting result when None."""
    now = datetime.now(timezone.utc)
    run = Run(
        id=1,
        run_type=RunType.BACKTEST,
        status=RunStatus.RUNNING,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        start_date=now,
        end_date=now,
        config_snapshot={},
        result=None,
        created_at=now,
        started_at=now,
        completed_at=None,
    )

    assert run.get_result() is None


# ==========================================
# RunFilter
# ==========================================


def test_run_filter_creation():
    """Test RunFilter creation."""
    filter = RunFilter(
        run_type=RunType.BACKTEST,
        status=RunStatus.COMPLETED,
        environment=RunEnvironment.DEV,
        symbol="BTCUSDT",
        timeframe="15m",
        limit=50,
        offset=10,
    )

    assert filter.run_type == RunType.BACKTEST
    assert filter.status == RunStatus.COMPLETED
    assert filter.limit == 50
    assert filter.offset == 10


def test_run_filter_defaults():
    """Test RunFilter default values."""
    filter = RunFilter()

    assert filter.run_type is None
    assert filter.status is None
    assert filter.limit == 100
    assert filter.offset == 0


def test_run_filter_to_sql_conditions_empty():
    """Test SQL generation with no filters."""
    filter = RunFilter()
    conditions, params = filter.to_sql_conditions()

    assert conditions == []
    assert params == {}


def test_run_filter_to_sql_conditions_single():
    """Test SQL generation with single filter."""
    filter = RunFilter(run_type=RunType.BACKTEST)
    conditions, params = filter.to_sql_conditions()

    assert len(conditions) == 1
    assert "run_type = :run_type" in conditions
    assert params["run_type"] == "backtest"


def test_run_filter_to_sql_conditions_multiple():
    """Test SQL generation with multiple filters."""
    created_after = datetime(2024, 1, 1, tzinfo=timezone.utc)

    filter = RunFilter(
        run_type=RunType.OPTIMIZATION,
        status=RunStatus.COMPLETED,
        symbol="ETHUSDT",
        created_after=created_after,
    )
    conditions, params = filter.to_sql_conditions()

    assert len(conditions) == 4
    assert "run_type = :run_type" in conditions
    assert "status = :status" in conditions
    assert "symbol = :symbol" in conditions
    assert "created_at >= :created_after" in conditions

    assert params["run_type"] == "optimization"
    assert params["status"] == "completed"
    assert params["symbol"] == "ETHUSDT"
    assert params["created_after"] == created_after


def test_run_filter_with_date_range():
    """Test filter with date range."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)

    filter = RunFilter(created_after=start, created_before=end)
    conditions, params = filter.to_sql_conditions()

    assert "created_at >= :created_after" in conditions
    assert "created_at <= :created_before" in conditions
    assert params["created_after"] == start
    assert params["created_before"] == end


def test_run_filter_with_foreign_keys():
    """Test filter with foreign key references."""
    filter = RunFilter(weights_set_id=42, optuna_study_id=10)
    conditions, params = filter.to_sql_conditions()

    assert "weights_set_id = :weights_set_id" in conditions
    assert "optuna_study_id = :optuna_study_id" in conditions
    assert params["weights_set_id"] == 42
    assert params["optuna_study_id"] == 10
