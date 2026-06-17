"""
Authentication module.

JWT-based authentication for the API with bcrypt password hashing.
"""

from .dependencies import (
    get_current_user,
    get_principal,
    require_admin,
    require_role,
    require_viewer,
)
from .models import Principal, Role, TokenResponse, User, UserLogin

__all__ = [
    "get_current_user",
    "get_principal",
    "require_admin",
    "require_viewer",
    "require_role",
    "Principal",
    "Role",
    "TokenResponse",
    "User",
    "UserLogin",
]
