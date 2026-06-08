#!/usr/bin/env python3
"""
Trading Loop - Paper and Live Trading.

This script runs the main trading loop for:
  - paper: Simulated trading (no real orders, uses testnet prices)
  - live: Real trading on Binance (testnet or mainnet)

The bot:
1. Fetches latest candles from the exchange
2. Calculates all indicator signals
3. Computes weighted score
4. Makes trading decisions based on strategy
5. Executes orders (simulated or real)
6. Logs everything to database and Redis

Usage:
    # Paper trading (simulated)
    python -m scripts.trading --mode paper --symbol BTCUSDT

    # Live trading on testnet
    python -m scripts.trading --mode live --symbol BTCUSDT --testnet

    # Live trading on mainnet (REAL MONEY!)
    python -m scripts.trading --mode live --symbol BTCUSDT

    # With docker:
    docker compose exec bot python -m scripts.trading --mode paper --symbol BTCUSDT
"""

import argparse
import asyncio
import logging
import os
import sys
import signal
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import uuid4, UUID

import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges import BinanceExchange
from exchanges.exceptions import ExchangeError
from runs.orders import (
    create_order,
    update_order_submitted,
    update_order_filled,
    update_order_cancelled,
    update_order_rejected,
)
from runs.errors import log_exception, ErrorCategory, ErrorSeverity
from strategy.config import StrategyEngineConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


class TradingBot:
    """
    Main trading bot class.

    Handles the trading loop for both paper and live modes.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        mode: str,
        testnet: bool,
        initial_capital: Decimal = Decimal("10000")
    ):
        """
        Initialize trading bot.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            timeframe: Candle timeframe (e.g., 15m)
            mode: Trading mode ('paper' or 'live')
            testnet: Whether to use testnet
            initial_capital: Initial capital for paper trading
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.mode = mode
        self.testnet = testnet
        self.initial_capital = initial_capital

        # Components (initialized in start())
        self.exchange: Optional[BinanceExchange] = None
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None

        # State
        self.run_id: Optional[int] = None  # Set when run record is created
        self.capital = initial_capital
        self.position: Optional[Dict[str, Any]] = None  # Current position
        self.weights: Dict[str, float] = {}
        self.is_running = False

        # Configuration (loaded from database in start())
        self.config: Optional[StrategyEngineConfig] = None

        # Tracking
        self.trades_today = 0
        self.last_trade_time: Optional[datetime] = None
        self.confirmation_count = 0
        self.pending_signal: Optional[str] = None
        self.pending_order: Optional[Dict[str, Any]] = None  # Track pending entry order

    async def start(self):
        """Initialize all components and start trading loop."""
        logger.info("=" * 80)
        logger.info("STARTING TRADING BOT")
        logger.info("=" * 80)
        logger.info(f"Mode: {self.mode.upper()}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Network: {'TESTNET' if self.testnet else 'MAINNET'}")
        logger.info(f"Initial Capital: {self.initial_capital} USDT")
        logger.info("=" * 80)

        try:
            # Initialize components
            await self._init_database()
            await self._load_config()
            await self._init_exchange()
            await self._init_redis()
            await self._load_weights()
            await self._create_run_record()

            # Start trading loop
            self.is_running = True
            await self._trading_loop()

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Gracefully stop the bot and cleanup resources."""
        # Prevent multiple calls to stop()
        if not self.is_running:
            return

        logger.info("Stopping trading bot...")
        self.is_running = False

        # Update run status
        if self.db_pool and self.run_id:
            try:
                await self._update_run_status("cancelled" if shutdown_requested else "completed")
            except Exception as e:
                logger.error(f"Failed to update run status: {e}")

        # Cleanup connections
        if self.exchange:
            try:
                await self.exchange.disconnect()
            except Exception as e:
                logger.error(f"Failed to disconnect exchange: {e}")

        if self.db_pool:
            try:
                await self.db_pool.close()
            except Exception as e:
                logger.error(f"Failed to close database pool: {e}")

        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception as e:
                logger.error(f"Failed to close Redis client: {e}")

        logger.info("Trading bot stopped.")

    async def _init_database(self):
        """Initialize database connection."""
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise ValueError("DATABASE_URL environment variable not set")

        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        self.db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        logger.info("Database connection established")

    async def _load_config(self):
        """Load configuration from database."""
        try:
            self.config = await StrategyEngineConfig.from_db(self.db_pool)
            logger.info("Configuration loaded from database")
            logger.info(f"  Entry threshold: {self.config.strategy.entry_threshold}")
            logger.info(f"  Exit threshold: {self.config.strategy.exit_threshold}")
            logger.info(f"  Confirmation candles: {self.config.strategy.confirmation_candles}")
            logger.info(f"  Max trades/day: {self.config.risk.max_trades_per_day}")
            logger.info(f"  Position size mode: {self.config.risk.position_size_mode.value}")
        except ValueError as e:
            logger.error(f"Failed to load configuration from database: {e}")
            logger.error("Please create a configuration first using: python -m main config create")
            raise

    async def _init_exchange(self):
        """Initialize exchange connection."""
        env_prefix = "BINANCE_TESTNET" if self.testnet else "BINANCE_MAINNET"
        api_key = os.getenv(f"{env_prefix}_API_KEY")
        api_secret = os.getenv(f"{env_prefix}_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError(f"Missing {env_prefix}_API_KEY and/or {env_prefix}_API_SECRET")

        self.exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            testnet=self.testnet
        )
        await self.exchange.connect()
        logger.info(f"Exchange connection established ({'testnet' if self.testnet else 'mainnet'})")

    async def _init_redis(self):
        """Initialize Redis connection."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed (non-fatal): {e}")
            self.redis_client = None

    async def _load_weights(self):
        """Load active weights from database."""
        query = """
            SELECT weights FROM weights_sets
            WHERE is_active = true
            LIMIT 1
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query)
            if row:
                weights = row["weights"]
                # Parse JSON string if needed
                if isinstance(weights, str):
                    weights = json.loads(weights)

                # Remove 'weight_' prefix from keys if present
                # Database stores as "weight_ema", but strategy expects "ema"
                self.weights = {
                    k.replace('weight_', ''): v
                    for k, v in weights.items()
                }
                logger.info(f"Loaded active weights: {json.dumps(self.weights, indent=2)}")
            else:
                # Default weights
                self.weights = {
                    "ema": 0.125, "macd": 0.125, "rsi": 0.125, "stoch_rsi": 0.125,
                    "bollinger": 0.125, "atr": 0.125, "obv": 0.10,
                    "fear_greed": 0.10, "user_indicator": 0.05
                }
                logger.warning("No active weights set, using defaults")

    async def _create_run_record(self):
        """Create run record in database."""
        environment = "testnet" if self.testnet else "live"
        if self.mode == "paper":
            environment = "paper"

        # Get current time for both start_date and end_date (live runs are open-ended)
        now = datetime.now(timezone.utc)

        # Create config snapshot using the loaded config
        config_snapshot = self.config.to_snapshot()
        config_snapshot.update({
            "mode": self.mode,
            "testnet": self.testnet,
            "weights": self.weights,
            "initial_capital": str(self.initial_capital),
        })

        query = """
            INSERT INTO runs (
                run_type, environment, status, symbol, timeframe,
                start_date, end_date, config_snapshot, started_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                "live" if self.mode == "live" else "paper",
                environment,
                "running",
                self.symbol,
                self.timeframe,
                now,  # start_date
                now,  # end_date (will be updated on completion)
                json.dumps(config_snapshot),
                now   # started_at
            )
            self.run_id = row["id"]

        logger.info(f"Created run record: {self.run_id}")

    async def _update_run_status(self, status: str):
        """Update run status in database."""
        query = """
            UPDATE runs SET status = $1, completed_at = $2
            WHERE id = $3
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, status, datetime.now(timezone.utc), self.run_id)

    async def _trading_loop(self):
        """Main trading loop."""
        # Calculate sleep interval based on timeframe
        timeframe_minutes = self._parse_timeframe_minutes(self.timeframe)
        check_interval = min(60, timeframe_minutes * 60 // 4)  # Check 4 times per candle, max 60s

        logger.info(f"Trading loop started (check interval: {check_interval}s)")

        while self.is_running and not shutdown_requested:
            try:
                # Reset daily counters at midnight UTC
                now = datetime.now(timezone.utc)
                if now.hour == 0 and now.minute < (check_interval // 60 + 1):
                    self.trades_today = 0
                    logger.info("Daily counters reset")

                # Execute one iteration
                await self._trading_iteration()

                # Publish heartbeat to Redis
                await self._publish_heartbeat()

            except ExchangeError as e:
                logger.error(f"Exchange error: {e}")
                await log_exception(
                    self.db_pool, e,
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.EXCHANGE_API,
                    context={"symbol": self.symbol},
                    run_id=self.run_id,
                )
                await asyncio.sleep(30)  # Wait before retry
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                await log_exception(
                    self.db_pool, e,
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.SYSTEM,
                    context={"symbol": self.symbol, "phase": "trading_loop"},
                    run_id=self.run_id,
                )
                await asyncio.sleep(10)

            # Sleep until next check, but wake up periodically to check shutdown flag
            # This makes shutdown more responsive
            sleep_remaining = check_interval
            while sleep_remaining > 0 and self.is_running and not shutdown_requested:
                sleep_chunk = min(5, sleep_remaining)  # Wake up every 5 seconds max
                await asyncio.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk

    async def _trading_iteration(self):
        """Single iteration of the trading loop."""
        # Fetch latest candles
        candles = await self.exchange.get_candles(
            symbol=self.symbol,
            timeframe=self.timeframe,
            limit=200  # Need enough for indicators
        )

        if len(candles) < 50:
            logger.warning(f"Not enough candles: {len(candles)} (need at least 50)")
            return

        # Store latest candles in database
        await self._store_candles(candles)

        # Calculate indicators and weighted score
        signals = self._calculate_signals(candles)
        weighted_score = self._calculate_weighted_score(signals)

        current_price = Decimal(str(candles[-1]["close"]))

        logger.info(
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
            f"Price: {current_price:.2f} | Score: {weighted_score:.3f} | "
            f"Position: {'LONG' if self.position else 'NONE'} | "
            f"Pending: {bool(self.pending_order)}"
        )

        # Check for pending order fills FIRST
        if self.pending_order:
            await self._check_pending_order(current_price)
            return  # Skip other logic while order is pending

        # Trading logic
        if self.position is None:
            # Not in position - check for entry
            await self._check_entry(weighted_score, current_price, candles, signals)
        else:
            # In position - check for exit
            await self._check_exit(weighted_score, current_price, candles, signals)

    def _calculate_signals(self, candles: list) -> Dict[str, float]:
        """
        Calculate indicator signals from candles.

        This is a simplified inline calculation for the trading loop.
        Returns signals normalized to [-1, 1].
        """
        import pandas as pd
        import numpy as np

        # Convert to DataFrame
        df = pd.DataFrame(candles)
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        volume = df['volume'].astype(float)

        signals = {}

        # EMA crossover
        ema_fast = close.ewm(span=50, adjust=False).mean()
        ema_slow = close.ewm(span=200, adjust=False).mean()
        ema_diff = (ema_fast - ema_slow) / ema_slow * 100
        signals["ema"] = float(np.clip(ema_diff.iloc[-1] / 5, -1, 1))

        # MACD
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        hist_std = histogram.rolling(window=20).std()
        if hist_std.iloc[-1] > 0:
            signals["macd"] = float(np.clip(histogram.iloc[-1] / (hist_std.iloc[-1] * 2), -1, 1))
        else:
            signals["macd"] = 0.0

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        rsi_value = rsi.iloc[-1]
        if rsi_value > 70:
            signals["rsi"] = -((rsi_value - 70) / 30)
        elif rsi_value < 30:
            signals["rsi"] = (30 - rsi_value) / 30
        else:
            signals["rsi"] = 0.0

        # Stochastic RSI
        rsi_min = rsi.rolling(window=14).min()
        rsi_max = rsi.rolling(window=14).max()
        stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
        stoch_k = stoch_rsi.rolling(window=3).mean() * 100
        stoch_value = stoch_k.iloc[-1]
        if stoch_value > 80:
            signals["stoch_rsi"] = -((stoch_value - 80) / 20)
        elif stoch_value < 20:
            signals["stoch_rsi"] = (20 - stoch_value) / 20
        else:
            signals["stoch_rsi"] = 0.0

        # Bollinger Bands
        sma_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std()
        upper = sma_20 + 2 * std_20
        lower = sma_20 - 2 * std_20
        bb_position = (close - lower) / (upper - lower + 1e-10)
        signals["bollinger"] = float(np.clip((0.5 - bb_position.iloc[-1]) * 2, -1, 1))

        # ATR (volatility - neutral signal, used for position sizing)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        atr_pct = atr / close * 100
        atr_percentile = atr_pct.rank(pct=True).iloc[-1]
        signals["atr"] = float((atr_percentile - 0.5) * 2)

        # OBV
        obv = (np.sign(close.diff()) * volume).cumsum()
        obv_fast = obv.ewm(span=10, adjust=False).mean()
        obv_slow = obv.ewm(span=30, adjust=False).mean()
        obv_diff = obv_fast - obv_slow
        obv_std = obv_diff.rolling(window=20).std()
        if obv_std.iloc[-1] > 0:
            signals["obv"] = float(np.clip(obv_diff.iloc[-1] / (obv_std.iloc[-1] * 2), -1, 1))
        else:
            signals["obv"] = 0.0

        # Fear & Greed (placeholder - would need external API)
        signals["fear_greed"] = 0.0

        # User indicator (placeholder - would need database lookup)
        signals["user_indicator"] = 0.0

        return signals

    def _calculate_weighted_score(self, signals: Dict[str, float]) -> float:
        """Calculate weighted score from signals."""
        score = 0.0
        contributions = {}
        for indicator, signal in signals.items():
            weight = self.weights.get(indicator, 0.0)
            contribution = signal * weight
            contributions[indicator] = contribution
            score += contribution

        # Log detailed breakdown
        logger.info("=" * 60)
        logger.info("SCORE CALCULATION BREAKDOWN:")
        for indicator in sorted(contributions.keys()):
            signal_val = signals[indicator]
            weight_val = self.weights.get(indicator, 0.0)
            contrib_val = contributions[indicator]
            logger.info(f"  {indicator:15s}: signal={signal_val:+.3f}, weight={weight_val:.3f}, contrib={contrib_val:+.4f}")
        logger.info(f"Raw score (before clamp): {score:+.4f}")

        clamped_score = max(-1.0, min(1.0, score))
        logger.info(f"Final score (after clamp): {clamped_score:+.4f}")
        logger.info("=" * 60)

        return clamped_score

    async def _check_pending_order(self, current_price: Decimal):
        """
        Check if pending order has been filled.

        For paper trading: Simulate fill after one iteration (realistic delay).
        For live trading: Query exchange for order status.
        """
        if not self.pending_order:
            return

        order_id = self.pending_order["db_order_id"]
        exchange_order_id = self.pending_order["exchange_order_id"]
        side = self.pending_order["side"]
        order_price = self.pending_order["price"]
        quantity = self.pending_order["quantity"]

        is_filled = False
        filled_price = order_price
        commission = Decimal("0")

        if self.mode == "live":
            # Query Binance for order status
            try:
                order_status = await self.exchange.get_order_status(
                    symbol=self.symbol,
                    order_id=exchange_order_id
                )

                status = order_status.get("status", "").upper()

                if status == "FILLED":
                    # Order fully filled
                    is_filled = True
                    filled_price = Decimal(str(order_status.get("avgPrice", order_price)))
                    # Get actual commission from exchange
                    commission = Decimal(str(order_status.get("commission", 0)))
                    if commission == 0:
                        # Estimate if not provided
                        commission = quantity * filled_price * Decimal("0.001")

                    logger.info(f"Order {exchange_order_id} FILLED at {filled_price}")

                elif status in ("CANCELED", "REJECTED", "EXPIRED"):
                    # Order failed
                    logger.warning(f"Order {exchange_order_id} {status}")
                    await update_order_cancelled(self.db_pool, order_id, f"Exchange status: {status}")
                    self.pending_order = None
                    return

                else:
                    # Still pending (NEW, PARTIALLY_FILLED)
                    logger.debug(f"Order {exchange_order_id} status: {status}")
                    return

            except ExchangeError as e:
                logger.error(f"Failed to check order status: {e}")
                # Continue to retry on next iteration
                return

        else:
            # Paper trading: Simulate fill with slight slippage
            # Fill after one iteration (simulates ~15-60s delay)
            is_filled = True

            # Simulate slippage: 0.05% on average
            import random
            slippage_pct = Decimal(str(random.uniform(-0.001, 0.001)))
            filled_price = order_price * (Decimal("1") + slippage_pct)
            commission = quantity * filled_price * Decimal("0.001")

            logger.info(f"[PAPER] Order filled at {filled_price} (slippage: {slippage_pct*100:.3f}%)")

        if is_filled:
            # Update order as filled
            await update_order_filled(
                db_pool=self.db_pool,
                order_id=order_id,
                filled_quantity=quantity,
                filled_price=filled_price,
                commission=commission,
                exchange_order_id=exchange_order_id,
            )

            # Update position state
            if side == "buy":
                # Entry order filled
                stop_loss = self.pending_order["stop_loss"]
                take_profit = self.pending_order["take_profit"]
                entry_score = self.pending_order["score"]
                entry_signals = self.pending_order["signals"]
                entry_time = datetime.now(timezone.utc)

                # Create trade entry in database
                trade_id = await self._create_trade_entry(
                    entry_price=filled_price,
                    quantity=quantity,
                    entry_time=entry_time,
                    entry_order_id=order_id,
                )

                self.position = {
                    "trade_id": trade_id,
                    "entry_price": filled_price,
                    "entry_time": entry_time,
                    "quantity": quantity,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "order_id": exchange_order_id,
                    "entry_order_id": order_id,
                    "entry_score": entry_score,
                    "entry_signals": entry_signals
                }

                logger.info("=" * 60)
                logger.info(f"POSITION OPENED")
                logger.info(f"Entry: {filled_price:.2f} | Qty: {quantity:.6f}")
                logger.info(f"SL: {stop_loss:.2f} | TP: {take_profit:.2f}")
                logger.info(f"Trade ID: {trade_id}")
                logger.info("=" * 60)

                # Publish to Redis
                await self._publish_trade_event("entry", filled_price, quantity)

            elif side == "sell":
                # Exit order filled - trade completed
                entry_price = self.position["entry_price"]
                pnl = (filled_price - entry_price) * quantity
                pnl_pct = (filled_price - entry_price) / entry_price * 100

                # Update capital
                self.capital += pnl

                # Update trade with exit data
                exit_reason = self.pending_order["exit_reason"]
                exit_score = self.pending_order["score"]
                exit_signals = self.pending_order["signals"]

                await self._log_trade(
                    trade_id=self.position["trade_id"],
                    exit_price=filled_price,
                    exit_reason=exit_reason,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_score=exit_score,
                    exit_signals=exit_signals,
                    exit_order_id=order_id,
                )

                logger.info("=" * 60)
                logger.info(f"POSITION CLOSED")
                logger.info(f"Entry: {entry_price:.2f} | Exit: {filled_price:.2f}")
                logger.info(f"P&L: {pnl:.2f} USDT ({pnl_pct:+.2f}%)")
                logger.info(f"Capital: {self.capital:.2f} USDT")
                logger.info("=" * 60)

                # Publish to Redis
                await self._publish_trade_event("exit", filled_price, quantity, pnl)

                # Clear position
                self.position = None

            # Clear pending order
            self.pending_order = None

    async def _check_entry(
        self,
        score: float,
        price: Decimal,
        candles: list,
        signals: Dict[str, float]
    ):
        """Check for entry conditions and execute if met."""
        # Check daily trade limit
        if self.trades_today >= self.config.risk.max_trades_per_day:
            return

        # Check cooldown
        if self.last_trade_time:
            cooldown_seconds = self.config.cooldown.after_trade_seconds
            cooldown_end = self.last_trade_time + timedelta(seconds=cooldown_seconds)
            if datetime.now(timezone.utc) < cooldown_end:
                return

        # Check entry threshold
        if score >= self.config.strategy.entry_threshold:
            # Anti-repainting confirmation
            if self.pending_signal == "entry":
                self.confirmation_count += 1
            else:
                self.pending_signal = "entry"
                self.confirmation_count = 1

            if self.confirmation_count >= self.config.strategy.confirmation_candles:
                # Execute entry
                await self._execute_entry(price, score, signals)
                self.pending_signal = None
                self.confirmation_count = 0
        else:
            self.pending_signal = None
            self.confirmation_count = 0

    async def _check_exit(
        self,
        score: float,
        price: Decimal,
        candles: list,
        signals: Dict[str, float]
    ):
        """Check for exit conditions and execute if met."""
        if not self.position:
            return

        exit_reason = None

        # Check stop-loss
        if self.position.get("stop_loss") and price <= self.position["stop_loss"]:
            exit_reason = "stop_loss"

        # Check take-profit
        elif self.position.get("take_profit") and price >= self.position["take_profit"]:
            exit_reason = "take_profit"

        # Check signal-based exit
        elif score <= self.config.strategy.exit_threshold:
            if self.pending_signal == "exit":
                self.confirmation_count += 1
            else:
                self.pending_signal = "exit"
                self.confirmation_count = 1

            if self.confirmation_count >= self.config.strategy.confirmation_candles:
                exit_reason = "signal"

        if exit_reason:
            await self._execute_exit(price, exit_reason, score, signals)
            self.pending_signal = None
            self.confirmation_count = 0
        elif self.pending_signal != "exit":
            self.pending_signal = None
            self.confirmation_count = 0

    async def _execute_entry(
        self,
        price: Decimal,
        score: float,
        signals: Dict[str, float]
    ):
        """Execute entry order."""
        # Calculate position size (simplified: use 95% of capital)
        position_size = self.capital * Decimal("0.95")
        quantity = position_size / price

        # Calculate stop-loss and take-profit (simplified: fixed percentages)
        stop_loss = price * Decimal("0.98")  # 2% stop-loss
        take_profit = price * Decimal("1.04")  # 4% take-profit

        logger.info("=" * 60)
        logger.info(f"ENTRY SIGNAL - Score: {score:.3f}")
        logger.info(f"Price: {price:.2f} | Quantity: {quantity:.6f}")
        logger.info(f"Stop-loss: {stop_loss:.2f} | Take-profit: {take_profit:.2f}")
        logger.info("=" * 60)

        # Log signal to database and get signal_id
        signal_id = await self._log_signal("entry", price, score, signals)

        # Create order record in database
        db_order_id = await create_order(
            db_pool=self.db_pool,
            run_id=self.run_id,
            symbol=self.symbol,
            side="buy",
            order_type="limit" if self.mode == "live" else "market",
            quantity=quantity,
            price=price,
            signal_id=signal_id,
            metadata={"score": score, "mode": self.mode},
        )

        exchange_order_id = None
        if self.mode == "live":
            # Place real order
            try:
                order = await self.exchange.place_limit_order(
                    symbol=self.symbol,
                    side="buy",
                    quantity=quantity,
                    price=price
                )
                exchange_order_id = str(order.get("orderId"))
                logger.info(f"Order placed on exchange: {exchange_order_id}")

                # Update order with exchange ID
                await update_order_submitted(self.db_pool, db_order_id, exchange_order_id)

            except ExchangeError as e:
                logger.error(f"Failed to place order: {e}")
                await update_order_rejected(self.db_pool, db_order_id, str(e))
                await log_exception(
                    self.db_pool, e,
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.ORDER,
                    context={"symbol": self.symbol, "side": "buy"},
                    run_id=self.run_id,
                )
                return
        else:
            # Paper trading - generate simulated order ID
            exchange_order_id = f"paper_{uuid4().hex[:8]}"
            logger.info(f"[PAPER] Order placed: {exchange_order_id}")

        # Store pending order for fill tracking
        self.pending_order = {
            "db_order_id": db_order_id,
            "exchange_order_id": exchange_order_id,
            "side": "buy",
            "price": price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "score": score,
            "signals": signals.copy(),
        }

        # Update trade counter (will be committed when order fills)
        self.trades_today += 1
        self.last_trade_time = datetime.now(timezone.utc)

        logger.info(f"Entry order pending: {exchange_order_id} | Price: {price:.2f}")

    async def _execute_exit(
        self,
        price: Decimal,
        reason: str,
        score: float,
        signals: Dict[str, float]
    ):
        """Execute exit order."""
        if not self.position:
            return

        quantity = self.position["quantity"]
        entry_price = self.position["entry_price"]
        pnl = (price - entry_price) * quantity
        pnl_pct = (price - entry_price) / entry_price * 100

        logger.info("=" * 60)
        logger.info(f"EXIT SIGNAL - Reason: {reason} | Score: {score:.3f}")
        logger.info(f"Entry: {entry_price:.2f} | Exit: {price:.2f}")
        logger.info(f"P&L: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
        logger.info("=" * 60)

        # Log signal to database
        signal_id = await self._log_signal("exit", price, score, signals)

        # Create order record in database
        db_order_id = await create_order(
            db_pool=self.db_pool,
            run_id=self.run_id,
            symbol=self.symbol,
            side="sell",
            order_type="market",
            quantity=quantity,
            price=price,
            signal_id=signal_id,
            metadata={"score": score, "reason": reason, "mode": self.mode},
        )

        exchange_order_id = None
        if self.mode == "live":
            # Place real market order (should fill immediately, but still verify)
            try:
                order = await self.exchange.place_market_order(
                    symbol=self.symbol,
                    side="sell",
                    quantity=quantity
                )
                exchange_order_id = str(order.get("orderId"))
                logger.info(f"Exit order placed on exchange: {exchange_order_id}")

                # Update order with exchange ID
                await update_order_submitted(self.db_pool, db_order_id, exchange_order_id)

            except ExchangeError as e:
                logger.error(f"Failed to place exit order: {e}")
                await update_order_rejected(self.db_pool, db_order_id, str(e))
                await log_exception(
                    self.db_pool, e,
                    severity=ErrorSeverity.CRITICAL,  # Exit failure is critical
                    category=ErrorCategory.ORDER,
                    context={"symbol": self.symbol, "side": "sell", "reason": reason},
                    run_id=self.run_id,
                )
                return
        else:
            # Paper trading - generate simulated order ID
            exchange_order_id = f"paper_{uuid4().hex[:8]}"
            logger.info(f"[PAPER] Exit order placed: {exchange_order_id}")

        # Store pending exit order for fill tracking
        self.pending_order = {
            "db_order_id": db_order_id,
            "exchange_order_id": exchange_order_id,
            "side": "sell",
            "price": price,
            "quantity": quantity,
            "exit_reason": reason,
            "score": score,
            "signals": signals.copy(),
        }

        logger.info(f"Exit order pending: {exchange_order_id} | Price: {price:.2f} | Reason: {reason}")

    async def _store_candles(self, candles: list):
        """Store candles in database."""
        query = """
            INSERT INTO candles (time, symbol, timeframe, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (time, symbol, timeframe) DO NOTHING
        """
        async with self.db_pool.acquire() as conn:
            for candle in candles[-10:]:  # Only store last 10 (most likely new)
                await conn.execute(
                    query,
                    candle["time"],
                    self.symbol,
                    self.timeframe,
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    candle["volume"]
                )

    async def _log_signal(
        self,
        signal_type: str,
        price: Decimal,
        score: float,
        signals: Dict[str, float]
    ) -> Optional[UUID]:
        """Log signal to database and return signal ID."""
        query = """
            INSERT INTO signals (
                run_id, time, symbol, signal_type, weighted_score,
                weights_snapshot, indicators_snapshot
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                self.run_id,
                datetime.now(timezone.utc),
                self.symbol,
                signal_type,
                score,
                json.dumps(self.weights),
                json.dumps(signals)
            )
        return row["id"] if row else None

    async def _create_trade_entry(
        self,
        entry_price: Decimal,
        quantity: Decimal,
        entry_time: datetime,
        entry_order_id: UUID,
    ) -> UUID:
        """
        Create trade entry in database when position opens.
        Returns trade_id to track the ongoing trade.
        """
        # Calculate entry commission (0.1% of entry value)
        entry_commission = quantity * entry_price * Decimal("0.001")

        query = """
            INSERT INTO trades (
                run_id, symbol, side, entry_order_id,
                opened_at, entry_price, quantity,
                commission_total, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                self.run_id,
                self.symbol,
                "long",
                entry_order_id,
                entry_time,
                entry_price,
                quantity,
                entry_commission,
                "open",
            )

        trade_id = row["id"]

        logger.info(
            f"Trade entry created: id={trade_id}, entry={entry_price:.2f}, qty={quantity:.6f}",
            extra={
                "run_id": self.run_id,
                "trade_id": str(trade_id),
                "entry_order_id": str(entry_order_id),
            }
        )

        return trade_id

    async def _log_trade(
        self,
        trade_id: UUID,
        exit_price: Decimal,
        exit_reason: str,
        pnl: Decimal,
        pnl_pct: float,
        exit_score: float,
        exit_signals: Dict[str, float],
        exit_order_id: Optional[UUID] = None,
    ):
        """Update trade with exit data and mark as closed."""
        # Calculate duration
        entry_time = self.position["entry_time"]
        exit_time = datetime.now(timezone.utc)
        duration_seconds = int((exit_time - entry_time).total_seconds())

        # Calculate exit commission and add to total (0.1% of exit value)
        quantity = self.position["quantity"]
        entry_price = self.position["entry_price"]
        exit_commission = quantity * exit_price * Decimal("0.001")

        # Total commission = entry commission (already in DB) + exit commission
        # We'll UPDATE by adding the exit commission to existing commission_total
        query = """
            UPDATE trades
            SET
                exit_order_id = $1,
                exit_price = $2,
                closed_at = $3,
                duration_seconds = $4,
                pnl = $5,
                pnl_percent = $6,
                commission_total = commission_total + $7,
                status = 'closed'
            WHERE id = $8
        """

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                exit_order_id,
                exit_price,
                exit_time,
                duration_seconds,
                pnl,
                pnl_pct,
                exit_commission,
                trade_id,
            )

        logger.info(
            f"Trade closed: id={trade_id}, entry={entry_price:.2f}, exit={exit_price:.2f}, "
            f"pnl={pnl:.2f} ({pnl_pct:+.2f}%), duration={duration_seconds}s",
            extra={
                "run_id": self.run_id,
                "trade_id": str(trade_id),
                "exit_order_id": str(exit_order_id) if exit_order_id else None,
            }
        )

    async def _publish_heartbeat(self):
        """Publish heartbeat to Redis."""
        if not self.redis_client:
            return

        try:
            heartbeat = {
                "run_id": str(self.run_id),
                "mode": self.mode,
                "symbol": self.symbol,
                "capital": float(self.capital),
                "position": bool(self.position),
                "trades_today": self.trades_today,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish("bot:heartbeat", json.dumps(heartbeat))
        except Exception as e:
            logger.debug(f"Failed to publish heartbeat: {e}")

    async def _publish_trade_event(
        self,
        event_type: str,
        price: Decimal,
        quantity: Decimal,
        pnl: Optional[Decimal] = None
    ):
        """Publish trade event to Redis."""
        if not self.redis_client:
            return

        try:
            event = {
                "run_id": str(self.run_id),
                "event": event_type,
                "symbol": self.symbol,
                "price": float(price),
                "quantity": float(quantity),
                "pnl": float(pnl) if pnl else None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish("bot:trades", json.dumps(event))
        except Exception as e:
            logger.debug(f"Failed to publish trade event: {e}")

    def _parse_timeframe_minutes(self, timeframe: str) -> int:
        """Parse timeframe string to minutes."""
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        if unit == 'm':
            return value
        elif unit == 'h':
            return value * 60
        elif unit == 'd':
            return value * 60 * 24
        elif unit == 'w':
            return value * 60 * 24 * 7
        else:
            return 15  # Default


async def run_trading_loop(
    symbol: str,
    timeframe: str,
    mode: str,
    testnet: bool,
    verbose: bool = False
):
    """
    Main entry point for trading loop.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe
        mode: 'paper' or 'live'
        testnet: Use testnet
        verbose: Enable verbose logging
    """
    load_dotenv()

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Register signal handlers for graceful shutdown
    # Use different approach for Windows vs Unix
    loop = asyncio.get_running_loop()
    signals_registered = False

    def shutdown_handler():
        global shutdown_requested
        logger.info("Received shutdown signal, initiating graceful shutdown...")
        shutdown_requested = True

    # Try to use asyncio signal handlers (Unix)
    try:
        loop.add_signal_handler(signal.SIGINT, shutdown_handler)
        loop.add_signal_handler(signal.SIGTERM, shutdown_handler)
        signals_registered = True
        logger.debug("Registered asyncio signal handlers (Unix)")
    except NotImplementedError:
        # On Windows, add_signal_handler is not implemented
        # Fall back to traditional signal handlers
        def sync_signal_handler(signum, frame):
            global shutdown_requested
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            shutdown_requested = True
            # Set a flag on the event loop to stop it gracefully
            loop.call_soon_threadsafe(lambda: None)

        signal.signal(signal.SIGINT, sync_signal_handler)
        signal.signal(signal.SIGTERM, sync_signal_handler)
        logger.debug("Registered traditional signal handlers (Windows)")

    bot = TradingBot(
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
        testnet=testnet
    )

    try:
        await bot.start()
    finally:
        # Remove signal handlers on exit
        if signals_registered:
            try:
                loop.remove_signal_handler(signal.SIGINT)
                loop.remove_signal_handler(signal.SIGTERM)
            except Exception:
                pass


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run trading bot (paper or live mode)"
    )

    parser.add_argument('--mode', choices=['paper', 'live'], required=True,
        help='Trading mode')
    parser.add_argument('--symbol', default='BTCUSDT',
        help='Trading symbol (default: BTCUSDT)')
    parser.add_argument('--timeframe', default='15m',
        help='Candle timeframe (default: 15m)')
    parser.add_argument('--testnet', action='store_true',
        help='Use Binance testnet (required for live mode testing)')
    parser.add_argument('-v', '--verbose', action='store_true',
        help='Enable verbose logging')

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    await run_trading_loop(
        symbol=args.symbol,
        timeframe=args.timeframe,
        mode=args.mode,
        testnet=args.testnet or args.mode == 'paper',
        verbose=args.verbose
    )


if __name__ == "__main__":
    asyncio.run(main())
