"""
Database configuration persistence.

This module handles loading and saving configuration to the database,
allowing runtime configuration changes to persist across restarts.
"""

import asyncpg
import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)


async def load_config_from_db(db_pool: asyncpg.Pool) -> dict[str, Any]:
    """
    Load all configuration from database.

    Loads the most recent configuration entry based on updated_at timestamp.
    This allows keeping a full audit trail of configuration changes.

    Returns:
        Dict containing the complete configuration.
        Example: {"strategy": {"entry_threshold": 0.6}, "risk": {"max_trades_per_day": 5}}
        Returns empty dict if no config exists.
    """
    import json

    query = "SELECT config FROM config ORDER BY updated_at DESC LIMIT 1"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query)

    if row and row["config"]:
        logger.info("Loaded configuration from database")
        # Parse JSON if it's a string, otherwise return as-is
        config = row["config"]
        if isinstance(config, str):
            return json.loads(config)
        return config

    logger.info("No configuration found in database")
    return {}


async def save_config_to_db(
    db_pool: asyncpg.Pool,
    config_dict: dict[str, Any],
) -> None:
    """
    Save complete configuration to database.

    Creates a new config entry with the complete configuration only if it differs
    from the current configuration. This preserves the full history of configuration
    changes for audit purposes while avoiding duplicate entries.

    Args:
        db_pool: Database connection pool
        config_dict: Complete configuration dictionary
    """
    import json

    # Load current config to check for changes
    current_config = await load_config_from_db(db_pool)

    # Compare configs - skip insert if identical
    if current_config == config_dict:
        logger.info("Configuration unchanged, skipping database insert")
        return

    # Insert new config entry (preserving history)
    # Note: asyncpg requires JSONB to be passed as a JSON string
    insert_query = """
        INSERT INTO config (config, created_at, updated_at)
        VALUES ($1::jsonb, NOW(), NOW())
    """

    async with db_pool.acquire() as conn:
        await conn.execute(insert_query, json.dumps(config_dict))

    logger.info("Saved new configuration entry to database")


async def update_config_in_db(
    db_pool: asyncpg.Pool,
    category: str,
    updates: dict[str, Any],
) -> None:
    """
    Update a specific category in the configuration.

    Loads existing config, merges updates for the category, and saves back.

    Args:
        db_pool: Database connection pool
        category: Config category (e.g., "strategy", "risk")
        updates: Dict of key-value pairs to update
    """
    # Load existing config
    config_dict = await load_config_from_db(db_pool)

    # Ensure category exists
    if category not in config_dict:
        config_dict[category] = {}

    # Merge updates
    config_dict[category].update(updates)

    # Save back to database
    await save_config_to_db(db_pool, config_dict)

    logger.info(f"Updated config category '{category}' with {len(updates)} values")


async def apply_db_config_to_settings(db_pool: asyncpg.Pool, settings_obj: "Settings") -> None:
    """
    Load configuration from database and apply to settings object.

    This should be called on API startup to restore persisted configuration.
    Only updates settings that exist in the database, preserving defaults otherwise.

    Args:
        db_pool: Database connection pool
        settings_obj: Settings object to update
    """
    config_dict = await load_config_from_db(db_pool)

    if not config_dict:
        logger.info("No persisted configuration found in database, using defaults")
        return

    # Apply strategy config
    strategy_config = config_dict.get("strategy", {})
    if "entry_threshold" in strategy_config:
        settings_obj.strategy_entry_threshold = float(strategy_config["entry_threshold"])
    if "exit_threshold" in strategy_config:
        settings_obj.strategy_exit_threshold = float(strategy_config["exit_threshold"])
    if "confirmation_candles" in strategy_config:
        settings_obj.strategy_confirmation_candles = int(strategy_config["confirmation_candles"])

    # Apply risk config
    risk_config = config_dict.get("risk", {})
    if "max_trades_per_day" in risk_config:
        settings_obj.risk_max_trades_per_day = int(risk_config["max_trades_per_day"])
    if "max_exposure_percent" in risk_config:
        settings_obj.risk_max_exposure_percent = float(risk_config["max_exposure_percent"])
    if "position_size_mode" in risk_config:
        settings_obj.risk_position_size_mode = str(risk_config["position_size_mode"])
    if "fixed_size_percent" in risk_config:
        settings_obj.risk_fixed_size_percent = float(risk_config["fixed_size_percent"])
    if "atr_multiplier" in risk_config:
        settings_obj.risk_atr_multiplier = float(risk_config["atr_multiplier"])
    if "capital_risk_percent" in risk_config:
        settings_obj.risk_capital_risk_percent = float(risk_config["capital_risk_percent"])

    # Apply stop-loss config
    sl_config = config_dict.get("stop_loss", {})
    if "mode" in sl_config:
        settings_obj.sl_mode = str(sl_config["mode"])
    if "atr_multiplier" in sl_config:
        settings_obj.sl_atr_multiplier = float(sl_config["atr_multiplier"])
    if "fixed_percent" in sl_config:
        settings_obj.sl_fixed_percent = float(sl_config["fixed_percent"])

    # Apply take-profit config
    tp_config = config_dict.get("take_profit", {})
    if "mode" in tp_config:
        settings_obj.tp_mode = str(tp_config["mode"])
    if "atr_multiplier" in tp_config:
        settings_obj.tp_atr_multiplier = float(tp_config["atr_multiplier"])
    if "fixed_percent" in tp_config:
        settings_obj.tp_fixed_percent = float(tp_config["fixed_percent"])

    logger.info("Applied persisted configuration from database")
