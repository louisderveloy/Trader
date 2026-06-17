"""
Authentication Pydantic models.

Request/response models for authentication endpoints.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    """Authorization role.

    - ``admin``: may start/stop/kill runs and perform all mutations.
    - ``viewer``: read-only access (list runs, view logs, view data).

    Any authenticated identity that maps to neither role is denied access
    entirely (handled in the resolver, never represented here).
    """

    ADMIN = "admin"
    VIEWER = "viewer"


class Principal(BaseModel):
    """Authenticated identity plus its resolved authorization role.

    Produced by ``get_principal`` regardless of auth mode (local JWT cookie or,
    in the future, Authelia OIDC), so route guards never depend on the source.
    """

    username: str = Field(..., description="Identity username/subject (the OIDC sub)")
    display_name: Optional[str] = Field(
        None, description="Human-friendly name for display (preferred_username/name)"
    )
    email: Optional[str] = Field(None, description="Email if available")
    role: Role = Field(..., description="Resolved authorization role")


class UserLogin(BaseModel):
    """Login request model."""

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class TokenResponse(BaseModel):
    """Token response model (deprecated - use LoginResponse with httpOnly cookies)."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class LoginResponse(BaseModel):
    """Login response model (token set in httpOnly cookie)."""

    message: str = Field(..., description="Login status message")
    username: str = Field(..., description="Logged in username")


class User(BaseModel):
    """User model."""

    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="Email address")

    class Config:
        """Pydantic config."""

        from_attributes = True
