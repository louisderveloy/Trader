# Exchange Connectors

This module provides exchange connectivity for the trading bot.

## Architecture

All exchange connectors inherit from the abstract `ExchangeBase` class, which defines a consistent interface for:
- Connecting/disconnecting
- Fetching market data (candles, ticker)
- Account management (balance)
- Order operations (place, cancel, status)

This abstraction allows the bot to easily support multiple exchanges by implementing the same interface.

## Supported Exchanges

### Binance (BinanceExchange)

**Status:** ✅ Implemented (Phase 2)

**Features:**
- Testnet and mainnet support
- Async operations using python-binance AsyncClient
- OHLCV candle fetching with flexible timeframes
- Real-time ticker data
- Limit orders (post-only and GTC)
- Market orders
- Order tracking and cancellation
- Balance queries

**Usage:**

```python
from bot.exchanges import BinanceExchange

# Create connector (testnet)
exchange = BinanceExchange(
    api_key="your_testnet_key",
    api_secret="your_testnet_secret",
    testnet=True
)

# Connect
await exchange.connect()

# Fetch candles
candles = await exchange.get_candles(
    symbol="BTCUSDT",
    timeframe="15m",
    limit=100
)

# Get ticker
ticker = await exchange.get_ticker("BTCUSDT")

# Get balance
balance = await exchange.get_balance("USDT")

# Place limit order
order = await exchange.place_limit_order(
    symbol="BTCUSDT",
    side="buy",
    quantity=Decimal("0.001"),
    price=Decimal("50000.00"),
    post_only=True
)

# Disconnect
await exchange.disconnect()
```

**Supported Timeframes:**
- 1m, 3m, 5m, 15m, 30m
- 1h, 2h, 4h, 6h, 8h, 12h
- 1d, 3d, 1w, 1M

**Error Handling:**

The connector raises specific exceptions for different error cases:
- `ConnectionError` — Failed to connect to exchange
- `AuthenticationError` — Invalid API credentials
- `InvalidSymbolError` — Invalid trading pair
- `InvalidTimeframeError` — Unsupported timeframe
- `InsufficientBalanceError` — Not enough balance for order
- `OrderNotFoundError` — Order doesn't exist
- `OrderRejectError` — Exchange rejected the order
- `RateLimitError` — Rate limit exceeded
- `ExchangeError` — Generic exchange error

## Testing

Test the connector with:

```bash
# From bot container
docker exec trader-bot python test_binance_connector.py
```

**Prerequisites:**
- Set `BINANCE_TESTNET_API_KEY` in `.env`
- Set `BINANCE_TESTNET_API_SECRET` in `.env`
- Ensure Binance testnet account has test funds

## Environment Variables

Required in `.env`:

```bash
# Binance Testnet (development)
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_secret_here

# Binance Mainnet (production - Phase 15)
BINANCE_MAINNET_API_KEY=your_mainnet_api_key_here
BINANCE_MAINNET_API_SECRET=your_mainnet_secret_here
```

## Future Exchanges

To add a new exchange:

1. Create `bot/exchanges/your_exchange.py`
2. Implement `ExchangeBase` interface
3. Add to `bot/exchanges/__init__.py`
4. Update this README

Example exchanges that could be added:
- Kraken
- Coinbase
- Bitfinex
- etc.

## Data Normalization

All exchange connectors normalize data to a standard format:

**Candles:**
```python
{
    "time": datetime,      # UTC timezone
    "open": Decimal,
    "high": Decimal,
    "low": Decimal,
    "close": Decimal,
    "volume": Decimal
}
```

**Ticker:**
```python
{
    "symbol": str,
    "last_price": Decimal,
    "bid": Decimal,
    "ask": Decimal,
    "volume_24h": Decimal,
    "timestamp": datetime
}
```

**Balance:**
```python
{
    "free": Decimal,       # Available balance
    "locked": Decimal,     # Balance in orders
    "total": Decimal       # free + locked
}
```

**Order:**
```python
{
    "order_id": str,
    "symbol": str,
    "side": str,           # "buy" or "sell"
    "type": str,           # "limit" or "market"
    "quantity": Decimal,
    "price": Decimal,      # None for market orders
    "filled_quantity": Decimal,
    "filled_price": Decimal,  # Average fill price
    "status": str,         # "pending", "filled", "cancelled", "rejected"
    "created_at": datetime,
    "updated_at": datetime
}
```

All prices and quantities use `Decimal` for precision (no floating point errors).
All timestamps are `datetime` objects with UTC timezone.
