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
from ..db_config import update_config_in_db
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
    request: Request,
    update_data: StrategyConfigUpdate,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyConfigResponse:
    """
    Update strategy configuration.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        request: FastAPI request object (for rate limiting and CSRF validation)
        update_data: Updated strategy configuration
        db_pool: Database connection pool

    Returns:
        Updated strategy configuration
    """
    # Validate CSRF token
    await validate_csrf_token(request)

    # Prepare updates dict
    updates = {}
    if update_data.entry_threshold is not None:
        settings.strategy_entry_threshold = update_data.entry_threshold
        updates["entry_threshold"] = update_data.entry_threshold

    if update_data.exit_threshold is not None:
        settings.strategy_exit_threshold = update_data.exit_threshold
        updates["exit_threshold"] = update_data.exit_threshold

    if update_data.confirmation_candles is not None:
        settings.strategy_confirmation_candles = update_data.confirmation_candles
        updates["confirmation_candles"] = update_data.confirmation_candles

    # Validate that entry_threshold > exit_threshold
    if settings.strategy_entry_threshold <= settings.strategy_exit_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le seuil d'entrée ({settings.strategy_entry_threshold}) doit être supérieur au seuil de sortie ({settings.strategy_exit_threshold})",
        )

    # Persist to database
    if updates:
        await update_config_in_db(db_pool, "strategy", updates)

    logger.info("Updated strategy configuration and persisted to database")

    return StrategyConfigResponse(
        entry_threshold=settings.strategy_entry_threshold,
        exit_threshold=settings.strategy_exit_threshold,
        confirmation_candles=settings.strategy_confirmation_candles,
    )


@router.patch("/risk", response_model=RiskConfigResponse)
@limiter.limit(lambda: settings.rate_limit_api_write)
async def update_risk_config(
    request: Request,
    update_data: RiskConfigUpdate,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> RiskConfigResponse:
    """
    Update risk management configuration.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        request: FastAPI request object (for rate limiting and CSRF validation)
        update_data: Updated risk configuration
        db_pool: Database connection pool

    Returns:
        Updated risk configuration
    """
    # Validate CSRF token
    await validate_csrf_token(request)

    # Prepare updates dict
    updates = {}
    if update_data.max_trades_per_day is not None:
        settings.risk_max_trades_per_day = update_data.max_trades_per_day
        updates["max_trades_per_day"] = update_data.max_trades_per_day

    if update_data.max_exposure_percent is not None:
        settings.risk_max_exposure_percent = update_data.max_exposure_percent
        updates["max_exposure_percent"] = update_data.max_exposure_percent

    if update_data.position_size_mode is not None:
        settings.risk_position_size_mode = update_data.position_size_mode.value
        updates["position_size_mode"] = update_data.position_size_mode.value

    if update_data.fixed_size_usdt is not None:
        settings.risk_fixed_size_usdt = update_data.fixed_size_usdt
        updates["fixed_size_usdt"] = update_data.fixed_size_usdt

    if update_data.atr_multiplier is not None:
        settings.risk_atr_multiplier = update_data.atr_multiplier
        updates["atr_multiplier"] = update_data.atr_multiplier

    if update_data.capital_risk_percent is not None:
        settings.risk_capital_risk_percent = update_data.capital_risk_percent
        updates["capital_risk_percent"] = update_data.capital_risk_percent

    # Persist to database
    if updates:
        await update_config_in_db(db_pool, "risk", updates)

    logger.info("Updated risk configuration and persisted to database")

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
    request: Request,
    symbol: Annotated[str, Query(description="Trading symbol")] = "BTCUSDT",
    update_data: UserIndicatorUpdateRequest = None,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
) -> UserIndicatorResponse:
    """
    Update user indicator for a symbol.

    Requires authentication and CSRF token.
    Rate limited to 30 requests per minute.

    Args:
        request: FastAPI request object (for rate limiting and CSRF validation)
        symbol: Trading symbol
        update_data: Updated user indicator

    Returns:
        Updated user indicator
    """
    # Validate CSRF token
    await validate_csrf_token(request)
    if update_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body required",
        )

    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(hours=update_data.expires_in_hours)

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
            float(update_data.signal),
            update_data.note,
            expires_at
        )

    logger.info(f"Updated user indicator for {symbol}: signal={update_data.signal}")

    return UserIndicatorResponse(
        symbol=row["symbol"],
        signal=float(row["signal"]),
        note=row["note"],
        expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
        status="ValueSet",
    )
