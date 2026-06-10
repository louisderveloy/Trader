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
6. Logs everything to database

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
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import uuid4, UUID

import asyncpg
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
from notifications.discord import DiscordNotifier
from utils.instance_lock import InstanceLockManager

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
        self.discord_notifier: Optional[DiscordNotifier] = None

        # State
        self.run_id: Optional[int] = None  # Set when run record is created
        self.capital = initial_capital
        self.position: Optional[Dict[str, Any]] = None  # Current position
        self.weights: Dict[str, float] = {}
        self.weights_set_id: Optional[UUID] = None  # Active weights set ID for score logging
        self.is_running = False
        self._stop_called = False  # Guards against double-stop
        self.lock_connection: Optional[asyncpg.Connection] = None  # Connection holding instance lock
        self.config_listener_conn: Optional[asyncpg.Connection] = None  # Dedicated connection for LISTEN
        self.config_listener_task: Optional[asyncio.Task] = None  # Background task for config updates

        # Configuration (loaded from database in start())
        self.config: Optional[StrategyEngineConfig] = None
        self.config_id: Optional[UUID] = None  # Database config ID for score logging

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
        # Only show initial capital for paper trading
        if self.mode == "paper":
            logger.info(f"Simulated Capital: {self.initial_capital} USDT")
        else:
            logger.info("Balance: Will fetch from exchange...")
        logger.info("=" * 80)

        try:
            # Initialize components
            await self._init_database()

            # Acquire instance lock BEFORE proceeding
            # This returns a persistent connection that must be held for the duration
            self.lock_connection = await InstanceLockManager.acquire_lock_connection(self.db_pool, self.mode)
            if not self.lock_connection:
                # Lock is held by another instance - check for details
                existing_run = await InstanceLockManager.check_existing_runs(self.db_pool, self.mode)
                error_msg = f"Cannot start {self.mode} trading: Another instance is already running"
                if existing_run:
                    error_msg += f"\n  Active run_id: {existing_run['id']}"
                    error_msg += f"\n  Started at: {existing_run['started_at']}"
                    error_msg += f"\n  Symbol: {existing_run.get('symbol', 'unknown')}"
                    error_msg += f"\n  Environment: {existing_run.get('environment', 'unknown')}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            # Advisory lock acquired — we are the sole instance.
            # Clean up any runs left in running/pending state by a previous crash or
            # container kill (SIGKILL leaves no time for graceful DB cleanup).
            await InstanceLockManager.cleanup_stale_runs(self.db_pool, self.mode)

            await self._load_config()
            await self._init_exchange()
            await self._init_discord()
            await self._load_weights()
            await self._create_run_record()

            # Start config update listener (non-blocking background task)
            await self._start_config_listener()

            # Log initial balance
            if self.mode == "live":
                try:
                    balance = await self.exchange.get_balance("USDT")
                    logger.info("=" * 80)
                    logger.info(f"ACCOUNT BALANCE:")
                    logger.info(f"  Free: {balance['free']} USDT")
                    logger.info(f"  Locked: {balance['locked']} USDT")
                    logger.info(f"  Total: {balance['total']} USDT")
                    logger.info("=" * 80)
                except Exception as e:
                    logger.warning(f"Could not fetch initial balance: {e}")
            else:
                logger.info("=" * 80)
                logger.info(f"SIMULATED CAPITAL: {self.capital} USDT")
                logger.info("=" * 80)

            # Send bot started notification
            if self.discord_notifier:
                try:
                    await self.discord_notifier.notify_bot_started(
                        mode=self.mode,
                        symbol=self.symbol,
                        testnet=self.testnet,
                    )
                except Exception as e:
                    logger.error(f"Failed to send bot started notification: {e}")

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
        if self._stop_called:
            return
        self._stop_called = True

        logger.info("Stopping trading bot...")
        self.is_running = False

        # SAFEGUARD: Check and close any open positions before shutdown
        if self.db_pool and self.run_id:
            await self._ensure_all_positions_closed()

        # Update run status
        if self.db_pool and self.run_id:
            try:
                await self._update_run_status("cancelled" if shutdown_requested else "completed")
            except Exception as e:
                logger.error(f"Failed to update run status: {e}")

        # Send bot stopped notification before cleanup
        if self.discord_notifier:
            try:
                reason = "User requested shutdown" if shutdown_requested else "Completed normally"
                await self.discord_notifier.notify_bot_stopped(
                    reason=reason,
                    trades_today=self.trades_today,
                    capital=self.capital,
                )
            except Exception as e:
                logger.error(f"Failed to send bot stopped notification: {e}")

        # Cleanup connections
        if self.exchange:
            try:
                await self.exchange.disconnect()
            except Exception as e:
                logger.error(f"Failed to disconnect exchange: {e}")

        if self.discord_notifier:
            try:
                await self.discord_notifier.close()
            except Exception as e:
                logger.error(f"Failed to close Discord notifier: {e}")

        # Stop config update listener
        await self._stop_config_listener()

        # Release instance lock before closing pool
        if self.lock_connection and self.db_pool:
            try:
                await InstanceLockManager.release_lock_connection(
                    self.db_pool, self.lock_connection, self.mode
                )
                self.lock_connection = None
            except Exception as e:
                logger.error(f"Failed to release instance lock: {e}")

        # Close database pool
        if self.db_pool:
            try:
                await self.db_pool.close()
            except Exception as e:
                logger.error(f"Failed to close database pool: {e}")

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
            self.config, self.config_id = await StrategyEngineConfig.from_db(self.db_pool)
            logger.info("Configuration loaded from database")
            logger.info(f"  Config ID: {self.config_id}")
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

    async def _init_discord(self):
        """Initialize Discord notifier."""
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url or webhook_url.startswith("https://discord.com/api/webhooks/YOUR_WEBHOOK"):
            logger.warning("Discord webhook not configured, notifications disabled")
            self.discord_notifier = None
            return

        # Check if notifications are enabled
        notify_enabled = os.getenv("NOTIFY_TRADE_OPENED", "true").lower() == "true"
        if not notify_enabled:
            logger.info("Discord notifications disabled in config")
            self.discord_notifier = None
            return

        rate_limit_seconds = int(os.getenv("DISCORD_RATE_LIMIT_PERIOD_SECONDS", "60"))
        self.discord_notifier = DiscordNotifier(
            webhook_url=webhook_url,
            db_pool=self.db_pool,
            rate_limit_seconds=rate_limit_seconds,
            enabled=True,
        )
        logger.info("Discord notifier initialized")

    async def _load_weights(self):
        """Load active weights from database."""
        query = """
            SELECT id, weights FROM weights_sets
            WHERE is_active = true
            LIMIT 1
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query)
            if row:
                weights = row["weights"]
                self.weights_set_id = row["id"]

                # Parse JSON string if needed
                if isinstance(weights, str):
                    weights = json.loads(weights)

                # Remove 'weight_' prefix from keys if present
                # Database stores as "weight_ema", but strategy expects "ema"
                self.weights = {
                    k.replace('weight_', ''): v
                    for k, v in weights.items()
                }
                logger.info(
                    f"Loaded active weights (set_id: {self.weights_set_id}): {json.dumps(self.weights, indent=2)}")
            else:
                # Default weights
                self.weights = {
                    "ema": 0.125, "macd": 0.125, "rsi": 0.125, "stoch_rsi": 0.125,
                    "bollinger": 0.125, "atr": 0.125, "obv": 0.10,
                    "fear_greed": 0.10, "user_indicator": 0.05
                }
                self.weights_set_id = None
                logger.warning("No active weights set, using defaults")

    async def _log_score(
            self,
            weighted_score: float,
            signals: Dict[str, float],
            current_time: datetime,
            order_id: Optional[UUID] = None
    ):
        """
        Log score calculation to score_logs table for statistical analysis.

        Args:
            weighted_score: Calculated weighted score
            signals: Dictionary of indicator signals
            current_time: Timestamp of calculation
            order_id: Optional order ID if score resulted in an order
        """
        # Skip logging if we don't have all required IDs
        if self.run_id is None or self.config_id is None or self.weights_set_id is None:
            logger.debug(
                f"Skipping score logging - missing IDs: "
                f"run_id={self.run_id}, config_id={self.config_id}, weights_set_id={self.weights_set_id}"
            )
            return

        # Build indicators snapshot
        indicators_snapshot = {
            "timestamp": current_time.isoformat(),
            "signals": signals,
            "weights": self.weights
        }

        async with self.db_pool.acquire() as conn:
            try:
                query = """
                    INSERT INTO score_logs (
                        run_id, config_id, weights_set_id, order_id,
                        time, symbol, weighted_score, indicators_snapshot
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """
                score_log_id = await conn.fetchval(
                    query,
                    self.run_id,
                    self.config_id,
                    self.weights_set_id,
                    order_id,
                    current_time,
                    self.symbol,
                    Decimal(str(weighted_score)),
                    json.dumps(indicators_snapshot)
                )
                logger.debug(f"Score logged to database (id: {score_log_id})")
            except Exception as e:
                logger.error(f"Failed to log score to database: {e}")

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
                now  # started_at
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

        # Send Discord notification when run completes
        if status in ("completed", "failed") and self.discord_notifier:
            try:
                # Fetch run details
                query_run = """
                    SELECT run_type, symbol, environment, start_date, completed_at
                    FROM runs WHERE id = $1
                """
                async with self.db_pool.acquire() as conn:
                    run = await conn.fetchrow(query_run, self.run_id)

                if run:
                    await self.discord_notifier.notify_run_completed(
                        run_type=run["run_type"],
                        symbol=run["symbol"],
                        environment=run["environment"],
                        start_date=run["start_date"],
                        end_date=run["completed_at"],
                    )
            except Exception as e:
                logger.error(f"Failed to send run completion notification: {e}")

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
        current_time = candles[-1]["time"]  # Already a datetime object from exchange

        # Log score to database for statistical analysis
        await self._log_score(weighted_score, signals, current_time)

        # Get current balance for logging
        if self.mode == "live":
            try:
                balance = await self.exchange.get_balance("USDT")
                balance_str = f"Balance: {balance['free']:.2f} USDT"
            except Exception:
                balance_str = "Balance: N/A"
        else:
            balance_str = f"Capital: {self.capital:.2f} USDT"

        logger.info(
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
            f"Price: {current_price:.2f} | Score: {weighted_score:.3f} | "
            f"Position: {'LONG' if self.position else 'NONE'} | "
            f"Pending: {bool(self.pending_order)} | "
            f"{balance_str}"
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
            logger.info(
                f"  {indicator:15s}: signal={signal_val:+.3f}, weight={weight_val:.3f}, contrib={contrib_val:+.4f}")
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

        # Validate exchange_order_id
        if not exchange_order_id or exchange_order_id == "None":
            logger.error(f"Invalid exchange_order_id: {exchange_order_id}. Cancelling pending order.")
            await update_order_rejected(self.db_pool, order_id, "Invalid exchange order ID")
            self.pending_order = None
            return

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

                # Note: normalized response has lowercase status
                status = order_status.get("status", "")

                if status == "filled":
                    # Order fully filled
                    is_filled = True
                    # Use filled_price from normalized response (average fill price)
                    filled_price = order_status.get("filled_price", order_price)
                    if filled_price is None:
                        filled_price = order_price

                    # Estimate commission (normalized response doesn't include commission)
                    commission = quantity * filled_price * Decimal("0.001")

                    logger.info(f"Order {exchange_order_id} FILLED at {filled_price}")

                elif status in ("cancelled", "rejected"):
                    # Order failed
                    logger.warning(f"Order {exchange_order_id} {status.upper()}")
                    await update_order_cancelled(self.db_pool, order_id, f"Exchange status: {status}")
                    self.pending_order = None
                    return

                else:
                    # Still pending (status = "pending")
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

            logger.info(f"[PAPER] Order filled at {filled_price} (slippage: {slippage_pct * 100:.3f}%)")

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

            # Send Discord notification for order filled
            if self.discord_notifier:
                try:
                    await self.discord_notifier.notify_order_filled(
                        symbol=self.symbol,
                        side=side,
                        filled_price=filled_price,
                        filled_quantity=quantity,
                        order_type=self.pending_order.get("order_type", "limit"),
                        commission=commission,
                        testnet=self.testnet,
                    )
                except Exception as e:
                    logger.error(f"Failed to send Discord notification: {e}")

            # Update position state
            if side == "buy":
                # Entry order filled
                stop_loss = self.pending_order["stop_loss"]
                take_profit = self.pending_order["take_profit"]
                entry_score = self.pending_order["score"]
                entry_signals = self.pending_order["signals"]
                entry_time = datetime.now(timezone.utc)

                # Calculate entry commission (0.1% of entry value)
                entry_commission = quantity * filled_price * Decimal("0.001")

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
                    "entry_commission": entry_commission,
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

                # Send Discord notification for trade opened
                if self.discord_notifier:
                    try:
                        await self.discord_notifier.notify_trade_opened(
                            symbol=self.symbol,
                            side="long",  # Assuming all trades are long for now
                            price=filled_price,
                            quantity=quantity,
                            score=entry_score,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send trade opened notification: {e}")

            elif side == "sell":
                # Exit order filled - trade completed
                entry_price = self.position["entry_price"]
                entry_commission = self.position["entry_commission"]

                # Calculate exit commission (0.1% of exit value)
                exit_commission = quantity * filled_price * Decimal("0.001")

                # Calculate gross P&L
                gross_pnl = (filled_price - entry_price) * quantity

                # Calculate net P&L (deduct both entry and exit commissions)
                net_pnl = gross_pnl - entry_commission - exit_commission
                net_pnl_pct = (net_pnl / (entry_price * quantity)) * 100

                # Update capital with NET P&L (after fees)
                self.capital += net_pnl

                # Update trade with exit data
                exit_reason = self.pending_order["exit_reason"]
                exit_score = self.pending_order["score"]
                exit_signals = self.pending_order["signals"]

                await self._log_trade(
                    trade_id=self.position["trade_id"],
                    exit_price=filled_price,
                    exit_reason=exit_reason,
                    net_pnl=net_pnl,
                    net_pnl_pct=net_pnl_pct,
                    exit_score=exit_score,
                    exit_signals=exit_signals,
                    exit_order_id=order_id,
                    exit_commission=exit_commission,
                )

                logger.info("=" * 60)
                logger.info(f"POSITION CLOSED")
                logger.info(f"Entry: {entry_price:.2f} | Exit: {filled_price:.2f}")
                logger.info(f"P&L: {net_pnl:.2f} USDT ({net_pnl_pct:+.2f}%) [NET after fees]")
                logger.info(
                    f"Fees: {entry_commission + exit_commission:.2f} USDT (entry: {entry_commission:.2f}, exit: {exit_commission:.2f})")
                logger.info(f"Capital: {self.capital:.2f} USDT")
                logger.info("=" * 60)

                # Send Discord notification for trade completion
                if self.discord_notifier:
                    try:
                        await self.discord_notifier.notify_trade_closed(
                            symbol=self.symbol,
                            side="long",
                            entry_price=entry_price,
                            exit_price=filled_price,
                            pnl=net_pnl,
                            pnl_pct=float(net_pnl_pct),
                            reason=exit_reason,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send Discord trade completion notification: {e}")

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

    async def _get_available_capital(self) -> Decimal:
        """
        Get available capital for trading.

        In live mode: Fetch actual USDT balance from exchange.
        In paper mode: Use simulated self.capital.

        Returns:
            Available USDT balance
        """
        if self.mode == "live":
            try:
                # Fetch actual USDT balance from exchange
                balance = await self.exchange.get_balance("USDT")
                available = balance["free"]

                logger.debug(
                    f"Exchange balance: {available} USDT (free), "
                    f"{balance['locked']} USDT (locked), "
                    f"{balance['total']} USDT (total)"
                )

                return available

            except Exception as e:
                logger.error(f"Failed to fetch balance from exchange: {e}")
                # Fallback to self.capital if balance fetch fails
                logger.warning(f"Using fallback capital: {self.capital} USDT")
                return self.capital
        else:
            # Paper trading: use simulated capital
            return self.capital

    async def _execute_entry(
            self,
            price: Decimal,
            score: float,
            signals: Dict[str, float]
    ):
        """Execute entry order."""
        # Get available capital (actual balance in live mode, simulated in paper mode)
        available_capital = await self._get_available_capital()

        if available_capital <= 0:
            logger.warning(f"No available capital (balance: {available_capital} USDT). Skipping entry.")
            return

        # Calculate position size: use 95% of available capital
        position_size = available_capital * Decimal("0.95")
        quantity = position_size / price

        # Validate minimum order size
        min_notional = Decimal("10")  # Binance minimum ~10 USDT per order
        order_value = quantity * price
        if order_value < min_notional:
            logger.warning(
                f"Order value {order_value:.2f} USDT below minimum {min_notional} USDT. "
                f"Available capital: {available_capital:.2f} USDT. Skipping entry."
            )
            return

        # Calculate stop-loss and take-profit (simplified: fixed percentages)
        stop_loss = price * Decimal("0.98")  # 2% stop-loss
        take_profit = price * Decimal("1.04")  # 4% take-profit

        logger.info("=" * 60)
        logger.info(f"ENTRY SIGNAL - Score: {score:.3f}")
        logger.info(f"Available capital: {available_capital:.2f} USDT")
        logger.info(f"Position size: {position_size:.2f} USDT (95% of capital)")
        logger.info(f"Price: {price:.2f} | Quantity: {quantity:.6f}")
        logger.info(f"Order value: {order_value:.2f} USDT")
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
                # Note: normalized order response uses "order_id" not "orderId"
                exchange_order_id = order.get("order_id")
                if not exchange_order_id:
                    raise ExchangeError(f"Order response missing order_id: {order}")
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
        order_type = "limit" if self.mode == "live" else "market"
        self.pending_order = {
            "db_order_id": db_order_id,
            "exchange_order_id": exchange_order_id,
            "side": "buy",
            "price": price,
            "quantity": quantity,
            "order_type": order_type,
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
        entry_commission = self.position["entry_commission"]

        # Calculate estimated exit commission (0.1% of exit value)
        exit_commission = quantity * price * Decimal("0.001")

        # Calculate estimated net P&L (after fees)
        gross_pnl = (price - entry_price) * quantity
        net_pnl = gross_pnl - entry_commission - exit_commission
        net_pnl_pct = (net_pnl / (entry_price * quantity)) * 100

        logger.info("=" * 60)
        logger.info(f"EXIT SIGNAL - Reason: {reason} | Score: {score:.3f}")
        logger.info(f"Entry: {entry_price:.2f} | Exit: {price:.2f}")
        logger.info(f"Estimated P&L: {net_pnl:.2f} USDT ({net_pnl_pct:.2f}%) [NET after fees]")
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
                # Note: normalized order response uses "order_id" not "orderId"
                exchange_order_id = order.get("order_id")
                if not exchange_order_id:
                    raise ExchangeError(f"Order response missing order_id: {order}")
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
            "order_type": "market",
            "exit_reason": reason,
            "score": score,
            "signals": signals.copy(),
        }

        logger.info(f"Exit order pending: {exchange_order_id} | Price: {price:.2f} | Reason: {reason}")

    async def _ensure_all_positions_closed(self):
        """
        Ensure all positions are closed before shutdown.

        This method checks:
        1. In-memory position (self.position)
        2. In-memory pending order (self.pending_order)
        3. Database open trades
        4. For live mode: Binance API open orders

        Any open positions are force-closed at market price.
        Any pending orders are cancelled.
        """
        logger.info("=" * 80)
        logger.info("SAFEGUARD: Checking for open positions before shutdown...")
        logger.info("=" * 80)

        has_open_positions = False

        # 1. Check in-memory pending order
        if self.pending_order:
            logger.warning(f"Found pending order in memory: {self.pending_order.get('exchange_order_id')}")
            has_open_positions = True

            # Cancel pending order if it's an entry order
            if self.pending_order.get("side") == "buy":
                logger.info("Cancelling pending entry order...")
                try:
                    if self.mode == "live" and self.exchange:
                        await self.exchange.cancel_order(
                            self.symbol,
                            self.pending_order.get("exchange_order_id")
                        )
                        logger.info("Pending entry order cancelled on exchange")

                    # Update order status in database
                    await update_order_cancelled(
                        self.db_pool,
                        self.pending_order.get("db_order_id"),
                        "Cancelled due to shutdown"
                    )
                    self.pending_order = None
                    logger.info("Pending entry order cancelled")
                except Exception as e:
                    logger.error(f"Failed to cancel pending order: {e}")

        # 2. Check in-memory position
        if self.position:
            logger.warning(f"Found open position in memory: {self.position}")
            has_open_positions = True

            # Force close position at market price
            logger.info("Force closing position at market price...")
            try:
                # Get current price
                ticker = await self.exchange.get_ticker(self.symbol)
                current_price = Decimal(str(ticker["last_price"]))

                # Execute forced exit
                await self._execute_exit(
                    price=current_price,
                    reason="Forced close on shutdown",
                    score=0.0,
                    signals={}
                )

                # Wait for exit order to be processed
                # In paper mode, the order fills immediately
                # In live mode, market orders typically fill immediately
                await asyncio.sleep(2)

                # Check if order was filled
                if self.pending_order and self.pending_order.get("side") == "sell":
                    # Force fill the exit order
                    await self._check_pending_order(current_price)

                logger.info("Position force closed successfully")
            except Exception as e:
                logger.error(f"Failed to force close position: {e}")

        # 3. Check database for open trades
        try:
            from runs.manager import RunManager
            run_manager = RunManager(self.db_pool)
            open_trades = await run_manager.get_open_trades(self.run_id)

            if open_trades:
                logger.warning(f"Found {len(open_trades)} open trade(s) in database:")
                for trade in open_trades:
                    logger.warning(f"  - Trade ID {trade['id']}: {trade['symbol']} @ {trade['entry_price']}")
                has_open_positions = True

                # If we have open trades in DB but not in memory, log error
                if not self.position:
                    logger.error(
                        "Database has open trades but no position in memory! "
                        "This indicates a state synchronization issue."
                    )
        except Exception as e:
            logger.error(f"Failed to check database for open trades: {e}")

        # 4. For live mode: Check Binance API for open orders
        if self.mode == "live" and self.exchange:
            try:
                logger.info("Checking Binance API for open orders...")
                open_orders = await self.exchange.get_open_orders(self.symbol)

                if open_orders:
                    logger.warning(f"Found {len(open_orders)} open order(s) on Binance:")
                    has_open_positions = True

                    for order in open_orders:
                        logger.warning(
                            f"  - Order {order.get('order_id')}: {order.get('side')} {order.get('quantity')} @ {order.get('price')}")

                        # Cancel each open order
                        try:
                            await self.exchange.cancel_order(
                                self.symbol,
                                order.get("order_id")
                            )
                            logger.info(f"Cancelled order {order.get('order_id')} on Binance")
                        except Exception as e:
                            logger.error(f"Failed to cancel order {order.get('order_id')}: {e}")
                else:
                    logger.info("No open orders found on Binance")
            except Exception as e:
                logger.error(f"Failed to check Binance for open orders: {e}")

        # Summary
        if has_open_positions:
            logger.warning("=" * 80)
            logger.warning("SAFEGUARD: Found and handled open positions")
            logger.warning("=" * 80)
        else:
            logger.info("=" * 80)
            logger.info("SAFEGUARD: No open positions found - safe to shutdown")
            logger.info("=" * 80)

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
            net_pnl: Decimal,
            net_pnl_pct: float,
            exit_score: float,
            exit_signals: Dict[str, float],
            exit_order_id: Optional[UUID] = None,
            exit_commission: Optional[Decimal] = None,
    ):
        """Update trade with exit data and mark as closed. P&L values are NET (after fees)."""
        # Calculate duration
        entry_time = self.position["entry_time"]
        exit_time = datetime.now(timezone.utc)
        duration_seconds = int((exit_time - entry_time).total_seconds())

        entry_price = self.position["entry_price"]

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
                net_pnl,
                net_pnl_pct,
                exit_commission,
                trade_id,
            )

        logger.info(
            f"Trade closed: id={trade_id}, entry={entry_price:.2f}, exit={exit_price:.2f}, "
            f"net_pnl={net_pnl:.2f} ({net_pnl_pct:+.2f}%) [after fees], duration={duration_seconds}s",
            extra={
                "run_id": self.run_id,
                "trade_id": str(trade_id),
                "exit_order_id": str(exit_order_id) if exit_order_id else None,
            }
        )

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

    async def _start_config_listener(self):
        """Start listening for config update notifications from PostgreSQL."""
        try:
            # Create a dedicated connection for LISTEN (can't use pooled connection)
            dsn = os.getenv("DATABASE_URL", "")
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
            self.config_listener_conn = await asyncpg.connect(dsn)

            # Add listener for config_updated channel
            await self.config_listener_conn.add_listener('config_updated', self._handle_config_notification)

            logger.info("✓ Config update listener started")
        except Exception as e:
            logger.error(f"Failed to start config listener: {e}")
            # Non-fatal - bot can continue without config hot-reload

    async def _handle_config_notification(self, connection, pid, channel, payload):
        """
        Handle config update notification from PostgreSQL.

        Args:
            connection: Database connection
            pid: Process ID of notifying backend
            channel: Notification channel name
            payload: JSON payload with config data
        """
        try:
            logger.info("=" * 60)
            logger.info("CONFIG UPDATE NOTIFICATION RECEIVED")
            logger.info(f"  Channel: {channel}")
            logger.info(f"  From PID: {pid}")

            # Parse the notification payload
            try:
                config_data = json.loads(payload)
                logger.info(f"  Config ID: {config_data.get('id')}")
                logger.info(f"  Updated at: {config_data.get('updated_at')}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse config notification payload: {e}")
                return

            # Reload config from database
            await self._reload_config()

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error handling config notification: {e}", exc_info=True)

    async def _reload_config(self):
        """Reload configuration from database (hot reload)."""
        try:
            logger.info("Reloading configuration from database...")

            # Store old config for comparison
            old_config = self.config

            # Load new config
            new_config, new_config_id = await StrategyEngineConfig.from_db(self.db_pool)

            # Log changes
            if old_config:
                logger.info("Configuration changes detected:")
                if old_config.strategy.entry_threshold != new_config.strategy.entry_threshold:
                    logger.info(
                        f"  Entry threshold: {old_config.strategy.entry_threshold} → {new_config.strategy.entry_threshold}")
                if old_config.strategy.exit_threshold != new_config.strategy.exit_threshold:
                    logger.info(
                        f"  Exit threshold: {old_config.strategy.exit_threshold} → {new_config.strategy.exit_threshold}")
                if old_config.strategy.confirmation_candles != new_config.strategy.confirmation_candles:
                    logger.info(
                        f"  Confirmation candles: {old_config.strategy.confirmation_candles} → {new_config.strategy.confirmation_candles}")
                if old_config.risk.max_trades_per_day != new_config.risk.max_trades_per_day:
                    logger.info(
                        f"  Max trades/day: {old_config.risk.max_trades_per_day} → {new_config.risk.max_trades_per_day}")
                if old_config.risk.position_size_mode != new_config.risk.position_size_mode:
                    logger.info(
                        f"  Position size mode: {old_config.risk.position_size_mode.value} → {new_config.risk.position_size_mode.value}")

            # Update config
            self.config = new_config
            self.config_id = new_config_id
            logger.info(f"  New config ID: {new_config_id}")

            # Reload weights (they might have changed too)
            await self._load_weights()

            logger.info("✓ Configuration reloaded successfully")

            # Send Discord notification about config reload
            if self.discord_notifier:
                try:
                    # Note: This is a custom notification, we may need to add a method for it
                    # For now, we'll just log it
                    pass
                except Exception as e:
                    logger.error(f"Failed to send config reload notification: {e}")

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}", exc_info=True)
            logger.warning("Bot will continue using previous configuration")

    async def _stop_config_listener(self):
        """Stop the config update listener."""
        if self.config_listener_conn:
            try:
                await self.config_listener_conn.remove_listener('config_updated', self._handle_config_notification)
                await self.config_listener_conn.close()
                self.config_listener_conn = None
                logger.info("✓ Config update listener stopped")
            except Exception as e:
                logger.error(f"Failed to stop config listener: {e}")


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
