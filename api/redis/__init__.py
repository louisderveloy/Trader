"""
Redis pub/sub module.

Handles Redis connections, event subscription (bot → API),
and command publishing (API → bot).
"""

from .client import RedisPool, get_redis_pool
from .commands import (
    ActivateWeightsCommand,
    ReconfigureCommand,
    StartTradingCommand,
    StopTradingCommand,
    publish_command,
)
from .events import (
    BotStateChangedEvent,
    ErrorEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    start_event_subscriber,
)

__all__ = [
    "RedisPool",
    "get_redis_pool",
    "ActivateWeightsCommand",
    "ReconfigureCommand",
    "StartTradingCommand",
    "StopTradingCommand",
    "publish_command",
    "BotStateChangedEvent",
    "ErrorEvent",
    "TradeClosedEvent",
    "TradeOpenedEvent",
    "start_event_subscriber",
]
