"""
Secret redaction for logs.

Run logs are written to a per-run file on a volume that is mounted read-only
into the API container and surfaced through ``GET /runs/{id}/logs``. To keep
secrets (Binance keys, the DB DSN, the Discord webhook) from ever reaching that
endpoint, this filter scrubs known secret shapes from every log record before it
is emitted (security review Finding #8).

It is a defense-in-depth net, not a licence to log secrets — code should still
avoid logging them in the first place.
"""

import logging
import re

# Each pattern captures a leading group to keep (e.g. the key name) and replaces
# the sensitive remainder with a placeholder.
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # key=value / "key": "value" forms for common secret-bearing names
    (re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|secret|password|passwd|token|webhook)"
        r"(\s*[:=]\s*|\"\s*:\s*\"?)([^\s,;\"']+)"
    ), r"\1\2***"),
    # Postgres DSN with embedded credentials
    (re.compile(r"(postgresql(?:\+asyncpg)?://)[^@\s]+@"), r"\1***@"),
    # Discord webhook URLs
    (re.compile(r"(https://discord(?:app)?\.com/api/webhooks/)\S+"), r"\1***"),
]

_PLACEHOLDER = "***REDACTED***"


def redact(text: str) -> str:
    """Return ``text`` with known secret shapes masked."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Logging filter that masks secrets in the fully-rendered message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_secret_redaction(root: logging.Logger | None = None) -> None:
    """Attach :class:`SecretRedactionFilter` to the root logger's handlers.

    Idempotent: safe to call multiple times.
    """
    root = root or logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
            handler.addFilter(SecretRedactionFilter())
