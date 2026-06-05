"""
Pydantic models for configuration endpoints.

Request/response models for bot configuration and indicator parameters.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class IndicatorConfigResponse(BaseModel):
    """Indicator configuration response."""

    name: str = Field(..., description="Indicator name")
    enabled: bool = Field(..., description="Whether indicator is enabled")
    parameters: dict[str, Any] = Field(..., description="Indicator parameters")
    description: Optional[str] = Field(None, description="Indicator description")


class StrategyConfigResponse(BaseModel):
    """Strategy configuration response."""

    entry_threshold: float = Field(..., description="Entry signal threshold [-1, 1]")
    exit_threshold: float = Field(..., description="Exit signal threshold [-1, 1]")
    confirmation_candles: int = Field(..., description="Anti-repainting confirmation candles")


class RiskConfigResponse(BaseModel):
    """Risk management configuration response."""

    max_trades_per_day: int = Field(..., description="Max trades per day")
    max_exposure_percent: float = Field(..., description="Max exposure as % of capital")
    position_size_mode: str = Field(..., description="Position sizing: fixed, confidence, risk_atr")
    fixed_size_usdt: float = Field(..., description="Fixed position size in USDT")
    atr_multiplier: float = Field(..., description="ATR multiplier for sizing")
    capital_risk_percent: float = Field(..., description="% of capital to risk per trade")


class StopLossTakeProfitConfigResponse(BaseModel):
    """Stop-loss and take-profit configuration response."""

    sl_mode: str = Field(..., description="SL mode: atr, fixed")
    sl_atr_multiplier: float = Field(..., description="SL ATR multiplier")
    sl_fixed_percent: float = Field(..., description="SL fixed percent")
    tp_mode: str = Field(..., description="TP mode: atr, fixed")
    tp_atr_multiplier: float = Field(..., description="TP ATR multiplier")
    tp_fixed_percent: float = Field(..., description="TP fixed percent")


class BinanceConfigResponse(BaseModel):
    """Binance configuration response."""

    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")
    testnet: bool = Field(..., description="Use Binance testnet")
    max_slippage_percent: float = Field(..., description="Max slippage %")
    order_timeout_seconds: int = Field(..., description="Order timeout in seconds")


class ConfigResponse(BaseModel):
    """Complete configuration response."""

    binance: BinanceConfigResponse = Field(..., description="Binance settings")
    strategy: StrategyConfigResponse = Field(..., description="Strategy settings")
    risk: RiskConfigResponse = Field(..., description="Risk management settings")
    stop_loss_take_profit: StopLossTakeProfitConfigResponse = Field(
        ..., description="Stop-loss/take-profit settings"
    )
    indicators: dict[str, IndicatorConfigResponse] = Field(
        ..., description="All indicator configurations"
    )


class IndicatorParameterUpdate(BaseModel):
    """Update for indicator parameter."""

    value: Any = Field(..., description="New parameter value")


class StrategyConfigUpdate(BaseModel):
    """Request to update strategy configuration."""

    entry_threshold: Optional[float] = Field(None, description="New entry threshold")
    exit_threshold: Optional[float] = Field(None, description="New exit threshold")
    confirmation_candles: Optional[int] = Field(None, description="New confirmation candles")


class RiskConfigUpdate(BaseModel):
    """Request to update risk configuration."""

    max_trades_per_day: Optional[int] = Field(None)
    max_exposure_percent: Optional[float] = Field(None)
    position_size_mode: Optional[str] = Field(None)
    fixed_size_usdt: Optional[float] = Field(None)
    atr_multiplier: Optional[float] = Field(None)
    capital_risk_percent: Optional[float] = Field(None)


class UserIndicatorResponse(BaseModel):
    """User indicator response."""

    symbol: str = Field(..., description="Symbol")
    signal: Optional[float] = Field(None, description="Signal value [-1, 1] or None if not set")
    note: Optional[str] = Field(None, description="User note")
    expires_at: Optional[str] = Field(None, description="Expiration timestamp")
    status: str = Field(default="ValueSet", description="Status: ValueSet or ValueNotSet")


class UserIndicatorUpdateRequest(BaseModel):
    """Request to update user indicator."""

    signal: float = Field(..., description="Signal value [-1, 1]", ge=-1, le=1)
    note: Optional[str] = Field(None, description="Optional note")
    expires_in_hours: int = Field(default=24, ge=1, description="How long the signal is valid (hours)")
