"""
Strategy engine for crypto trading bot.

This module implements the core strategy engine with weighted scoring,
position sizing, risk management, and stop-loss/take-profit logic.
"""

from .types import (
    DecisionType,
    PositionSizeMode,
    StopLossMode,
    TakeProfitMode,
    WeightsSnapshot,
    IndicatorSnapshot,
    TradingDecision,
    ConfirmationState,
    PositionState,
    RiskState
)

from .config import (
    StrategyConfig,
    RiskConfig,
    StopLossConfig,
    TakeProfitConfig,
    CooldownConfig,
    StrategyEngineConfig
)

from .sizing import calculate_position_size, calculate_position_quantity
from .stops import (
    calculate_stop_loss,
    calculate_take_profit,
    calculate_risk_reward_ratio
)
from .risk import RiskManager
from .engine import StrategyEngine

__all__ = [
    # Types
    "DecisionType",
    "PositionSizeMode",
    "StopLossMode",
    "TakeProfitMode",
    "WeightsSnapshot",
    "IndicatorSnapshot",
    "TradingDecision",
    "ConfirmationState",
    "PositionState",
    "RiskState",
    # Config
    "StrategyConfig",
    "RiskConfig",
    "StopLossConfig",
    "TakeProfitConfig",
    "CooldownConfig",
    "StrategyEngineConfig",
    # Position sizing
    "calculate_position_size",
    "calculate_position_quantity",
    # Stop-loss / Take-profit
    "calculate_stop_loss",
    "calculate_take_profit",
    "calculate_risk_reward_ratio",
    # Risk management
    "RiskManager",
    # Core engine
    "StrategyEngine",
]
