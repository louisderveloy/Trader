"""
Shared cookie helpers for authentication.

Centralises the attributes of the session and CSRF cookies so the local-login
path (api/auth/routes.py) and the OIDC callback (api/auth/oidc_routes.py) issue
byte-for-byte identical cookies.

Cookie policy (see docs/Authentification.md §5):

- ``access_token`` (session): httpOnly, Secure in prod, SameSite=Strict in prod,
  **host-only** (no domain ⇒ only sent to api.trader.derveloy.eu). The dashboard
  and API share the registrable domain ``trader.derveloy.eu`` so Strict still
  carries the cookie on same-site XHR.
- ``csrf_access_token`` (double-submit): readable by JS, scoped to the trading
  project subdomains only (``.trader.derveloy.eu`` in prod), SameSite=Strict.
"""

from fastapi import Response

from ..config import settings

SESSION_COOKIE = "access_token"
CSRF_COOKIE = "csrf_access_token"


def _is_prod() -> bool:
    return settings.environment == "prod"


def _samesite() -> str:
    # Strict is safe in prod: dashboard/API/Authelia share trader.derveloy.eu (same site).
    # Lax in dev keeps localhost cross-port flows frictionless.
    return "strict" if _is_prod() else "lax"


def _csrf_domain() -> str | None:
    # Scope the CSRF cookie to the trading project only, never the whole parent domain.
    return ".trader.derveloy.eu" if _is_prod() else None


def set_session_cookie(response: Response, token: str) -> None:
    """Set the httpOnly session JWT cookie (host-only)."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=_is_prod(),
        samesite=_samesite(),
        domain=None,  # host-only: only api.trader.derveloy.eu receives it
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie (attributes must match set_session_cookie)."""
    response.delete_cookie(key=SESSION_COOKIE, domain=None, samesite=_samesite())


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set the readable double-submit CSRF cookie."""
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,  # must be readable by JavaScript
        secure=_is_prod(),
        samesite=_samesite(),
        domain=_csrf_domain(),
        max_age=3600,
    )


def set_txn_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    """Set the encrypted OIDC transaction cookie (host-only, Lax, scoped to /auth/oidc).

    SameSite=Lax (not Strict) so the cookie is carried on the top-level navigation
    back from Authelia to the callback.
    """
    response.set_cookie(
        key=name,
        value=value,
        httponly=True,
        secure=_is_prod(),
        samesite="lax",
        domain=None,
        path="/auth/oidc",
        max_age=max_age,
    )


def clear_txn_cookie(response: Response, name: str) -> None:
    """Clear an OIDC transaction cookie (attributes must match set_txn_cookie)."""
    response.delete_cookie(key=name, domain=None, path="/auth/oidc", samesite="lax")


def set_stepup_cookie(response: Response, value: str, max_age: int) -> None:
    """Set the httpOnly step-up grant cookie (host-only, consumed by the live-run start)."""
    response.set_cookie(
        key="oidc_stepup",
        value=value,
        httponly=True,
        secure=_is_prod(),
        samesite=_samesite(),
        domain=None,
        path="/",
        max_age=max_age,
    )


def clear_stepup_cookie(response: Response) -> None:
    """Clear the step-up grant cookie (single-use)."""
    response.delete_cookie(key="oidc_stepup", domain=None, path="/", samesite=_samesite())
