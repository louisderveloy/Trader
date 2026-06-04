# Strategy Engine

Core strategy engine for the crypto trading bot, implementing weighted scoring, position sizing, risk management, and stop-loss/take-profit logic.

## Overview

The strategy engine is the decision-making core of the bot. It:

1. **Weighted Scoring**: Combines normalized indicator signals using optimized weights
2. **Anti-Repainting**: Confirms signals over multiple candles before acting
3. **Position Sizing**: Three modes (fixed, confidence-based, risk-based ATR)
4. **Risk Management**: Enforces quotas, exposure limits, and cooldowns
5. **Stop-Loss/Take-Profit**: Calculates exit levels (ATR-based or fixed percentage)
6. **Decision Logging**: Records complete snapshots for transparency and debugging

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      StrategyEngine                         │
│  • Load active weights from weights_sets table              │
│  • Calculate weighted score from indicator signals          │
│  • Check entry/exit thresholds                              │
│  • Manage anti-repainting confirmation state                │
│  • Create TradingDecision with complete snapshots           │
└──────────────┬──────────────────────────────────────────────┘
               │
               ├─► PositionSizer (sizing.py)
               │   • Fixed: constant USDT amount
               │   • Confidence: proportional to score
               │   • Risk ATR: based on ATR and % capital to risk
               │
               ├─► StopLossCalculator (stops.py)
               │   • ATR-based: entry_price - (ATR × multiplier)
               │   • Fixed: entry_price × (1 - percent/100)
               │
               ├─► TakeProfitCalculator (stops.py)
               │   • ATR-based: entry_price + (ATR × multiplier)
               │   • Fixed: entry_price × (1 + percent/100)
               │
               └─► RiskManager (risk.py)
                   • Track daily trades
                   • Check exposure limits
                   • Enforce cooldown periods
```

## Modules

### `types.py`
Core type definitions:
- `DecisionType`: ENTRY_LONG, EXIT, SKIP
- `PositionSizeMode`: FIXED, CONFIDENCE, RISK_ATR
- `StopLossMode`, `TakeProfitMode`: ATR, FIXED
- `TradingDecision`: Complete decision with snapshots
- `WeightsSnapshot`, `IndicatorSnapshot`: JSONB snapshots
- `ConfirmationState`: Anti-repainting state tracking
- `PositionState`: Current position tracking
- `RiskState`: Risk management state

### `config.py`
Configuration dataclasses:
- `StrategyConfig`: Entry/exit thresholds, confirmation candles
- `RiskConfig`: Quotas, exposure, sizing mode
- `StopLossConfig`, `TakeProfitConfig`: Exit level configuration
- `CooldownConfig`: Post-trade cooldown
- `StrategyEngineConfig`: Aggregate configuration with `from_env()` loader

### `sizing.py` (TODO: Phase 4)
Position sizing calculations:
- `calculate_position_size()`: Main sizing function
- Support for three modes: FIXED, CONFIDENCE, RISK_ATR

### `stops.py` (TODO: Phase 4)
Stop-loss and take-profit calculations:
- `calculate_stop_loss()`: Stop-loss price calculation
- `calculate_take_profit()`: Take-profit price calculation
- Support for ATR-based and fixed percentage modes

### `risk.py` (TODO: Phase 4)
Risk management:
- `RiskManager`: Quota and exposure tracking
- Integration with database to count daily trades
- Cooldown enforcement

### `engine.py` (TODO: Phase 4)
Core strategy engine:
- `StrategyEngine`: Main orchestrator
- Weighted scoring: Σ (signal_i × poids_i)
- Integration with weights_sets table
- Anti-repainting confirmation
- Complete decision logging with snapshots

## Usage Example

```python
from strategy import StrategyEngineConfig, StrategyEngine
from indicators import compute_all_indicators

# Load configuration from environment
config = StrategyEngineConfig.from_env()

# Initialize strategy engine
engine = StrategyEngine(
    config=config,
    run_id=current_run_id,
    db_pool=db_pool
)

# For each new candle...
candles = exchange.get_candles(symbol="BTCUSDT", timeframe="15m", limit=300)

# Compute all indicators
indicator_results = compute_all_indicators(candles, config)

# Make trading decision
decision = await engine.make_decision(
    candles=candles,
    indicator_results=indicator_results,
    current_price=candles[-1].close,
    current_time=candles[-1].timestamp
)

# Act on decision
if decision.decision_type == DecisionType.ENTRY_LONG:
    order = await exchange.place_limit_order(
        symbol=decision.symbol,
        side="buy",
        quantity=decision.position_size_qty,
        price=decision.entry_price
    )
elif decision.decision_type == DecisionType.EXIT:
    order = await exchange.place_market_order(
        symbol=decision.symbol,
        side="sell",
        quantity=current_position.quantity
    )
# SKIP: do nothing
```

## Configuration

All configuration is loaded from environment variables:

### Strategy
- `STRATEGY_ENTRY_THRESHOLD` (float, default: 0.6): Weighted score to enter position
- `STRATEGY_EXIT_THRESHOLD` (float, default: -0.3): Weighted score to exit position
- `STRATEGY_CONFIRMATION_CANDLES` (int, default: 2): Anti-repainting confirmation

### Risk Management
- `RISK_MAX_TRADES_PER_DAY` (int, default: 5): Max trades per day
- `RISK_MAX_EXPOSURE_PERCENT` (float, default: 30.0): Max % capital exposed
- `RISK_POSITION_SIZE_MODE` (enum, default: "confidence"): Sizing mode
- `RISK_FIXED_SIZE_USDT` (float, default: 100.0): Fixed size (FIXED mode)
- `RISK_ATR_MULTIPLIER` (float, default: 2.0): ATR multiplier (RISK_ATR mode)
- `RISK_CAPITAL_RISK_PERCENT` (float, default: 1.0): % capital to risk (RISK_ATR mode)

### Stop-Loss
- `SL_MODE` (enum, default: "atr"): Stop-loss mode (atr | fixed)
- `SL_ATR_MULTIPLIER` (float, default: 2.0): ATR multiplier (ATR mode)
- `SL_FIXED_PERCENT` (float, default: 2.0): Fixed % loss (FIXED mode)

### Take-Profit
- `TP_MODE` (enum, default: "atr"): Take-profit mode (atr | fixed)
- `TP_ATR_MULTIPLIER` (float, default: 3.0): ATR multiplier (ATR mode)
- `TP_FIXED_PERCENT` (float, default: 4.0): Fixed % gain (FIXED mode)

### Cooldown
- `COOLDOWN_AFTER_TRADE_SECONDS` (int, default: 3600): Cooldown after trade close

## Weighted Scoring

The strategy engine calculates a weighted score using indicator signals and optimized weights:

```
weighted_score = Σ (signal_i × weight_i)
                 i=1..N

where:
  signal_i ∈ [-1, 1]  (normalized indicator signal)
  weight_i ∈ [0, 1]    (optimized weight from weights_sets table)
  result ∈ [-1, 1]     (normalized weighted score)
```

Example with 9 indicators:
```
weighted_score = (ema_signal × 0.15) +
                 (macd_signal × 0.20) +
                 (rsi_signal × 0.12) +
                 (stoch_rsi_signal × 0.08) +
                 (bollinger_signal × 0.10) +
                 (atr_signal × 0.05) +
                 (obv_signal × 0.15) +
                 (fear_greed_signal × 0.10) +
                 (user_indicator_signal × 0.05)
```

Weights are loaded from the `weights_sets` table (the row with `is_active = TRUE`).

## Anti-Repainting

To prevent acting on unconfirmed signals that may disappear on the next candle:

1. **First signal**: Weighted score crosses entry/exit threshold → start confirmation
2. **Confirmation**: Track consecutive candles where condition remains true
3. **Action**: Only act after `confirmation_candles` consecutive confirmations

Example with `confirmation_candles = 2`:
```
Candle 1: score = 0.65 → entry condition met → count = 1
Candle 2: score = 0.70 → entry condition still met → count = 2 → ENTRY_LONG
```

If the condition breaks before confirmation:
```
Candle 1: score = 0.65 → entry condition met → count = 1
Candle 2: score = 0.55 → entry condition NOT met → reset count = 0
```

## Decision Logging

Every decision (ENTRY_LONG, EXIT, SKIP) is logged to the `signals` table with:

- **weighted_score**: The calculated score ∈ [-1, 1]
- **weights_snapshot**: Active weights at decision time (JSONB)
- **indicators_snapshot**: All indicator values and signals (JSONB)
- **decision_reason**: Human-readable explanation

This ensures complete transparency and enables post-mortem analysis.

## Testing

Comprehensive unit tests in `/tests/`:

- `test_strategy_types.py`: Type validation and edge cases
- `test_strategy_config.py`: Configuration loading and validation
- `test_strategy_sizing.py`: Position sizing for all three modes
- `test_strategy_stops.py`: Stop-loss and take-profit calculations
- `test_strategy_risk.py`: Risk management quotas and cooldowns
- `test_strategy_engine.py`: End-to-end strategy engine behavior

Target: >70% test coverage

## Database Integration

The strategy engine interacts with these tables:

- **weights_sets**: Load active weights (`is_active = TRUE`)
- **signals**: Insert decision logs with snapshots
- **trades**: Query for daily trade count and cooldown
- **runs**: Record run configuration snapshot

All database operations use async PostgreSQL via asyncpg.

## Future Extensions

- **Short positions**: Currently only ENTRY_LONG is supported (v1)
- **Multi-pair**: Currently single pair BTC/USDT (v1)
- **Dynamic thresholds**: Adjust thresholds based on market conditions
- **Trailing stops**: Dynamic stop-loss adjustment
