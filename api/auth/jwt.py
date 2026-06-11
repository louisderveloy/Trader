"""
JWT token utilities.

Handles JWT token encoding, decoding, and verification.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against hashed password.

    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hashed password

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hashed password
    """
    return pwd_context.hash(password)


def create_access_token(
    data: dict[str, str], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token.

    Args:
        data: Data to encode in token (e.g., {"sub": username})
        expires_delta: Optional custom expiration delta

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    # Encode JWT
    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict[str, str]]:
    """
    Decode and verify JWT access token.

    Args:
        token: JWT token to decode

    Returns:
        Decoded token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


def verify_admin_credentials(username: str, password: str) -> bool:
    """
    Verify admin username and password.

    Args:
        username: Username to verify
        password: Plain text password to verify

    Returns:
        True if credentials match admin user, False otherwise
    """
    # Check username
    if username != settings.admin_username:
        return False

    # Prefer the bcrypt hash when configured (recommended; see ADMIN_PASSWORD_HASH
    # in .env.example for how to generate it). Falls back to a constant-time plain
    # comparison only when no hash is set (dev convenience).
    if settings.admin_password_hash:
        return verify_password(password, settings.admin_password_hash)

    return secrets.compare_digest(password, settings.admin_password)
