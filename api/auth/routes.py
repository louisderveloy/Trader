"""
Authentication routes.

Endpoints for login and user information.
"""

import asyncio
import logging
import random
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..config import settings
from ..limiter import limiter
from .dependencies import get_current_user
from .jwt import create_access_token, verify_admin_credentials
from .models import LoginResponse, User, UserLogin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
@limiter.limit(lambda: settings.rate_limit_login)
async def login(
    request: Request,
    response: Response,
    credentials: UserLogin
) -> LoginResponse:
    """
    Login endpoint.

    Verify credentials and set JWT token in httpOnly cookie.

    Rate limited to 5 attempts per minute to prevent brute force attacks.

    Args:
        request: FastAPI request object (for rate limiting)
        response: FastAPI response object (for setting cookie)
        credentials: Username and password

    Returns:
        Login success message with username

    Raises:
        HTTPException: 401 if credentials are invalid
        HTTPException: 429 if rate limit exceeded (5 attempts/minute)
    """

    # Verify credentials
    if not verify_admin_credentials(credentials.username, credentials.password):
        # Generic log message (no username to prevent enumeration)
        logger.warning(f"Failed login attempt from {request.client.host}")

        # Add artificial delay to prevent timing attacks
        # Random delay between 0.1 and 0.3 seconds
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Generic error message (no distinction between invalid username vs password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": credentials.username})

    # Set httpOnly cookie with JWT token
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # Cannot be accessed by JavaScript (XSS protection)
        secure=settings.environment == "prod",  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=settings.jwt_access_token_expire_minutes * 60,  # Convert minutes to seconds
    )

    logger.info(f"Successful login from {request.client.host}")

    return LoginResponse(message="Login successful", username=credentials.username)


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user)
) -> dict:
    """
    Logout endpoint.

    Clears the JWT token httpOnly cookie.

    Requires valid authentication.

    Args:
        response: FastAPI response object (for clearing cookie)
        user: Current authenticated user (from dependency)

    Returns:
        Logout success message
    """
    # Clear the access_token cookie
    response.delete_cookie(key="access_token")

    logger.info(f"Successful logout: username={user.username}")

    return {"message": "Logout successful"}


@router.get("/csrf-token")
async def get_csrf_token(
    request: Request,
    response: Response
) -> dict:
    """
    Get CSRF token for state-changing operations.

    Note: With httpOnly cookies and SameSite=strict, CSRF protection is largely
    redundant, but we provide this endpoint for defense in depth.

    The CSRF token is set as a cookie that can be read by JavaScript and should
    be included in the X-CSRF-Token header for all POST/PATCH/PUT/DELETE requests.

    Args:
        request: FastAPI request object
        response: FastAPI response object (for setting CSRF cookie)

    Returns:
        Success message with the CSRF token
    """
    # Generate a secure random CSRF token
    csrf_token = secrets.token_urlsafe(32)

    # Set token in a readable cookie (not httpOnly, so JavaScript can read it)
    # This is the double-submit cookie pattern
    response.set_cookie(
        key="csrf_access_token",
        value=csrf_token,
        httponly=False,  # Must be readable by JavaScript
        secure=settings.environment == "prod",
        samesite="strict",
        max_age=3600  # 1 hour
    )

    return {
        "detail": "CSRF token set in cookie",
        "csrf_token": csrf_token  # Also return in body for convenience
    }


@router.get("/me", response_model=User)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_current_user_info(
    request: Request,
    user: User = Depends(get_current_user)
) -> User:
    """
    Get current user information.

    Requires valid JWT token.
    Rate limited to 60 requests per minute.

    Args:
        request: FastAPI request object (for rate limiting)
        user: Current authenticated user (from dependency)

    Returns:
        Current user information
    """
    return user
