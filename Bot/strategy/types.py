"""
Strategy engine type definitions.

This module defines all core types, enums, and dataclasses used by the strategy engine
for decision making, position sizing, risk management, and stop-loss/take-profit logic.
"""

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from uuid import UUID


class DecisionType(str, Enum):
    """Type of trading decision."""

    ENTRY_LONG = "entry_long"  # Open a long position
    EXIT = "exit"  # Close current position
    SKIP = "skip"  # No action taken


class PositionSizeMode(str, Enum):
    """Position sizing calculation mode."""

    FIXED = "fixed"  # Fixed USDT amount per trade
    CONFIDENCE = "confidence"  # Size proportional to weighted score
    RISK_ATR = "risk_atr"  # Size based on ATR and % capital to risk


class StopLossMode(str, Enum):
    """Stop-loss calculation mode."""

    ATR = "atr"  # ATR-based stop-loss
    FIXED = "fixed"  # Fixed percentage stop-loss


class TakeProfitMode(str, Enum):
    """Take-profit calculation mode."""

    ATR = "atr"  # ATR-based take-profit
    FIXED = "fixed"  # Fixed percentage take-profit


@dataclass
class WeightsSnapshot:
    """Snapshot of active indicator weights at decision time."""

    weights_set_id: UUID
    weights_set_name: str
    weights: Dict[str, float]  # {"ema": 0.15, "macd": 0.20, ...}
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        return {
            "weights_set_id": str(self.weights_set_id),
            "weights_set_name": self.weights_set_name,
            "weights": self.weights,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class IndicatorSnapshot:
    """Snapshot of all indicator values and signals at decision time."""

    timestamp: datetime
    symbol: str
    candle_close: Decimal
    indicators: Dict[str, Dict[str, Any]]  # {"ema": {"ema_50": 42100.00, "signal": 0.45}, ...}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        def serialize_value(value):
            """Recursively serialize values, converting Decimal to float."""
            if isinstance(value, Decimal):
                return float(value)
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return [serialize_value(v) for v in value]
            else:
                return value

        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "candle_close": float(self.candle_close),
            "indicators": serialize_value(self.indicators)
        }


@dataclass
class TradingDecision:
    """
    Complete trading decision with all context and snapshots.

    This represents the output of the strategy engine for a single candle,
    including the decision type, weighted score, weights snapshot, indicators snapshot,
    and human-readable reason for the decision.
    """

    decision_type: DecisionType
    timestamp: datetime
    symbol: str
    weighted_score: float  # Result of Σ (signal_i × poids_i) ∈ [-1, 1]
    weights_snapshot: WeightsSnapshot
    indicators_snapshot: IndicatorSnapshot
    decision_reason: str  # Human-readable explanation

    # Optional fields for entry decisions
    entry_price: Optional[Decimal] = None
    position_size_usdt: Optional[Decimal] = None
    position_size_qty: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    def __post_init__(self):
        """Validate decision data."""
        if not -1.0 <= self.weighted_score <= 1.0:
            raise ValueError(f"Weighted score must be in [-1, 1], got {self.weighted_score}")

    def validate_complete(self):
        """
        Validate that decision is complete with all required fields.

        Should be called after enhancement for ENTRY_LONG decisions.

        Raises:
            ValueError: If required fields are missing
        """
        if self.decision_type == DecisionType.ENTRY_LONG:
            if self.entry_price is None:
                raise ValueError("entry_price is required for ENTRY_LONG decisions")
            if self.position_size_usdt is None:
                raise ValueError("position_size_usdt is required for ENTRY_LONG decisions")


@dataclass
class ConfirmationState:
    """
    Anti-repainting confirmation state.

    Tracks consecutive candles where entry/exit conditions are met
    to prevent acting on unconfirmed signals.
    """

    decision_type: DecisionType
    consecutive_candles: int  # Number of consecutive candles confirming the signal
    first_seen_at: datetime
    last_weighted_score: float

    def is_confirmed(self, required_candles: int) -> bool:
        """Check if signal is confirmed over required number of candles."""
        return self.consecutive_candles >= required_candles


@dataclass
class PositionState:
    """
    Current position state.

    Tracks open position details for decision making and risk management.
    """

    is_open: bool
    symbol: Optional[str] = None
    entry_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    @property
    def exposure_usdt(self) -> Decimal:
        """Calculate current exposure in USDT."""
        if not self.is_open or self.entry_price is None or self.quantity is None:
            return Decimal("0")
        return self.entry_price * self.quantity


@dataclass
class RiskState:
    """
    Risk management state.

    Tracks quotas, cooldowns, and exposure limits.
    """

    trades_today: int
    last_trade_closed_at: Optional[datetime]
    current_exposure_usdt: Decimal

    def is_in_cooldown(self, cooldown_seconds: int, current_time: datetime) -> bool:
        """Check if still in cooldown period after last trade."""
        if self.last_trade_closed_at is None:
            return False
        elapsed = (current_time - self.last_trade_closed_at).total_seconds()
        return elapsed < cooldown_seconds

    def can_open_new_trade(
        self,
        max_trades_per_day: int,
        max_exposure_percent: float,
        total_capital: Decimal,
        new_position_size: Decimal,
        cooldown_seconds: int,
        current_time: datetime
    ) -> tuple[bool, str]:
        """
        Check if a new trade can be opened given risk constraints.

        Returns:
            (can_open, reason) tuple
        """
        # Check daily trade quota
        if self.trades_today >= max_trades_per_day:
            return False, f"Daily trade quota reached ({self.trades_today}/{max_trades_per_day})"

        # Check cooldown
        if self.is_in_cooldown(cooldown_seconds, current_time):
            remaining = cooldown_seconds - (current_time - self.last_trade_closed_at).total_seconds()
            return False, f"In cooldown period ({remaining:.0f}s remaining)"

        # Check exposure limit
        new_total_exposure = self.current_exposure_usdt + new_position_size
        max_exposure = total_capital * Decimal(str(max_exposure_percent / 100.0))

        if new_total_exposure > max_exposure:
            return False, (
                f"Exposure limit exceeded: {new_total_exposure:.2f} USDT "
                f"(max {max_exposure:.2f} USDT = {max_exposure_percent}% of capital)"
            )

        return True, "OK"
