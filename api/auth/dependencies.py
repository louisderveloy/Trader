"""
FastAPI authentication dependencies.

Provides dependency functions for JWT token verification from httpOnly cookies.
"""

from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, status

from ..config import settings
from .jwt import decode_access_token
from .models import Principal, Role, User


async def get_current_user(
    access_token: Optional[str] = Cookie(None, alias="access_token")
) -> User:
    """
    FastAPI dependency to get current authenticated user from JWT token in httpOnly cookie.

    Args:
        access_token: JWT token from httpOnly cookie

    Returns:
        Current user

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.username}
    """
    # Check if token is present
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode token
    payload = decode_access_token(access_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract username from token
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify username matches admin (mono-user v1)
    if username != settings.admin_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return user
    return User(username=username, email=settings.admin_email)


async def _resolve_oidc_principal(authorization: Optional[str]) -> Principal:
    """Resolve a principal from an Authelia-issued OIDC JWT.

    Stub for the PROD-ONLY Authelia rollout. The full implementation validates the
    bearer token against Authelia's JWKS (``auth.trader.derveloy.eu``) and maps the
    ``groups`` claim to a :class:`Role`. It is intentionally inert until that work
    lands so enabling ``AUTH_MODE=authelia_oidc`` without the wiring fails loudly
    rather than silently granting access.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authelia OIDC authentication is not yet wired. Use AUTH_MODE=local until rollout.",
    )


async def get_principal(
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    authorization: Optional[str] = Header(None),
) -> Principal:
    """Resolve the current :class:`Principal` (identity + role) for the active auth mode.

    - ``local`` (default, only mode in dev): validates the JWT cookie via
      :func:`get_current_user`; the mono-user maps to :attr:`Role.ADMIN`.
    - ``authelia_oidc`` (prod, future): delegates to :func:`_resolve_oidc_principal`.
    """
    mode = settings.auth_mode

    if mode == "local":
        user = await get_current_user(access_token)
        return Principal(username=user.username, email=user.email, role=Role.ADMIN)

    if mode == "authelia_oidc":
        return await _resolve_oidc_principal(authorization)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Invalid AUTH_MODE: {mode!r}",
    )


def require_role(*allowed: Role):
    """Build a dependency that admits only the given roles, else 403."""

    async def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges for this action",
            )
        return principal

    return _checker


# Route guards: admin for mutations, viewer (or admin) for reads.
require_admin = require_role(Role.ADMIN)
require_viewer = require_role(Role.ADMIN, Role.VIEWER)
