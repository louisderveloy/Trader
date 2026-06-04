"""
Authentication Pydantic models.

Request/response models for authentication endpoints.
"""

from pydantic import BaseModel, EmailStr, Field


class UserLogin(BaseModel):
    """Login request model."""

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class User(BaseModel):
    """User model."""

    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="Email address")

    class Config:
        """Pydantic config."""

        from_attributes = True
