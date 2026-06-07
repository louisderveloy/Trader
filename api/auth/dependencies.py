"""
FastAPI authentication dependencies.

Provides dependency functions for JWT token verification from httpOnly cookies.
"""

from typing import Optional

from fastapi import Cookie, HTTPException, status

from ..config import settings
from .jwt import decode_access_token
from .models import User


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
