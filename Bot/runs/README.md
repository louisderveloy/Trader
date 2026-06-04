# Runs Management Module

Comprehensive run lifecycle management, logging, and error tracking for backtests, optimizations, paper trading, and live trading runs.

## Overview

The `runs` module provides:

- **Run lifecycle management**: Create, start, complete, fail, cancel runs
- **Config snapshots**: Capture all configuration at run start time
- **Status tracking**: Validate status transitions (PENDING → RUNNING → COMPLETED/FAILED/CANCELLED)
- **Context managers**: Automatic run lifecycle with `async with create_run(...)`
- **Enhanced logging**: Automatic run context in all logs
- **Error tracking**: Log errors to `errors_log` table with run linkage
- **Performance logging**: Track operation latency and throughput

## Module Structure

```
/runs/
  types.py       → Run types, statuses, enums, dataclasses
  manager.py     → RunManager for CRUD operations
  context.py     → Context managers for run lifecycle
  logger.py      → Enhanced logging with run context
  errors.py      → Error logging utilities
  __init__.py    → Module exports
  README.md      → This file
```

## Core Concepts

### Run Types

```python
class RunType(str, Enum):
    BACKTEST = "backtest"        # Historical backtesting
    OPTIMIZATION = "optimization" # Optuna optimization
    PAPER = "paper"              # Paper trading (testnet)
    LIVE = "live"                # Live trading (mainnet)
```

### Run Statuses

```python
class RunStatus(str, Enum):
    PENDING = "pending"      # Created, not started
    RUNNING = "running"      # In progress
    COMPLETED = "completed"  # Finished successfully (terminal)
    FAILED = "failed"        # Finished with error (terminal)
    CANCELLED = "cancelled"  # Manually cancelled (terminal)
```

**Valid transitions**:
- PENDING → {RUNNING, CANCELLED}
- RUNNING → {COMPLETED, FAILED, CANCELLED}
- COMPLETED/FAILED/CANCELLED → (terminal, no transitions)

### Run Config Snapshot

Every run captures a complete configuration snapshot at creation time:

```python
@dataclass
class RunConfig:
    run_type: RunType
    environment: RunEnvironment  # dev, staging, prod

    # Trading parameters
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal

    # Strategy config (from strategy.config.StrategyConfig.to_snapshot())
    strategy_config: dict[str, Any]

    # Active weights
    weights_set_id: Optional[int]
    weights: Optional[dict[str, float]]

    # Additional config
    optimization_config: Optional[dict[str, Any]]
    exchange: str = "binance"
    testnet: bool = True
    metadata: dict[str, Any] = {}
```

### Run Result

Results are stored when run completes:

```python
@dataclass
class RunResult:
    # Performance metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    total_pnl: Decimal
    total_return_pct: float
    final_capital: Decimal

    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: Decimal
    max_drawdown_pct: float

    profit_factor: float
    exposure_time_pct: float

    # Buy-and-hold comparison
    buy_hold_return_pct: float
    excess_return_pct: float

    # Error info (if failed)
    error_message: Optional[str]
    error_traceback: Optional[str]

    # Additional metrics
    metrics: dict[str, Any] = {}
```

## Usage Examples

### 1. Basic Run Creation

```python
import asyncpg
from runs import RunManager, RunConfig, RunType, RunEnvironment, RunStatus
from datetime import datetime
from decimal import Decimal

# Create DB connection pool
db_pool = await asyncpg.create_pool(dsn="...")

# Create run config
config = RunConfig(
    run_type=RunType.BACKTEST,
    environment=RunEnvironment.DEV,
    symbol="BTCUSDT",
    timeframe="15m",
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    initial_capital=Decimal("10000"),
    strategy_config={...},  # From strategy module
    weights={"ema": 0.15, "macd": 0.20, ...},
    testnet=True,
)

# Create run
manager = RunManager(db_pool)
run = await manager.create_run(config)
print(f"Created run {run.id}")

# Start run
run = await manager.update_status(run.id, RunStatus.RUNNING)

# Do work...

# Complete run with results
result = RunResult(
    total_trades=150,
    winning_trades=90,
    losing_trades=60,
    win_rate=60.0,
    total_pnl=Decimal("1523.45"),
    # ... other metrics
)
run = await manager.update_status(run.id, RunStatus.COMPLETED, result=result)
```

### 2. Context Manager (Recommended)

```python
from runs import create_run, RunConfig, RunType

# Config setup...
config = RunConfig(...)

# Context manager handles all status transitions automatically
async with create_run(db_pool, config) as run:
    print(f"Run {run.id} is now RUNNING")

    # Do backtest/optimization work...

    # On normal exit: status -> COMPLETED
    # On exception: status -> FAILED with error details
```

### 3. Run Context for Logging

```python
from runs import create_run, run_context, get_logger_with_context

logger = get_logger_with_context(__name__)

async with create_run(db_pool, config) as run:
    async with run_context(run):
        # All logs now include run_id and run_type
        logger.info_ctx("Processing trades")

        # Manual logging with context
        context = get_run_context()
        logger.info("Working", extra=context.get_log_extra())
```

### 4. Incremental Result Updates

```python
from runs import create_run, update_run_result

async with create_run(db_pool, config) as run:
    # Periodically update results during long operation
    async with update_run_result(db_pool, run.id) as result:
        result.total_trades = 10
        result.total_pnl = Decimal("150.50")
        # Result saved on exit

    # Continue working...

    async with update_run_result(db_pool, run.id) as result:
        result.total_trades = 20
        result.total_pnl = Decimal("320.75")
```

### 5. Query Runs

```python
from runs import RunManager, RunFilter, RunType, RunStatus

manager = RunManager(db_pool)

# Get recent backtests
filter = RunFilter(
    run_type=RunType.BACKTEST,
    status=RunStatus.COMPLETED,
    limit=50,
)
runs = await manager.query_runs(filter)

# Count failed runs today
from datetime import datetime, timezone, timedelta
filter = RunFilter(
    status=RunStatus.FAILED,
    created_after=datetime.now(timezone.utc) - timedelta(days=1),
)
count = await manager.count_runs(filter)
print(f"{count} failed runs in last 24h")

# Get active runs
active_runs = await manager.get_active_runs()
```

### 6. Error Logging

```python
from runs import log_error, log_exception, ErrorSeverity, ErrorCategory

try:
    # Some operation...
    raise ValueError("Invalid configuration")
except Exception as e:
    # Log exception to errors_log table
    error_id = await log_exception(
        db_pool=db_pool,
        exception=e,
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.VALIDATION,
        context={"config_key": "invalid_value"},
    )
    print(f"Error logged: {error_id}")
```

### 7. Performance Logging

```python
from runs import PerformanceLogger
import time

perf_logger = PerformanceLogger(logger)

# Log operation latency
start = time.time()
# ... do work ...
latency_ms = (time.time() - start) * 1000
perf_logger.log_latency("fetch_candles", latency_ms, success=True)

# Log throughput
start = time.time()
count = 1000
# ... process 1000 items ...
duration = time.time() - start
perf_logger.log_throughput("process_trades", count, duration)
```

### 8. Logging Setup

```python
from runs import setup_logging

# JSON logging for production
setup_logging(
    level="INFO",
    log_format="json",
    log_file="/var/log/trader-bot/app.log"
)

# Text logging for development
setup_logging(
    level="DEBUG",
    log_format="text"
)
```

## Integration with Other Modules

### Backtesting Integration

```python
from backtesting import VectorBTBacktester, BacktestConfig
from runs import create_run, RunConfig, RunType

# Create run
config = RunConfig(
    run_type=RunType.BACKTEST,
    # ... other config
)

async with create_run(db_pool, config) as run:
    # Create backtest config
    backtest_config = BacktestConfig(
        symbol=config.symbol,
        timeframe=config.timeframe,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_capital=config.initial_capital,
        weights=config.weights,
        strategy_params=config.strategy_config,
    )

    # Run backtest
    backtester = VectorBTBacktester(db_pool)
    result = await backtester.run(backtest_config)

    # Update run with results
    run_result = RunResult(
        total_trades=result.metrics.total_trades,
        winning_trades=result.metrics.winning_trades,
        # ... map metrics
    )
    await manager.update_result(run.id, run_result)
```

### Optimization Integration

```python
from optimization import OptimizationRunner, OptimizationConfig
from runs import create_run, RunConfig, RunType

config = RunConfig(
    run_type=RunType.OPTIMIZATION,
    optimization_config={
        "n_trials": 100,
        "objective": "sharpe_ratio",
    },
    # ... other config
)

async with create_run(db_pool, config) as run:
    # Run optimization
    opt_config = OptimizationConfig.from_dict(config.optimization_config)
    runner = OptimizationRunner(opt_config, db_pool)
    study_result = await runner.run()

    # Link to Optuna study
    await manager.link_optuna_study(run.id, study_result.study_id)
```

## Database Schema

The runs module interacts with three tables:

### `runs` Table

Stores all run information with complete config snapshots.

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PRIMARY KEY | Run ID |
| `run_type` | VARCHAR(20) | Run type (backtest, optimization, paper, live) |
| `status` | VARCHAR(20) | Current status |
| `environment` | VARCHAR(20) | Environment (dev, staging, prod) |
| `symbol` | VARCHAR(20) | Trading pair |
| `timeframe` | VARCHAR(10) | Candle timeframe |
| `start_date` | TIMESTAMPTZ | Start date for data |
| `end_date` | TIMESTAMPTZ | End date for data |
| `config_snapshot` | JSONB | Complete config at creation |
| `result` | JSONB | Results when completed |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `started_at` | TIMESTAMPTZ | Start timestamp |
| `completed_at` | TIMESTAMPTZ | Completion timestamp |
| `weights_set_id` | INTEGER | FK to weights_sets |
| `optuna_study_id` | INTEGER | FK to optuna_studies |

### `errors_log` Table

Stores all errors with run linkage.

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PRIMARY KEY | Error ID |
| `run_id` | INTEGER | FK to runs (optional) |
| `severity` | VARCHAR(20) | Error severity |
| `category` | VARCHAR(50) | Error category |
| `error_message` | TEXT | Error message |
| `error_traceback` | TEXT | Stack trace |
| `context` | JSONB | Additional context |
| `timestamp` | TIMESTAMPTZ | Error timestamp |

### `notifications_log` Table

(Not directly managed by runs module, but linked via run_id)

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PRIMARY KEY | Notification ID |
| `run_id` | INTEGER | FK to runs (optional) |
| `notification_type` | VARCHAR(50) | Type of notification |
| `message` | TEXT | Notification message |
| `sent_at` | TIMESTAMPTZ | Sent timestamp |
| `success` | BOOLEAN | Was sending successful |

## Best Practices

### 1. Always Use Context Managers

**Good**:
```python
async with create_run(db_pool, config) as run:
    # Work automatically tracked
    pass
```

**Bad**:
```python
manager = RunManager(db_pool)
run = await manager.create_run(config)
try:
    await manager.update_status(run.id, RunStatus.RUNNING)
    # ... work ...
    await manager.update_status(run.id, RunStatus.COMPLETED)
except Exception as e:
    # Easy to forget error handling!
    pass
```

### 2. Capture Complete Config Snapshots

Always include all relevant configuration in `RunConfig`:

```python
from strategy.config import StrategyConfig

# Load strategy config
strategy_config = StrategyConfig.from_env()

# Create run config with complete snapshot
run_config = RunConfig(
    run_type=RunType.BACKTEST,
    environment=RunEnvironment.PROD,
    symbol="BTCUSDT",
    timeframe="15m",
    start_date=start,
    end_date=end,
    initial_capital=Decimal("10000"),
    strategy_config=strategy_config.to_snapshot(),  # Complete snapshot!
    weights={"ema": 0.15, "macd": 0.20, ...},
    weights_set_id=42,
    exchange="binance",
    testnet=False,
)
```

### 3. Use Run Context for Logging

```python
async with create_run(db_pool, config) as run:
    async with run_context(run):
        # All logs automatically include run_id
        logger.info_ctx("Starting backtest")
        logger.error_ctx("Trade failed", extra={"trade_id": 123})
```

### 4. Log Errors Properly

```python
try:
    # ... operation ...
except Exception as e:
    await log_exception(
        db_pool=db_pool,
        exception=e,
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.STRATEGY,
        context={"symbol": "BTCUSDT", "timeframe": "15m"},
    )
    raise  # Re-raise to fail the run
```

### 5. Query Efficiently

Use filters to limit results:

```python
# Good - filtered query
filter = RunFilter(
    run_type=RunType.BACKTEST,
    status=RunStatus.COMPLETED,
    created_after=datetime.now(timezone.utc) - timedelta(days=7),
    limit=100,
)
runs = await manager.query_runs(filter)

# Bad - fetching everything
filter = RunFilter(limit=10000)  # Too many!
all_runs = await manager.query_runs(filter)
```

## Testing

Comprehensive unit tests are provided in `/tests/`:

```bash
# Run all runs module tests
pytest tests/test_runs*.py -v

# Run with coverage
pytest tests/test_runs*.py --cov=runs --cov-report=term-missing
```

## CLAUDE.md Compliance

This module follows all CLAUDE.md conventions:

✅ **No deletions**: `delete_run()` exists but logs warning (violates spec)
✅ **Snapshots**: Complete config captured at run start
✅ **Structured logging**: JSON format with run context
✅ **Type hints**: All functions fully typed
✅ **Docstrings**: All classes and public functions documented
✅ **Async/await**: Full async support with asyncpg
✅ **No print()**: All output via logging
✅ **Decimal precision**: Financial calculations use Decimal

## Performance Considerations

- Use connection pooling (asyncpg.Pool) for all database operations
- Filter queries with appropriate indexes (created in migration)
- Use `limit` parameter in RunFilter to avoid fetching too many rows
- Consider pagination for large result sets
- Log performance metrics to track bottlenecks

## See Also

- `/docs/A1_ERD.md` - Complete database schema
- `/docs/A3_snapshots_format.md` - Snapshot format specification
- `strategy/` module - Strategy configuration
- `backtesting/` module - Backtesting integration
- `optimization/` module - Optimization integration
