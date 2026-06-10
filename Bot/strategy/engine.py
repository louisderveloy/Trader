"""
Core strategy engine.

This module implements the main strategy engine with:
1. Weighted scoring: Σ (signal_i × poids_i)
2. Integration with weights_sets table
3. Anti-repainting confirmation over N candles
4. Entry/exit threshold checking
5. Complete decision logging with snapshots

The StrategyEngine is the main orchestrator that ties together
all other strategy components (sizing, stops, risk management).
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID
import json

from .types import (
    DecisionType,
    WeightsSnapshot,
    IndicatorSnapshot,
    TradingDecision,
    ConfirmationState,
    PositionState
)
from .config import StrategyEngineConfig
from .sizing import calculate_position_size, calculate_position_quantity
from .stops import calculate_stop_loss, calculate_take_profit, calculate_risk_reward_ratio
from .risk import RiskManager

# Structured logging
logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Core strategy engine for trading decisions.

    This engine:
    1. Loads active indicator weights from database
    2. Calculates weighted scores from indicator signals
    3. Manages anti-repainting confirmation state
    4. Checks entry/exit thresholds
    5. Integrates with position sizing, stops, and risk management
    6. Creates complete TradingDecision objects with snapshots
    7. Logs all decisions to signals table
    """

    def __init__(
        self,
        config: StrategyEngineConfig,
        run_id: int,
        db_pool,
        config_id: Optional[UUID] = None,
        risk_manager: Optional[RiskManager] = None
    ):
        """
        Initialize strategy engine.

        Args:
            config: Complete strategy engine configuration
            run_id: Current run ID (integer)
            db_pool: asyncpg connection pool for database queries
            config_id: Optional config ID from database (for score logging)
            risk_manager: Optional RiskManager instance (created if not provided)
        """
        self.config = config
        self.run_id = run_id
        self.db_pool = db_pool
        self.config_id = config_id

        # Create risk manager if not provided
        self.risk_manager = risk_manager or RiskManager(
            run_id=run_id,
            risk_config=config.risk,
            cooldown_config=config.cooldown,
            db_pool=db_pool
        )

        # State tracking
        self._active_weights: Optional[WeightsSnapshot] = None
        self._confirmation_state: Optional[ConfirmationState] = None
        self._position_state: PositionState = PositionState(is_open=False)

        logger.info(
            "Strategy engine initialized",
            extra={
                "run_id": str(run_id),
                "config": config.to_snapshot()
            }
        )

    async def load_active_weights(self) -> WeightsSnapshot:
        """
        Load active indicator weights from weights_sets table.

        Queries the database for the weights_set with is_active = TRUE
        and creates a WeightsSnapshot.

        Returns:
            WeightsSnapshot with active weights

        Raises:
            ValueError: If no active weights set found
            Exception: If database query fails
        """
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT id, name, weights, created_at
                FROM weights_sets
                WHERE is_active = TRUE
                LIMIT 1
            """
            row = await conn.fetchrow(query)

            if row is None:
                raise ValueError("No active weights set found in database")

            weights_snapshot = WeightsSnapshot(
                weights_set_id=row["id"],
                weights_set_name=row["name"],
                weights=row["weights"],  # Already JSONB dict
                timestamp=row["created_at"]
            )

        self._active_weights = weights_snapshot

        logger.info(
            "Active weights loaded",
            extra={
                "weights_set_id": str(weights_snapshot.weights_set_id),
                "weights_set_name": weights_snapshot.weights_set_name,
                "weights": weights_snapshot.weights
            }
        )

        return weights_snapshot

    def calculate_weighted_score(
        self,
        indicator_signals: Dict[str, float],
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate weighted score from indicator signals.

        Formula:
            weighted_score = Σ (signal_i × weight_i)

        Args:
            indicator_signals: Dictionary of {indicator_name: signal_value}
                              where signal_value ∈ [-1, 1]
            weights: Optional weights dict (uses active weights if not provided)

        Returns:
            Weighted score ∈ [-1, 1]

        Raises:
            ValueError: If active weights not loaded or signal values invalid

        Example:
            >>> signals = {
            ...     "ema": 0.45,
            ...     "macd": 0.65,
            ...     "rsi": 0.17,
            ...     "stoch_rsi": 0.24,
            ...     "bollinger": -0.15,
            ...     "atr": 0.0,
            ...     "obv": 0.35,
            ...     "fear_greed": 0.30,
            ...     "user_indicator": 0.80
            ... }
            >>> score = engine.calculate_weighted_score(signals)
            >>> print(f"Weighted score: {score:.4f}")
        """
        if weights is None:
            if self._active_weights is None:
                raise ValueError("Active weights not loaded. Call load_active_weights() first.")
            weights = self._active_weights.weights

        # Validate all signals are in [-1, 1]
        for indicator, signal in indicator_signals.items():
            if not -1.0 <= signal <= 1.0:
                raise ValueError(
                    f"Signal for {indicator} must be in [-1, 1], got {signal}"
                )

        # Calculate weighted sum normalized by total weight
        raw_score = 0.0
        for indicator, weight in weights.items():
            signal = indicator_signals.get(indicator, 0.0)
            raw_score += signal * weight

        weight_sum = sum(abs(w) for w in weights.values())
        weighted_score = raw_score / weight_sum if weight_sum > 0 else raw_score
        weighted_score = max(-1.0, min(1.0, weighted_score))

        logger.debug(
            "Weighted score calculated",
            extra={
                "indicator_signals": indicator_signals,
                "weights": weights,
                "weighted_score": weighted_score
            }
        )

        return weighted_score

    async def make_decision(
        self,
        candles: List[Any],  # List of CandleData (from indicators module)
        indicator_results: Dict[str, Any],  # Dict of {indicator_name: IndicatorResult}
        current_price: Decimal,
        current_time: datetime,
        total_capital: Decimal,
        symbol: str = "BTCUSDT"
    ) -> TradingDecision:
        """
        Make a trading decision based on current market state.

        This is the main entry point for the strategy engine.

        Args:
            candles: List of recent candles
            indicator_results: Dictionary of computed indicator results
            current_price: Current market price
            current_time: Current timestamp
            total_capital: Total available capital in USDT
            symbol: Trading symbol

        Returns:
            TradingDecision with complete snapshots

        Raises:
            ValueError: If required data is missing
            Exception: If database operations fail
        """
        # Load active weights if not already loaded
        if self._active_weights is None:
            await self.load_active_weights()

        # Extract signals from indicator results
        indicator_signals = {}
        indicators_data = {}

        for indicator_name, result in indicator_results.items():
            # Get signal value (assuming IndicatorResult has a signal attribute)
            signal_value = result.signal.value if hasattr(result, "signal") else 0.0
            indicator_signals[indicator_name] = signal_value

            # Build indicators snapshot data
            indicators_data[indicator_name] = {
                "signal": signal_value,
                **result.values  # Include all indicator values
            }

        # Calculate weighted score
        weighted_score = self.calculate_weighted_score(indicator_signals)

        # Create snapshots
        weights_snapshot = self._active_weights
        indicators_snapshot = IndicatorSnapshot(
            timestamp=current_time,
            symbol=symbol,
            candle_close=current_price,
            indicators=indicators_data
        )

        # Log score calculation for statistics
        await self._log_score(
            weighted_score=weighted_score,
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            current_time=current_time,
            symbol=symbol
        )

        # Determine decision type based on current state and thresholds
        decision_type, decision_reason = await self._determine_decision(
            weighted_score=weighted_score,
            current_time=current_time,
            current_price=current_price,
            total_capital=total_capital,
            indicator_results=indicator_results
        )

        # Create base trading decision
        decision = TradingDecision(
            decision_type=decision_type,
            timestamp=current_time,
            symbol=symbol,
            weighted_score=weighted_score,
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            decision_reason=decision_reason
        )

        # If ENTRY_LONG, calculate position size and stops
        if decision_type == DecisionType.ENTRY_LONG:
            decision = await self._enhance_entry_decision(
                decision=decision,
                current_price=current_price,
                total_capital=total_capital,
                indicator_results=indicator_results
            )
            # Validate decision is complete with all required fields
            decision.validate_complete()

        # Log decision to database
        await self._log_decision(decision)

        logger.info(
            "Trading decision made",
            extra={
                "decision_type": decision.decision_type.value,
                "weighted_score": weighted_score,
                "decision_reason": decision_reason,
                "symbol": symbol,
                "current_price": float(current_price)
            }
        )

        return decision

    async def _determine_decision(
        self,
        weighted_score: float,
        current_time: datetime,
        current_price: Decimal,
        total_capital: Decimal,
        indicator_results: Dict[str, Any]
    ) -> tuple[DecisionType, str]:
        """
        Determine decision type based on weighted score, thresholds, and confirmations.

        Implements anti-repainting logic and threshold checking.

        Returns:
            (decision_type, decision_reason) tuple
        """
        # Check if we should exit (only if position is open)
        if self._position_state.is_open:
            if weighted_score <= self.config.strategy.exit_threshold:
                # Check for confirmation
                confirmed = await self._check_confirmation(
                    decision_type=DecisionType.EXIT,
                    weighted_score=weighted_score,
                    current_time=current_time
                )

                if confirmed:
                    return (
                        DecisionType.EXIT,
                        f"Exit signal confirmed: score {weighted_score:.4f} <= "
                        f"threshold {self.config.strategy.exit_threshold}"
                    )
                else:
                    return (
                        DecisionType.SKIP,
                        f"Exit signal pending confirmation "
                        f"({self._confirmation_state.consecutive_candles}/"
                        f"{self.config.strategy.confirmation_candles})"
                    )

        # Check if we should enter (only if no position open)
        if not self._position_state.is_open:
            if weighted_score >= self.config.strategy.entry_threshold:
                # Check for confirmation
                confirmed = await self._check_confirmation(
                    decision_type=DecisionType.ENTRY_LONG,
                    weighted_score=weighted_score,
                    current_time=current_time
                )

                if not confirmed:
                    return (
                        DecisionType.SKIP,
                        f"Entry signal pending confirmation "
                        f"({self._confirmation_state.consecutive_candles}/"
                        f"{self.config.strategy.confirmation_candles})"
                    )

                # Check risk constraints
                # Get ATR for position sizing
                atr_value = None
                if "atr" in indicator_results:
                    atr_result = indicator_results["atr"]
                    atr_value = atr_result.values.get("value")

                # Calculate position size
                position_size_usdt = calculate_position_size(
                    mode=self.config.risk.position_size_mode,
                    config=self.config.risk,
                    weighted_score=weighted_score,
                    current_price=current_price,
                    total_capital=total_capital,
                    atr_value=atr_value
                )

                # Check if we can open new trade
                can_open, reason = await self.risk_manager.can_open_new_trade(
                    new_position_size_usdt=position_size_usdt,
                    total_capital=total_capital,
                    current_time=current_time
                )

                if not can_open:
                    return DecisionType.SKIP, f"Entry blocked by risk management: {reason}"

                return (
                    DecisionType.ENTRY_LONG,
                    f"Entry signal confirmed: score {weighted_score:.4f} >= "
                    f"threshold {self.config.strategy.entry_threshold}"
                )

        # Default: skip
        return DecisionType.SKIP, f"No action: score {weighted_score:.4f} in neutral zone"

    async def _check_confirmation(
        self,
        decision_type: DecisionType,
        weighted_score: float,
        current_time: datetime
    ) -> bool:
        """
        Check if signal is confirmed over required number of candles.

        Implements anti-repainting logic.

        Returns:
            True if confirmed, False otherwise
        """
        required_candles = self.config.strategy.confirmation_candles

        # If no confirmation state, initialize it
        if self._confirmation_state is None:
            self._confirmation_state = ConfirmationState(
                decision_type=decision_type,
                consecutive_candles=1,
                first_seen_at=current_time,
                last_weighted_score=weighted_score
            )
            return required_candles == 1

        # If decision type matches, increment count
        if self._confirmation_state.decision_type == decision_type:
            self._confirmation_state.consecutive_candles += 1
            self._confirmation_state.last_weighted_score = weighted_score
        else:
            # Different decision type, reset
            self._confirmation_state = ConfirmationState(
                decision_type=decision_type,
                consecutive_candles=1,
                first_seen_at=current_time,
                last_weighted_score=weighted_score
            )

        # Check if confirmed
        is_confirmed = self._confirmation_state.is_confirmed(required_candles)

        logger.debug(
            "Confirmation check",
            extra={
                "decision_type": decision_type.value,
                "consecutive_candles": self._confirmation_state.consecutive_candles,
                "required_candles": required_candles,
                "is_confirmed": is_confirmed
            }
        )

        return is_confirmed

    async def _enhance_entry_decision(
        self,
        decision: TradingDecision,
        current_price: Decimal,
        total_capital: Decimal,
        indicator_results: Dict[str, Any]
    ) -> TradingDecision:
        """
        Enhance ENTRY_LONG decision with position size and stop-loss/take-profit.

        Modifies the decision object in-place.

        Returns:
            Enhanced TradingDecision
        """
        # Get ATR value if available
        atr_value = None
        if "atr" in indicator_results:
            atr_result = indicator_results["atr"]
            atr_value = atr_result.values.get("value")
            if atr_value is not None:
                atr_value = Decimal(str(atr_value))

        # Calculate position size
        position_size_usdt = calculate_position_size(
            mode=self.config.risk.position_size_mode,
            config=self.config.risk,
            weighted_score=decision.weighted_score,
            current_price=current_price,
            total_capital=total_capital,
            atr_value=atr_value
        )

        # Calculate position quantity
        position_size_qty = calculate_position_quantity(
            position_size_usdt=position_size_usdt,
            current_price=current_price
        )

        # Calculate stop-loss
        stop_loss_price = calculate_stop_loss(
            mode=self.config.stop_loss.mode,
            config=self.config.stop_loss,
            entry_price=current_price,
            atr_value=atr_value
        )

        # Calculate take-profit
        take_profit_price = calculate_take_profit(
            mode=self.config.take_profit.mode,
            config=self.config.take_profit,
            entry_price=current_price,
            atr_value=atr_value
        )

        # Calculate risk/reward ratio
        rr_ratio = calculate_risk_reward_ratio(
            entry_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price
        )

        # Update decision
        decision.entry_price = current_price
        decision.position_size_usdt = position_size_usdt
        decision.position_size_qty = position_size_qty
        decision.stop_loss_price = stop_loss_price
        decision.take_profit_price = take_profit_price

        # Enhance decision reason with details
        decision.decision_reason += (
            f" | Size: {float(position_size_usdt):.2f} USDT ({float(position_size_qty):.5f} units) "
            f"| SL: {float(stop_loss_price):.2f} | TP: {float(take_profit_price):.2f} "
            f"| R/R: {float(rr_ratio):.2f}:1"
        )

        return decision

    async def _log_decision(self, decision: TradingDecision):
        """
        Log trading decision to signals table.

        Inserts a new row in signals table with complete snapshots.

        Args:
            decision: TradingDecision to log
        """
        async with self.db_pool.acquire() as conn:
            query = """
                INSERT INTO signals (
                    run_id, time, symbol, signal_type, weighted_score,
                    weights_snapshot, indicators_snapshot, decision_reason
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """
            signal_id = await conn.fetchval(
                query,
                self.run_id,
                decision.timestamp,
                decision.symbol,
                decision.decision_type.value,
                Decimal(str(decision.weighted_score)),
                json.dumps(decision.weights_snapshot.to_dict()),
                json.dumps(decision.indicators_snapshot.to_dict()),
                decision.decision_reason
            )

        logger.info(
            "Decision logged to database",
            extra={
                "signal_id": str(signal_id),
                "run_id": str(self.run_id),
                "decision_type": decision.decision_type.value
            }
        )

    async def _log_score(
        self,
        weighted_score: float,
        weights_snapshot: WeightsSnapshot,
        indicators_snapshot: IndicatorSnapshot,
        current_time: datetime,
        symbol: str,
        order_id: Optional[UUID] = None
    ):
        """
        Log score calculation to score_logs table for statistical analysis.

        This method logs every score calculation, regardless of whether
        it resulted in a trading decision or order.

        Args:
            weighted_score: Calculated weighted score
            weights_snapshot: Snapshot of weights used
            indicators_snapshot: Snapshot of indicator values
            current_time: Timestamp of calculation
            symbol: Trading symbol
            order_id: Optional order ID if score resulted in an order
        """
        if self.config_id is None:
            logger.warning(
                "config_id not set, skipping score logging",
                extra={"run_id": str(self.run_id)}
            )
            return

        async with self.db_pool.acquire() as conn:
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
                weights_snapshot.weights_set_id,
                order_id,
                current_time,
                symbol,
                Decimal(str(weighted_score)),
                json.dumps(indicators_snapshot.to_dict())
            )

        logger.debug(
            "Score logged to database",
            extra={
                "score_log_id": str(score_log_id),
                "run_id": str(self.run_id),
                "weighted_score": weighted_score,
                "symbol": symbol
            }
        )

    def update_position_state(self, position_state: PositionState):
        """
        Update current position state.

        This should be called by the trading bot when positions are opened/closed.

        Args:
            position_state: New position state
        """
        self._position_state = position_state

        logger.info(
            "Position state updated",
            extra={
                "is_open": position_state.is_open,
                "symbol": position_state.symbol,
                "entry_price": float(position_state.entry_price) if position_state.entry_price else None,
                "quantity": float(position_state.quantity) if position_state.quantity else None
            }
        )

    def get_position_state(self) -> PositionState:
        """Get current position state."""
        return self._position_state

    def reset_confirmation_state(self):
        """Reset confirmation state (useful for testing or after major events)."""
        self._confirmation_state = None
        logger.info("Confirmation state reset")
