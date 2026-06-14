"""
Authelia OIDC relying-party routes (prod-only, AUTH_MODE=authelia_oidc).

Implements the BFF Authorization Code + PKCE flow plus the live-run step-up:

    GET  /auth/oidc/login            -> redirect to Authelia
    GET  /auth/oidc/callback         -> validate, issue session, land on dashboard
    GET  /auth/oidc/stepup           -> force re-auth (max_age=0, prompt=login)
    GET  /auth/oidc/stepup/callback  -> validate fresh re-auth, issue step-up grant
    POST /auth/oidc/logout           -> clear session

These routes return 404 unless AUTH_MODE=authelia_oidc, so they never shadow the
local login in dev.
"""

import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from ..config import settings
from ..limiter import limiter
from . import oidc
from .cookies import (
    clear_session_cookie,
    clear_stepup_cookie,
    clear_txn_cookie,
    set_session_cookie,
    set_stepup_cookie,
    set_txn_cookie,
)
from .dependencies import get_principal, require_admin
from .jwt import create_access_token
from .models import Principal, Role

logger = logging.getLogger(__name__)

router = APIRouter()

# Relative-path allowlist for post-login redirects (open-redirect guard).
_SAFE_RETURN_TO = re.compile(r"^/[A-Za-z0-9/_-]*$")


def _require_oidc_mode() -> None:
    """OIDC routes only exist when Authelia is the configured provider."""
    if settings.auth_mode != "authelia_oidc":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _safe_return_to(raw: Optional[str]) -> str:
    """Validate a return_to against the relative-path allowlist, else '/'."""
    if not raw or "//" in raw or ".." in raw or not _SAFE_RETURN_TO.match(raw):
        return "/"
    return raw


def _callback_uri() -> str:
    return f"{settings.api_public_base_url.rstrip('/')}/auth/oidc/callback"


def _stepup_callback_uri() -> str:
    return f"{settings.api_public_base_url.rstrip('/')}/auth/oidc/stepup/callback"


def _dashboard_url(path: str) -> str:
    return f"{settings.dashboard_public_base_url.rstrip('/')}{path}"


@router.get("/login")
@limiter.limit(lambda: settings.rate_limit_login)
async def oidc_login(request: Request, return_to: Optional[str] = None) -> RedirectResponse:
    """Begin the OIDC login. Full-page navigation target (never an XHR)."""
    _require_oidc_mode()
    auth_url, txn = await oidc.build_authorization(
        redirect_uri=_callback_uri(),
        return_to=_safe_return_to(return_to),
    )
    resp = RedirectResponse(auth_url, status_code=status.HTTP_303_SEE_OTHER)
    set_txn_cookie(resp, oidc.TXN_COOKIE, txn, oidc.TXN_TTL_SECONDS)
    return resp


@router.get("/callback")
@limiter.limit(lambda: settings.rate_limit_login)
async def oidc_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    oidc_txn: Optional[str] = Cookie(None, alias=oidc.TXN_COOKIE),
) -> RedirectResponse:
    """Complete the login: validate id_token, issue our session, land on the dashboard."""
    _require_oidc_mode()

    # Always clear the (single-use) transaction cookie, whatever the outcome.
    def _redirect(path: str) -> RedirectResponse:
        r = RedirectResponse(_dashboard_url(path), status_code=status.HTTP_303_SEE_OTHER)
        clear_txn_cookie(r, oidc.TXN_COOKIE)
        return r

    if not code or not state or not oidc_txn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback")

    txn = oidc.open_transaction(oidc_txn)
    if not _const_eq(state, txn.get("state", "")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State mismatch")

    tokens = await oidc.exchange_code(
        code=code, code_verifier=txn["code_verifier"], redirect_uri=txn["redirect_uri"]
    )
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No id_token")

    claims = await oidc.validate_id_token(id_token, expected_nonce=txn["nonce"])
    role = oidc.resolve_role(oidc.extract_groups(claims))

    if role is None:
        # Authenticated but unauthorised: no session, land on /no-access.
        logger.info("OIDC login denied (no mapped group): sub=%s", claims.get("sub"))
        return _redirect("/no-access")

    # Mint our own session JWT carrying the resolved role.
    token_data = {"sub": str(claims["sub"]), "role": role.value}
    if claims.get("email"):
        token_data["email"] = str(claims["email"])
    session_jwt = create_access_token(data=token_data)

    resp = _redirect(_safe_return_to(txn.get("return_to")))
    set_session_cookie(resp, session_jwt)
    logger.info("OIDC login OK: sub=%s role=%s", claims.get("sub"), role.value)
    return resp


@router.get("/stepup")
@limiter.limit(lambda: settings.rate_limit_login)
async def oidc_stepup(
    request: Request,
    return_to: Optional[str] = None,
    principal: Principal = Depends(require_admin),
) -> RedirectResponse:
    """Force a fresh re-authentication before a live run (max_age=0, prompt=login)."""
    _require_oidc_mode()
    auth_url, txn = await oidc.build_authorization(
        redirect_uri=_stepup_callback_uri(),
        return_to=_safe_return_to(return_to),
        prompt="login",
        max_age=0,
        extra_txn={"session_sub": principal.username},
    )
    resp = RedirectResponse(auth_url, status_code=status.HTTP_303_SEE_OTHER)
    set_txn_cookie(resp, oidc.TXN_COOKIE, txn, oidc.TXN_TTL_SECONDS)
    return resp


@router.get("/stepup/callback")
@limiter.limit(lambda: settings.rate_limit_login)
async def oidc_stepup_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    oidc_txn: Optional[str] = Cookie(None, alias=oidc.TXN_COOKIE),
    principal: Principal = Depends(get_principal),
) -> RedirectResponse:
    """Validate the fresh re-auth and issue a single-use step-up grant.

    Re-resolves the role from the FRESH id_token (not the session) and binds the
    fresh ``sub`` to the current session, so a demoted/other user cannot pass.
    """
    _require_oidc_mode()

    def _redirect(path: str, *, ok: bool) -> RedirectResponse:
        r = RedirectResponse(_dashboard_url(path), status_code=status.HTTP_303_SEE_OTHER)
        clear_txn_cookie(r, oidc.TXN_COOKIE)
        return r

    if not code or not state or not oidc_txn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid callback")

    txn = oidc.open_transaction(oidc_txn)
    if not _const_eq(state, txn.get("state", "")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State mismatch")
    # The step-up must belong to the same session that started it.
    if not _const_eq(txn.get("session_sub", ""), principal.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch")

    tokens = await oidc.exchange_code(
        code=code, code_verifier=txn["code_verifier"], redirect_uri=txn["redirect_uri"]
    )
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No id_token")

    claims = await oidc.validate_id_token(id_token, expected_nonce=txn["nonce"])

    # Fresh re-authentication: auth_time must be recent.
    auth_time = claims.get("auth_time")
    if not isinstance(auth_time, (int, float)) or (
        time.time() - float(auth_time) > settings.oidc_stepup_max_age_seconds + oidc.LEEWAY_SECONDS
    ):
        logger.warning("Step-up rejected: stale auth_time (sub=%s)", claims.get("sub"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Re-authentication too old")

    # Re-resolve role from the FRESH token and bind the fresh sub to the session.
    fresh_role = oidc.resolve_role(oidc.extract_groups(claims))
    if fresh_role != Role.ADMIN:
        logger.warning("Step-up rejected: fresh role not admin (sub=%s)", claims.get("sub"))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    if not _const_eq(str(claims.get("sub", "")), principal.username):
        logger.warning("Step-up rejected: fresh sub != session sub")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Identity mismatch")

    grant = oidc.seal_stepup_grant(sub=principal.username)
    resp = _redirect(_safe_return_to(txn.get("return_to")), ok=True)
    set_stepup_cookie(resp, grant, settings.oidc_stepup_max_age_seconds)
    logger.info("Step-up grant issued: sub=%s", principal.username)
    return resp


@router.post("/logout")
async def oidc_logout(response: Response, principal: Principal = Depends(get_principal)) -> dict:
    """Clear the API session (and any pending step-up grant)."""
    _require_oidc_mode()
    clear_session_cookie(response)
    clear_stepup_cookie(response)
    logger.info("OIDC logout: sub=%s", principal.username)
    return {"message": "Logout successful"}


def _const_eq(a: str, b: str) -> bool:
    import hmac

    return bool(a) and bool(b) and hmac.compare_digest(a, b)
