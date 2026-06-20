"""
Tests for the rate-limit client-IP key function (security review #15).

Behind Traefik the socket peer is Traefik, so the limiter must derive the real
client IP from X-Forwarded-For. The rightmost entry is the IP Traefik appended
(the true peer); a client prepending a forged IP must NOT be able to move its
own bucket.

Run with the API deps installed; not collected by the bot ``tests/`` suite.
"""

from starlette.requests import Request

from api.limiter import client_ip_key_func


def _request(headers: dict[str, str] | None = None, client_host: str = "172.20.0.5") -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_no_xff_falls_back_to_peer() -> None:
    # Dev / no proxy: use the socket peer.
    assert client_ip_key_func(_request(client_host="10.0.0.9")) == "10.0.0.9"


def test_single_xff_entry() -> None:
    assert client_ip_key_func(_request({"X-Forwarded-For": "5.6.7.8"})) == "5.6.7.8"


def test_spoofed_prefix_cannot_move_bucket() -> None:
    # Client sends "1.1.1.1"; Traefik appends the real peer 5.6.7.8 on the right.
    # The key MUST be the rightmost (real) IP, never the client-controlled left.
    key = client_ip_key_func(_request({"X-Forwarded-For": "1.1.1.1, 5.6.7.8"}))
    assert key == "5.6.7.8"
    assert key != "1.1.1.1"


def test_malformed_trailing_comma_falls_back() -> None:
    # A trailing comma yields an empty rightmost token; don't bucket everyone
    # under "" — fall back to the socket peer.
    key = client_ip_key_func(_request({"X-Forwarded-For": "1.2.3.4,"}, client_host="10.0.0.7"))
    assert key == "10.0.0.7"
