"""
Authelia OpenID Connect relying-party utilities.

This module is the "OIDC utils" layer: it builds authorization requests, validates
Authelia-issued ``id_token`` (RS256 via JWKS), maps the ``groups`` claim to an
internal :class:`Role`, and seals/opens the short-lived OIDC transaction cookie.

Design rules (see .agent/security-review.md):

- **Never import ``api/auth/jwt.py``.** That module signs/verifies *our own* session
  cookie with HS256. Authelia's ``id_token`` is RS256 and is validated here with a
  completely separate code path so an attacker cannot trigger HS/RS algorithm
  confusion.
- **Fail closed.** Any discovery/JWKS/validation error raises; nothing is granted on
  error.
- The transaction cookie is **encrypted** (Fernet) because it carries the PKCE
  ``code_verifier``; it is single-use and short-lived.

The dev bypass (``DEV_USER_GROUP``) lives in :func:`resolve_role` callers, not here;
see :func:`api.auth.dependencies.get_principal`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

import httpx
from authlib.jose import JsonWebKey, jwt as jose_jwt
from authlib.jose.errors import JoseError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from ..config import settings
from .models import Role

logger = logging.getLogger(__name__)

# Cookie names
TXN_COOKIE = "oidc_txn"
STEPUP_COOKIE = "oidc_stepup"

# Transaction cookie lifetime (seconds): an authorization round-trip is short-lived.
TXN_TTL_SECONDS = 300

# Clock skew tolerance when validating token time claims.
LEEWAY_SECONDS = 30

# How long discovery + JWKS documents are cached.
_DISCOVERY_TTL = 3600
_JWKS_TTL = 3600

# Simple in-process caches: {url: (expires_at, value)}
_discovery_cache: dict[str, tuple[float, dict]] = {}
_jwks_cache: dict[str, tuple[float, object]] = {}


# ----------------------------------------------------------------------------
# Group → Role mapping (used in both OIDC and dev-bypass paths)
# ----------------------------------------------------------------------------
def resolve_role(groups: list[str]) -> Optional[Role]:
    """Map a list of group names to the highest applicable role.

    Admin wins over viewer. Returns ``None`` when the identity belongs to neither
    configured group (⇒ access denied, no session issued).
    """
    group_set = {g for g in groups if g}
    if settings.oidc_admin_group in group_set:
        return Role.ADMIN
    if settings.oidc_viewer_group in group_set:
        return Role.VIEWER
    return None


def is_admin(role: Optional[Role]) -> bool:
    """True if the resolved role is admin."""
    return role == Role.ADMIN


def is_viewer(role: Optional[Role]) -> bool:
    """True if the resolved role grants at least read access (viewer or admin)."""
    return role in (Role.ADMIN, Role.VIEWER)


def has_access(role: Optional[Role]) -> bool:
    """True if the identity maps to any known role."""
    return role is not None


# ----------------------------------------------------------------------------
# Transaction cookie (encrypted, single-use, short-lived)
# ----------------------------------------------------------------------------
def _fernet() -> Fernet:
    """Build a Fernet from the dedicated OIDC transaction secret."""
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.oidc_transaction_secret.encode("utf-8")).digest()
    )
    return Fernet(key)


def seal_transaction(payload: dict) -> str:
    """Encrypt a transaction payload for storage in the txn cookie."""
    return _fernet().encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")


def open_transaction(token: str, *, ttl: int = TXN_TTL_SECONDS) -> dict:
    """Decrypt + TTL-check a transaction cookie. Raises 400 on any problem."""
    try:
        raw = _fernet().decrypt(token.encode("ascii"), ttl=ttl)
        return json.loads(raw)
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Invalid OIDC transaction cookie: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired login transaction"
        )


# ----------------------------------------------------------------------------
# Discovery + JWKS
# ----------------------------------------------------------------------------
async def _get_discovery() -> dict:
    """Fetch and cache the OIDC discovery document. Fail closed."""
    issuer = settings.authelia_oidc_issuer.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    now = time.time()
    cached = _discovery_cache.get(url)
    if cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            doc = resp.json()
    except Exception as exc:  # noqa: BLE001 - fail closed on any discovery error
        logger.error("OIDC discovery failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider unavailable",
        )
    if doc.get("issuer") != issuer:
        logger.error("OIDC discovery issuer mismatch: %r != %r", doc.get("issuer"), issuer)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider misconfigured",
        )
    _discovery_cache[url] = (now + _DISCOVERY_TTL, doc)
    return doc


async def _get_jwks(jwks_uri: str, *, force: bool = False):
    """Fetch and cache the JWKS key set. Fail closed."""
    now = time.time()
    cached = _jwks_cache.get(jwks_uri)
    if cached and cached[0] > now and not force:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            key_set = JsonWebKey.import_key_set(resp.json())
    except Exception as exc:  # noqa: BLE001 - fail closed
        logger.error("JWKS fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider unavailable",
        )
    _jwks_cache[jwks_uri] = (now + _JWKS_TTL, key_set)
    return key_set


# ----------------------------------------------------------------------------
# Authorization request
# ----------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


async def build_authorization(
    *,
    redirect_uri: str,
    return_to: str,
    prompt: Optional[str] = None,
    max_age: Optional[int] = None,
    extra_txn: Optional[dict] = None,
) -> tuple[str, str]:
    """Build the authorization URL and the (sealed) transaction cookie value.

    Args:
        redirect_uri: absolute callback URL registered with Authelia.
        return_to: validated relative path to land on after login.
        prompt / max_age: step-up controls (``prompt="login"`` + ``max_age=0``).
        extra_txn: extra fields to bind into the transaction (e.g. session ``sub``).

    Returns:
        ``(authorization_url, sealed_txn_cookie_value)``.
    """
    disc = await _get_discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = _b64url(secrets.token_bytes(64))
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode("ascii")).digest())

    params = {
        "client_id": settings.authelia_oidc_client_id,
        "response_type": "code",
        "scope": "openid profile email groups",
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if prompt:
        params["prompt"] = prompt
    if max_age is not None:
        params["max_age"] = str(max_age)

    auth_url = str(httpx.URL(disc["authorization_endpoint"]).copy_merge_params(params))

    txn = {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "return_to": return_to,
    }
    if extra_txn:
        txn.update(extra_txn)

    return auth_url, seal_transaction(txn)


# ----------------------------------------------------------------------------
# Code exchange + id_token validation
# ----------------------------------------------------------------------------
async def exchange_code(*, code: str, code_verifier: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for tokens at the token endpoint. Fail closed."""
    disc = await _get_discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.authelia_oidc_client_id,
        "client_secret": settings.authelia_oidc_client_secret,
        "code_verifier": code_verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(disc["token_endpoint"], data=data)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001 - fail closed
        logger.warning("OIDC code exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        )


async def validate_id_token(raw_token: str, *, expected_nonce: str) -> dict:
    """Validate an Authelia ``id_token`` and return its claims.

    Enforces RS256, issuer, audience, expiry, and nonce. Raises 401 on any failure.
    """
    # Defensively reject any non-RS256 token before touching the key set.
    try:
        header_b64 = raw_token.split(".", 1)[0]
        header = json.loads(base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4)))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    if header.get("alg") != "RS256":
        logger.warning("id_token rejected: alg=%r (only RS256 allowed)", header.get("alg"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token algorithm")

    disc = await _get_discovery()
    issuer = settings.authelia_oidc_issuer.rstrip("/")
    claims_options = {
        "iss": {"essential": True, "value": issuer},
        "aud": {"essential": True, "values": [settings.authelia_oidc_client_id]},
        "exp": {"essential": True},
        "sub": {"essential": True},
    }

    key_set = await _get_jwks(disc["jwks_uri"])
    try:
        claims = jose_jwt.decode(raw_token, key_set, claims_options=claims_options)
        claims.validate(leeway=LEEWAY_SECONDS)
    except (JoseError, ValueError) as exc:
        # Possibly a rotated signing key: refresh JWKS once and retry.
        try:
            key_set = await _get_jwks(disc["jwks_uri"], force=True)
            claims = jose_jwt.decode(raw_token, key_set, claims_options=claims_options)
            claims.validate(leeway=LEEWAY_SECONDS)
        except (JoseError, ValueError) as exc2:
            logger.warning("id_token validation failed: %s", exc2)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Constant-time nonce check (defends against token injection / replay).
    token_nonce = claims.get("nonce", "")
    if not token_nonce or not hmac.compare_digest(str(token_nonce), expected_nonce):
        logger.warning("id_token nonce mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not str(claims.get("sub", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return dict(claims)


def extract_groups(claims: dict) -> list[str]:
    """Read the groups claim defensively (string or list)."""
    groups = claims.get("groups", [])
    if isinstance(groups, str):
        return [groups]
    if isinstance(groups, list):
        return [str(g) for g in groups]
    return []


# ----------------------------------------------------------------------------
# Step-up grant (encrypted httpOnly cookie authorizing one live-run start)
# ----------------------------------------------------------------------------
def seal_stepup_grant(*, sub: str) -> str:
    """Seal a short-lived step-up grant bound to a session subject.

    The grant proves the holder freshly re-authenticated as ``sub`` with the admin
    role. It is delivered as an httpOnly cookie; the live-run start consumes it.
    Single use in practice: the start endpoint clears the cookie on consume and the
    live single-instance advisory lock prevents a second concurrent live run.
    """
    payload = {"purpose": "live_stepup", "sub": sub, "iat": int(time.time())}
    return _fernet().encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")


def verify_stepup_grant(token: Optional[str], *, sub: str) -> bool:
    """Verify a step-up grant cookie against the current session subject + freshness."""
    if not token:
        return False
    try:
        raw = _fernet().decrypt(token.encode("ascii"), ttl=settings.oidc_stepup_max_age_seconds)
        payload = json.loads(raw)
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return False
    return (
        payload.get("purpose") == "live_stepup"
        and isinstance(payload.get("sub"), str)
        and hmac.compare_digest(payload["sub"], sub)
    )
