"""
Simple CSRF protection helper.

Uses double-submit cookie pattern:
1. Server generates a random token and sets it in a readable cookie
2. Client reads the cookie and sends it in the X-CSRF-Token header
3. Server validates that the cookie value matches the header value

Note: With httpOnly session cookies and SameSite=strict, CSRF is already
largely mitigated, but this provides defense in depth.
"""

import hmac

from fastapi import HTTPException, Request, status


async def validate_csrf_token(request: Request) -> None:
    """
    Validate CSRF token from double-submit cookie pattern.

    Checks that the CSRF token in the cookie matches the token in the header.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 403 if CSRF validation fails
    """
    # Get CSRF token from cookie
    cookie_token = request.cookies.get("csrf_access_token")

    # Get CSRF token from header
    header_token = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")

    # Both must be present and match
    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing"
        )

    # Constant-time comparison to avoid leaking the token via timing.
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed"
        )
