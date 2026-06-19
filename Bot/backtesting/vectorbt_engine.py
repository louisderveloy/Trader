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

# Import error logging
from runs.errors import log_exception, ErrorCategory, ErrorSeverity
from runs.context import get_current_run_id

from indicators import ema, macd, rsi, stoch_rsi, bollinger, atr, obv

# Indicator signals are computed via each indicator module's vectorized signal_series(),
# the same single source of truth the live/paper trading loop uses through compute()/
# to_signal() — see indicators/*.py. This guarantees the backtest can't drift from live.

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
            # build_equity_curve expects 'timestamp' column, but candles_df has 'time' as index
            candles_for_equity = self.candles_df.reset_index().rename(columns={'time': 'timestamp'})
            equity_curve = build_equity_curve(
                result.trades,
                self.config.initial_capital,
                candles_for_equity
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

            # Log error to database if db_pool is available
            if self.db_pool:
                try:
                    await log_exception(
                        self.db_pool, e,
                        severity=ErrorSeverity.HIGH,
                        category=ErrorCategory.STRATEGY,
                        context={
                            "symbol": self.config.symbol,
                            "timeframe": self.config.timeframe,
                            "engine": "vectorbt",
                        },
                        run_id=get_current_run_id(),
                    )
                except Exception as log_err:
                    logger.warning(f"Failed to log exception to database: {log_err}")

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
            DataFrame: Candles with columns [time, open, high, low, close, volume]
        """
        if not self.db_pool:
            raise ValueError("Database pool required to load candles")

        logger.info("Loading candles from database")

        query = """
            SELECT
                time,
                open,
                high,
                low,
                close,
                volume
            FROM candles
            WHERE symbol = $1
                AND timeframe = $2
                AND time >= $3
                AND time <= $4
            ORDER BY time ASC
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
        df = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])

        # Convert Decimal to float for vectorbt compatibility
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # Set time as index
        df.set_index('time', inplace=True)

        logger.info(f"Loaded {len(df)} candles from database")

        return df

    async def calculate_signals(self) -> None:
        """
        Calculate all indicator signals and weighted scores.

        Populates self.signals_df with:
        - Individual indicator signals (vectorized for all bars)
        - Weighted score

        Note: Each indicator's signal is computed via its module's vectorized
        signal_series() (indicators/<name>.py) — the same single source of truth
        the live/paper trading loop reads through compute()/to_signal(). This
        guarantees the backtest can never drift from live for the same candles
        and params (see GitHub issue #9).
        """
        logger.info("Calculating indicator signals (vectorized)")

        if self.candles_df is None or self.candles_df.empty:
            raise ValueError("No candles available for signal calculation")

        # Initialize signals DataFrame
        self.signals_df = pd.DataFrame(index=self.candles_df.index)

        # Load weights from strategy_params (or use defaults)
        weights = self.config.strategy_params.get('weights', self._get_default_weights())

        # Defensive guard: the weights dict must use unprefixed indicator keys
        # (e.g. "ema", "macd"). If a caller passes a wrong namespace (e.g. Optuna's
        # prefixed "weight_ema"), every weights.get('ema', default) lookup misses and
        # the backtest silently runs on DEFAULT weights — which previously produced
        # meaningless (often zero) walk-forward test scores. Warn loudly instead.
        if weights and not any(ind in weights for ind in self._get_default_weights()):
            logger.warning(
                "[WEIGHTS] Supplied weights dict has no recognised indicator keys "
                "(got %s) — falling back to DEFAULT weights. Pass unprefixed keys "
                "like 'ema'/'macd', not 'weight_ema'.",
                list(weights.keys()),
            )

        # indicators/*.py's validate_candles() requires a 'timestamp' column;
        # candles_df carries it as the 'time' index instead. Add it without
        # disturbing the index so every signal_series() result stays aligned
        # with self.signals_df (also indexed by candles_df.index).
        candles_for_indicators = self.candles_df.copy()
        candles_for_indicators['timestamp'] = candles_for_indicators.index

        # Each indicator's own param keys (e.g. macd's 'fast'/'slow'/'signal', not
        # 'fast_period'/'slow_period') — passing strategy_params straight through
        # means live and backtest read identical keys, not a second hand-maintained
        # naming convention.
        ema_params = self.config.strategy_params.get('ema', {})
        macd_params = self.config.strategy_params.get('macd', {})
        rsi_params = self.config.strategy_params.get('rsi', {})
        stoch_params = self.config.strategy_params.get('stoch_rsi', {})
        bb_params = self.config.strategy_params.get('bollinger', {})
        atr_params = self.config.strategy_params.get('atr', {})
        obv_params = self.config.strategy_params.get('obv', {})

        # ===== EMA: Fast vs Slow crossover signal =====
        self.signals_df['ema_signal'] = ema.signal_series(candles_for_indicators, ema_params)

        # ===== MACD: Histogram sign and magnitude =====
        self.signals_df['macd_signal'] = macd.signal_series(candles_for_indicators, macd_params)

        # ===== RSI: Contrarian overbought/oversold =====
        self.signals_df['rsi_signal'] = rsi.signal_series(candles_for_indicators, rsi_params)

        # ===== Stochastic RSI =====
        self.signals_df['stoch_rsi_signal'] = stoch_rsi.signal_series(candles_for_indicators, stoch_params)

        # ===== Bollinger Bands: Position within bands =====
        self.signals_df['bollinger_signal'] = bollinger.signal_series(candles_for_indicators, bb_params)

        # ===== ATR: Volatility percentile =====
        # Keep the raw ATR series for ATR-based SL/TP stop sizing (see _compute_stop_arrays)
        self.signals_df['atr'] = atr.compute_series(candles_for_indicators, atr_params)['atr']
        self.signals_df['atr_signal'] = atr.signal_series(candles_for_indicators, atr_params)

        # ===== OBV: Volume trend =====
        self.signals_df['obv_signal'] = obv.signal_series(candles_for_indicators, obv_params)

        # ===== Fear & Greed (simplified - use neutral 0.0 for backtesting) =====
        self.signals_df['fear_greed_signal'] = 0.0

        # ===== User indicator (simplified - use neutral 0.0 for backtesting) =====
        self.signals_df['user_signal'] = 0.0

        # Fill any NaN values with 0 (neutral)
        self.signals_df = self.signals_df.fillna(0.0)

        # Calculate weighted score: Σ (signal_i × weight_i) / Σ |weight_i|
        # Normalize by sum of absolute weights so score fills [-1, 1] range
        # This matches the strategy engine behavior where weights sum to 1.0
        used_weights = {
            'ema': weights.get('ema', 0.15),
            'macd': weights.get('macd', 0.20),
            'rsi': weights.get('rsi', 0.15),
            'stoch_rsi': weights.get('stoch_rsi', 0.10),
            'bollinger': weights.get('bollinger', 0.10),
            'atr': weights.get('atr', 0.10),
            'obv': weights.get('obv', 0.10),
            'fear_greed': weights.get('fear_greed', 0.05),
            'user_indicator': weights.get('user_indicator', 0.0),
        }
        weight_sum = sum(abs(w) for w in used_weights.values())

        raw_score = (
            self.signals_df['ema_signal'] * used_weights['ema'] +
            self.signals_df['macd_signal'] * used_weights['macd'] +
            self.signals_df['rsi_signal'] * used_weights['rsi'] +
            self.signals_df['stoch_rsi_signal'] * used_weights['stoch_rsi'] +
            self.signals_df['bollinger_signal'] * used_weights['bollinger'] +
            self.signals_df['atr_signal'] * used_weights['atr'] +
            self.signals_df['obv_signal'] * used_weights['obv'] +
            self.signals_df['fear_greed_signal'] * used_weights['fear_greed'] +
            self.signals_df['user_signal'] * used_weights['user_indicator']
        )

        weighted_score = raw_score / weight_sum if weight_sum > 0 else raw_score
        self.signals_df['weighted_score'] = np.clip(weighted_score, -1.0, 1.0)

        # DEBUG: Log individual signal distributions
        logger.debug(
            "Individual signal distributions",
            extra={
                "ema_signal": {
                    "mean": float(self.signals_df['ema_signal'].mean()),
                    "std": float(self.signals_df['ema_signal'].std()),
                    "min": float(self.signals_df['ema_signal'].min()),
                    "max": float(self.signals_df['ema_signal'].max())
                },
                "macd_signal": {
                    "mean": float(self.signals_df['macd_signal'].mean()),
                    "std": float(self.signals_df['macd_signal'].std()),
                    "min": float(self.signals_df['macd_signal'].min()),
                    "max": float(self.signals_df['macd_signal'].max())
                },
                "rsi_signal": {
                    "mean": float(self.signals_df['rsi_signal'].mean()),
                    "std": float(self.signals_df['rsi_signal'].std()),
                    "min": float(self.signals_df['rsi_signal'].min()),
                    "max": float(self.signals_df['rsi_signal'].max())
                },
                "bollinger_signal": {
                    "mean": float(self.signals_df['bollinger_signal'].mean()),
                    "std": float(self.signals_df['bollinger_signal'].std()),
                    "min": float(self.signals_df['bollinger_signal'].min()),
                    "max": float(self.signals_df['bollinger_signal'].max())
                }
            }
        )

        logger.info(
            "Signals calculated (vectorized)",
            extra={
                "mean_score": float(weighted_score.mean()),
                "std_score": float(weighted_score.std()),
                "min_score": float(weighted_score.min()),
                "max_score": float(weighted_score.max()),
                "weights_used": weights
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
        # For backtesting/optimization, use lower thresholds to allow trades
        entry_threshold = self.config.strategy_params.get('entry_threshold', 0.05)  # Lowered from 0.3
        exit_threshold = self.config.strategy_params.get('exit_threshold', -0.05)  # Lowered from -0.1

        weighted_score = self.signals_df['weighted_score']

        # Entry: weighted_score > entry_threshold
        entries = weighted_score > entry_threshold

        # Exit: weighted_score < exit_threshold
        exits = weighted_score < exit_threshold

        logger.info(
            f"[SIGNALS] entry_thresh={entry_threshold}, exit_thresh={exit_threshold}, "
            f"score_range=[{float(weighted_score.min()):.4f}, {float(weighted_score.max()):.4f}], "
            f"score_mean={float(weighted_score.mean()):.4f}, "
            f"entries={int(entries.sum())}, exits={int(exits.sum())}, candles={len(weighted_score)}"
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

        # Stop-loss / take-profit as fractions of entry price (vectorbt convention).
        # Same semantics as the strategy engine / event-driven backtester so the
        # two engines stay coherent (CLAUDE.md <2% rule).
        sl_stop, tp_stop = self._compute_stop_arrays(close_prices)

        # Run portfolio simulation
        portfolio = vbt.Portfolio.from_signals(
            close=close_prices,
            entries=entries,
            exits=exits,
            init_cash=float(self.config.initial_capital),
            fees=total_fees,  # Combined commission + slippage
            sl_stop=sl_stop,
            tp_stop=tp_stop,
            freq='15T'  # 15-minute frequency
        )

        return portfolio

    def _compute_stop_arrays(self, close_prices: pd.Series):
        """Build sl_stop / tp_stop for vectorbt as fractions of entry price.

        - FIXED mode: a flat fraction (e.g. 2% → 0.02).
        - ATR mode: a per-bar fraction = ATR * multiplier / close, matching
          SL = entry - ATR*mult used by the strategy engine. Bars without a
          valid ATR fall back to np.inf (vectorbt = "no stop") so warm-up bars
          don't get a spurious tight stop.

        Returns:
            (sl_stop, tp_stop) — each a float scalar (FIXED) or np.ndarray (ATR).
        """
        sl_cfg = self.config.strategy_params.get('stop_loss', {}) or {}
        tp_cfg = self.config.strategy_params.get('take_profit', {}) or {}

        def _arr(cfg, default_mode, default_mult, default_pct):
            mode = str(cfg.get('mode', default_mode)).lower()
            if mode == 'fixed':
                return float(cfg.get('fixed_percent', default_pct)) / 100.0
            mult = float(cfg.get('atr_multiplier', default_mult))
            if 'atr' in self.signals_df:
                frac = (self.signals_df['atr'] * mult) / close_prices
                return frac.replace([np.inf, -np.inf], np.nan).fillna(np.inf).to_numpy()
            # No ATR available → no stop rather than a wrong one
            return np.inf

        sl_stop = _arr(sl_cfg, 'atr', 2.0, 2.0)
        tp_stop = _arr(tp_cfg, 'atr', 3.0, 4.0)
        return sl_stop, tp_stop

    def extract_trades(self, portfolio: vbt.Portfolio) -> List[BacktestTrade]:
        """
        Extract trades from vectorbt portfolio.

        Args:
            portfolio: vectorbt Portfolio object

        Returns:
            List[BacktestTrade]: List of completed trades
        """
        trades = []

        # Get trade records as DataFrame for easier access
        try:
            trade_df = portfolio.trades.records_readable
        except Exception as e:
            # Fallback: no trades or empty
            logger.warning(f"No trades found in portfolio (records_readable failed): {e}")
            return trades

        if trade_df is None or len(trade_df) == 0:
            logger.warning("No trades found in portfolio")
            return trades

        # DEBUG: Log DataFrame columns and sample data
        logger.debug(
            f"Vectorbt trade_df: columns={list(trade_df.columns)}, shape={trade_df.shape}"
        )
        if len(trade_df) > 0:
            first_row = trade_df.iloc[0]
            logger.debug(
                f"Sample trade row (first): {first_row.to_dict()}"
            )

        # Get the index (timestamps) for mapping entry/exit indices to times
        index = self.candles_df.index

        # DEBUG: Log index info
        logger.debug(
            f"Candles index: type={type(index[0]).__name__}, first={index[0]}, last={index[-1]}, len={len(index)}"
        )

        for i, row in trade_df.iterrows():
            # Calculate P&L components
            # vectorbt records_readable uses specific column names - handle variations
            # PnL column
            if 'PnL' in row:
                gross_pnl = Decimal(str(row['PnL']))
            elif 'pnl' in row:
                gross_pnl = Decimal(str(row['pnl']))
            else:
                gross_pnl = Decimal("0")

            # Fees - vectorbt splits into Entry Fees + Exit Fees
            entry_fees = float(row.get('Entry Fees', 0) or 0)
            exit_fees = float(row.get('Exit Fees', 0) or 0)
            commission = Decimal(str(entry_fees + exit_fees))
            slippage = Decimal("0")  # Included in fees for vectorbt

            # Net PnL: vectorbt's PnL already includes fees, so don't subtract again
            net_pnl = gross_pnl

            # Entry/Exit prices - vectorbt uses 'Avg Entry Price' / 'Avg Exit Price'
            if 'Avg Entry Price' in row:
                entry_price = Decimal(str(row['Avg Entry Price']))
            elif 'Entry Price' in row:
                entry_price = Decimal(str(row['Entry Price']))
            else:
                entry_price = Decimal("0")

            if 'Avg Exit Price' in row:
                exit_price = Decimal(str(row['Avg Exit Price']))
            elif 'Exit Price' in row:
                exit_price = Decimal(str(row['Exit Price']))
            else:
                exit_price = Decimal("0")

            # Size
            if 'Size' in row:
                size = Decimal(str(row['Size']))
            elif 'size' in row:
                size = Decimal(str(row['size']))
            else:
                size = Decimal("0")

            # Entry/Exit timestamps - vectorbt records_readable provides timestamps directly
            # NOT indices! Use 'Entry Timestamp' / 'Exit Timestamp' columns
            if 'Entry Timestamp' in row:
                entry_time = row['Entry Timestamp']
            elif 'Entry Idx' in row:
                entry_idx = int(row['Entry Idx'])
                entry_time = index[entry_idx] if entry_idx < len(index) else index[-1]
            else:
                entry_time = index[0]

            if 'Exit Timestamp' in row:
                exit_time = row['Exit Timestamp']
            elif 'Exit Idx' in row:
                exit_idx = int(row['Exit Idx'])
                exit_time = index[exit_idx] if exit_idx < len(index) else index[-1]
            else:
                exit_time = index[-1]

            # Calculate return percentage
            # vectorbt provides 'Return' column directly, use it if available
            if 'Return' in row:
                return_pct = Decimal(str(row['Return'] * 100))  # Convert to percentage
            elif entry_price > 0 and size > 0:
                return_pct = (net_pnl / (entry_price * size)) * 100
            else:
                return_pct = Decimal("0")

            trade = BacktestTrade(
                trade_number=i + 1,
                direction=TradeDirection.LONG,  # Assuming long only for now
                entry_time=entry_time,
                entry_price=entry_price,
                entry_order_type=OrderType.MARKET,  # vectorbt uses market orders
                quantity=size,
                exit_time=exit_time,
                exit_price=exit_price,
                exit_order_type=OrderType.MARKET,
                exit_reason="signal",  # Simplified
                gross_pnl=gross_pnl,
                commission_paid=commission,
                slippage_cost=slippage,
                net_pnl=net_pnl,
                return_pct=return_pct
            )

            trades.append(trade)

            # DEBUG: Log first 5 trades with PnL details
            if i < 5:
                logger.debug(
                    f"Trade {i}: entry_time={entry_time}, exit_time={exit_time}, "
                    f"entry={float(entry_price):.2f}, exit={float(exit_price):.2f}, size={float(size):.6f}, "
                    f"pnl={float(net_pnl):.4f}, return={float(return_pct):.4f}%"
                )

        # DEBUG: Summary of all trades PnL
        if trades:
            all_net_pnl = [float(t.net_pnl) for t in trades]
            total_pnl = sum(all_net_pnl)
            positive = sum(1 for p in all_net_pnl if p > 0)
            negative = sum(1 for p in all_net_pnl if p < 0)
            zero = sum(1 for p in all_net_pnl if p == 0)
            logger.info(
                f"Extracted {len(trades)} trades: total_pnl={total_pnl:.2f}, "
                f"avg={total_pnl/len(all_net_pnl):.4f}, min={min(all_net_pnl):.4f}, max={max(all_net_pnl):.4f}, "
                f"positive={positive}, negative={negative}, zero={zero}"
            )
        else:
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
            'user_indicator': 0.05
        }
