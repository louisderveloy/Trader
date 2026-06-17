"""
FastAPI authentication dependencies.

Provides dependency functions for JWT token verification from httpOnly cookies.
"""

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status

from ..config import settings
from .jwt import decode_access_token
from .models import Principal, Role, User
from .oidc import resolve_role


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


def _resolve_oidc_principal(access_token: Optional[str]) -> Principal:
    """Resolve a principal from *our own* session cookie in OIDC mode.

    In ``authelia_oidc`` mode the session cookie is the HS256 JWT we minted at the
    OIDC callback (``sub``/``role``/``email`` claims), NOT the raw Authelia id_token.
    We therefore decode it with the same machinery as local mode and never call
    Authelia per request. (Authelia's RS256 id_token is validated only at the callback,
    in :mod:`api.auth.oidc`.)
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(access_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    role_raw = payload.get("role")
    if not sub or role_raw not in (Role.ADMIN.value, Role.VIEWER.value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )
    return Principal(
        username=sub,
        display_name=payload.get("display_name"),
        email=payload.get("email"),
        role=Role(role_raw),
    )


async def get_principal(
    access_token: Optional[str] = Cookie(None, alias="access_token"),
) -> Principal:
    """Resolve the current :class:`Principal` (identity + role) for the active auth mode.

    - ``local`` (dev only): validates the JWT cookie via :func:`get_current_user`, then
      derives the role from ``DEV_USER_GROUP`` (the dev auth bypass). Guarded so it can
      only ever run in the dev environment.
    - ``authelia_oidc`` (prod): decodes our session JWT (set at the OIDC callback).
    """
    mode = settings.auth_mode

    if mode == "local":
        # Dev bypass: only valid in the dev environment. Prod boot already refuses
        # AUTH_MODE=local (config.validate_production_secrets), but guard in depth.
        if settings.environment != "dev":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AUTH_MODE=local is only permitted in the dev environment.",
            )
        user = await get_current_user(access_token)
        role = resolve_role(settings.dev_user_groups_list)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DEV_USER_GROUP maps to no role (set 'admins' or 'viewers').",
            )
        return Principal(
            username=user.username,
            display_name=user.username,
            email=user.email,
            role=role,
        )

    if mode == "authelia_oidc":
        return _resolve_oidc_principal(access_token)

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
