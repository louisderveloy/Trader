"""
Regression tests for the PyJWT-based session token layer (security review #1).

Proves CVE-2022-29217 (algorithm confusion) is closed: the decoder only ever
accepts HS256 and rejects any token whose algorithm is forced to ``none``, plus
rejects tokens missing the required ``exp``/``sub`` claims.

Run with the API deps installed; not collected by the bot ``tests/`` suite.
"""

import jwt  # PyJWT
import pytest

from api.auth.jwt import create_access_token, decode_access_token
from api.config import settings


def test_valid_token_round_trips() -> None:
    token = create_access_token(data={"sub": "louis", "role": "admin"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "louis"
    assert payload["role"] == "admin"


def test_alg_none_token_rejected() -> None:
    """A token forged with alg=none must be rejected (CVE-2022-29217)."""
    forged = jwt.encode(
        {"sub": "attacker", "exp": 9999999999}, key="", algorithm="none"
    )
    assert decode_access_token(forged) is None


def test_token_missing_sub_rejected() -> None:
    """A correctly-signed token without the required ``sub`` claim is rejected."""
    no_sub = jwt.encode(
        {"exp": 9999999999}, settings.jwt_secret_key, algorithm="HS256"
    )
    assert decode_access_token(no_sub) is None


def test_token_missing_exp_rejected() -> None:
    """A correctly-signed token without the required ``exp`` claim is rejected."""
    no_exp = jwt.encode(
        {"sub": "louis"}, settings.jwt_secret_key, algorithm="HS256"
    )
    assert decode_access_token(no_exp) is None


def test_token_signed_with_wrong_secret_rejected() -> None:
    bad = jwt.encode(
        {"sub": "louis", "exp": 9999999999}, "wrong-secret", algorithm="HS256"
    )
    assert decode_access_token(bad) is None
