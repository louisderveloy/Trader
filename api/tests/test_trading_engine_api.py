"""
Tests for trading engine configuration models and validation.
"""

import pytest
from pydantic import ValidationError

from api.models.enums import TradingEngineType
from api.models.config import (
    TradingEngineConfigResponse,
    TradingEngineConfigUpdate,
    ConfigResponse,
    BinanceConfigResponse,
    StrategyConfigResponse,
    RiskConfigResponse,
    StopLossTakeProfitConfigResponse,
    CooldownConfigResponse,
)


def test_trading_engine_type_enum():
    """Verify supported trading engine types."""
    assert TradingEngineType.INDICATORS == "indicators"
    assert TradingEngineType.PREDICTIVE_MODEL == "predictive_model"


def test_trading_engine_update_valid():
    """Verify TradingEngineConfigUpdate with valid types."""
    update1 = TradingEngineConfigUpdate(engine_type=TradingEngineType.INDICATORS)
    assert update1.engine_type == TradingEngineType.INDICATORS

    update2 = TradingEngineConfigUpdate(engine_type=TradingEngineType.PREDICTIVE_MODEL)
    assert update2.engine_type == TradingEngineType.PREDICTIVE_MODEL


def test_trading_engine_update_invalid():
    """Verify TradingEngineConfigUpdate rejects unknown engine types."""
    with pytest.raises(ValidationError):
        TradingEngineConfigUpdate(engine_type="random_architecture")


def test_config_response_includes_trading_engine():
    """Verify ConfigResponse serializes trading_engine field."""
    cfg = ConfigResponse(
        trading_engine=TradingEngineConfigResponse(engine_type="predictive_model"),
        binance=BinanceConfigResponse(
            symbol="BTCUSDC",
            timeframe="15m",
            max_slippage_percent=0.2,
            order_timeout_seconds=3600,
        ),
        strategy=StrategyConfigResponse(
            entry_threshold=0.85,
            exit_threshold=0.88,
            confirmation_candles=1,
        ),
        risk=RiskConfigResponse(
            max_trades_per_day=5,
            max_exposure_percent=30.0,
            position_size_mode="fixed",
            fixed_size_percent=10.0,
            atr_multiplier=2.0,
            capital_risk_percent=1.0,
        ),
        stop_loss_take_profit=StopLossTakeProfitConfigResponse(
            sl_mode="fixed",
            sl_atr_multiplier=2.0,
            sl_fixed_percent=2.0,
            tp_mode="fixed",
            tp_atr_multiplier=3.0,
            tp_fixed_percent=4.0,
        ),
        cooldown=CooldownConfigResponse(
            after_trade_seconds=3600,
        ),
        indicators={},
    )

    data = cfg.model_dump()
    assert "trading_engine" in data
    assert data["trading_engine"]["engine_type"] == "predictive_model"
