"""
Authentication module.

JWT-based authentication for the API with bcrypt password hashing.
"""

from .dependencies import get_current_user
from .models import TokenResponse, User, UserLogin

__all__ = ["get_current_user", "TokenResponse", "User", "UserLogin"]
