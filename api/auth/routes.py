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
from ..limiter import client_ip_key_func, limiter
from .cookies import clear_session_cookie, set_csrf_cookie, set_session_cookie
from .dependencies import get_current_user, get_principal
from .jwt import create_access_token, verify_admin_credentials
from .models import LoginResponse, Principal, User, UserLogin


def _require_local_mode() -> None:
    """Disable the local password path unless AUTH_MODE=local.

    In OIDC mode the only authentication path is Authelia; the username/password
    login would be a parallel bypass. Return 404 (not 403) so the endpoint appears
    not to exist to scanners.
    """
    if settings.auth_mode != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

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
        HTTPException: 404 if AUTH_MODE != local (use Authelia OIDC instead)
        HTTPException: 429 if rate limit exceeded (5 attempts/minute)
    """
    _require_local_mode()

    # Verify credentials
    if not verify_admin_credentials(credentials.username, credentials.password):
        # Generic log message (no username to prevent enumeration). Use the real
        # client IP (not Traefik's) so failed-login logs are actionable (#15).
        logger.warning(f"Failed login attempt from {client_ip_key_func(request)}")

        # Add artificial delay to prevent timing attacks
        # Random delay between 0.1 and 0.3 seconds
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Generic error message (no distinction between invalid username vs password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token (local mono-user always maps to the admin role)
    access_token = create_access_token(data={"sub": credentials.username})

    # Set httpOnly session cookie (see api/auth/cookies.py for the policy)
    set_session_cookie(response, access_token)

    logger.info(f"Successful login from {client_ip_key_func(request)}")

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
    # Clear the session cookie (attributes must match set_session_cookie)
    clear_session_cookie(response)

    logger.info(f"Successful logout: username={user.username}")

    return {"message": "Logout successful"}


@router.get("/csrf-token")
async def get_csrf_token(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_principal),
) -> dict:
    """
    Get CSRF token for state-changing operations.

    Requires authentication so an anonymous caller cannot mint CSRF tokens.

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
    # Generate a secure random CSRF token (double-submit cookie pattern)
    csrf_token = secrets.token_urlsafe(32)

    # Set token in a readable cookie (not httpOnly, so JavaScript can read it)
    set_csrf_cookie(response, csrf_token)

    return {
        "detail": "CSRF token set in cookie",
        "csrf_token": csrf_token  # Also return in body for convenience
    }


@router.get("/me", response_model=Principal)
@limiter.limit(lambda: settings.rate_limit_api_read)
async def get_current_user_info(
    request: Request,
    principal: Principal = Depends(get_principal)
) -> Principal:
    """
    Get current identity and authorization role.

    Requires valid authentication. The ``role`` (admin/viewer) lets the dashboard
    show or hide mutating actions.
    Rate limited to 60 requests per minute.
    """
    return principal
