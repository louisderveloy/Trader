"""Simple test script for Binance connector.

This script verifies the Binance connector can:
1. Connect to testnet
2. Fetch candles
3. Get ticker data
4. Get balance

Run from bot container:
    python test_binance_connector.py
"""

import asyncio
import os
import sys
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges import BinanceExchange


async def main():
    """Test Binance connector."""
    # Get credentials from environment
    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")

    if not api_key or not api_secret:
        print("❌ ERROR: BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET must be set in .env")
        print("   Please configure your Binance testnet API credentials first.")
        return 1

    print("=" * 60)
    print("🧪 Testing Binance Connector (Testnet)")
    print("=" * 60)

    # Create connector
    exchange = BinanceExchange(api_key=api_key, api_secret=api_secret, testnet=True)

    try:
        # Test 1: Connect
        print("\n[1/4] Testing connection...")
        await exchange.connect()
        print("✅ Connected to Binance testnet")

        # Test 2: Fetch candles
        print("\n[2/4] Testing candle fetching...")
        candles = await exchange.get_candles(symbol="BTCUSDT", timeframe="15m", limit=5)
        print(f"✅ Fetched {len(candles)} candles")
        print(f"    Latest candle: {candles[-1]['time']} - Close: ${candles[-1]['close']}")

        # Test 3: Get ticker
        print("\n[3/4] Testing ticker data...")
        ticker = await exchange.get_ticker(symbol="BTCUSDT")
        print(f"✅ Ticker data retrieved")
        print(f"    Last price: ${ticker['last_price']}")
        print(f"    Bid: ${ticker['bid']} | Ask: ${ticker['ask']}")
        print(f"    24h volume: {ticker['volume_24h']} BTC")

        # Test 4: Get balance
        print("\n[4/4] Testing balance retrieval...")
        usdt_balance = await exchange.get_balance("USDT")
        btc_balance = await exchange.get_balance("BTC")
        print(f"✅ Balance data retrieved")
        print(f"    USDT: {usdt_balance['total']} (free: {usdt_balance['free']}, locked: {usdt_balance['locked']})")
        print(f"    BTC:  {btc_balance['total']} (free: {btc_balance['free']}, locked: {btc_balance['locked']})")

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Always disconnect
        print("\n🔌 Disconnecting...")
        await exchange.disconnect()
        print("✅ Disconnected")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
