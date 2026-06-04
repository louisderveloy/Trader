"""
Redis event subscription (bot → API).

Handles subscribing to Redis pub/sub channel for bot events.
"""

import asyncio
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from redis import asyncio as aioredis

from ..config import settings

logger = logging.getLogger(__name__)

# In-memory event buffer (LRU with max 1000 events)
# Used for dashboard polling until WebSocket is implemented
_event_buffer: deque = deque(maxlen=1000)


@dataclass
class TradeOpenedEvent:
    """Trade opened event from bot."""

    run_id: int
    trade_id: str  # UUID
    symbol: str
    direction: str  # "long" | "short"
    entry_price: Decimal
    size: Decimal
    timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeOpenedEvent":
        """Create from dict."""
        return cls(
            run_id=data["run_id"],
            trade_id=data["trade_id"],
            symbol=data["symbol"],
            direction=data["direction"],
            entry_price=Decimal(str(data["entry_price"])),
            size=Decimal(str(data["size"])),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class TradeClosedEvent:
    """Trade closed event from bot."""

    run_id: int
    trade_id: str
    exit_price: Decimal
    pnl: Decimal
    pnl_percent: float
    reason: str  # "take_profit" | "stop_loss" | "signal"
    timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeClosedEvent":
        """Create from dict."""
        return cls(
            run_id=data["run_id"],
            trade_id=data["trade_id"],
            exit_price=Decimal(str(data["exit_price"])),
            pnl=Decimal(str(data["pnl"])),
            pnl_percent=data["pnl_percent"],
            reason=data["reason"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class ErrorEvent:
    """Error event from bot."""

    run_id: Optional[int]
    severity: str  # "warning" | "error" | "critical"
    category: str
    message: str
    traceback: Optional[str]
    timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorEvent":
        """Create from dict."""
        return cls(
            run_id=data.get("run_id"),
            severity=data["severity"],
            category=data["category"],
            message=data["message"],
            traceback=data.get("traceback"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class BotStateChangedEvent:
    """Bot state changed event."""

    status: str  # "running" | "paused" | "stopped"
    timestamp: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BotStateChangedEvent":
        """Create from dict."""
        return cls(
            status=data["status"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


# Event type mapping
EVENT_TYPE_MAP = {
    "trade_opened": TradeOpenedEvent,
    "trade_closed": TradeClosedEvent,
    "error": ErrorEvent,
    "bot_state_changed": BotStateChangedEvent,
}


def parse_event(message: str) -> Optional[tuple[str, Any]]:
    """
    Parse Redis pub/sub message into event object.

    Args:
        message: JSON message from Redis

    Returns:
        Tuple of (event_type, event_object) or None if parsing fails
    """
    try:
        data = json.loads(message)
        event_type = data.get("type")

        if event_type not in EVENT_TYPE_MAP:
            logger.warning(f"Unknown event type: {event_type}")
            return None

        event_class = EVENT_TYPE_MAP[event_type]
        event = event_class.from_dict(data)

        return event_type, event

    except Exception as e:
        logger.error(f"Failed to parse event: {e}")
        return None


async def start_event_subscriber(redis: aioredis.Redis) -> None:
    """
    Start Redis pub/sub subscriber for bot events.

    Runs in background task, listening to bot:events channel.

    Args:
        redis: Redis connection pool

    Note:
        This function runs indefinitely until cancelled.
    """
    logger.info(f"Starting event subscriber: channel={settings.redis_channel_events}")

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(settings.redis_channel_events)

        logger.info("Event subscriber started successfully")

        async for message in pubsub.listen():
            # Skip non-message types
            if message["type"] != "message":
                continue

            # Parse event
            data = message["data"]
            parsed = parse_event(data)

            if parsed:
                event_type, event = parsed
                logger.info(f"Received event: type={event_type}")

                # Store in buffer for dashboard polling
                _event_buffer.append(
                    {
                        "type": event_type,
                        "data": asdict(event) if hasattr(event, "__dataclass_fields__") else event,
                        "received_at": datetime.utcnow().isoformat(),
                    }
                )

                # TODO: Send to WebSocket clients (Task #12)

    except asyncio.CancelledError:
        logger.info("Event subscriber cancelled")
        await pubsub.unsubscribe(settings.redis_channel_events)
        await pubsub.close()
        raise

    except Exception as e:
        logger.error(f"Event subscriber error: {e}")
        raise


def get_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    """
    Get recent events from buffer.

    Args:
        limit: Maximum number of events to return

    Returns:
        List of recent events
    """
    return list(_event_buffer)[-limit:]
