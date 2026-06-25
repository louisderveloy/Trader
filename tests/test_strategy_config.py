"""
Unit tests for strategy/config.py
"""

import pytest
import os

from strategy.config import (
    StrategyConfig,
    RiskConfig,
    StopLossConfig,
    TakeProfitConfig,
    CooldownConfig,
    StrategyEngineConfig
)
from strategy.types import PositionSizeMode, StopLossMode, TakeProfitMode


# --- StrategyConfig tests ---

def test_strategy_config_defaults():
    """Test StrategyConfig with default values"""
    config = StrategyConfig()

    assert config.entry_threshold == 0.6
    assert config.exit_threshold == -0.3
    assert config.confirmation_candles == 2


def test_strategy_config_custom():
    """Test StrategyConfig with custom values"""
    config = StrategyConfig(
        entry_threshold=0.7,
        exit_threshold=-0.2,
        confirmation_candles=3
    )

    assert config.entry_threshold == 0.7
    assert config.exit_threshold == -0.2
    assert config.confirmation_candles == 3


def test_strategy_config_invalid_entry_threshold():
    """Test StrategyConfig with invalid entry_threshold"""
    with pytest.raises(ValueError, match="entry_threshold must be in \\[-1, 1\\]"):
        StrategyConfig(entry_threshold=1.5)


def test_strategy_config_invalid_exit_threshold():
    """Test StrategyConfig with invalid exit_threshold"""
    with pytest.raises(ValueError, match="exit_threshold must be in \\[-1, 1\\]"):
        StrategyConfig(exit_threshold=-1.5)


def test_strategy_config_exit_above_entry():
    """Test StrategyConfig with exit_threshold >= entry_threshold"""
    with pytest.raises(ValueError, match="exit_threshold .* must be < entry_threshold"):
        StrategyConfig(entry_threshold=0.5, exit_threshold=0.6)


def test_strategy_config_invalid_confirmation_candles():
    """Test StrategyConfig with invalid confirmation_candles"""
    with pytest.raises(ValueError, match="confirmation_candles must be >= 1"):
        StrategyConfig(confirmation_candles=0)


# --- RiskConfig tests ---

def test_risk_config_defaults():
    """Test RiskConfig with default values"""
    config = RiskConfig()

    assert config.max_trades_per_day == 5
    assert config.max_exposure_percent == 30.0
    assert config.position_size_mode == PositionSizeMode.CONFIDENCE
    assert config.fixed_size_percent == 10.0
    assert config.atr_multiplier == 2.0
    assert config.capital_risk_percent == 1.0


def test_risk_config_custom():
    """Test RiskConfig with custom values"""
    config = RiskConfig(
        max_trades_per_day=10,
        max_exposure_percent=50.0,
        position_size_mode=PositionSizeMode.FIXED,
        fixed_size_percent=20.0
    )

    assert config.max_trades_per_day == 10
    assert config.max_exposure_percent == 50.0
    assert config.position_size_mode == PositionSizeMode.FIXED


def test_risk_config_invalid_max_trades():
    """Test RiskConfig with invalid max_trades_per_day"""
    with pytest.raises(ValueError, match="max_trades_per_day must be >= 1"):
        RiskConfig(max_trades_per_day=0)


def test_risk_config_invalid_max_exposure():
    """Test RiskConfig with invalid max_exposure_percent"""
    with pytest.raises(ValueError, match="max_exposure_percent must be in \\(0, 100\\]"):
        RiskConfig(max_exposure_percent=150.0)


def test_risk_config_invalid_fixed_size():
    """Test RiskConfig with invalid fixed_size_percent (<= 0)"""
    with pytest.raises(ValueError, match="fixed_size_percent must be in \\(0, 100\\]"):
        RiskConfig(fixed_size_percent=-100.0)


def test_risk_config_fixed_size_above_100():
    """Test RiskConfig rejects fixed_size_percent above 100% of capital"""
    with pytest.raises(ValueError, match="fixed_size_percent must be in \\(0, 100\\]"):
        RiskConfig(fixed_size_percent=150.0)


def test_risk_config_invalid_atr_multiplier():
    """Test RiskConfig with invalid atr_multiplier"""
    with pytest.raises(ValueError, match="atr_multiplier must be > 0"):
        RiskConfig(atr_multiplier=-1.0)


def test_risk_config_invalid_capital_risk():
    """Test RiskConfig with invalid capital_risk_percent"""
    with pytest.raises(ValueError, match="capital_risk_percent must be in \\(0, 100\\]"):
        RiskConfig(capital_risk_percent=150.0)


# --- StopLossConfig tests ---

def test_stop_loss_config_defaults():
    """Test StopLossConfig with default values"""
    config = StopLossConfig()

    assert config.mode == StopLossMode.ATR
    assert config.atr_multiplier == 2.0
    assert config.fixed_percent == 2.0


def test_stop_loss_config_custom():
    """Test StopLossConfig with custom values"""
    config = StopLossConfig(
        mode=StopLossMode.FIXED,
        fixed_percent=3.0
    )

    assert config.mode == StopLossMode.FIXED
    assert config.fixed_percent == 3.0


def test_stop_loss_config_invalid_atr_multiplier():
    """Test StopLossConfig with invalid atr_multiplier"""
    with pytest.raises(ValueError, match="atr_multiplier must be > 0"):
        StopLossConfig(atr_multiplier=-1.0)


def test_stop_loss_config_invalid_fixed_percent():
    """Test StopLossConfig with invalid fixed_percent"""
    with pytest.raises(ValueError, match="fixed_percent must be in \\(0, 100\\]"):
        StopLossConfig(fixed_percent=150.0)


# --- TakeProfitConfig tests ---

def test_take_profit_config_defaults():
    """Test TakeProfitConfig with default values"""
    config = TakeProfitConfig()

    assert config.mode == TakeProfitMode.ATR
    assert config.atr_multiplier == 3.0
    assert config.fixed_percent == 4.0


def test_take_profit_config_custom():
    """Test TakeProfitConfig with custom values"""
    config = TakeProfitConfig(
        mode=TakeProfitMode.FIXED,
        fixed_percent=5.0
    )

    assert config.mode == TakeProfitMode.FIXED
    assert config.fixed_percent == 5.0


def test_take_profit_config_invalid_atr_multiplier():
    """Test TakeProfitConfig with invalid atr_multiplier"""
    with pytest.raises(ValueError, match="atr_multiplier must be > 0"):
        TakeProfitConfig(atr_multiplier=-1.0)


def test_take_profit_config_invalid_fixed_percent():
    """Test TakeProfitConfig with invalid fixed_percent"""
    with pytest.raises(ValueError, match="fixed_percent must be in \\(0, 100\\]"):
        TakeProfitConfig(fixed_percent=150.0)


# --- CooldownConfig tests ---

def test_cooldown_config_defaults():
    """Test CooldownConfig with default values"""
    config = CooldownConfig()

    assert config.after_trade_seconds == 3600


def test_cooldown_config_custom():
    """Test CooldownConfig with custom value"""
    config = CooldownConfig(after_trade_seconds=1800)

    assert config.after_trade_seconds == 1800


def test_cooldown_config_invalid_seconds():
    """Test CooldownConfig with invalid after_trade_seconds"""
    with pytest.raises(ValueError, match="after_trade_seconds must be >= 0"):
        CooldownConfig(after_trade_seconds=-100)


# --- StrategyEngineConfig tests ---

def test_strategy_engine_config_creation():
    """Test StrategyEngineConfig creation"""
    strategy = StrategyConfig()
    risk = RiskConfig()
    sl = StopLossConfig()
    tp = TakeProfitConfig()
    cooldown = CooldownConfig()

    config = StrategyEngineConfig(
        strategy=strategy,
        risk=risk,
        stop_loss=sl,
        take_profit=tp,
        cooldown=cooldown
    )

    assert config.strategy == strategy
    assert config.risk == risk
    assert config.stop_loss == sl
    assert config.take_profit == tp
    assert config.cooldown == cooldown


def test_strategy_engine_config_from_env():
    """Test StrategyEngineConfig.from_env() with environment variables"""
    # Set environment variables
    os.environ["STRATEGY_ENTRY_THRESHOLD"] = "0.7"
    os.environ["STRATEGY_EXIT_THRESHOLD"] = "-0.2"
    os.environ["STRATEGY_CONFIRMATION_CANDLES"] = "3"
    os.environ["RISK_MAX_TRADES_PER_DAY"] = "10"
    os.environ["RISK_MAX_EXPOSURE_PERCENT"] = "40.0"
    os.environ["RISK_POSITION_SIZE_MODE"] = "fixed"
    os.environ["SL_MODE"] = "fixed"
    os.environ["SL_FIXED_PERCENT"] = "3.0"
    os.environ["TP_MODE"] = "fixed"
    os.environ["TP_FIXED_PERCENT"] = "5.0"
    os.environ["COOLDOWN_AFTER_TRADE_SECONDS"] = "1800"

    config = StrategyEngineConfig.from_env()

    assert config.strategy.entry_threshold == 0.7
    assert config.strategy.exit_threshold == -0.2
    assert config.strategy.confirmation_candles == 3
    assert config.risk.max_trades_per_day == 10
    assert config.risk.max_exposure_percent == 40.0
    assert config.risk.position_size_mode == PositionSizeMode.FIXED
    assert config.stop_loss.mode == StopLossMode.FIXED
    assert config.stop_loss.fixed_percent == 3.0
    assert config.take_profit.mode == TakeProfitMode.FIXED
    assert config.take_profit.fixed_percent == 5.0
    assert config.cooldown.after_trade_seconds == 1800

    # Cleanup
    for key in [
        "STRATEGY_ENTRY_THRESHOLD", "STRATEGY_EXIT_THRESHOLD", "STRATEGY_CONFIRMATION_CANDLES",
        "RISK_MAX_TRADES_PER_DAY", "RISK_MAX_EXPOSURE_PERCENT", "RISK_POSITION_SIZE_MODE",
        "SL_MODE", "SL_FIXED_PERCENT", "TP_MODE", "TP_FIXED_PERCENT", "COOLDOWN_AFTER_TRADE_SECONDS"
    ]:
        os.environ.pop(key, None)


def test_strategy_engine_config_from_env_defaults():
    """Test StrategyEngineConfig.from_env() with default values"""
    # Clear environment variables
    for key in [
        "STRATEGY_ENTRY_THRESHOLD", "STRATEGY_EXIT_THRESHOLD", "STRATEGY_CONFIRMATION_CANDLES",
        "RISK_MAX_TRADES_PER_DAY", "RISK_MAX_EXPOSURE_PERCENT", "RISK_POSITION_SIZE_MODE",
        "SL_MODE", "SL_FIXED_PERCENT", "TP_MODE", "TP_FIXED_PERCENT", "COOLDOWN_AFTER_TRADE_SECONDS"
    ]:
        os.environ.pop(key, None)

    config = StrategyEngineConfig.from_env()

    # Should use default values
    assert config.strategy.entry_threshold == 0.6
    assert config.risk.max_trades_per_day == 5
    assert config.stop_loss.mode == StopLossMode.ATR


def test_strategy_engine_config_to_snapshot():
    """Test StrategyEngineConfig.to_snapshot()"""
    config = StrategyEngineConfig(
        strategy=StrategyConfig(entry_threshold=0.7),
        risk=RiskConfig(max_trades_per_day=10),
        stop_loss=StopLossConfig(mode=StopLossMode.FIXED),
        take_profit=TakeProfitConfig(mode=TakeProfitMode.FIXED),
        cooldown=CooldownConfig(after_trade_seconds=1800)
    )

    snapshot = config.to_snapshot()

    assert snapshot["strategy"]["entry_threshold"] == 0.7
    assert snapshot["risk"]["max_trades_per_day"] == 10
    assert snapshot["stop_loss"]["mode"] == "fixed"
    assert snapshot["take_profit"]["mode"] == "fixed"
    assert snapshot["cooldown"]["after_trade_seconds"] == 1800
