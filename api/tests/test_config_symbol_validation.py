"""
Tests for the user-indicator `symbol` allowlist (security review #11).

The `symbol` query param on GET/PATCH /config/user-indicator is validated by the
`valid_symbol` dependency against AVAILABLE_SYMBOLS, so the user_indicator table
can't be polluted with fictitious symbols. Tested directly (the Query(...)
metadata is inert outside FastAPI's injection).

Run with the API deps installed; not collected by the bot ``tests/`` suite.
"""

import pytest
from fastapi import HTTPException

from api.config import settings
from api.routes.config import valid_symbol


def test_valid_symbol_passes() -> None:
    sym = settings.available_symbols_list[0]
    assert valid_symbol(sym) == sym


def test_lowercase_symbol_normalized() -> None:
    sym = settings.available_symbols_list[0]
    assert valid_symbol(sym.lower()) == sym


def test_default_is_allowlisted() -> None:
    # No-arg call must validate: the configured default is always in the
    # allowlist (config.py available_symbols_list fallback). Locks that invariant.
    assert valid_symbol() == settings.binance_default_symbol.upper()


@pytest.mark.parametrize("bad", ["BTCUSDT", "FAKEUSDC", "'; DROP TABLE user_indicator;--"])
def test_fictitious_symbol_rejected(bad: str) -> None:
    with pytest.raises(HTTPException) as exc:
        valid_symbol(bad)
    assert exc.value.status_code == 422
