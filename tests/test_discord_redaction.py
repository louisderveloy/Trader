"""
Regression tests for Discord webhook secret redaction (security review #13).

httpx exceptions embed the request URL — which contains the webhook token — in
their string form. DiscordNotifier.send() must redact that before logging, while
still keeping the Discord response body (response.text) for debugging.
"""

import asyncio
import logging

import httpx
import pytest

from notifications.discord import DiscordNotifier, NotificationType

_WEBHOOK = "https://discord.com/api/webhooks/123456789/SuperSecretTokenABCDEF"
_TOKEN = "SuperSecretTokenABCDEF"


def _notifier() -> DiscordNotifier:
    # db_pool unused on the send() logging path; rate_limit 0 skips the sleep.
    return DiscordNotifier(webhook_url=_WEBHOOK, db_pool=None, rate_limit_seconds=0)


def test_exception_url_token_is_redacted(caplog) -> None:
    notifier = _notifier()

    class _FakeClient:
        async def post(self, url, json=None):
            # httpx errors include the URL (with token) in their message.
            raise httpx.ConnectError(f"connection failed for url '{url}'")

    async def _fake_get_client():
        return _FakeClient()

    notifier._get_client = _fake_get_client

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(notifier.send("hello", NotificationType.INFO))

    assert result is False
    assert _TOKEN not in caplog.text
    assert "discord.com/api/webhooks/" in caplog.text  # url shape kept, token masked
    assert "***" in caplog.text


def test_response_text_is_kept_but_no_token(caplog) -> None:
    notifier = _notifier()

    class _Resp:
        status_code = 401
        text = '{"message": "Unknown Webhook", "code": 10015}'

    class _FakeClient:
        async def post(self, url, json=None):
            return _Resp()

    async def _fake_get_client():
        return _FakeClient()

    notifier._get_client = _fake_get_client

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(notifier.send("hello", NotificationType.INFO))

    assert result is False
    # response.text is retained for debugging...
    assert "Unknown Webhook" in caplog.text
    # ...and the token never appears.
    assert _TOKEN not in caplog.text
