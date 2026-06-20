"""
Rate limiting configuration using slowapi.

This module creates the limiter instance that can be imported and used
as a decorator across all route modules.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import settings


def client_ip_key_func(request: Request) -> str:
    """Rate-limit key = the real client IP, not Traefik's internal Docker IP.

    Behind Traefik the TCP peer is always Traefik, so ``get_remote_address``
    would put every client in one bucket (security review #15). Traefik appends
    the true peer to X-Forwarded-For (default ``notAppendXForwardedFor=false``)
    and, with empty ``trustedIPs``/no ``insecure``, does NOT trust a
    client-supplied XFF — so the **rightmost** entry is the IP Traefik observed
    and cannot be spoofed by the client prepending forged values.

    Assumes exactly one trusted proxy hop (Traefik). If a CDN is ever put in
    front, the client IP shifts left and this must count more hops from the
    right. No XFF (dev / no proxy) falls back to the socket peer.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        client = xff.split(",")[-1].strip()
        if client:
            return client
    return get_remote_address(request)


# Create limiter instance
# This will be used as a decorator on route functions
limiter = Limiter(
    key_func=client_ip_key_func,
    enabled=settings.rate_limit_enabled
)
