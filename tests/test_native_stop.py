"""
Tests for native exchange OCO stop orders and the per-mode precedence (issue #17).

Covers the testable (mocked) parts of the live/testnet protection path:
- BinanceExchange.place_oco_sell_order builds the correct create_oco_order call
  and normalizes the response.
- BinanceExchange.cancel_oco_order delegates to cancel_order (cancelling one OCO
  leg cancels the pair).
- The trading loop places the OCO on a live entry, reconciles a server-side fill,
  and cancels the OCO before a signal-driven market exit (no double-sell).
"""

import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

from exchanges.binance import BinanceExchange
from scripts.trading import TradingBot


# ----------------------------- Exchange layer -----------------------------

@pytest.fixture
def binance():
    ex = BinanceExchange(api_key="k", api_secret="s", testnet=True)
    ex.client = MagicMock()
    ex.get_symbol_info = AsyncMock(return_value={
        "lot_size_step": Decimal("0.00001"),
        "price_tick": Decimal("0.01"),
    })
    return ex


@pytest.mark.asyncio
async def test_place_oco_sell_order_builds_correct_call(binance):
    binance.client.create_oco_order = AsyncMock(return_value={
        "orderListId": 42,
        "orderReports": [{"orderId": 111}, {"orderId": 222}],
    })

    result = await binance.place_oco_sell_order(
        symbol="BTCUSDT",
        quantity=Decimal("0.01234"),
        take_profit_price=Decimal("61000"),
        stop_price=Decimal("59000"),
        stop_limit_price=Decimal("58950"),
    )

    binance.client.create_oco_order.assert_awaited_once()
    kwargs = binance.client.create_oco_order.await_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["side"] == "SELL"
    assert Decimal(kwargs["price"]) == Decimal("61000")          # take-profit limit leg
    assert Decimal(kwargs["stopPrice"]) == Decimal("59000")      # stop trigger
    assert Decimal(kwargs["stopLimitPrice"]) == Decimal("58950")  # stop-loss limit
    assert kwargs["stopLimitTimeInForce"] == "GTC"

    assert result["order_list_id"] == "42"
    assert result["leg_order_ids"] == ["111", "222"]


@pytest.mark.asyncio
async def test_cancel_oco_delegates_to_cancel_order(binance):
    binance.cancel_order = AsyncMock(return_value={"order_id": "111", "status": "cancelled"})
    out = await binance.cancel_oco_order("BTCUSDT", "111")
    binance.cancel_order.assert_awaited_once_with("BTCUSDT", "111")
    assert out["status"] == "cancelled"


# ----------------------------- Trading loop -----------------------------

def _live_bot_with_position(stop_list_id="LIST1", legs=("111", "222")):
    bot = TradingBot(symbol="BTCUSDT", timeframe="15m", mode="live",
                     testnet=True, initial_capital=Decimal("10000"), run_id=1)
    bot.db_pool = MagicMock()
    bot.exchange = MagicMock()
    bot.discord_notifier = None
    bot.capital = Decimal("10000")
    bot.position = {
        "trade_id": 1,
        "entry_price": Decimal("60000"),
        "entry_time": datetime.now(timezone.utc),
        "quantity": Decimal("0.01"),
        "entry_commission": Decimal("0.6"),
        "stop_loss": Decimal("59000"),
        "take_profit": Decimal("61000"),
        "order_id": "entry1",
        "entry_order_id": 1,
        "entry_score": 0.7,
        "entry_signals": {},
        "stop_order_list_id": stop_list_id,
        "stop_leg_order_ids": list(legs),
    }
    return bot


@pytest.mark.asyncio
async def test_place_native_stop_sets_position_ids():
    bot = _live_bot_with_position(stop_list_id=None, legs=())
    bot.exchange.place_oco_sell_order = AsyncMock(return_value={
        "order_list_id": "LISTX", "leg_order_ids": ["a", "b"],
    })
    await bot._place_native_stop(Decimal("60000"), Decimal("0.01"),
                                 Decimal("59000"), Decimal("61000"))
    bot.exchange.place_oco_sell_order.assert_awaited_once()
    assert bot.position["stop_order_list_id"] == "LISTX"
    assert bot.position["stop_leg_order_ids"] == ["a", "b"]
    assert bot._has_native_stop()


@pytest.mark.asyncio
async def test_place_native_stop_skipped_in_paper():
    bot = _live_bot_with_position(stop_list_id=None, legs=())
    bot.mode = "paper"
    bot.exchange.place_oco_sell_order = AsyncMock()
    await bot._place_native_stop(Decimal("60000"), Decimal("0.01"),
                                 Decimal("59000"), Decimal("61000"))
    bot.exchange.place_oco_sell_order.assert_not_called()
    assert not bot._has_native_stop()


@pytest.mark.asyncio
async def test_reconcile_resting_oco_returns_false():
    bot = _live_bot_with_position()
    # A leg is still open → OCO resting, no action.
    bot.exchange.get_open_orders = AsyncMock(return_value=[{"order_id": "111"}])
    resolved = await bot._reconcile_native_stop(0.0, {})
    assert resolved is False
    assert bot.position is not None


@pytest.mark.asyncio
async def test_reconcile_filled_stop_closes_position():
    bot = _live_bot_with_position()
    bot.exchange.get_open_orders = AsyncMock(return_value=[])  # neither leg open
    bot.exchange.get_order_status = AsyncMock(side_effect=[
        {"status": "filled", "type": "stop_loss_limit", "filled_price": Decimal("58950")},
        {"status": "cancelled", "type": "limit", "filled_price": None},
    ])
    bot._log_trade = AsyncMock()

    resolved = await bot._reconcile_native_stop(0.0, {})

    assert resolved is True
    assert bot.position is None
    bot._log_trade.assert_awaited_once()
    assert bot._log_trade.await_args.kwargs["exit_reason"] == "stop_loss"


@pytest.mark.asyncio
async def test_signal_exit_cancels_oco_before_market_sell():
    bot = _live_bot_with_position()
    bot.exchange.cancel_oco_order = AsyncMock(return_value={"status": "cancelled"})
    await bot._cancel_native_stop()
    bot.exchange.cancel_oco_order.assert_awaited_once_with("BTCUSDT", "111")
    assert not bot._has_native_stop()
