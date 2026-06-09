"""
Strategy engine configuration.

This module defines configuration dataclasses for all strategy engine components,
loaded from environment variables or database settings.
"""

import logging
from dataclasses import dataclass

from .types import PositionSizeMode, StopLossMode, TakeProfitMode

logger = logging.getLogger(__name__)


@dataclass
class StrategyConfig:
    """Core strategy configuration."""

    entry_threshold: float = 0.6  # Weighted score threshold to enter position
    exit_threshold: float = -0.3  # Weighted score threshold to exit position
    confirmation_candles: int = 2  # Anti-repainting: required consecutive candles

    def __post_init__(self):
        """Validate configuration."""
        if not -1.0 <= self.entry_threshold <= 1.0:
            raise ValueError(f"entry_threshold must be in [-1, 1], got {self.entry_threshold}")
        if not -1.0 <= self.exit_threshold <= 1.0:
            raise ValueError(f"exit_threshold must be in [-1, 1], got {self.exit_threshold}")
        if self.exit_threshold >= self.entry_threshold:
            raise ValueError(
                f"exit_threshold ({self.exit_threshold}) must be < entry_threshold ({self.entry_threshold})"
            )
        if self.confirmation_candles < 1:
            raise ValueError(f"confirmation_candles must be >= 1, got {self.confirmation_candles}")


@dataclass
class RiskConfig:
    """Risk management configuration."""

    max_trades_per_day: int = 5  # Maximum trades allowed per day
    max_exposure_percent: float = 30.0  # Maximum % of capital exposed simultaneously
    position_size_mode: PositionSizeMode = PositionSizeMode.CONFIDENCE  # Position sizing mode
    fixed_size_usdt: float = 100.0  # Fixed size in USDT (FIXED mode only)
    atr_multiplier: float = 2.0  # ATR multiplier for sizing (RISK_ATR mode only)
    capital_risk_percent: float = 1.0  # % capital to risk per trade (RISK_ATR mode only)

    def __post_init__(self):
        """Validate configuration."""
        if self.max_trades_per_day < 1:
            raise ValueError(f"max_trades_per_day must be >= 1, got {self.max_trades_per_day}")
        if not 0.0 < self.max_exposure_percent <= 100.0:
            raise ValueError(
                f"max_exposure_percent must be in (0, 100], got {self.max_exposure_percent}"
            )
        if self.fixed_size_usdt <= 0:
            raise ValueError(f"fixed_size_usdt must be > 0, got {self.fixed_size_usdt}")
        if self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {self.atr_multiplier}")
        if not 0.0 < self.capital_risk_percent <= 100.0:
            raise ValueError(
                f"capital_risk_percent must be in (0, 100], got {self.capital_risk_percent}"
            )


@dataclass
class StopLossConfig:
    """Stop-loss configuration."""

    mode: StopLossMode = StopLossMode.ATR  # Stop-loss calculation mode
    atr_multiplier: float = 2.0  # ATR multiplier (ATR mode only)
    fixed_percent: float = 2.0  # Fixed % loss (FIXED mode only)

    def __post_init__(self):
        """Validate configuration."""
        if self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {self.atr_multiplier}")
        if not 0.0 < self.fixed_percent <= 100.0:
            raise ValueError(f"fixed_percent must be in (0, 100], got {self.fixed_percent}")


@dataclass
class TakeProfitConfig:
    """Take-profit configuration."""

    mode: TakeProfitMode = TakeProfitMode.ATR  # Take-profit calculation mode
    atr_multiplier: float = 3.0  # ATR multiplier (ATR mode only)
    fixed_percent: float = 4.0  # Fixed % gain (FIXED mode only)

    def __post_init__(self):
        """Validate configuration."""
        if self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {self.atr_multiplier}")
        if not 0.0 < self.fixed_percent <= 100.0:
            raise ValueError(f"fixed_percent must be in (0, 100], got {self.fixed_percent}")


@dataclass
class CooldownConfig:
    """Cooldown configuration."""

    after_trade_seconds: int = 3600  # Cooldown period after closing a trade

    def __post_init__(self):
        """Validate configuration."""
        if self.after_trade_seconds < 0:
            raise ValueError(f"after_trade_seconds must be >= 0, got {self.after_trade_seconds}")


@dataclass
class StrategyEngineConfig:
    """
    Complete strategy engine configuration.

    Aggregates all configuration components for easy management and passing.
    """

    strategy: StrategyConfig
    risk: RiskConfig
    stop_loss: StopLossConfig
    take_profit: TakeProfitConfig
    cooldown: CooldownConfig

    @classmethod
    def from_env(cls) -> "StrategyEngineConfig":
        """
        Load configuration from environment variables.

        This method reads all STRATEGY_*, RISK_*, SL_*, TP_*, and COOLDOWN_*
        environment variables and constructs a complete configuration object.

        Returns:
            StrategyEngineConfig instance with values from environment

        Raises:
            ValueError: If any configuration value is invalid
        """
        import os

        # Strategy configuration
        strategy = StrategyConfig(
            entry_threshold=float(os.getenv("STRATEGY_ENTRY_THRESHOLD", "0.6")),
            exit_threshold=float(os.getenv("STRATEGY_EXIT_THRESHOLD", "-0.3")),
            confirmation_candles=int(os.getenv("STRATEGY_CONFIRMATION_CANDLES", "2"))
        )

        # Risk configuration
        position_size_mode_str = os.getenv("RISK_POSITION_SIZE_MODE", "confidence")
        risk = RiskConfig(
            max_trades_per_day=int(os.getenv("RISK_MAX_TRADES_PER_DAY", "5")),
            max_exposure_percent=float(os.getenv("RISK_MAX_EXPOSURE_PERCENT", "30.0")),
            position_size_mode=PositionSizeMode(position_size_mode_str),
            fixed_size_usdt=float(os.getenv("RISK_FIXED_SIZE_USDT", "100.0")),
            atr_multiplier=float(os.getenv("RISK_ATR_MULTIPLIER", "2.0")),
            capital_risk_percent=float(os.getenv("RISK_CAPITAL_RISK_PERCENT", "1.0"))
        )

        # Stop-loss configuration
        sl_mode_str = os.getenv("SL_MODE", "atr")
        stop_loss = StopLossConfig(
            mode=StopLossMode(sl_mode_str),
            atr_multiplier=float(os.getenv("SL_ATR_MULTIPLIER", "2.0")),
            fixed_percent=float(os.getenv("SL_FIXED_PERCENT", "2.0"))
        )

        # Take-profit configuration
        tp_mode_str = os.getenv("TP_MODE", "atr")
        take_profit = TakeProfitConfig(
            mode=TakeProfitMode(tp_mode_str),
            atr_multiplier=float(os.getenv("TP_ATR_MULTIPLIER", "3.0")),
            fixed_percent=float(os.getenv("TP_FIXED_PERCENT", "4.0"))
        )

        # Cooldown configuration
        cooldown = CooldownConfig(
            after_trade_seconds=int(os.getenv("COOLDOWN_AFTER_TRADE_SECONDS", "3600"))
        )

        return cls(
            strategy=strategy,
            risk=risk,
            stop_loss=stop_loss,
            take_profit=take_profit,
            cooldown=cooldown
        )

    @classmethod
    async def from_db(cls, db_pool) -> tuple["StrategyEngineConfig", "UUID"]:
        """
        Load configuration from database.

        Loads the most recent configuration from the config table.

        Args:
            db_pool: asyncpg database connection pool

        Returns:
            Tuple of (StrategyEngineConfig instance, config_id UUID)

        Raises:
            ValueError: If no configuration exists in database
            ValueError: If any configuration value is invalid
        """
        import json
        from uuid import UUID

        query = "SELECT id, config FROM config ORDER BY updated_at DESC LIMIT 1"

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query)

        if not row or not row["config"]:
            raise ValueError(
                "No configuration found in database. Please create a config first using 'python -m main config create'")

        # Parse config
        config = row["config"]
        if isinstance(config, str):
            config = json.loads(config)

        logger.debug(f"Loaded config: {config}")

        # Extract strategy config
        strategy_data = config.get("strategy", {})
        strategy = StrategyConfig(
            entry_threshold=float(strategy_data.get("entry_threshold", 0.6)),
            exit_threshold=float(strategy_data.get("exit_threshold", -0.3)),
            confirmation_candles=int(strategy_data.get("confirmation_candles", 2))
        )

        # Extract risk config
        risk_data = config.get("risk", {})
        position_size_mode_str = risk_data.get("position_size_mode", "confidence")
        risk = RiskConfig(
            max_trades_per_day=int(risk_data.get("max_trades_per_day", 5)),
            max_exposure_percent=float(risk_data.get("max_exposure_percent", 30.0)),
            position_size_mode=PositionSizeMode(position_size_mode_str),
            fixed_size_usdt=float(risk_data.get("fixed_size_usdt", 100.0)),
            atr_multiplier=float(risk_data.get("atr_multiplier", 2.0)),
            capital_risk_percent=float(risk_data.get("capital_risk_percent", 1.0))
        )

        # Extract stop-loss config
        sl_data = config.get("stop_loss", {})
        sl_mode_str = sl_data.get("mode", "atr")
        stop_loss = StopLossConfig(
            mode=StopLossMode(sl_mode_str),
            atr_multiplier=float(sl_data.get("atr_multiplier", 2.0)),
            fixed_percent=float(sl_data.get("fixed_percent", 2.0))
        )

        # Extract take-profit config
        tp_data = config.get("take_profit", {})
        tp_mode_str = tp_data.get("mode", "atr")
        take_profit = TakeProfitConfig(
            mode=TakeProfitMode(tp_mode_str),
            atr_multiplier=float(tp_data.get("atr_multiplier", 3.0)),
            fixed_percent=float(tp_data.get("fixed_percent", 4.0))
        )

        # Extract cooldown config
        cooldown_data = config.get("cooldown", {})
        cooldown = CooldownConfig(
            after_trade_seconds=int(cooldown_data.get("after_trade_seconds", 3600))
        )

        config_instance = cls(
            strategy=strategy,
            risk=risk,
            stop_loss=stop_loss,
            take_profit=take_profit,
            cooldown=cooldown
        )

        return config_instance, row["id"]

    def to_snapshot(self) -> dict:
        """
        Convert configuration to snapshot format for runs.config_snapshot.

        Returns:
            Dictionary matching A3_snapshots_format.md specification
        """
        return {
            "strategy": {
                "entry_threshold": self.strategy.entry_threshold,
                "exit_threshold": self.strategy.exit_threshold,
                "confirmation_candles": self.strategy.confirmation_candles
            },
            "risk": {
                "max_trades_per_day": self.risk.max_trades_per_day,
                "max_exposure_percent": self.risk.max_exposure_percent,
                "position_size_mode": self.risk.position_size_mode.value,
                "fixed_size_usdt": self.risk.fixed_size_usdt,
                "atr_multiplier": self.risk.atr_multiplier,
                "capital_risk_percent": self.risk.capital_risk_percent
            },
            "stop_loss": {
                "mode": self.stop_loss.mode.value,
                "atr_multiplier": self.stop_loss.atr_multiplier,
                "fixed_percent": self.stop_loss.fixed_percent
            },
            "take_profit": {
                "mode": self.take_profit.mode.value,
                "atr_multiplier": self.take_profit.atr_multiplier,
                "fixed_percent": self.take_profit.fixed_percent
            },
            "cooldown": {
                "after_trade_seconds": self.cooldown.after_trade_seconds
            }
        }
