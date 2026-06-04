# Tests

Unit and integration tests for the Trader Bot.

## Running Tests

### Prerequisites

Make sure the bot container is running with dev dependencies:

```bash
# Build with dev dependencies (dev environment)
docker compose build bot

# Start services
docker compose up -d
```

### Run All Tests

**Windows:**
```cmd
run-tests.bat
```

**Linux/Mac:**
```bash
./run-tests.sh
```

**Or directly with docker compose:**
```bash
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests -v
```

### Run Specific Tests

**Single test file:**
```bash
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests/indicators/test_ema.py -v
```

**Single test class:**
```bash
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests/indicators/test_ema.py::TestEMACompute -v
```

**Single test function:**
```bash
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests/indicators/test_ema.py::TestEMACompute::test_compute_with_default_params -v
```

### Run with Coverage

```bash
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests --cov=bot --cov-report=html
```

Coverage report will be generated in `htmlcov/` directory.

### Test Options

- `-v`: Verbose output
- `-s`: Show print statements
- `-x`: Stop on first failure
- `-k EXPRESSION`: Run tests matching expression
- `--lf`: Run last failed tests
- `--tb=short`: Shorter traceback format

## Test Structure

```
tests/
├── __init__.py
├── README.md
├── indicators/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures for indicators
│   ├── test_types.py         # Test indicator types and utilities
│   ├── test_ema.py           # Test EMA indicator
│   ├── test_rsi.py           # Test RSI indicator
│   ├── test_macd.py          # Test MACD indicator
│   └── ...                   # Other indicator tests
├── strategy/                 # Strategy engine tests (Phase 4)
├── backtesting/             # Backtesting engine tests (Phase 5)
└── integration/             # Integration tests
```

## Writing Tests

### Test Fixtures

Common fixtures are defined in `conftest.py`:

- `sample_candles`: 300 candles with uptrend
- `downtrend_candles`: 300 candles with downtrend
- `sideways_candles`: 300 candles with sideways movement
- `volatile_candles`: 300 candles with high volatility
- `insufficient_candles`: Only 10 candles (for testing errors)

### Test Helpers

- `assert_signal_in_range(value)`: Assert signal is in [-1, 1]
- `assert_result_has_values(result, keys)`: Assert result has expected keys

### Example Test

```python
def test_my_indicator(sample_candles):
    """Test my indicator computation."""
    params = {'period': 14}
    result = my_indicator.compute(sample_candles, params)

    assert isinstance(result, IndicatorResult)
    assert result.values['my_value'] is not None

    signal = my_indicator.to_signal(result)
    assert_signal_in_range(signal.value)
```

## Coverage Goals

- **Target**: >70% code coverage
- **Priority**: Core business logic (indicators, strategy, backtesting)
- **Lower priority**: Utility functions, simple getters/setters

## CI/CD

Tests run automatically on GitHub Actions for:
- Every push to `main` or `dev`
- Every pull request
- Scheduled nightly builds

See `.github/workflows/test.yml` for CI configuration.
