"""
Fear & Greed Index indicator.

This indicator fetches the Crypto Fear & Greed Index from alternative.me API.
The index aggregates various market metrics (volatility, volume, social media,
surveys, dominance, trends) into a single score from 0 to 100:

- 0-24: Extreme Fear (potential buy opportunity)
- 25-49: Fear
- 50: Neutral
- 51-75: Greed
- 76-100: Extreme Greed (potential sell opportunity)

The indicator can be interpreted both ways:
- Contrarian: Extreme fear = buy, extreme greed = sell
- Trend-following: Fear = bearish, greed = bullish

We use contrarian interpretation by default (as is common in crypto trading).

API: https://api.alternative.me/fng/
Caching: Index updates daily, so we cache for 4 hours
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx

from indicators.types import IndicatorResult, IndicatorSignal

logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: Optional[datetime] = None
_CACHE_DURATION = timedelta(hours=4)


async def _fetch_fear_greed_index() -> Dict[str, Any]:
    """
    Fetch Fear & Greed Index from API with caching.

    Returns:
        Dictionary with 'value' (int 0-100) and 'classification' (str)

    Raises:
        httpx.HTTPError: If API request fails
    """
    global _cache, _cache_timestamp

    # Check cache
    if _cache is not None and _cache_timestamp is not None:
        if datetime.utcnow() - _cache_timestamp < _CACHE_DURATION:
            logger.debug("Using cached Fear & Greed Index")
            return _cache

    # Fetch from API
    url = "https://api.alternative.me/fng/"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

    # Parse response
    if 'data' not in data or len(data['data']) == 0:
        raise ValueError("Invalid response from Fear & Greed Index API")

    latest = data['data'][0]
    result = {
        'value': int(latest['value']),
        'classification': latest['value_classification'],
        'timestamp': int(latest['timestamp']),
    }

    # Update cache
    _cache = result
    _cache_timestamp = datetime.utcnow()

    logger.info(
        "Fetched Fear & Greed Index from API",
        extra={
            'value': result['value'],
            'classification': result['classification'],
        }
    )

    return result


def compute(candles, params: Dict[str, Any]) -> IndicatorResult:
    """
    Fetch Fear & Greed Index.

    Note: This is an async function but we need to handle it synchronously
    in the indicator framework. The actual implementation will need to be called
    from an async context.

    Args:
        candles: Not used (Fear & Greed is independent of candle data)
        params: Dictionary (no parameters needed)

    Returns:
        IndicatorResult containing:
            - value: Fear & Greed Index value (0-100)
            - classification: Text classification (e.g., "Extreme Fear")

    Raises:
        RuntimeError: If API call fails
    """
    # Note: This is a placeholder. The actual implementation needs to be async.
    # In practice, this will be called from an async context that can await.
    import asyncio

    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Fetch data
        if loop.is_running():
            # If loop is already running, we need to create a task
            # This shouldn't happen in normal usage
            raise RuntimeError(
                "Fear & Greed Index fetch must be called from an async context"
            )
        else:
            data = loop.run_until_complete(_fetch_fear_greed_index())

    except Exception as e:
        logger.error(
            "Failed to fetch Fear & Greed Index",
            extra={'error': str(e)},
            exc_info=True
        )
        # Return neutral value on error
        return IndicatorResult(
            values={
                'value': 50,
                'classification': 'unknown',
                'error': str(e),
            },
            metadata={
                'source': 'alternative.me',
                'fetch_failed': True,
            }
        )

    result = IndicatorResult(
        values={
            'value': data['value'],
            'classification': data['classification'],
        },
        metadata={
            'source': 'alternative.me',
            'timestamp': data['timestamp'],
            'fetch_failed': False,
        }
    )

    logger.debug(
        "Fear & Greed Index retrieved",
        extra={
            'value': data['value'],
            'classification': data['classification'],
        }
    )

    return result


def to_signal(values: IndicatorResult) -> IndicatorSignal:
    """
    Convert Fear & Greed Index to normalized signal.

    Signal logic (contrarian):
    - 0-24 (Extreme Fear): Strong bullish signal (+0.7 to +1.0)
    - 25-49 (Fear): Moderate bullish signal (+0.2 to +0.7)
    - 50 (Neutral): No signal (0)
    - 51-75 (Greed): Moderate bearish signal (-0.2 to -0.7)
    - 76-100 (Extreme Greed): Strong bearish signal (-0.7 to -1.0)

    Args:
        values: Result from compute() function

    Returns:
        IndicatorSignal with value in range [-1, 1]:
        - +1: Extreme fear (contrarian buy opportunity)
        - 0: Neutral
        - -1: Extreme greed (contrarian sell opportunity)
    """
    value = values.values.get('value')
    classification = values.values.get('classification', 'unknown')
    fetch_failed = values.metadata.get('fetch_failed', False) if values.metadata else False

    # Handle fetch failure
    if fetch_failed or value is None:
        return IndicatorSignal(
            value=0.0,
            metadata={
                'reason': 'api_fetch_failed',
                'classification': 'unknown',
            }
        )

    # Contrarian normalization: fear = bullish, greed = bearish
    # Map [0, 100] to [+1, -1]
    # value 0 → +1, value 50 → 0, value 100 → -1
    signal_value = 1.0 - (value / 50.0)

    # Clamp to valid range
    signal_value = max(-1.0, min(1.0, signal_value))

    # Build metadata
    metadata: Dict[str, Any] = {
        'value': value,
        'classification': classification,
    }

    # Determine reason based on classification
    if value <= 24:
        metadata['reason'] = 'extreme_fear_contrarian_bullish'
        metadata['interpretation'] = 'Market in extreme fear, potential buy opportunity'
    elif value <= 49:
        metadata['reason'] = 'fear_contrarian_bullish'
        metadata['interpretation'] = 'Market in fear, moderately bullish'
    elif value == 50:
        metadata['reason'] = 'neutral'
        metadata['interpretation'] = 'Market neutral'
    elif value <= 75:
        metadata['reason'] = 'greed_contrarian_bearish'
        metadata['interpretation'] = 'Market in greed, moderately bearish'
    else:  # 76-100
        metadata['reason'] = 'extreme_greed_contrarian_bearish'
        metadata['interpretation'] = 'Market in extreme greed, potential sell opportunity'

    logger.debug(
        "Fear & Greed signal generated",
        extra={
            'signal_value': signal_value,
            'reason': metadata['reason'],
            'value': value,
            'classification': classification,
        }
    )

    return IndicatorSignal(value=signal_value, metadata=metadata)
