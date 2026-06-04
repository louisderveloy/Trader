# Indicators Module

Technical indicators engine for the crypto trading bot. All indicators provide standardized interfaces for calculation and signal normalization.

## Architecture

### Standard Interface

Every indicator module implements two functions:

```python
def compute(candles: pd.DataFrame, params: Dict[str, Any]) -> IndicatorResult:
    """Calculate raw indicator values from OHLCV data."""
    ...

def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """Convert raw values to normalized signal in range [-1, 1]."""
    ...
```

### Signal Normalization

All signals are normalized to the range `[-1, 1]`:

- **+1.0**: Strong bullish signal (buy)
- **0.0**: Neutral signal
- **-1.0**: Strong bearish signal (sell)

This standardization allows the strategy engine to:
- Apply weighted scoring across different indicator types
- Compare signals from different indicators on the same scale
- Implement consistent entry/exit thresholds

## Indicators

### Trend Indicators

#### EMA (Exponential Moving Average)
**File**: `ema.py`

Crossover-based trend indicator using fast and slow EMAs.

**Parameters**:
- `fast_period`: Fast EMA period (default: 50)
- `slow_period`: Slow EMA period (default: 200)

**Signal Logic**:
- Fast EMA > Slow EMA → Bullish (+1)
- Fast EMA < Slow EMA → Bearish (-1)
- Magnitude based on percentage separation

**Config**: `INDICATOR_EMA_FAST_PERIOD`, `INDICATOR_EMA_SLOW_PERIOD`

#### MACD (Moving Average Convergence Divergence)
**File**: `macd.py`

Trend momentum indicator using exponential moving averages.

**Parameters**:
- `fast`: Fast EMA period (default: 12)
- `slow`: Slow EMA period (default: 26)
- `signal`: Signal line period (default: 9)

**Signal Logic**:
- MACD line > Signal line → Bullish
- MACD line < Signal line → Bearish
- Histogram divergence indicates strength

**Config**: `INDICATOR_MACD_FAST`, `INDICATOR_MACD_SLOW`, `INDICATOR_MACD_SIGNAL`

### Oscillators

#### RSI (Relative Strength Index)
**File**: `rsi.py`

Momentum oscillator measuring speed and magnitude of price changes.

**Parameters**:
- `period`: Lookback period (default: 14)
- `overbought`: Overbought threshold (default: 70)
- `oversold`: Oversold threshold (default: 30)

**Signal Logic** (Contrarian):
- RSI < 30 → Oversold, bullish signal (+1)
- RSI > 70 → Overbought, bearish signal (-1)
- RSI ≈ 50 → Neutral (0)

**Config**: `INDICATOR_RSI_PERIOD`, `INDICATOR_RSI_OVERBOUGHT`, `INDICATOR_RSI_OVERSOLD`

#### Stochastic RSI
**File**: `stoch_rsi.py`

Oscillator applying stochastic formula to RSI values.

**Parameters**:
- `period`: RSI period (default: 14)
- `k`: %K smoothing period (default: 3)
- `d`: %D smoothing period (default: 3)

**Signal Logic**:
- Similar to RSI but more sensitive
- %K and %D crossover provides additional signals

**Config**: `INDICATOR_STOCH_RSI_PERIOD`, `INDICATOR_STOCH_RSI_K`, `INDICATOR_STOCH_RSI_D`

### Volatility Indicators

#### Bollinger Bands
**File**: `bollinger.py`

Volatility bands around a simple moving average.

**Parameters**:
- `period`: SMA period (default: 20)
- `std`: Standard deviations for bands (default: 2.0)

**Signal Logic**:
- Price near lower band → Oversold, bullish
- Price near upper band → Overbought, bearish
- Band width indicates volatility

**Config**: `INDICATOR_BOLLINGER_PERIOD`, `INDICATOR_BOLLINGER_STD`

#### ATR (Average True Range)
**File**: `atr.py`

Volatility measure using true range calculation.

**Parameters**:
- `period`: ATR period (default: 14)

**Signal Logic**:
- Normalized using percentile rank
- High ATR (high volatility) → May indicate trend change
- Low ATR (low volatility) → Consolidation

**Config**: `INDICATOR_ATR_PERIOD`

**Note**: ATR is also used for position sizing and stop-loss/take-profit calculation in the strategy engine.

### Volume Indicators

#### OBV (On Balance Volume)
**File**: `obv.py`

Cumulative volume indicator for trend confirmation.

**Parameters**: None

**Signal Logic**:
- Rising OBV → Accumulation, bullish
- Falling OBV → Distribution, bearish
- Normalized using EMA-based trend

**Config**: None

### Sentiment Indicators

#### Fear & Greed Index
**File**: `fear_greed.py`

External market sentiment indicator from alternative.me API.

**Parameters**: None

**Signal Logic**:
- Direct mapping: Fear (0) → -1, Greed (100) → +1
- Contrarian interpretation possible
- Cached for 4 hours (updates daily)

**Config**: None

**API**: https://api.alternative.me/fng/

#### User Indicator
**File**: `user_indicator.py`

Manual user input from dashboard.

**Parameters**:
- `symbol`: Trading pair to query

**Signal Logic**:
- Direct user input (-1 to +1)
- Respects expiration time
- Logs user note for transparency

**Config**: Database `user_indicator` table

## Data Format

### Input: Candle DataFrame

All `compute()` functions expect a pandas DataFrame with:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | Candle opening time (UTC) |
| `open` | Decimal | Opening price |
| `high` | Decimal | Highest price |
| `low` | Lowest price |
| `close` | Decimal | Closing price |
| `volume` | Decimal | Trading volume |

**Validation**:
- All required columns must be present
- No NaN values in critical columns (close, high, low)
- Sufficient data for indicator calculation (validated per indicator)

### Output: IndicatorResult

```python
@dataclass
class IndicatorResult:
    values: Dict[str, Any]           # Calculated values
    metadata: Optional[Dict[str, Any]]  # Optional metadata
```

**Example**:
```python
IndicatorResult(
    values={
        "ema_50": 42000.5,
        "ema_200": 41000.2,
        "crossover": "bullish"
    },
    metadata={"last_cross_timestamp": "2024-01-15 10:30:00"}
)
```

### Output: IndicatorSignal

```python
@dataclass
class IndicatorSignal:
    value: float  # In range [-1, 1]
    metadata: Optional[Dict[str, Any]]
```

**Example**:
```python
IndicatorSignal(
    value=0.75,
    metadata={"reason": "fast_ema_above_slow", "separation_percent": 2.3}
)
```

## Usage Example

```python
import pandas as pd
from decimal import Decimal
from indicators import ema, types

# Prepare candle data
candles = pd.DataFrame({
    'timestamp': pd.date_range('2024-01-01', periods=300, freq='15min'),
    'open': [Decimal(str(40000 + i * 10)) for i in range(300)],
    'high': [Decimal(str(40010 + i * 10)) for i in range(300)],
    'low': [Decimal(str(39990 + i * 10)) for i in range(300)],
    'close': [Decimal(str(40005 + i * 10)) for i in range(300)],
    'volume': [Decimal('100.5') for _ in range(300)],
})

# Calculate indicator
params = {
    'fast_period': 50,
    'slow_period': 200
}

result = ema.compute(candles, params)
print(f"EMA values: {result.values}")

# Convert to signal
signal = ema.to_signal(result)
print(f"Signal: {signal.value} (in range [-1, 1])")
print(f"Reason: {signal.metadata.get('reason')}")

# Validate signal is in valid range
assert -1.0 <= signal.value <= 1.0
```

## Testing

All indicators must have unit tests covering:

1. **Basic calculation**: Verify indicator values are correct
2. **Signal normalization**: Ensure signals are in [-1, 1]
3. **Edge cases**: Insufficient data, NaN values, zero division
4. **Parameter validation**: Invalid parameters raise appropriate errors

Run tests:
```bash
pytest tests/indicators/ -v
```

## Implementation Checklist

When implementing a new indicator:

- [ ] Create `<indicator>.py` in `bot/indicators/`
- [ ] Implement `compute(candles, params) -> IndicatorResult`
- [ ] Implement `to_signal(values) -> IndicatorSignal`
- [ ] Add type hints to all functions
- [ ] Add docstrings to all public functions
- [ ] Use structured logging (no `print()`)
- [ ] Validate input data using `validate_candles()`
- [ ] Ensure signal is always in [-1, 1] range
- [ ] Handle edge cases (insufficient data, NaN, etc.)
- [ ] Add module to `__init__.py` exports
- [ ] Create unit tests in `tests/indicators/test_<indicator>.py`
- [ ] Update this README with indicator details

## Normalization Utilities

The `utils.py` module provides helper functions for common normalization patterns:

- `normalize_to_range()`: Linear normalization to [-1, 1]
- `normalize_oscillator()`: Oscillator zone normalization (RSI-style)
- `normalize_crossover()`: Crossover-based normalization (EMA-style)
- `normalize_percentile()`: Percentile rank normalization (ATR-style)
- `calculate_ema()`, `calculate_sma()`: Common calculations
- `safe_divide()`: Zero-safe division

See `utils.py` for full API documentation.

## Logging

All indicators use structured JSON logging:

```python
import logging
import json

logger = logging.getLogger(__name__)

logger.info(json.dumps({
    "event": "indicator_calculated",
    "indicator": "rsi",
    "params": params,
    "signal": signal.value,
    "metadata": signal.metadata
}))
```

**Never use `print()`** - all output must go through the logger.

## Performance Considerations

- Use vectorized pandas/numpy operations (avoid Python loops)
- Cache expensive calculations when possible
- Validate inputs early to fail fast
- Use appropriate data types (Decimal for prices, float for calculations)
- Consider memory usage for large historical datasets

## Future Extensions

Potential indicators to add in future phases:

- Ichimoku Cloud
- Volume Weighted Average Price (VWAP)
- Money Flow Index (MFI)
- Parabolic SAR
- Aroon Indicator
- Commodity Channel Index (CCI)
- Custom ML-based indicators
