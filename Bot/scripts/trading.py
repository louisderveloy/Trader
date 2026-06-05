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
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges import BinanceExchange
from exchanges.exceptions import ExchangeError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


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
        self.run_id = uuid4()
        self.capital = initial_capital
        self.position: Optional[Dict[str, Any]] = None  # Current position
        self.weights: Dict[str, float] = {}
        self.is_running = False

        # Configuration (loaded from database)
        self.entry_threshold = 0.3
        self.exit_threshold = -0.2
        self.confirmation_candles = 2
        self.max_trades_per_day = 5
        self.cooldown_minutes = 60

        # Tracking
        self.trades_today = 0
        self.last_trade_time: Optional[datetime] = None
        self.confirmation_count = 0
        self.pending_signal: Optional[str] = None

    async def start(self):
        """Initialize all components and start trading loop."""
        logger.info("=" * 80)
        logger.info("STARTING TRADING BOT")
        logger.info("=" * 80)
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Mode: {self.mode.upper()}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Network: {'TESTNET' if self.testnet else 'MAINNET'}")
        logger.info(f"Initial Capital: {self.initial_capital} USDT")
        logger.info("=" * 80)

        try:
            # Initialize components
            await self._init_database()
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
        logger.info("Stopping trading bot...")
        self.is_running = False

        # Update run status
        if self.db_pool:
            try:
                await self._update_run_status("cancelled" if shutdown_requested else "completed")
            except Exception as e:
                logger.error(f"Failed to update run status: {e}")

        # Cleanup connections
        if self.exchange:
            await self.exchange.disconnect()
        if self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.close()

        logger.info("Trading bot stopped.")

    async def _init_database(self):
        """Initialize database connection."""
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise ValueError("DATABASE_URL environment variable not set")

        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        self.db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        logger.info("Database connection established")

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
                self.weights = row["weights"]
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

        query = """
            INSERT INTO runs (
                id, run_type, environment, status, symbol, timeframe,
                initial_capital, config_snapshot, started_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        config_snapshot = {
            "mode": self.mode,
            "testnet": self.testnet,
            "weights": self.weights,
            "entry_threshold": self.entry_threshold,
            "exit_threshold": self.exit_threshold,
            "confirmation_candles": self.confirmation_candles,
            "max_trades_per_day": self.max_trades_per_day,
            "cooldown_minutes": self.cooldown_minutes
        }

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                self.run_id,
                "live" if self.mode == "live" else "paper",
                environment,
                "running",
                self.symbol,
                self.timeframe,
                self.initial_capital,
                json.dumps(config_snapshot),
                datetime.now(timezone.utc)
            )
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
                await asyncio.sleep(30)  # Wait before retry
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                await asyncio.sleep(10)

            # Sleep until next check
            await asyncio.sleep(check_interval)

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
            f"Position: {'LONG' if self.position else 'NONE'}"
        )

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
        for indicator, signal in signals.items():
            weight = self.weights.get(indicator, 0.0)
            score += signal * weight
        return max(-1.0, min(1.0, score))

    async def _check_entry(
        self,
        score: float,
        price: Decimal,
        candles: list,
        signals: Dict[str, float]
    ):
        """Check for entry conditions and execute if met."""
        # Check daily trade limit
        if self.trades_today >= self.max_trades_per_day:
            return

        # Check cooldown
        if self.last_trade_time:
            cooldown_end = self.last_trade_time + timedelta(minutes=self.cooldown_minutes)
            if datetime.now(timezone.utc) < cooldown_end:
                return

        # Check entry threshold
        if score >= self.entry_threshold:
            # Anti-repainting confirmation
            if self.pending_signal == "entry":
                self.confirmation_count += 1
            else:
                self.pending_signal = "entry"
                self.confirmation_count = 1

            if self.confirmation_count >= self.confirmation_candles:
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
        elif score <= self.exit_threshold:
            if self.pending_signal == "exit":
                self.confirmation_count += 1
            else:
                self.pending_signal = "exit"
                self.confirmation_count = 1

            if self.confirmation_count >= self.confirmation_candles:
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

        if self.mode == "live":
            # Place real order
            try:
                order = await self.exchange.place_limit_order(
                    symbol=self.symbol,
                    side="buy",
                    quantity=quantity,
                    price=price
                )
                order_id = order.get("orderId")
                logger.info(f"Order placed: {order_id}")
            except ExchangeError as e:
                logger.error(f"Failed to place order: {e}")
                return
        else:
            order_id = f"paper_{uuid4().hex[:8]}"
            logger.info(f"[PAPER] Simulated order: {order_id}")

        # Update state
        self.position = {
            "entry_price": price,
            "entry_time": datetime.now(timezone.utc),
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "order_id": order_id,
            "entry_score": score,
            "entry_signals": signals.copy()
        }
        self.trades_today += 1
        self.last_trade_time = datetime.now(timezone.utc)

        # Log to database
        await self._log_signal("entry", price, score, signals)

        # Publish to Redis
        await self._publish_trade_event("entry", price, quantity)

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

        if self.mode == "live":
            # Place real order
            try:
                order = await self.exchange.place_market_order(
                    symbol=self.symbol,
                    side="sell",
                    quantity=quantity
                )
                order_id = order.get("orderId")
                logger.info(f"Exit order placed: {order_id}")
            except ExchangeError as e:
                logger.error(f"Failed to place exit order: {e}")
                return
        else:
            order_id = f"paper_{uuid4().hex[:8]}"
            logger.info(f"[PAPER] Simulated exit: {order_id}")

        # Update capital
        self.capital += pnl

        # Log trade to database
        await self._log_trade(price, reason, pnl, pnl_pct, score, signals)

        # Log to database
        await self._log_signal("exit", price, score, signals)

        # Publish to Redis
        await self._publish_trade_event("exit", price, quantity, pnl)

        # Clear position
        self.position = None

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
    ):
        """Log signal to database."""
        query = """
            INSERT INTO signals (
                run_id, time, symbol, signal_type, weighted_score,
                decision, weights_snapshot, indicators_snapshot
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                self.run_id,
                datetime.now(timezone.utc),
                self.symbol,
                signal_type,
                score,
                signal_type,
                json.dumps(self.weights),
                json.dumps(signals)
            )

    async def _log_trade(
        self,
        exit_price: Decimal,
        exit_reason: str,
        pnl: Decimal,
        pnl_pct: float,
        exit_score: float,
        exit_signals: Dict[str, float]
    ):
        """Log completed trade to database."""
        query = """
            INSERT INTO trades (
                run_id, symbol, side, opened_at, closed_at,
                entry_price, exit_price, quantity, pnl, pnl_pct,
                exit_reason, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """
        metadata = {
            "entry_score": self.position["entry_score"],
            "exit_score": exit_score,
            "entry_signals": self.position["entry_signals"],
            "exit_signals": exit_signals
        }

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                self.run_id,
                self.symbol,
                "long",
                self.position["entry_time"],
                datetime.now(timezone.utc),
                self.position["entry_price"],
                exit_price,
                self.position["quantity"],
                pnl,
                pnl_pct,
                exit_reason,
                json.dumps(metadata)
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
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot = TradingBot(
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
        testnet=testnet
    )

    await bot.start()


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
