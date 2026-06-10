"""
Security headers middleware.

Adds security-related HTTP headers to all responses:
- Content-Security-Policy (CSP)
- X-Frame-Options
- X-Content-Type-Options
- Strict-Transport-Security (HSTS) in production
- X-XSS-Protection
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.

    This middleware adds essential security headers to protect against
    common web vulnerabilities including XSS, clickjacking, and MIME sniffing.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and add security headers to the response.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            Response with security headers added
        """
        response: Response = await call_next(request)

        # Content Security Policy
        # Restricts sources from which content can be loaded
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )

        # Prevent clickjacking by disallowing iframe embedding
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        # Forces browser to respect declared Content-Type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # HTTP Strict Transport Security (HSTS)
        # Force HTTPS for 1 year (production only)
        if settings.environment == "prod":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # XSS protection for legacy browsers
        # Modern browsers use CSP instead
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Limit referrer leakage to third parties
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Deny powerful browser features the dashboard never needs
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response
