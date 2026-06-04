"""
Redis command publishing (API → bot).

Handles publishing commands to Redis pub/sub channel for bot.
"""

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from redis import asyncio as aioredis

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class StartTradingCommand:
    """Start trading command."""

    run_id: int


@dataclass
class StopTradingCommand:
    """Stop trading command."""

    reason: str


@dataclass
class ReconfigureCommand:
    """Reconfigure bot parameters command."""

    config_updates: dict[str, Any]  # Strategy params to update


@dataclass
class ActivateWeightsCommand:
    """Activate weights set command."""

    weights_set_id: int


async def publish_command(
    redis: aioredis.Redis, command_type: str, command: Any
) -> bool:
    """
    Publish command to bot via Redis pub/sub.

    Args:
        redis: Redis connection
        command_type: Command type string
        command: Command object (dataclass)

    Returns:
        True if published successfully, False otherwise
    """
    try:
        # Convert command to dict
        if hasattr(command, "__dataclass_fields__"):
            command_data = asdict(command)
        else:
            command_data = command

        # Build message
        message = {"type": command_type, **command_data}

        # Publish to Redis
        message_json = json.dumps(message)
        await redis.publish(settings.redis_channel_commands, message_json)

        logger.info(f"Published command: type={command_type}")
        return True

    except Exception as e:
        logger.error(f"Failed to publish command: {e}")
        return False
