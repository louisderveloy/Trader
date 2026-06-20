"""
Tests for the pre-lock Binance credential check (security review #20).

A missing API key/secret must fail fast (before the instance lock / run record),
with a clear error rather than passing None to the SDK.
"""

import pytest

from scripts.trading import TradingBot


def _bot(testnet: bool = True) -> TradingBot:
    return TradingBot(symbol="BTCUSDC", timeframe="15m", mode="paper", testnet=testnet)


def test_missing_testnet_keys_raises(monkeypatch) -> None:
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    with pytest.raises(ValueError, match="BINANCE_TESTNET"):
        _bot(testnet=True)._validate_credentials()


def test_present_keys_returned(monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "s")
    assert _bot(testnet=True)._validate_credentials() == ("k", "s")


def test_mainnet_prefix_selected_when_not_testnet(monkeypatch) -> None:
    monkeypatch.delenv("BINANCE_MAINNET_API_KEY", raising=False)
    monkeypatch.setenv("BINANCE_MAINNET_API_SECRET", "s")
    with pytest.raises(ValueError, match="BINANCE_MAINNET"):
        _bot(testnet=False)._validate_credentials()
