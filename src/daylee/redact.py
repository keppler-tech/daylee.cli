"""Client-side secret redaction for prompt digests.

Mirrored on the server in code/app/services/claude_code/redact.py — both
sides apply the same patterns as defence in depth.
"""

from __future__ import annotations

import re


_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "[REDACTED-GITHUB-PAT]"),
    (re.compile(r"\bxox[bpoasr]-[A-Za-z0-9-]+"), "[REDACTED-SLACK-TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "[REDACTED-SECRET-KEY]"),
    (re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"), "[REDACTED-SECRET-KEY]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED-JWT]",
    ),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED-PRIVATE-KEY]",
    ),
]


_MAX_DIGEST_BYTES = 2048


def redact_text(text: str | None) -> str | None:
    if not text:
        return text
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    encoded = redacted.encode("utf-8", errors="ignore")
    if len(encoded) > _MAX_DIGEST_BYTES:
        encoded = encoded[:_MAX_DIGEST_BYTES]
        redacted = encoded.decode("utf-8", errors="ignore") + "…"
    return redacted


def is_env_path(path: str) -> bool:
    """Heuristic — any path that looks like a secrets file."""
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    if name.startswith(".env") or name.endswith(".env"):
        return True
    if name.startswith("secrets.") or name.startswith("secret."):
        return True
    return False
