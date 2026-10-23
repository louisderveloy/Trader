"""
Predictive strategy engine based on hybrid Deep Learning + XGBoost model.

This engine:
1. Maintains a memory buffer of historical and incoming candles (CandleMemoryBuffer)
2. Extracts 10 dense features via ONNX Runtime using the feature_dense layer
3. Evaluates class probabilities [prob_hold, prob_buy, prob_sell] via XGBoost
4. Applies probability-based entry and exit thresholds
5. Uses strictly fixed Stop-Loss and Take-Profit percentages
6. Fires immediately without confirmation candles
7. Respects risk management quotas and limits
8. Logs decisions to the signals table
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import numpy as np
import onnxruntime as ort
import xgboost as xgb

from .config import StrategyEngineConfig
from .features import CandleMemoryBuffer
from .risk import RiskManager
from .sizing import calculate_position_quantity, calculate_position_size
from .types import (
    DecisionType,
    IndicatorSnapshot,
    PositionState,
    TradingDecision,
    WeightsSnapshot,
)

logger = logging.getLogger(__name__)


def _find_model_file(filename: str) -> str:
    """Locate model file across standard container and local directories."""
    candidates = [
        os.path.join("/models", filename),
        os.path.join("models", filename),
        os.path.join(os.path.dirname(__file__), "..", "..", "models", filename),
        os.path.join("G:\\Dev\\Trader\\models", filename),
    ]
    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path
    raise FileNotFoundError(
        f"Model file '{filename}' not found. Searched in: {[os.path.abspath(p) for p in candidates]}"
    )


class PredictiveStrategyEngine:
    """
    Autonomous predictive strategy engine powered by DL feature extraction and XGBoost.
    """

    def __init__(
        self,
        config: StrategyEngineConfig,
        run_id: int,
        db_pool,
        config_id: Optional[UUID] = None,
        risk_manager: Optional[RiskManager] = None,
        onnx_model_filename: str = "feature_extractor.onnx",
        xgb_model_filename: str = "hybridre_cnn_gru_dense_xgboost_return_1.4185_xgb.json",
    ):
        self.config = config
        self.run_id = run_id
        self.db_pool = db_pool
        self.config_id = config_id

        # Risk manager for exposure and daily trade quotas
        self.risk_manager = risk_manager or RiskManager(
            run_id=run_id,
            risk_config=config.risk,
            cooldown_config=config.cooldown,
            db_pool=db_pool,
        )

        # In-memory candle buffer (caches 59 past normalized candles)
        self.buffer = CandleMemoryBuffer(norm_window=200, window_size=60)

        # Position tracking
        self._position_state: PositionState = PositionState(is_open=False)

        # Active weights set ID (optional, for score_logs foreign key if present)
        self._active_weights_set_id: Optional[UUID] = None

        # Load models
        onnx_path = _find_model_file(onnx_model_filename)
        xgb_path = _find_model_file(xgb_model_filename)

        logger.info(f"Loading ONNX feature extractor from: {onnx_path}")
        self.onnx_session = ort.InferenceSession(onnx_path)
        self.onnx_input_name = self.onnx_session.get_inputs()[0].name

        logger.info(f"Loading XGBoost booster from: {xgb_path}")
        self.xgb_booster = xgb.Booster()
        self.xgb_booster.load_model(xgb_path)

        logger.info(
            f"PredictiveStrategyEngine initialized successfully for run_id={run_id}"
        )

    def update_config(
        self,
        config: StrategyEngineConfig,
        config_id: Optional[UUID] = None,
    ) -> None:
        """Apply hot-reloaded configuration to the engine and risk manager."""
        self.config = config
        if config_id is not None:
            self.config_id = config_id
        self.risk_manager.risk_config = config.risk
        self.risk_manager.cooldown_config = config.cooldown
        logger.info(
            "Predictive strategy engine configuration updated",
            extra={"run_id": str(self.run_id)},
        )

    def update_position_state(self, position_state: PositionState) -> None:
        """Update current position state."""
        self._position_state = position_state
        logger.info(
            "Predictive engine position state updated",
            extra={
                "is_open": position_state.is_open,
                "symbol": position_state.symbol,
                "entry_price": float(position_state.entry_price) if position_state.entry_price else None,
            },
        )

    def get_position_state(self) -> PositionState:
        """Get current position state."""
        return self._position_state

    async def _resolve_weights_set_id(self) -> Optional[UUID]:
        """Fetch active weights_set_id from database if available (for score_logs foreign key)."""
        if self._active_weights_set_id is not None:
            return self._active_weights_set_id
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT id FROM weights_sets WHERE is_active = true LIMIT 1")
                if row:
                    self._active_weights_set_id = row["id"]
        except Exception as e:
            logger.debug(f"Could not resolve active weights_set_id: {e}")
        return self._active_weights_set_id

    async def load_active_weights(self) -> None:
        """Refresh active weights_set_id from database if available."""
        self._active_weights_set_id = None
        await self._resolve_weights_set_id()

    async def make_decision(
        self,
        candles: List[Any],
        indicator_results: Optional[Dict[str, Any]] = None,
        current_price: Decimal = Decimal("0"),
        current_time: Optional[datetime] = None,
        total_capital: Decimal = Decimal("0"),
        symbol: str = "BTCUSDC",
    ) -> TradingDecision:
        """
        Evaluate ML probabilities and make an automated trading decision.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # 1. Update in-memory candle buffer
        if not self.buffer.is_warmed_up or self.buffer.candle_count < 60:
            self.buffer.warm_up(candles)

        if candles:
            latest_candle = candles[-1]
            _, sequence_tensor = self.buffer.add_candle(latest_candle)
        else:
            sequence_tensor = self.buffer.get_latest_sequence()

        if sequence_tensor is None or sequence_tensor.shape != (1, 60, 11):
            reason = f"Insufficient candle history for ML model (buffer count: {self.buffer.candle_count}/60)"
            return self._build_skip_decision(
                current_time=current_time,
                symbol=symbol,
                current_price=current_price,
                reason=reason,
            )

        # 2. Run inference: DL feature extractor -> XGBoost probabilities
        dense_features = self.onnx_session.run(None, {self.onnx_input_name: sequence_tensor})[0]
        probabilities = self.xgb_booster.inplace_predict(dense_features)[0]
        prob_hold, prob_buy, prob_sell = float(probabilities[0]), float(probabilities[1]), float(probabilities[2])

        # Net directional score in [-1.0, 1.0] for compatibility with dashboards and score logs
        weighted_score = max(-1.0, min(1.0, float(prob_buy - prob_sell)))

        # Build snapshots
        weights_set_id = await self._resolve_weights_set_id()
        weights_snapshot = WeightsSnapshot(
            weights_set_id=weights_set_id,
            weights_set_name="predictive_model_hybrid_dl_xgb",
            weights={
                "prob_hold": prob_hold,
                "prob_buy": prob_buy,
                "prob_sell": prob_sell,
            },
            timestamp=current_time,
        )

        indicators_snapshot = IndicatorSnapshot(
            timestamp=current_time,
            symbol=symbol,
            candle_close=current_price,
            indicators={
                "model_probabilities": {
                    "hold": prob_hold,
                    "buy": prob_buy,
                    "sell": prob_sell,
                },
                "feature_dense": dense_features[0].tolist(),
            },
        )

        # Log score to score_logs if config_id and weights_set_id are set
        if self.config_id is not None and weights_set_id is not None:
            await self._log_score(
                weighted_score=weighted_score,
                weights_snapshot=weights_snapshot,
                indicators_snapshot=indicators_snapshot,
                current_time=current_time,
                symbol=symbol,
            )

        # 3. Decision logic
        # Fixed SL/TP percentages as Decimals
        sl_percent = Decimal(str(self.config.stop_loss.fixed_percent))
        tp_percent = Decimal(str(self.config.take_profit.fixed_percent))
        sl_factor = sl_percent / Decimal("100")
        tp_factor = tp_percent / Decimal("100")

        # Thresholds
        entry_threshold = float(self.config.strategy.entry_threshold)
        exit_threshold = float(self.config.strategy.exit_threshold)

        decision_type = DecisionType.SKIP
        decision_reason = "No trade signal"
        stop_loss_price: Optional[Decimal] = None
        take_profit_price: Optional[Decimal] = None
        position_size_usdt: Optional[Decimal] = None
        position_size_qty: Optional[Decimal] = None

        if self._position_state.is_open:
            entry_price = self._position_state.entry_price or current_price
            profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else Decimal("0")

            # Check fixed Stop-Loss
            if profit_pct <= -sl_factor:
                decision_type = DecisionType.EXIT
                decision_reason = f"Stop-Loss: profit {float(profit_pct * 100):.2f}% <= -{float(sl_percent):.2f}%"
            # Check fixed Take-Profit
            elif profit_pct >= tp_factor:
                decision_type = DecisionType.EXIT
                decision_reason = f"Take-Profit: profit {float(profit_pct * 100):.2f}% >= {float(tp_percent):.2f}%"
            # Check model sell signal
            elif prob_sell >= exit_threshold:
                decision_type = DecisionType.EXIT
                decision_reason = f"Model Exit Signal: prob_sell {prob_sell:.4f} >= threshold {exit_threshold:.4f}"
            else:
                decision_type = DecisionType.SKIP
                decision_reason = f"In position, prob_sell {prob_sell:.4f} < threshold {exit_threshold:.4f}"

        else:
            # Check model buy signal
            if prob_buy >= entry_threshold:
                # Calculate position size
                position_size_usdt = calculate_position_size(
                    mode=self.config.risk.position_size_mode,
                    config=self.config.risk,
                    weighted_score=weighted_score,
                    current_price=current_price,
                    total_capital=total_capital,
                    atr_value=None,
                )

                # Check risk quotas
                can_open, risk_reason = await self.risk_manager.can_open_new_trade(
                    new_position_size_usdt=position_size_usdt,
                    total_capital=total_capital,
                    current_time=current_time,
                )

                if can_open:
                    decision_type = DecisionType.ENTRY_LONG
                    decision_reason = f"Model Entry Signal: prob_buy {prob_buy:.4f} >= threshold {entry_threshold:.4f}"
                    position_size_qty = calculate_position_quantity(
                        position_size_usdt=position_size_usdt,
                        current_price=current_price,
                    )
                    # Fixed Stop-Loss and Take-Profit price levels
                    stop_loss_price = current_price * (Decimal("1") - sl_factor)
                    take_profit_price = current_price * (Decimal("1") + tp_factor)
                else:
                    decision_type = DecisionType.SKIP
                    decision_reason = f"Entry blocked by risk management: {risk_reason}"
            else:
                decision_type = DecisionType.SKIP
                decision_reason = f"prob_buy {prob_buy:.4f} < threshold {entry_threshold:.4f}"

        # 4. Build and log decision
        decision = TradingDecision(
            decision_type=decision_type,
            timestamp=current_time,
            symbol=symbol,
            weighted_score=weighted_score,
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            decision_reason=decision_reason,
            entry_price=current_price if decision_type == DecisionType.ENTRY_LONG else None,
            position_size_usdt=position_size_usdt,
            position_size_qty=position_size_qty,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

        if decision_type == DecisionType.ENTRY_LONG:
            decision.validate_complete()

        await self._log_decision(decision)

        logger.info(
            "Predictive engine decision made",
            extra={
                "decision_type": decision.decision_type.value,
                "weighted_score": weighted_score,
                "prob_buy": prob_buy,
                "prob_sell": prob_sell,
                "decision_reason": decision_reason,
            },
        )

        return decision

    def _build_skip_decision(
        self,
        current_time: datetime,
        symbol: str,
        current_price: Decimal,
        reason: str,
    ) -> TradingDecision:
        """Construct fallback skip decision during warm-up."""
        weights_snapshot = WeightsSnapshot(
            weights_set_id=self._active_weights_set_id,
            weights_set_name="predictive_model_warmup",
            weights={"prob_hold": 1.0, "prob_buy": 0.0, "prob_sell": 0.0},
            timestamp=current_time,
        )
        indicators_snapshot = IndicatorSnapshot(
            timestamp=current_time,
            symbol=symbol,
            candle_close=current_price,
            indicators={"status": "warming_up"},
        )
        return TradingDecision(
            decision_type=DecisionType.SKIP,
            timestamp=current_time,
            symbol=symbol,
            weighted_score=0.0,
            weights_snapshot=weights_snapshot,
            indicators_snapshot=indicators_snapshot,
            decision_reason=reason,
        )

    async def _log_decision(self, decision: TradingDecision) -> None:
        """Log decision into database signals table."""
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
                Decimal(str(round(decision.weighted_score, 4))),
                json.dumps(decision.weights_snapshot.to_dict()),
                json.dumps(decision.indicators_snapshot.to_dict()),
                decision.decision_reason,
            )

        logger.debug(f"Predictive decision logged to DB: signal_id={signal_id}")

    async def _log_score(
        self,
        weighted_score: float,
        weights_snapshot: WeightsSnapshot,
        indicators_snapshot: IndicatorSnapshot,
        current_time: datetime,
        symbol: str,
        order_id: Optional[UUID] = None,
    ) -> None:
        """Log score calculation to score_logs table."""
        if self.config_id is None or weights_snapshot.weights_set_id is None:
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
            await conn.fetchval(
                query,
                self.run_id,
                self.config_id,
                weights_snapshot.weights_set_id,
                order_id,
                current_time,
                symbol,
                Decimal(str(round(weighted_score, 4))),
                json.dumps(indicators_snapshot.to_dict()),
            )
