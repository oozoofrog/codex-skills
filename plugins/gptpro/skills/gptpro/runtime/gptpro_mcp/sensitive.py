"""Shared secret-like detectors for package preparation and runtime audit paths."""

from __future__ import annotations

import re

OPENAI_TUNNEL_ID_TEXT = r"tunnel_[a-z0-9]{32}"
OPENAI_TUNNEL_ID = re.compile(OPENAI_TUNNEL_ID_TEXT)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("openai-tunnel-id", re.compile(rf"\b{OPENAI_TUNNEL_ID_TEXT}\b")),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|auth[_-]?token)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=:-]{12,}"
        ),
    ),
)


def secret_detector_names(text: str) -> tuple[str, ...]:
    """Return stable detector names without retaining or echoing matched values."""

    return tuple(name for name, pattern in SECRET_PATTERNS if pattern.search(text))
