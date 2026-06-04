"""
Authentication routes.

Endpoints for login and user information.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from .dependencies import get_current_user
from .jwt import create_access_token, verify_admin_credentials
from .models import TokenResponse, User, UserLogin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin) -> TokenResponse:
    """
    Login endpoint.

    Verify credentials and return JWT access token.

    Args:
        credentials: Username and password

    Returns:
        JWT access token

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Verify credentials
    if not verify_admin_credentials(credentials.username, credentials.password):
        logger.warning(f"Failed login attempt: username={credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": credentials.username})

    logger.info(f"Successful login: username={credentials.username}")

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=User)
async def get_current_user_info(user: User = Depends(get_current_user)) -> User:
    """
    Get current user information.

    Requires valid JWT token.

    Args:
        user: Current authenticated user (from dependency)

    Returns:
        Current user information
    """
    return user
