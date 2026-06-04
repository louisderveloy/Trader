"""
User Indicator - Manual user input from dashboard.

This indicator retrieves manual market analysis input from the user via the dashboard.
Users can set a sentiment value (-1 to +1) for each symbol with:
- Signal value: -1 (bearish) to +1 (bullish)
- Note: Text explanation for the sentiment
- Expiration: Optional expiration datetime

The indicator reads from the `user_indicator` table in the database and:
- Filters by symbol
- Checks expiration
- Logs the user note for transparency
- Returns the user's signal value directly

This allows users to inject their own market analysis, news reactions, or
manual overrides into the trading strategy.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from indicators.types import IndicatorResult, IndicatorSignal

logger = logging.getLogger(__name__)


async def compute_async(
    db_session: AsyncSession,
    symbol: str,
    params: Optional[Dict[str, Any]] = None
) -> IndicatorResult:
    """
    Fetch user indicator value from database (async version).

    Args:
        db_session: Async SQLAlchemy session
        symbol: Trading symbol (e.g., "BTCUSDT")
        params: Optional parameters (not used)

    Returns:
        IndicatorResult containing:
            - value: User's signal value (-1 to +1)
            - note: User's explanation text
            - expires_at: Expiration datetime if set
            - is_active: Whether the indicator is currently active

    Note:
        This is an async function that must be called from an async context.
    """
    from db.models import UserIndicator  # Import here to avoid circular dependency

    try:
        # Query for active user indicator for this symbol
        query = select(UserIndicator).where(
            UserIndicator.symbol == symbol,
            UserIndicator.is_active == True  # noqa: E712
        )

        result = await db_session.execute(query)
        user_indicator = result.scalar_one_or_none()

        if user_indicator is None:
            # No user indicator set for this symbol
            return IndicatorResult(
                values={
                    'value': None,
                    'note': None,
                    'expires_at': None,
                    'is_active': False,
                },
                metadata={
                    'symbol': symbol,
                    'reason': 'no_indicator_set',
                }
            )

        # Check expiration
        now = datetime.utcnow()
        is_expired = False
        if user_indicator.expires_at is not None:
            is_expired = now > user_indicator.expires_at

        if is_expired:
            # Indicator has expired
            logger.info(
                "User indicator expired",
                extra={
                    'symbol': symbol,
                    'expired_at': user_indicator.expires_at.isoformat(),
                    'value': user_indicator.value,
                }
            )
            return IndicatorResult(
                values={
                    'value': None,
                    'note': user_indicator.note,
                    'expires_at': user_indicator.expires_at.isoformat(),
                    'is_active': False,
                },
                metadata={
                    'symbol': symbol,
                    'reason': 'expired',
                    'expired_at': user_indicator.expires_at.isoformat(),
                }
            )

        # Valid user indicator found
        result = IndicatorResult(
            values={
                'value': float(user_indicator.value),
                'note': user_indicator.note,
                'expires_at': user_indicator.expires_at.isoformat() if user_indicator.expires_at else None,
                'is_active': True,
            },
            metadata={
                'symbol': symbol,
                'reason': 'active',
                'created_at': user_indicator.created_at.isoformat(),
                'updated_at': user_indicator.updated_at.isoformat(),
            }
        )

        logger.info(
            "User indicator retrieved",
            extra={
                'symbol': symbol,
                'value': user_indicator.value,
                'note': user_indicator.note,
                'expires_at': user_indicator.expires_at.isoformat() if user_indicator.expires_at else 'never',
            }
        )

        return result

    except Exception as e:
        logger.error(
            "Failed to fetch user indicator from database",
            extra={
                'symbol': symbol,
                'error': str(e),
            },
            exc_info=True
        )
        # Return inactive indicator on error
        return IndicatorResult(
            values={
                'value': None,
                'note': None,
                'expires_at': None,
                'is_active': False,
            },
            metadata={
                'symbol': symbol,
                'reason': 'database_error',
                'error': str(e),
            }
        )


def compute(candles, params: Dict[str, Any]) -> IndicatorResult:
    """
    Synchronous wrapper for user indicator (not recommended).

    Note: This is a placeholder for the standard indicator interface.
    The actual implementation should use compute_async() from an async context.

    Args:
        candles: Not used (user indicator is independent of candles)
        params: Dictionary with keys:
            - db_session: AsyncSession (required)
            - symbol: Trading symbol (required)

    Returns:
        IndicatorResult

    Raises:
        ValueError: If db_session or symbol not provided
    """
    db_session = params.get('db_session')
    symbol = params.get('symbol')

    if db_session is None or symbol is None:
        raise ValueError(
            "User indicator requires 'db_session' and 'symbol' parameters"
        )

    # This would need to be called from an async context in practice
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        raise RuntimeError(
            "User indicator must be called from an async context. "
            "Use compute_async() instead."
        )

    return loop.run_until_complete(compute_async(db_session, symbol, params))


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert user indicator value to signal.

    Signal logic:
    - Returns user's value directly (already in [-1, +1] range)
    - If no active indicator: returns neutral (0)
    - Logs user note for transparency and audit trail

    Args:
        values: Result from compute() or compute_async()

    Returns:
        IndicatorSignal with user's value
    """
    value = values.values.get('value')
    note = values.values.get('note')
    is_active = values.values.get('is_active', False)
    expires_at = values.values.get('expires_at')
    reason = values.metadata.get('reason', 'unknown') if values.metadata else 'unknown'

    # Handle inactive or missing indicator
    if not is_active or value is None:
        return IndicatorSignal(
            value=0.0,
            metadata={
                'reason': reason,
                'is_active': False,
                'note': note,
            }
        )

    # Validate that user value is in valid range
    if not -1.0 <= value <= 1.0:
        logger.warning(
            "User indicator value out of range, clamping",
            extra={
                'original_value': value,
                'clamped_value': max(-1.0, min(1.0, value)),
            }
        )
        value = max(-1.0, min(1.0, value))

    # Build metadata with user context
    metadata: Dict[str, Any] = {
        'reason': 'user_input',
        'is_active': True,
        'user_note': note,
    }

    if expires_at:
        metadata['expires_at'] = expires_at

    # Determine interpretation
    if value > 0.5:
        metadata['interpretation'] = 'strong_bullish_user_signal'
    elif value > 0:
        metadata['interpretation'] = 'moderate_bullish_user_signal'
    elif value < -0.5:
        metadata['interpretation'] = 'strong_bearish_user_signal'
    elif value < 0:
        metadata['interpretation'] = 'moderate_bearish_user_signal'
    else:
        metadata['interpretation'] = 'neutral_user_signal'

    logger.info(
        "User indicator signal generated",
        extra={
            'signal_value': value,
            'interpretation': metadata['interpretation'],
            'user_note': note,
            'expires_at': expires_at,
        }
    )

    return IndicatorSignal(value=value, metadata=metadata)
