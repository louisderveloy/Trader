"""
Vectorbt-based backtesting engine.

This module provides fast, vectorized backtesting using the vectorbt library.
It's optimized for Optuna optimization runs where speed is critical.

Note: This implementation is approximate (assumes instant fills) and should
be validated against the event-driven backtester for production use.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
import time

import pandas as pd
import numpy as np
import vectorbt as vbt
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

# Import indicator modules for signal calculation
from indicators import ema, macd, rsi, stoch_rsi, bollinger, atr, obv, fear_greed

# Structured logging
logger = logging.getLogger(__name__)


class VectorbtBacktester(BacktesterBase):
    """
    Fast vectorized backtesting using vectorbt.

    This engine:
    1. Loads candles from database
    2. Calculates all indicator signals
    3. Computes weighted scores vectorially
    4. Generates entry/exit signals
    5. Runs portfolio simulation with vectorbt
    6. Calculates standardized metrics

    Advantages:
    - Very fast (vectorized operations)
    - Good for optimization (many iterations)

    Limitations:
    - Assumes instant fills at close price
    - Simplified slippage model (flat percentage)
    - No limit order simulation
    - No latency simulation
    """

    def __init__(
        self,
        config: BacktestConfig,
        db_pool: Optional[asyncpg.Pool] = None
    ):
        """Initialize vectorbt backtester."""
        super().__init__(config, db_pool)
        self.candles_df: Optional[pd.DataFrame] = None
        self.signals_df: Optional[pd.DataFrame] = None

    async def run(self) -> BacktestResult:
        """
        Execute vectorbt backtest.

        Returns:
            BacktestResult: Complete backtest result with trades and metrics
        """
        start_time = time.time()

        logger.info(
            "Starting vectorbt backtest",
            extra={
                "symbol": self.config.symbol,
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_capital": float(self.config.initial_capital)
            }
        )

        result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=self.config,
            timestamp=datetime.now(timezone.utc)
        )

        try:
            # Validate configuration
            await self.validate_config()

            # Load historical candles
            self.candles_df = await self.load_candles()

            if self.candles_df.empty:
                raise ValueError("No candles loaded from database")

            result.candles_processed = len(self.candles_df)

            # Calculate all indicator signals
            await self.calculate_signals()

            # Generate entry/exit signals from weighted scores
            entries, exits = self.generate_entry_exit_signals()

            # Run portfolio simulation
            portfolio = self.run_portfolio_simulation(entries, exits)

            # Extract trades from portfolio
            result.trades = self.extract_trades(portfolio)

            # Build equity curve
            equity_curve = build_equity_curve(
                result.trades,
                self.config.initial_capital,
                self.candles_df
            )

            # Calculate metrics
            result.metrics = calculate_metrics(
                result.trades,
                self.config,
                equity_curve
            )

            result.success = True

        except Exception as e:
            logger.error(
                "Vectorbt backtest failed",
                extra={"error": str(e)},
                exc_info=True
            )
            result.success = False
            result.error_message = str(e)

        result.execution_time_seconds = time.time() - start_time

        logger.info(
            "Vectorbt backtest completed",
            extra={
                "success": result.success,
                "trades": len(result.trades),
                "execution_time_seconds": result.execution_time_seconds
            }
        )

        return result

    async def load_candles(self) -> pd.DataFrame:
        """
        Load historical candles from database.

        Returns:
            DataFrame: Candles with columns [timestamp, open, high, low, close, volume]
        """
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

        # Convert Decimal to float for vectorbt compatibility
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # Set timestamp as index
        df.set_index('timestamp', inplace=True)

        logger.info(f"Loaded {len(df)} candles from database")

        return df

    async def calculate_signals(self) -> None:
        """
        Calculate all indicator signals and weighted scores.

        Populates self.signals_df with:
        - Individual indicator signals
        - Weighted score
        """
        logger.info("Calculating indicator signals")

        if self.candles_df is None or self.candles_df.empty:
            raise ValueError("No candles available for signal calculation")

        # Convert DataFrame to candles format for indicators
        candles = self.candles_df.reset_index().to_dict('records')

        # Initialize signals DataFrame
        self.signals_df = pd.DataFrame(index=self.candles_df.index)

        # Load weights (or use defaults)
        weights = self.config.weights or self._get_default_weights()

        # Calculate each indicator and its signal
        # Note: In production, these would come from the database weights_sets table

        # EMA
        ema_result = ema.compute(candles, self.config.strategy_params.get('ema', {}))
        ema_signal = ema.to_signal(ema_result.values)
        self.signals_df['ema_signal'] = ema_signal.value

        # MACD
        macd_result = macd.compute(candles, self.config.strategy_params.get('macd', {}))
        macd_signal = macd.to_signal(macd_result.values)
        self.signals_df['macd_signal'] = macd_signal.value

        # RSI
        rsi_result = rsi.compute(candles, self.config.strategy_params.get('rsi', {}))
        rsi_signal = rsi.to_signal(rsi_result.values)
        self.signals_df['rsi_signal'] = rsi_signal.value

        # Stochastic RSI
        stoch_result = stoch_rsi.compute(candles, self.config.strategy_params.get('stoch_rsi', {}))
        stoch_signal = stoch_rsi.to_signal(stoch_result.values)
        self.signals_df['stoch_rsi_signal'] = stoch_signal.value

        # Bollinger Bands
        bb_result = bollinger.compute(candles, self.config.strategy_params.get('bollinger', {}))
        bb_signal = bollinger.to_signal(bb_result.values)
        self.signals_df['bollinger_signal'] = bb_signal.value

        # ATR
        atr_result = atr.compute(candles, self.config.strategy_params.get('atr', {}))
        atr_signal = atr.to_signal(atr_result.values)
        self.signals_df['atr_signal'] = atr_signal.value

        # OBV
        obv_result = obv.compute(candles, {})
        obv_signal = obv.to_signal(obv_result.values)
        self.signals_df['obv_signal'] = obv_signal.value

        # Fear & Greed (simplified - use neutral 0.0 for backtesting)
        self.signals_df['fear_greed_signal'] = 0.0

        # User indicator (simplified - use neutral 0.0 for backtesting)
        self.signals_df['user_signal'] = 0.0

        # Calculate weighted score: Σ (signal_i × weight_i)
        weighted_score = (
            self.signals_df['ema_signal'] * weights.get('ema', 0.15) +
            self.signals_df['macd_signal'] * weights.get('macd', 0.20) +
            self.signals_df['rsi_signal'] * weights.get('rsi', 0.15) +
            self.signals_df['stoch_rsi_signal'] * weights.get('stoch_rsi', 0.10) +
            self.signals_df['bollinger_signal'] * weights.get('bollinger', 0.10) +
            self.signals_df['atr_signal'] * weights.get('atr', 0.10) +
            self.signals_df['obv_signal'] * weights.get('obv', 0.10) +
            self.signals_df['fear_greed_signal'] * weights.get('fear_greed', 0.05) +
            self.signals_df['user_signal'] * weights.get('user', 0.05)
        )

        self.signals_df['weighted_score'] = weighted_score

        logger.info(
            "Signals calculated",
            extra={
                "mean_score": float(weighted_score.mean()),
                "std_score": float(weighted_score.std())
            }
        )

    def generate_entry_exit_signals(self) -> tuple[pd.Series, pd.Series]:
        """
        Generate entry and exit signals from weighted scores.

        Uses strategy thresholds from config to determine when to enter/exit.

        Returns:
            Tuple[Series, Series]: (entry_signals, exit_signals) as boolean Series
        """
        if self.signals_df is None or self.signals_df.empty:
            raise ValueError("No signals calculated")

        # Get thresholds from config (or use defaults)
        entry_threshold = self.config.strategy_params.get('entry_threshold', 0.3)
        exit_threshold = self.config.strategy_params.get('exit_threshold', -0.1)

        # Entry: weighted_score > entry_threshold
        entries = self.signals_df['weighted_score'] > entry_threshold

        # Exit: weighted_score < exit_threshold
        exits = self.signals_df['weighted_score'] < exit_threshold

        logger.info(
            "Generated entry/exit signals",
            extra={
                "total_entry_signals": int(entries.sum()),
                "total_exit_signals": int(exits.sum())
            }
        )

        return entries, exits

    def run_portfolio_simulation(
        self,
        entries: pd.Series,
        exits: pd.Series
    ) -> vbt.Portfolio:
        """
        Run portfolio simulation with vectorbt.

        Args:
            entries: Boolean series indicating entry signals
            exits: Boolean series indicating exit signals

        Returns:
            vbt.Portfolio: Portfolio object with simulation results
        """
        logger.info("Running vectorbt portfolio simulation")

        # Use close prices
        close_prices = self.candles_df['close']

        # Calculate fees and slippage
        total_fees = float(self.config.commission_rate + self.config.slippage_pct)

        # Run portfolio simulation
        portfolio = vbt.Portfolio.from_signals(
            close=close_prices,
            entries=entries,
            exits=exits,
            init_cash=float(self.config.initial_capital),
            fees=total_fees,  # Combined commission + slippage
            freq='15T'  # 15-minute frequency
        )

        return portfolio

    def extract_trades(self, portfolio: vbt.Portfolio) -> List[BacktestTrade]:
        """
        Extract trades from vectorbt portfolio.

        Args:
            portfolio: vectorbt Portfolio object

        Returns:
            List[BacktestTrade]: List of completed trades
        """
        trades = []

        # Get trade records from portfolio
        trade_records = portfolio.trades.records

        if len(trade_records) == 0:
            logger.warning("No trades found in portfolio")
            return trades

        for i, record in enumerate(trade_records):
            # Calculate P&L components
            gross_pnl = Decimal(str(record['pnl']))
            commission = Decimal(str(abs(record['fees'])))
            slippage = Decimal("0")  # Included in fees for vectorbt

            net_pnl = gross_pnl - commission

            trade = BacktestTrade(
                trade_number=i + 1,
                direction=TradeDirection.LONG,  # Assuming long only for now
                entry_time=record['entry_idx'],
                entry_price=Decimal(str(record['entry_price'])),
                entry_order_type=OrderType.MARKET,  # vectorbt uses market orders
                quantity=Decimal(str(record['size'])),
                exit_time=record['exit_idx'],
                exit_price=Decimal(str(record['exit_price'])),
                exit_order_type=OrderType.MARKET,
                exit_reason="signal",  # Simplified
                gross_pnl=gross_pnl,
                commission_paid=commission,
                slippage_cost=slippage,
                net_pnl=net_pnl,
                return_pct=(net_pnl / (Decimal(str(record['entry_price'])) * Decimal(str(record['size'])))) * 100
            )

            trades.append(trade)

        logger.info(f"Extracted {len(trades)} trades from portfolio")

        return trades

    def _get_default_weights(self) -> Dict[str, float]:
        """
        Get default indicator weights.

        These are used if no weights are specified in config.

        Returns:
            Dict[str, float]: Default weights summing to 1.0
        """
        return {
            'ema': 0.15,
            'macd': 0.20,
            'rsi': 0.15,
            'stoch_rsi': 0.10,
            'bollinger': 0.10,
            'atr': 0.10,
            'obv': 0.10,
            'fear_greed': 0.05,
            'user': 0.05
        }
