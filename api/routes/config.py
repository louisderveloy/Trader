"""
Configuration management endpoints.

REST API for reading and updating bot configuration and indicator parameters.
"""
import asyncpg
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import User, get_current_user
from ..config import settings
from ..csrf_helper import validate_csrf_token
from ..database import get_db_pool
from ..limiter import limiter
from ..models.config import (
    ConfigResponse,
    IndicatorConfigResponse,
    RiskConfigResponse,
    RiskConfigUpdate,
    StrategyConfigResponse,
    StrategyConfigUpdate,
    StopLossTakeProfitConfigResponse,
    UserIndicatorResponse,
    UserIndicatorUpdateRequest,
    BinanceConfigResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ConfigResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_config(
    request: Request,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> ConfigResponse:
    """
    Get complete bot configuration.

    Requires authentication.
    Rate limited to 60 requests per minute.

    Returns:
        Complete bot configuration including strategy, risk, and indicator settings
    """
    # Build indicator configs
    indicators = {
        "ema": IndicatorConfigResponse(
            name="ema",
            enabled=True,
            parameters={
                "fast_period": 50,
                "slow_period": 200,
            },
            description="Exponential Moving Average",
        ),
        "macd": IndicatorConfigResponse(
            name="macd",
            enabled=True,
            parameters={"fast": 12, "slow": 26, "signal": 9},
            description="MACD",
        ),
        "rsi": IndicatorConfigResponse(
            name="rsi",
            enabled=True,
            parameters={"period": 14, "overbought": 70, "oversold": 30},
            description="Relative Strength Index",
        ),
        "bollinger": IndicatorConfigResponse(
            name="bollinger",
            enabled=True,
            parameters={"period": 20, "std_dev": 2},
            description="Bollinger Bands",
        ),
        "atr": IndicatorConfigResponse(
            name="atr",
            enabled=True,
            parameters={"period": 14},
            description="Average True Range",
        ),
        "obv": IndicatorConfigResponse(
            name="obv",
            enabled=True,
            parameters={},
            description="On Balance Volume",
        ),
        "fear_greed": IndicatorConfigResponse(
            name="fear_greed",
            enabled=True,
            parameters={},
            description="Fear & Greed Index",
        ),
        "user_indicator": IndicatorConfigResponse(
            name="user_indicator",
            enabled=True,
            parameters={},
            description="Manual User Indicator",
        ),
    }

    return ConfigResponse(
        binance=BinanceConfigResponse(
            symbol=settings.binance_default_symbol,
            timeframe=settings.binance_default_timeframe,
            testnet=settings.binance_testnet,
            max_slippage_percent=0.2,  # From config
            order_timeout_seconds=settings.cooldown_after_trade_seconds,
        ),
        strategy=StrategyConfigResponse(
            entry_threshold=settings.strategy_entry_threshold,
            exit_threshold=settings.strategy_exit_threshold,
            confirmation_candles=settings.strategy_confirmation_candles,
        ),
        risk=RiskConfigResponse(
            max_trades_per_day=settings.risk_max_trades_per_day,
            max_exposure_percent=settings.risk_max_exposure_percent,
            position_size_mode=settings.risk_position_size_mode,
            fixed_size_usdt=float(settings.risk_fixed_size_usdt),
            atr_multiplier=settings.risk_atr_multiplier,
            capital_risk_percent=settings.risk_capital_risk_percent,
        ),
        stop_loss_take_profit=StopLossTakeProfitConfigResponse(
            sl_mode=settings.sl_mode,
            sl_atr_multiplier=settings.sl_atr_multiplier,
            sl_fixed_percent=settings.sl_fixed_percent,
            tp_mode=settings.tp_mode,
            tp_atr_multiplier=settings.tp_atr_multiplier,
            tp_fixed_percent=settings.tp_fixed_percent,
        ),
        indicators=indicators,
    )


@router.patch("/strategy", response_model=StrategyConfigResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def update_strategy_config(
    http_request: Request,
    request: StrategyConfigUpdate,
    user: User = Depends(get_current_user),
) -> StrategyConfigResponse:
    """
    Update strategy configuration.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        request: Updated strategy configuration

    Returns:
        Updated strategy configuration
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    # Update in-memory settings (for now)
    # TODO: Persist to database for durability
    if request.entry_threshold is not None:
        settings.strategy_entry_threshold = request.entry_threshold
    if request.exit_threshold is not None:
        settings.strategy_exit_threshold = request.exit_threshold
    if request.confirmation_candles is not None:
        settings.strategy_confirmation_candles = request.confirmation_candles

    logger.info("Updated strategy configuration")

    return StrategyConfigResponse(
        entry_threshold=settings.strategy_entry_threshold,
        exit_threshold=settings.strategy_exit_threshold,
        confirmation_candles=settings.strategy_confirmation_candles,
    )


@router.patch("/risk", response_model=RiskConfigResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def update_risk_config(
    http_request: Request,
    request: RiskConfigUpdate,
    user: User = Depends(get_current_user),
) -> RiskConfigResponse:
    """
    Update risk management configuration.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        request: Updated risk configuration

    Returns:
        Updated risk configuration
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    # Update in-memory settings (for now)
    # TODO: Persist to database for durability
    if request.max_trades_per_day is not None:
        settings.risk_max_trades_per_day = request.max_trades_per_day
    if request.max_exposure_percent is not None:
        settings.risk_max_exposure_percent = request.max_exposure_percent
    if request.position_size_mode is not None:
        settings.risk_position_size_mode = request.position_size_mode

    logger.info("Updated risk configuration")

    return RiskConfigResponse(
        max_trades_per_day=settings.risk_max_trades_per_day,
        max_exposure_percent=settings.risk_max_exposure_percent,
        position_size_mode=settings.risk_position_size_mode,
        fixed_size_usdt=float(settings.risk_fixed_size_usdt),
        atr_multiplier=settings.risk_atr_multiplier,
        capital_risk_percent=settings.risk_capital_risk_percent,
    )


@router.get("/user-indicator", response_model=UserIndicatorResponse)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_user_indicator(
    request: Request,
    symbol: Annotated[str, Query(description="Trading symbol")] = "BTCUSDT",
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserIndicatorResponse:
    """
    Get user indicator for a symbol.

    Requires authentication.
    Rate limited to 60 requests per minute.

    Args:
        request: FastAPI request object (for rate limiting)
        symbol: Trading symbol

    Returns:
        User indicator value (defaults to signal=0 if none exists)
    """
    query = """
        SELECT symbol, signal, note, expires_at
        FROM user_indicator
        WHERE symbol = $1
        ORDER BY created_at DESC
        LIMIT 1
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query, symbol)

    if not row:
        # Return indicator with ValueNotSet status
        logger.info(f"No user indicator found for {symbol}")
        return UserIndicatorResponse(
            symbol=symbol,
            signal=None,
            note=None,
            expires_at=None,
            status="ValueNotSet",
        )

    return UserIndicatorResponse(
        symbol=row["symbol"],
        signal=float(row["signal"]),
        note=row["note"],
        expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
        status="ValueSet",
    )


@router.patch("/user-indicator", response_model=UserIndicatorResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def update_user_indicator(
    http_request: Request,
    symbol: Annotated[str, Query(description="Trading symbol")] = "BTCUSDT",
    request: UserIndicatorUpdateRequest = None,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserIndicatorResponse:
    """
    Update user indicator for a symbol.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        http_request: FastAPI request object (for CSRF validation)
        symbol: Trading symbol
        request: Updated user indicator

    Returns:
        Updated user indicator
    """
    # Validate CSRF token
    await validate_csrf_token(http_request)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body required",
        )

    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours)

    async with db_pool.acquire() as conn:
        # Delete existing indicator for this symbol
        await conn.execute("DELETE FROM user_indicator WHERE symbol = $1", symbol)

        # Insert new indicator
        insert_query = """
            INSERT INTO user_indicator (symbol, signal, note, expires_at, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            RETURNING symbol, signal, note, expires_at
        """
        row = await conn.fetchrow(
            insert_query,
            symbol,
            float(request.signal),
            request.note,
            expires_at
        )

    logger.info(f"Updated user indicator for {symbol}: signal={request.signal}")

    return UserIndicatorResponse(
        symbol=row["symbol"],
        signal=float(row["signal"]),
        note=row["note"],
        expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
        status="ValueSet",
    )
