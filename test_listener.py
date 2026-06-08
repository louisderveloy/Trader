#!/usr/bin/env python3
"""
Minimal test for PostgreSQL LISTEN/NOTIFY functionality.

This script sets up a listener and waits for notifications.
Run test_config_reload.py in another terminal to trigger a notification.
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()


async def test_listener():
    """Test the PostgreSQL LISTEN/NOTIFY setup."""
    dsn = os.getenv("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trading_bot")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    print("=" * 80)
    print("CONFIG UPDATE LISTENER TEST")
    print("=" * 80)
    print("\nConnecting to database...")

    conn = await asyncpg.connect(dsn)

    def notification_handler(connection, pid, channel, payload):
        """Handle incoming notifications."""
        print("\n" + "=" * 80)
        print("📨 NOTIFICATION RECEIVED!")
        print("=" * 80)
        print(f"Channel: {channel}")
        print(f"From PID: {pid}")
        print(f"\nPayload:")
        try:
            data = json.loads(payload)
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(payload)
        print("=" * 80)

    try:
        # Add listener
        await conn.add_listener('config_updated', notification_handler)
        print("✓ Listening on channel 'config_updated'")
        print("\n⏳ Waiting for notifications...")
        print("   Run 'python test_config_reload.py' in another terminal to test")
        print("   Press Ctrl+C to exit\n")

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n\n✓ Test completed")
    finally:
        await conn.remove_listener('config_updated', notification_handler)
        await conn.close()
        print("✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(test_listener())
