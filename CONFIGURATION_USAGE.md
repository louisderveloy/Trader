# Configuration System - Complete Implementation

## Overview

The bot now uses **database-driven configuration** for ALL operations. Configuration is stored in the `config` table and loaded at runtime by all components.

---

## Configuration Table Structure

```sql
Table: config
├── id (UUID, primary key)
├── config (JSONB) - Complete configuration as JSON blob
├── created_at (timestamp with time zone)
└── updated_at (timestamp with time zone)
```

The system loads the **most recent** entry (sorted by `updated_at DESC`) and preserves full audit history.

---

## Configuration Categories

The configuration JSON contains 5 main categories:

### 1. Strategy Configuration
- `entry_threshold` (float, -1.0 to 1.0): Weighted score threshold to enter a position
- `exit_threshold` (float, -1.0 to 1.0): Weighted score threshold to exit a position
- `confirmation_candles` (int, ≥1): Number of consecutive candles required to confirm a signal

### 2. Risk Management
- `max_trades_per_day` (int, ≥1): Maximum number of trades allowed per day
- `max_exposure_percent` (float, 0-100): Maximum % of capital exposed simultaneously
- `position_size_mode` (string): "fixed", "confidence", or "risk_atr"
- `fixed_size_percent` (float, 0-100): Fixed position size as % of total capital (if mode=fixed)
- `atr_multiplier` (float, >0): ATR multiplier for sizing (if mode=risk_atr)
- `capital_risk_percent` (float, 0-100): % capital to risk per trade (if mode=risk_atr)

### 3. Stop-Loss Configuration
- `mode` (string): "atr" or "fixed"
- `atr_multiplier` (float, >0): ATR multiplier for stop-loss (if mode=atr)
- `fixed_percent` (float, 0-100): Fixed % loss (if mode=fixed)

### 4. Take-Profit Configuration
- `mode` (string): "atr" or "fixed"
- `atr_multiplier` (float, >0): ATR multiplier for take-profit (if mode=atr)
- `fixed_percent` (float, 0-100): Fixed % gain (if mode=fixed)

### 5. Cooldown Configuration
- `after_trade_seconds` (int, ≥0): Cooldown period after closing a trade

---

## How Each Command Uses Configuration

### ✅ `config create` - Interactive Configuration Creator
**Status**: Fully implemented
**Configuration Usage**: Creates and saves configuration to database

**Example**:
```bash
docker compose exec bot python -m main config create
```

**What it does**:
1. Prompts for ALL parameters with tooltips
2. Validates input (ranges, choices)
3. Compares with current config (skips if identical)
4. Saves to database

---

### ✅ `paper` - Paper Trading
**Status**: Fully implemented
**Configuration Usage**: Loads config from database on startup

**Example**:
```bash
docker compose exec bot python -m main paper --symbol BTCUSDT
```

**What it does**:
1. Calls `StrategyEngineConfig.from_db(db_pool)` on startup
2. Uses `config.strategy.entry_threshold` for buy signals
3. Uses `config.strategy.exit_threshold` for sell signals
4. Uses `config.strategy.confirmation_candles` for anti-repainting
5. Uses `config.risk.*` for position sizing and limits
6. Uses `config.stop_loss.*` and `config.take_profit.*` for exits
7. Uses `config.cooldown.after_trade_seconds` for post-trade cooldown

**Files modified**:
- `bot/scripts/trading.py:134-141` - Added `_load_config()` method
- `bot/scripts/trading.py:523-543` - Uses `self.config.strategy.*` and `self.config.risk.*`

---

### ✅ `live` - Live Trading
**Status**: Fully implemented
**Configuration Usage**: Same as paper trading

**Example**:
```bash
docker compose exec bot python -m main live --symbol BTCUSDT --testnet
```

**What it does**: Identical to paper trading (shares same code path)

---

### ✅ `backtest` - Backtesting
**Status**: Fully implemented
**Configuration Usage**: Loads config from database before running backtest

**Example**:
```bash
docker compose exec bot python -m main backtest \
  --symbol BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2024-06-01 \
  --save
```

**What it does**:
1. Loads `StrategyEngineConfig.from_db(db_pool)` in `run_backtest_cli()`
2. Injects thresholds into `BacktestConfig.strategy_params`:
   ```python
   strategy_params={
       "weights": weights,
       "entry_threshold": strategy_config.strategy.entry_threshold,
       "exit_threshold": strategy_config.strategy.exit_threshold,
       "confirmation_candles": strategy_config.strategy.confirmation_candles,
   }
   ```
3. Backtester uses these thresholds for signal generation

**Files modified**:
- `bot/scripts/backtest.py:38` - Import `StrategyEngineConfig`
- `bot/scripts/backtest.py:130` - Added `strategy_config` parameter
- `bot/scripts/backtest.py:165-174` - Inject thresholds into `strategy_params`
- `bot/scripts/backtest.py:338-349` - Load config in CLI

---

### ✅ `optimize` - Optuna Optimization
**Status**: Fully implemented
**Configuration Usage**: Loads config from database and uses for ALL trials

**Example**:
```bash
docker compose exec bot python -m main optimize run \
  --study-name btc_2024 \
  --n-trials 100 \
  --n-splits 4
```

**What it does**:
1. `OptimizationRunner._load_strategy_config()` loads config on startup
2. Passes `strategy_config` to `ObjectiveFunction`
3. **Every Optuna trial** uses database thresholds:
   ```python
   strategy_params={
       "weights": trial_weights,
       "entry_threshold": strategy_config.strategy.entry_threshold,
       "exit_threshold": strategy_config.strategy.exit_threshold,
       "confirmation_candles": strategy_config.strategy.confirmation_candles,
   }
   ```
4. Both training AND test evaluations use same thresholds

**Files modified**:
- `bot/optimization/runner.py:35` - Import `StrategyEngineConfig`
- `bot/optimization/runner.py:76` - Added `strategy_config` field
- `bot/optimization/runner.py:147` - Load config before optimization
- `bot/optimization/runner.py:283-297` - `_load_strategy_config()` method
- `bot/optimization/runner.py:168-171` - Pass `strategy_config` to `evaluate_weights`
- `bot/optimization/runner.py:348-353` - Pass `strategy_config` to `create_objective_function`
- `bot/optimization/objective.py:26` - Import `StrategyEngineConfig`
- `bot/optimization/objective.py:48` - Added `strategy_config` parameter
- `bot/optimization/objective.py:160-173` - Inject thresholds into backtest config
- `bot/optimization/objective.py:299` - Added `strategy_config` parameter to `evaluate_weights`
- `bot/optimization/objective.py:327-335` - Inject thresholds in `evaluate_weights`

---

### ❌ `fetch` - Historical Data Fetching
**Status**: N/A
**Configuration Usage**: None (does not need trading configuration)

**Example**:
```bash
docker compose exec bot python -m main fetch \
  --symbol BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

---

### ❌ `status` - System Health Check
**Status**: N/A
**Configuration Usage**: None (only checks services)

**Example**:
```bash
docker compose exec bot python -m main status
```

---

## Configuration Loading Strategy

### Where Config is Loaded

| Component | Load Timing | Method |
|-----------|-------------|--------|
| Trading Bot (paper/live) | On startup | `TradingBot._load_config()` |
| Backtest Script | Before backtest | `run_backtest_cli()` |
| Optimization Runner | Before optimization | `OptimizationRunner._load_strategy_config()` |
| API Endpoints | On API startup | `apply_db_config_to_settings()` |

### Error Handling

All components throw a **clear error** if no configuration exists:

```
ValueError: No configuration found in database.
Please create a config first using 'python -m main config create'
```

This ensures users cannot run the bot without proper configuration.

---

## Configuration Flow Diagram

```
┌─────────────────────────────────────┐
│ python -m main config create        │
│ (Interactive wizard)                │
└─────────────────┬───────────────────┘
                  │
                  ▼
          ┌───────────────┐
          │ config table  │ ← Most recent entry (ORDER BY updated_at DESC)
          │ (PostgreSQL)  │
          └───────┬───────┘
                  │
        ┌─────────┴─────────┬──────────────────┬────────────────┐
        │                   │                  │                │
        ▼                   ▼                  ▼                ▼
┌──────────────┐    ┌──────────────┐   ┌──────────────┐  ┌──────────────┐
│ Paper/Live   │    │ Backtest     │   │ Optimize     │  │ API          │
│ Trading      │    │              │   │              │  │ (FastAPI)    │
└──────────────┘    └──────────────┘   └──────────────┘  └──────────────┘
     │                    │                   │                 │
     ▼                    ▼                   ▼                 ▼
Uses entry/exit     Uses entry/exit     Uses entry/exit    Exposes config
thresholds for      thresholds for      thresholds for     via REST API
signal generation   signal generation   ALL trials         for dashboard
```

---

## Verification Checklist

### ✅ Completed
- [x] Database config loading in trading bot
- [x] Database config loading in backtest script
- [x] Database config loading in optimization runner
- [x] Interactive config creation wizard
- [x] Config validation (ranges, constraints)
- [x] Audit trail (history preservation)
- [x] Deduplication (skip identical configs)
- [x] Error handling (no config = clear error)
- [x] All thresholds injected into backtester
- [x] Optimization uses DB thresholds for ALL trials
- [x] CLI integration (`python -m main config create`)

### Configuration Coverage
- [x] Entry threshold (buy signals)
- [x] Exit threshold (sell signals)
- [x] Confirmation candles (anti-repainting)
- [x] Max trades per day
- [x] Max exposure percent
- [x] Position sizing mode
- [x] Stop-loss configuration
- [x] Take-profit configuration
- [x] Cooldown configuration

---

## Migration Guide

### Before (Hardcoded)
```python
# Old: Hardcoded in code
entry_threshold = 0.3
exit_threshold = -0.2
```

### After (Database-Driven)
```python
# New: Loaded from database
config = await StrategyEngineConfig.from_db(db_pool)
entry_threshold = config.strategy.entry_threshold
exit_threshold = config.strategy.exit_threshold
```

---

## Example Configuration JSON

```json
{
  "strategy": {
    "entry_threshold": 0.6,
    "exit_threshold": -0.3,
    "confirmation_candles": 2
  },
  "risk": {
    "max_trades_per_day": 5,
    "max_exposure_percent": 30.0,
    "position_size_mode": "confidence",
    "fixed_size_percent": 10.0,
    "atr_multiplier": 2.0,
    "capital_risk_percent": 1.0
  },
  "stop_loss": {
    "mode": "atr",
    "atr_multiplier": 2.0,
    "fixed_percent": 2.0
  },
  "take_profit": {
    "mode": "atr",
    "atr_multiplier": 3.0,
    "fixed_percent": 4.0
  },
  "cooldown": {
    "after_trade_seconds": 3600
  }
}
```

---

## Testing Commands

```bash
# 1. Create configuration (REQUIRED FIRST)
docker compose exec bot python -m main config create

# 2. Verify configuration loaded in backtest
docker compose exec bot python -m main backtest \
  --symbol BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2024-03-01

# 3. Verify configuration loaded in optimization
docker compose exec bot python -m main optimize run \
  --study-name test_config \
  --n-trials 5 \
  --n-splits 2

# 4. Verify configuration loaded in paper trading
docker compose exec bot python -m main paper --symbol BTCUSDT
# (Ctrl+C after verifying it starts without errors)
```

---

## Conclusion

**All bot operations now use database configuration**. The hardcoded thresholds (0.05, -0.05) are **no longer used**. Every component loads configuration from the database on startup and uses the configured thresholds for decision-making.

The system is **production-ready** with proper error handling, validation, and audit trail preservation.
