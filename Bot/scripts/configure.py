#!/usr/bin/env python3
"""
Interactive Configuration Creator

This script guides you through creating a bot configuration interactively,
asking for each parameter with descriptions and tooltips.

The configuration is saved to the database and can be loaded by the bot.

Usage:
    python -m scripts.configure
    # Or via main.py:
    python -m main config create
"""

import asyncio
import asyncpg
import json
import logging
import os
import sys
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ConfigParam:
    """Configuration parameter with metadata."""

    def __init__(
        self,
        name: str,
        description: str,
        param_type: type,
        default: Any,
        tooltip: str,
        choices: Optional[list] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ):
        self.name = name
        self.description = description
        self.param_type = param_type
        self.default = default
        self.tooltip = tooltip
        self.choices = choices
        self.min_value = min_value
        self.max_value = max_value

    def prompt(self) -> Any:
        """Prompt user for value."""
        print("\n" + "=" * 80)
        print(f"📋 {self.name}")
        print("-" * 80)
        print(f"Description: {self.description}")
        print(f"💡 {self.tooltip}")

        if self.choices:
            print(f"Choices: {', '.join(self.choices)}")
        if self.min_value is not None or self.max_value is not None:
            range_str = f"Range: "
            if self.min_value is not None:
                range_str += f"{self.min_value} ≤ "
            range_str += "value"
            if self.max_value is not None:
                range_str += f" ≤ {self.max_value}"
            print(range_str)

        print(f"Default: {self.default}")
        print("-" * 80)

        while True:
            response = input(f"Enter value (or press Enter for default): ").strip()

            # Use default if empty
            if not response:
                return self.default

            # Validate and convert
            try:
                if self.param_type == bool:
                    value = response.lower() in ['true', '1', 'yes', 'y']
                elif self.param_type == int:
                    value = int(response)
                elif self.param_type == float:
                    value = float(response)
                else:
                    value = response

                # Validate choices
                if self.choices and value not in self.choices:
                    print(f"❌ Invalid choice. Must be one of: {', '.join(self.choices)}")
                    continue

                # Validate range
                if self.min_value is not None and value < self.min_value:
                    print(f"❌ Value must be >= {self.min_value}")
                    continue
                if self.max_value is not None and value > self.max_value:
                    print(f"❌ Value must be <= {self.max_value}")
                    continue

                return value

            except ValueError:
                print(f"❌ Invalid input. Expected {self.param_type.__name__}")
                continue


# Define all configuration parameters with descriptions
STRATEGY_PARAMS = [
    ConfigParam(
        name="Entry Threshold",
        description="Weighted score threshold to enter a position",
        param_type=float,
        default=0.6,
        tooltip="Score must exceed this value to trigger a buy signal. Higher = more selective. Range: -1.0 to 1.0",
        min_value=-1.0,
        max_value=1.0,
    ),
    ConfigParam(
        name="Exit Threshold",
        description="Weighted score threshold to exit a position",
        param_type=float,
        default=-0.3,
        tooltip="Score must fall below this value to trigger a sell signal. Must be < entry threshold. Range: -1.0 to 1.0",
        min_value=-1.0,
        max_value=1.0,
    ),
    ConfigParam(
        name="Confirmation Candles",
        description="Number of consecutive candles required to confirm a signal",
        param_type=int,
        default=2,
        tooltip="Anti-repainting protection. Signal must persist for this many candles before executing. Higher = safer but slower. Min: 1",
        min_value=1,
        max_value=10,
    ),
]

RISK_PARAMS = [
    ConfigParam(
        name="Max Trades Per Day",
        description="Maximum number of trades allowed per day",
        param_type=int,
        default=5,
        tooltip="Limits overtrading. Bot will stop opening new positions after reaching this limit. Resets at midnight UTC. Min: 1",
        min_value=1,
        max_value=50,
    ),
    ConfigParam(
        name="Max Exposure Percent",
        description="Maximum percentage of capital exposed simultaneously",
        param_type=float,
        default=30.0,
        tooltip="Maximum % of total capital that can be in open positions at once. Example: 30 = can use up to 30% of capital. Range: 0-100",
        min_value=0.1,
        max_value=100.0,
    ),
    ConfigParam(
        name="Position Size Mode",
        description="Method for calculating position size",
        param_type=str,
        default="confidence",
        tooltip="'fixed' = constant USDT amount, 'confidence' = size based on signal strength, 'risk_atr' = ATR-based risk management",
        choices=["fixed", "confidence", "risk_atr"],
    ),
    ConfigParam(
        name="Fixed Size USDT",
        description="Fixed position size in USDT (used if mode=fixed)",
        param_type=float,
        default=100.0,
        tooltip="Constant position size when using 'fixed' mode. Example: 100 = always trade 100 USDT worth. Min: 10",
        min_value=10.0,
        max_value=1000000.0,
    ),
    ConfigParam(
        name="ATR Multiplier (Risk)",
        description="ATR multiplier for position sizing (used if mode=risk_atr)",
        param_type=float,
        default=2.0,
        tooltip="Multiplier for ATR-based position sizing. Higher = larger positions in volatile markets. Typically 1.5-3.0. Min: 0.1",
        min_value=0.1,
        max_value=10.0,
    ),
    ConfigParam(
        name="Capital Risk Percent",
        description="Percentage of capital to risk per trade (used if mode=risk_atr)",
        param_type=float,
        default=1.0,
        tooltip="How much % of total capital to risk on each trade. Example: 1.0 = risk 1% of capital per trade. Conservative: 0.5-1%, Aggressive: 2-3%. Range: 0.1-10",
        min_value=0.1,
        max_value=10.0,
    ),
]

STOP_LOSS_PARAMS = [
    ConfigParam(
        name="Stop Loss Mode",
        description="Method for calculating stop-loss level",
        param_type=str,
        default="atr",
        tooltip="'atr' = based on ATR (volatility-adjusted), 'fixed' = fixed percentage below entry",
        choices=["atr", "fixed"],
    ),
    ConfigParam(
        name="Stop Loss ATR Multiplier",
        description="ATR multiplier for stop-loss (used if mode=atr)",
        param_type=float,
        default=2.0,
        tooltip="Stop-loss = entry_price - (ATR × multiplier). Higher = wider stops. Typically 1.5-3.0. Min: 0.1",
        min_value=0.1,
        max_value=10.0,
    ),
    ConfigParam(
        name="Stop Loss Fixed Percent",
        description="Fixed percentage for stop-loss (used if mode=fixed)",
        param_type=float,
        default=2.0,
        tooltip="Stop-loss % below entry. Example: 2.0 = stop at -2% from entry. Range: 0.1-20",
        min_value=0.1,
        max_value=20.0,
    ),
]

TAKE_PROFIT_PARAMS = [
    ConfigParam(
        name="Take Profit Mode",
        description="Method for calculating take-profit level",
        param_type=str,
        default="atr",
        tooltip="'atr' = based on ATR (volatility-adjusted), 'fixed' = fixed percentage above entry",
        choices=["atr", "fixed"],
    ),
    ConfigParam(
        name="Take Profit ATR Multiplier",
        description="ATR multiplier for take-profit (used if mode=atr)",
        param_type=float,
        default=3.0,
        tooltip="Take-profit = entry_price + (ATR × multiplier). Higher = wider targets. Typically 2.0-4.0. Min: 0.1",
        min_value=0.1,
        max_value=20.0,
    ),
    ConfigParam(
        name="Take Profit Fixed Percent",
        description="Fixed percentage for take-profit (used if mode=fixed)",
        param_type=float,
        default=4.0,
        tooltip="Take-profit % above entry. Example: 4.0 = exit at +4% from entry. Range: 0.1-50",
        min_value=0.1,
        max_value=50.0,
    ),
]

COOLDOWN_PARAMS = [
    ConfigParam(
        name="Cooldown After Trade (seconds)",
        description="Cooldown period after closing a trade before opening another",
        param_type=int,
        default=3600,
        tooltip="Prevents rapid re-entry. Example: 3600 = wait 1 hour after closing a trade. 0 = no cooldown. Range: 0-86400 (24h)",
        min_value=0,
        max_value=86400,
    ),
]


async def save_config_to_db(db_pool: asyncpg.Pool, config_dict: Dict[str, Any]):
    """
    Save configuration to database.

    Creates a new config entry (preserving history).
    """
    import json

    # Load current config to check for changes
    query = "SELECT config FROM config ORDER BY updated_at DESC LIMIT 1"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(query)

    current_config = {}
    if row and row["config"]:
        current_config = row["config"]
        if isinstance(current_config, str):
            current_config = json.loads(current_config)

    # Compare configs - skip insert if identical
    if current_config == config_dict:
        logger.info("⚠️  Configuration unchanged, skipping database insert")
        return

    # Insert new config entry (preserving history)
    insert_query = """
        INSERT INTO config (config, created_at, updated_at)
        VALUES ($1::jsonb, NOW(), NOW())
    """

    async with db_pool.acquire() as conn:
        await conn.execute(insert_query, json.dumps(config_dict))

    logger.info("✅ Configuration saved to database")


async def create_config_interactive():
    """
    Interactive configuration creator.

    Prompts user for all configuration parameters and saves to database.
    """
    print("\n" + "=" * 80)
    print("🤖 TRADING BOT - CONFIGURATION CREATOR")
    print("=" * 80)
    print("This wizard will guide you through creating a bot configuration.")
    print("Press Enter to use the default value for any parameter.")
    print("=" * 80)

    # Initialize config dict
    config = {
        "strategy": {},
        "risk": {},
        "stop_loss": {},
        "take_profit": {},
        "cooldown": {}
    }

    # Strategy configuration
    print("\n" + "🎯 STRATEGY CONFIGURATION".center(80))
    config["strategy"]["entry_threshold"] = STRATEGY_PARAMS[0].prompt()
    config["strategy"]["exit_threshold"] = STRATEGY_PARAMS[1].prompt()

    # Validate: exit < entry
    while config["strategy"]["exit_threshold"] >= config["strategy"]["entry_threshold"]:
        print("\n❌ Exit threshold must be < entry threshold!")
        config["strategy"]["exit_threshold"] = STRATEGY_PARAMS[1].prompt()

    config["strategy"]["confirmation_candles"] = STRATEGY_PARAMS[2].prompt()

    # Risk configuration
    print("\n" + "⚠️  RISK MANAGEMENT CONFIGURATION".center(80))
    for param in RISK_PARAMS:
        key = param.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        config["risk"][key] = param.prompt()

    # Stop-loss configuration
    print("\n" + "🛑 STOP-LOSS CONFIGURATION".center(80))
    for param in STOP_LOSS_PARAMS:
        key = param.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        config["stop_loss"][key] = param.prompt()

    # Take-profit configuration
    print("\n" + "🎯 TAKE-PROFIT CONFIGURATION".center(80))
    for param in TAKE_PROFIT_PARAMS:
        key = param.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        config["take_profit"][key] = param.prompt()

    # Cooldown configuration
    print("\n" + "⏱️  COOLDOWN CONFIGURATION".center(80))
    for param in COOLDOWN_PARAMS:
        key = param.name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("__", "_")
        config["cooldown"][key] = param.prompt()

    # Display summary
    print("\n" + "=" * 80)
    print("📝 CONFIGURATION SUMMARY")
    print("=" * 80)
    print(json.dumps(config, indent=2))
    print("=" * 80)

    # Confirm
    confirm = input("\n✅ Save this configuration to database? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("❌ Configuration not saved. Exiting.")
        return

    # Connect to database and save
    load_dotenv()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL environment variable not set")

    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)

    try:
        await save_config_to_db(db_pool, config)
        print("\n" + "=" * 80)
        print("🎉 Configuration successfully saved!")
        print("=" * 80)
        print("You can now start the bot with:")
        print("  python -m main paper --symbol BTCUSDT")
        print("  python -m main live --symbol BTCUSDT --testnet")
        print("=" * 80 + "\n")
    finally:
        await db_pool.close()


async def main():
    """Main entry point."""
    try:
        await create_config_interactive()
    except KeyboardInterrupt:
        print("\n\n❌ Configuration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
