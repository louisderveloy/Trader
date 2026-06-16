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

import pandas as pd

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
from indicators import compute_all_indicators
from strategy.config import StrategyEngineConfig
from strategy.engine import StrategyEngine
from strategy.types import DecisionType, PositionState
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
            initial_capital: Decimal = Decimal("10000"),
            run_id: Optional[int] = None,
    ):
        """
        Initialize trading bot.

        Args:
            symbol: Trading symbol (e.g., BTCUSDC)
            timeframe: Candle timeframe (e.g., 15m)
            mode: Trading mode ('paper' or 'live')
            testnet: Whether to use testnet
            initial_capital: Initial capital for paper trading
            run_id: Pre-created PENDING run to adopt (dashboard supervisor); when
                None the bot creates its own run record (CLI behaviour).
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
        # When provided, the bot adopts this existing PENDING run instead of
        # creating a new one (see _create_run_record).
        self.run_id: Optional[int] = run_id
        self.capital = initial_capital
        self.position: Optional[Dict[str, Any]] = None  # Current position
        self.weights: Dict[str, float] = {}
        self.weights_set_id: Optional[UUID] = None  # Active weights set ID for score logging
        self.is_running = False
        self._stop_called = False  # Guards against double-stop
        self._run_adopted = False  # True once we own the run row (adopted or created)
        self._fatal_error: Optional[Exception] = None  # set if start() aborts
        self.lock_connection: Optional[asyncpg.Connection] = None  # Connection holding instance lock
        self.config_listener_conn: Optional[asyncpg.Connection] = None  # Dedicated connection for LISTEN
        self.config_listener_task: Optional[asyncio.Task] = None  # Background task for config updates

        # Configuration (loaded from database in start())
        self.config: Optional[StrategyEngineConfig] = None
        self.config_id: Optional[UUID] = None  # Database config ID for score logging

        # Strategy engine — owns scoring, anti-repaint confirmation, threshold
        # checks, risk quotas, sizing and SL/TP level computation. The trading
        # loop only executes its decisions and monitors SL/TP price levels.
        self.engine: Optional[StrategyEngine] = None

        # Tracking (informational only; the engine's RiskManager is authoritative
        # for the daily-quota / cooldown gating, sourced from the trades table)
        self.trades_today = 0
        self.last_trade_time: Optional[datetime] = None
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
            # Exclude the run we were launched to adopt — it is legitimately
            # 'pending' and must survive this zombie cleanup.
            await InstanceLockManager.cleanup_stale_runs(
                self.db_pool, self.mode, exclude_run_id=self.run_id
            )

            await self._load_config()
            await self._init_exchange()
            await self._init_discord()
            await self._load_weights()
            await self._create_run_record()
            # We now own this run row (adopted a pending run, or created a new one).
            self._run_adopted = True

            # Initialize the strategy engine (needs config + run_id + db_pool)
            self._init_engine()

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
            self._fatal_error = e
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

        # Update run status — only for a run we actually adopted/created. If start()
        # aborted before adoption (e.g. lock held, adopt failed) we must NOT touch the
        # row: the supervisor will mark it failed, and clobbering it here is what
        # previously recorded never-started runs as 'completed'.
        if self.db_pool and self.run_id and self._run_adopted:
            if shutdown_requested:
                final_status = "cancelled"
            elif self._fatal_error is not None:
                final_status = "failed"
            else:
                final_status = "completed"
            try:
                await self._update_run_status(final_status)
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

        if self.run_id is not None:
            # Adopt a pre-created PENDING run (dashboard supervisor flow): flip it
            # to RUNNING and enrich its snapshot. Fail loudly if it's not adoptable
            # (already running, terminal, or missing) — never silently create one.
            adopt_query = """
                UPDATE runs
                SET status = 'running',
                    environment = $2,
                    symbol = $3,
                    timeframe = $4,
                    config_snapshot = $5,
                    started_at = COALESCE(started_at, $6)
                WHERE id = $1 AND status = 'pending'
                RETURNING id
            """
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    adopt_query,
                    self.run_id,
                    environment,
                    self.symbol,
                    self.timeframe,
                    json.dumps(config_snapshot),
                    now,
                )
            if not row:
                raise RuntimeError(
                    f"Cannot adopt run {self.run_id}: not found or not in 'pending' state"
                )
            logger.info(f"Adopted pre-created run record: {self.run_id}")
            return

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
        """Single iteration of the trading loop.

        Decision-making (scoring, anti-repaint confirmation, thresholds, risk
        quotas, sizing, SL/TP level computation) is delegated to the
        StrategyEngine. This loop only:
          1. Fetches/stores candles and computes indicator signals,
          2. Monitors the open position's SL/TP price levels (software stop),
          3. Executes the engine's entry/exit decisions.
        """
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

        current_price = Decimal(str(candles[-1]["close"]))
        current_time = candles[-1]["time"]  # Already a datetime object from exchange

        # Check for pending order fills FIRST (skip everything else while pending)
        if self.pending_order:
            await self._check_pending_order(current_price)
            return

        # Compute all indicator signals via the shared aggregation helper
        candles_df = self._candles_to_df(candles)
        indicator_results = compute_all_indicators(candles_df)
        signals = {name: r.signal.value for name, r in indicator_results.items()}

        # Keep the engine's position view in sync with execution-layer state
        self._sync_engine_position()

        # Ask the engine for a decision (also logs score + decision snapshot).
        # A decision-computation failure (e.g. SL/TP cannot be derived because an
        # indicator is momentarily unavailable) is treated as a graceful skip for
        # this iteration rather than aborting the loop.
        total_capital = await self._get_available_capital()
        try:
            decision = await self.engine.make_decision(
                candles=candles,
                indicator_results=indicator_results,
                current_price=current_price,
                current_time=current_time,
                total_capital=total_capital,
                symbol=self.symbol,
            )
        except Exception as e:
            logger.warning(f"Decision computation failed this iteration; skipping. ({e})")
            return
        weighted_score = decision.weighted_score

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

        # In position: SL/TP price levels take precedence over signal exits
        if self.position is not None:
            stop_reason = self._price_stop_reason(current_price)
            if stop_reason:
                await self._execute_exit(current_price, stop_reason, weighted_score, signals)
                return
            if decision.decision_type == DecisionType.EXIT:
                await self._execute_exit(current_price, "signal", weighted_score, signals)
            return

        # Flat: act on an entry decision
        if decision.decision_type == DecisionType.ENTRY_LONG:
            await self._execute_entry(decision, current_price, signals)

    def _candles_to_df(self, candles: list) -> pd.DataFrame:
        """Convert the exchange candle dicts to the indicator DataFrame schema.

        Indicators expect columns [timestamp, open, high, low, close, volume];
        the exchange returns dicts keyed by 'time'/'open'/.../'volume'.
        """
        return pd.DataFrame({
            "timestamp": [c["time"] for c in candles],
            "open": [float(c["open"]) for c in candles],
            "high": [float(c["high"]) for c in candles],
            "low": [float(c["low"]) for c in candles],
            "close": [float(c["close"]) for c in candles],
            "volume": [float(c["volume"]) for c in candles],
        })

    def _sync_engine_position(self):
        """Mirror the execution-layer position into the engine's position state."""
        if self.position is not None:
            self.engine.update_position_state(PositionState(
                is_open=True,
                symbol=self.symbol,
                entry_price=self.position.get("entry_price"),
                quantity=self.position.get("quantity"),
                entry_time=self.position.get("entry_time"),
                stop_loss_price=self.position.get("stop_loss"),
                take_profit_price=self.position.get("take_profit"),
            ))
        else:
            self.engine.update_position_state(PositionState(is_open=False))

    def _price_stop_reason(self, price: Decimal) -> Optional[str]:
        """Return 'stop_loss'/'take_profit' if the price breached a stored level.

        This is the software-monitored stop (checked once per iteration). In
        live/testnet a native exchange stop order is the primary protection;
        this acts as a backup. Returns None if no level is breached.
        """
        if not self.position:
            return None
        stop_loss = self.position.get("stop_loss")
        take_profit = self.position.get("take_profit")
        if stop_loss is not None and price <= stop_loss:
            return "stop_loss"
        if take_profit is not None and price >= take_profit:
            return "take_profit"
        return None

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
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
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

    def _init_engine(self):
        """Instantiate the StrategyEngine once config, run_id and db_pool are ready.

        The engine owns weighted scoring, anti-repaint confirmation, entry/exit
        threshold checks, risk quotas (daily trades / cooldown / exposure, sourced
        from the trades table), position sizing and SL/TP level computation.
        """
        self.engine = StrategyEngine(
            config=self.config,
            run_id=self.run_id,
            db_pool=self.db_pool,
            config_id=self.config_id,
        )
        logger.info("Strategy engine wired into trading loop")

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
            decision,
            price: Decimal,
            signals: Dict[str, float]
    ):
        """Execute entry order using the engine's sizing and SL/TP levels.

        Sizing and stop-loss/take-profit come from the StrategyEngine decision
        (ATR-based or fixed per the active config) — no longer hardcoded.
        """
        score = float(decision.weighted_score)

        # Get available capital (actual balance in live mode, simulated in paper mode)
        available_capital = await self._get_available_capital()
        if available_capital <= 0:
            logger.warning(f"No available capital (balance: {available_capital} USDT). Skipping entry.")
            return

        # Position size comes from the engine; clamp so we never order more than
        # the available capital allows (95% buffer for fees/slippage).
        quantity = decision.position_size_qty
        if quantity is None or quantity <= 0:
            logger.warning("Engine returned no position size; skipping entry.")
            return
        order_value = quantity * price
        max_value = available_capital * Decimal("0.95")
        if order_value > max_value:
            quantity = max_value / price
            order_value = quantity * price

        # Validate minimum order size
        min_notional = Decimal("10")  # Binance minimum ~10 USDT per order
        if order_value < min_notional:
            logger.warning(
                f"Order value {order_value:.2f} USDT below minimum {min_notional} USDT. "
                f"Available capital: {available_capital:.2f} USDT. Skipping entry."
            )
            return

        # Stop-loss / take-profit computed by the engine (ATR or fixed per config)
        stop_loss = decision.stop_loss_price
        take_profit = decision.take_profit_price
        if stop_loss is None or take_profit is None:
            logger.warning("Engine decision missing SL/TP levels; skipping entry.")
            return

        logger.info("=" * 60)
        logger.info(f"ENTRY SIGNAL - Score: {score:.3f}")
        logger.info(f"Available capital: {available_capital:.2f} USDT")
        logger.info(f"Position size: {order_value:.2f} USDT | Quantity: {quantity:.6f}")
        logger.info(f"Price: {price:.2f}")
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
            stop_loss_price: Optional[Decimal] = None,
            take_profit_price: Optional[Decimal] = None,
    ) -> UUID:
        """
        Create trade entry in database when position opens.
        Persists the stop-loss / take-profit levels the position was opened with.
        Returns trade_id to track the ongoing trade.
        """
        # Calculate entry commission (0.1% of entry value)
        entry_commission = quantity * entry_price * Decimal("0.001")

        query = """
            INSERT INTO trades (
                run_id, symbol, side, entry_order_id,
                opened_at, entry_price, quantity,
                commission_total, status,
                stop_loss_price, take_profit_price
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
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
                stop_loss_price,
                take_profit_price,
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
                exit_reason = $8,
                status = 'closed'
            WHERE id = $9
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
                exit_reason,
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
        verbose: bool = False,
        run_id: Optional[int] = None,
):
    """
    Main entry point for trading loop.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe
        mode: 'paper' or 'live'
        testnet: Use testnet
        verbose: Enable verbose logging
        run_id: Pre-created PENDING run to adopt (dashboard supervisor)
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
        testnet=testnet,
        run_id=run_id,
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
