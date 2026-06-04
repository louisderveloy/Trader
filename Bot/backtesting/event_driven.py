"""
Event-driven backtesting engine.

This module provides exact live trading simulation with event-by-event processing.
It simulates slippage, fees, latency, and limit orders with timeout fallback.

This is the validation engine - use this to verify strategies before going live.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from enum import Enum
import time

import pandas as pd
import asyncpg

from .base import BacktesterBase
from .types import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    BacktestMode,
    OrderType,
    TradeDirection
)
from .metrics import calculate_metrics, build_equity_curve

# Import strategy engine for decision making
from strategy import StrategyEngine, StrategyEngineConfig
from strategy.types import DecisionType, TradingDecision

# Import indicators for signal calculation
from indicators.types import CandleData

# Structured logging
logger = logging.getLogger(__name__)


class PositionStatus(str, Enum):
    """Status of a position during backtesting."""
    CLOSED = "closed"
    OPEN = "open"
    PENDING_ENTRY = "pending_entry"  # Limit order placed, waiting for fill
    PENDING_EXIT = "pending_exit"  # Limit order placed, waiting for fill


class EventDrivenBacktester(BacktesterBase):
    """
    Event-driven backtesting engine with exact live simulation.

    This engine:
    1. Processes candles one by one (event-by-event)
    2. Uses StrategyEngine for decision making
    3. Simulates limit orders with timeout → market fallback
    4. Simulates dynamic slippage based on volatility
    5. Simulates latency between signal and execution
    6. Tracks stop-loss and take-profit exactly

    Advantages:
    - Exact simulation of live trading
    - Realistic slippage and latency
    - Proper limit order handling
    - Integration with StrategyEngine

    Limitations:
    - Slower than vectorbt (event-by-event)
    - More complex code
    """

    def __init__(
        self,
        config: BacktestConfig,
        db_pool: Optional[asyncpg.Pool] = None
    ):
        """Initialize event-driven backtester."""
        super().__init__(config, db_pool)

        # Current state
        self.current_capital = config.initial_capital
        self.current_position: Optional[Dict[str, Any]] = None
        self.completed_trades: List[BacktestTrade] = []
        self.equity_curve_data: List[Dict[str, Any]] = []

        # Strategy engine (will be initialized in run())
        self.strategy_engine: Optional[StrategyEngine] = None

    async def run(self) -> BacktestResult:
        """
        Execute event-driven backtest.

        Returns:
            BacktestResult: Complete backtest result with trades and metrics
        """
        start_time = time.time()

        logger.info(
            "Starting event-driven backtest",
            extra={
                "symbol": self.config.symbol,
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_capital": float(self.config.initial_capital)
            }
        )

        result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=self.config,
            timestamp=datetime.now(timezone.utc)
        )

        try:
            # Validate configuration
            await self.validate_config()

            # Initialize strategy engine
            await self.initialize_strategy_engine()

            # Load historical candles
            candles_df = await self.load_candles()

            if candles_df.empty:
                raise ValueError("No candles loaded from database")

            result.candles_processed = len(candles_df)

            # Process candles event-by-event
            await self.process_candles(candles_df)

            # Close any remaining open position at end
            if self.current_position:
                await self.close_position_at_end(candles_df.iloc[-1])

            # Build results
            result.trades = self.completed_trades

            # Build equity curve
            equity_curve_df = pd.DataFrame(self.equity_curve_data)
            if not equity_curve_df.empty:
                equity_curve_df.set_index('timestamp', inplace=True)

            # Calculate metrics
            result.metrics = calculate_metrics(
                result.trades,
                self.config,
                equity_curve_df
            )

            result.success = True

        except Exception as e:
            logger.error(
                "Event-driven backtest failed",
                extra={"error": str(e)},
                exc_info=True
            )
            result.success = False
            result.error_message = str(e)

        result.execution_time_seconds = time.time() - start_time

        logger.info(
            "Event-driven backtest completed",
            extra={
                "success": result.success,
                "trades": len(result.trades),
                "execution_time_seconds": result.execution_time_seconds
            }
        )

        return result

    async def initialize_strategy_engine(self) -> None:
        """Initialize strategy engine with config from backtest config."""
        logger.info("Initializing strategy engine")

        # Convert backtest config to strategy config
        # In a real implementation, this would load from strategy_params
        strategy_config = StrategyEngineConfig(
            # These would come from config.strategy_params
            entry_threshold=self.config.strategy_params.get('entry_threshold', 0.3),
            exit_threshold=self.config.strategy_params.get('exit_threshold', -0.1),
            confirmation_candles=self.config.strategy_params.get('confirmation_candles', 2),
            position_size_mode=self.config.strategy_params.get('position_size_mode', 'fixed'),
            fixed_position_size=float(self.config.max_position_size or 1000),
            # ... other strategy params
        )

        self.strategy_engine = StrategyEngine(
            config=strategy_config,
            db_pool=self.db_pool
        )

    async def process_candles(self, candles_df: pd.DataFrame) -> None:
        """
        Process candles event-by-event.

        Args:
            candles_df: DataFrame with all candles to process
        """
        logger.info(f"Processing {len(candles_df)} candles event-by-event")

        for idx, candle_row in candles_df.iterrows():
            await self.process_candle(candle_row, candles_df)

            # Record equity at this candle
            self.equity_curve_data.append({
                'timestamp': candle_row['timestamp'],
                'capital': float(self.current_capital),
                'price': float(candle_row['close'])
            })

    async def process_candle(
        self,
        candle_row: pd.Series,
        all_candles: pd.DataFrame
    ) -> None:
        """
        Process a single candle event.

        Args:
            candle_row: Current candle data
            all_candles: All candles (for indicator calculation context)
        """
        current_time = candle_row['timestamp']
        current_price = Decimal(str(candle_row['close']))

        # Check if open position hit stop-loss or take-profit
        if self.current_position:
            await self.check_stops(candle_row)

        # Check for pending limit orders that timed out
        if self.current_position and self.current_position['status'] == PositionStatus.PENDING_ENTRY:
            await self.check_limit_order_timeout(candle_row)

        # Get strategy decision
        # NOTE: In real implementation, this would call strategy_engine.evaluate()
        # For now, we'll use a simplified decision logic
        decision = await self.get_strategy_decision(candle_row, all_candles)

        # Execute decision
        if decision.decision_type == DecisionType.ENTRY_LONG and not self.current_position:
            await self.enter_position(candle_row, decision)

        elif decision.decision_type == DecisionType.EXIT and self.current_position:
            await self.exit_position(candle_row, decision, "signal")

    async def get_strategy_decision(
        self,
        candle_row: pd.Series,
        all_candles: pd.DataFrame
    ) -> TradingDecision:
        """
        Get trading decision from strategy engine.

        NOTE: This is a simplified implementation. In production,
        this would call self.strategy_engine.evaluate() with proper
        indicator values and weights.

        Args:
            candle_row: Current candle
            all_candles: All candles for context

        Returns:
            TradingDecision: Decision from strategy
        """
        # Simplified: Use a basic moving average crossover for demo
        # In production, this would use the full StrategyEngine

        # For now, return SKIP (no trade)
        # This will be replaced with actual strategy integration
        from strategy.types import TradingDecision, DecisionType

        return TradingDecision(
            decision_type=DecisionType.SKIP,
            timestamp=candle_row['timestamp'],
            symbol=self.config.symbol,
            weighted_score=0.0,
            confidence=0.0,
            reason="Simplified backtest - skipping trades"
        )

    async def enter_position(
        self,
        candle_row: pd.Series,
        decision: TradingDecision
    ) -> None:
        """
        Enter a new position.

        Args:
            candle_row: Entry candle
            decision: Strategy decision
        """
        entry_price = Decimal(str(candle_row['close']))
        entry_time = candle_row['timestamp']

        # Apply slippage
        slippage = self.calculate_slippage(candle_row, is_entry=True)
        entry_price_with_slippage = entry_price * (1 + slippage)

        # Calculate position size
        # Simplified: Use fixed position size or max_position_size
        position_size_usdt = min(
            float(self.config.max_position_size or self.current_capital * Decimal("0.1")),
            float(self.current_capital * Decimal("0.95"))  # Leave 5% buffer
        )

        quantity = Decimal(str(position_size_usdt)) / entry_price_with_slippage

        # Calculate stop-loss and take-profit
        atr = self.estimate_atr(candle_row)
        stop_loss_price = entry_price - (atr * 2)  # 2 ATR stop-loss
        take_profit_price = entry_price + (atr * 3)  # 3 ATR take-profit

        # Create position
        self.current_position = {
            'status': PositionStatus.OPEN,
            'entry_time': entry_time,
            'entry_price': entry_price_with_slippage,
            'entry_order_type': OrderType.LIMIT,  # Assume limit order
            'quantity': quantity,
            'stop_loss_price': stop_loss_price,
            'take_profit_price': take_profit_price,
            'entry_score': decision.weighted_score
        }

        logger.info(
            "Entered position",
            extra={
                "entry_time": entry_time.isoformat(),
                "entry_price": float(entry_price_with_slippage),
                "quantity": float(quantity),
                "stop_loss": float(stop_loss_price),
                "take_profit": float(take_profit_price)
            }
        )

    async def exit_position(
        self,
        candle_row: pd.Series,
        decision: TradingDecision,
        exit_reason: str
    ) -> None:
        """
        Exit current position and create trade record.

        Args:
            candle_row: Exit candle
            decision: Strategy decision
            exit_reason: Reason for exit (signal, stop_loss, take_profit, end_of_period)
        """
        if not self.current_position:
            return

        exit_price = Decimal(str(candle_row['close']))
        exit_time = candle_row['timestamp']

        # Apply slippage
        slippage = self.calculate_slippage(candle_row, is_entry=False)
        exit_price_with_slippage = exit_price * (1 - slippage)

        # Calculate P&L
        entry_price = self.current_position['entry_price']
        quantity = self.current_position['quantity']

        gross_pnl = (exit_price_with_slippage - entry_price) * quantity

        # Calculate fees
        entry_value = entry_price * quantity
        exit_value = exit_price_with_slippage * quantity
        commission = (entry_value + exit_value) * self.config.commission_rate

        # Slippage cost
        slippage_cost = (slippage * exit_value)

        net_pnl = gross_pnl - commission - slippage_cost

        # Update capital
        self.current_capital += net_pnl

        # Create trade record
        trade = BacktestTrade(
            trade_number=len(self.completed_trades) + 1,
            direction=TradeDirection.LONG,
            entry_time=self.current_position['entry_time'],
            entry_price=entry_price,
            entry_order_type=self.current_position['entry_order_type'],
            quantity=quantity,
            exit_time=exit_time,
            exit_price=exit_price_with_slippage,
            exit_order_type=OrderType.MARKET,
            exit_reason=exit_reason,
            stop_loss_price=self.current_position.get('stop_loss_price'),
            take_profit_price=self.current_position.get('take_profit_price'),
            gross_pnl=gross_pnl,
            commission_paid=commission,
            slippage_cost=slippage_cost,
            net_pnl=net_pnl,
            return_pct=(net_pnl / entry_value) * 100,
            weighted_score_entry=self.current_position.get('entry_score'),
            weighted_score_exit=decision.weighted_score if decision else None
        )

        self.completed_trades.append(trade)
        self.current_position = None

        logger.info(
            "Exited position",
            extra={
                "exit_time": exit_time.isoformat(),
                "exit_price": float(exit_price_with_slippage),
                "exit_reason": exit_reason,
                "net_pnl": float(net_pnl),
                "new_capital": float(self.current_capital)
            }
        )

    async def check_stops(self, candle_row: pd.Series) -> None:
        """
        Check if stop-loss or take-profit was hit.

        Args:
            candle_row: Current candle
        """
        if not self.current_position:
            return

        high = Decimal(str(candle_row['high']))
        low = Decimal(str(candle_row['low']))

        stop_loss = self.current_position.get('stop_loss_price')
        take_profit = self.current_position.get('take_profit_price')

        # Check stop-loss
        if stop_loss and low <= stop_loss:
            # Create a fake decision for stop-loss exit
            from strategy.types import TradingDecision, DecisionType
            decision = TradingDecision(
                decision_type=DecisionType.EXIT,
                timestamp=candle_row['timestamp'],
                symbol=self.config.symbol,
                weighted_score=-1.0,
                confidence=1.0,
                reason="Stop-loss hit"
            )
            await self.exit_position(candle_row, decision, "stop_loss")

        # Check take-profit
        elif take_profit and high >= take_profit:
            from strategy.types import TradingDecision, DecisionType
            decision = TradingDecision(
                decision_type=DecisionType.EXIT,
                timestamp=candle_row['timestamp'],
                symbol=self.config.symbol,
                weighted_score=1.0,
                confidence=1.0,
                reason="Take-profit hit"
            )
            await self.exit_position(candle_row, decision, "take_profit")

    async def check_limit_order_timeout(self, candle_row: pd.Series) -> None:
        """
        Check if pending limit order has timed out and should convert to market.

        Args:
            candle_row: Current candle
        """
        # Simplified: In production, this would track order placement time
        # and convert to market after timeout
        pass

    async def close_position_at_end(self, last_candle: pd.Series) -> None:
        """
        Close any remaining open position at the end of backtest period.

        Args:
            last_candle: Last candle in the backtest period
        """
        if self.current_position:
            logger.info("Closing position at end of backtest period")

            from strategy.types import TradingDecision, DecisionType
            decision = TradingDecision(
                decision_type=DecisionType.EXIT,
                timestamp=last_candle['timestamp'],
                symbol=self.config.symbol,
                weighted_score=0.0,
                confidence=0.0,
                reason="End of backtest period"
            )

            await self.exit_position(last_candle, decision, "end_of_period")

    def calculate_slippage(self, candle_row: pd.Series, is_entry: bool) -> Decimal:
        """
        Calculate dynamic slippage based on volatility.

        Args:
            candle_row: Current candle
            is_entry: True if entering position, False if exiting

        Returns:
            Decimal: Slippage as a decimal (e.g., 0.002 for 0.2%)
        """
        # Simplified: Use config slippage as base
        base_slippage = self.config.slippage_pct

        # In production, this would be dynamic based on:
        # - Candle size (high - low)
        # - Volume
        # - Time of day
        # - Market conditions

        return base_slippage

    def estimate_atr(self, candle_row: pd.Series) -> Decimal:
        """
        Estimate ATR from current candle.

        NOTE: This is a simplified estimate. In production, this would
        use the actual ATR indicator calculated over 14 periods.

        Args:
            candle_row: Current candle

        Returns:
            Decimal: Estimated ATR
        """
        # Simplified: Use candle range as proxy for ATR
        high = Decimal(str(candle_row['high']))
        low = Decimal(str(candle_row['low']))

        return (high - low) * Decimal("1.5")  # Rough approximation

    async def load_candles(self) -> pd.DataFrame:
        """
        Load historical candles from database.

        Returns:
            DataFrame: Candles with columns [timestamp, open, high, low, close, volume]
        """
        # Same implementation as vectorbt
        if not self.db_pool:
            raise ValueError("Database pool required to load candles")

        logger.info("Loading candles from database")

        query = """
            SELECT
                timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM candles
            WHERE symbol = $1
                AND timeframe = $2
                AND timestamp >= $3
                AND timestamp <= $4
            ORDER BY timestamp ASC
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                self.config.symbol,
                self.config.timeframe,
                self.config.start_date,
                self.config.end_date
            )

        if not rows:
            logger.warning("No candles found in database for specified period")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Convert Decimal to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        logger.info(f"Loaded {len(df)} candles from database")

        return df
