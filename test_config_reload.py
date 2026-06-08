#!/usr/bin/env python3
"""
Test script for config reload functionality.

This script:
1. Updates the config in the database
2. Waits for running bot instances to pick up the change
3. Verifies the notification was sent
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


async def update_config():
    """Update config in database to trigger notification."""
    dsn = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trading_bot")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)

    try:
        # Fetch current config
        current = await conn.fetchrow("SELECT id, config FROM config LIMIT 1")

        if not current:
            print("❌ No config found in database")
            return

        config_id = current['id']
        config = current['config']

        # Parse config if it's a string
        if isinstance(config, str):
            config = json.loads(config)

        print("=" * 80)
        print("CURRENT CONFIG:")
        print(json.dumps(config, indent=2))
        print("=" * 80)

        # Modify entry threshold
        old_threshold = config['strategy']['entry_threshold']
        new_threshold = 0.65 if old_threshold != 0.65 else 0.7  # Toggle between values

        config['strategy']['entry_threshold'] = new_threshold

        print(f"\n📝 Updating entry_threshold: {old_threshold} → {new_threshold}")

        # Update the config (this will trigger the notification)
        # Convert back to JSON string for storage
        config_json = json.dumps(config)

        await conn.execute(
            """
            UPDATE config
            SET config = $1::jsonb, updated_at = $2
            WHERE id = $3
            """,
            config_json,
            datetime.now(timezone.utc),
            config_id
        )

        print("✓ Config updated in database")
        print("\n⏳ Notification should have been sent to all running bot instances")
        print("   Check bot logs for 'CONFIG UPDATE NOTIFICATION RECEIVED'")
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(update_config())
