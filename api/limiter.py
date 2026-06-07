"""
Rate limiting configuration using slowapi.

This module creates the limiter instance that can be imported and used
as a decorator across all route modules.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

# Create limiter instance
# This will be used as a decorator on route functions
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled
)
