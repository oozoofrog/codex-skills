"""Secret and path screening for Schema-6 inline immutable snapshots."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|auth[_-]?token)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=:-]{12,}"
        ),
    ),
)

SECRET_PATH_PARTS = {
    ".env",
    ".aws",
    ".ssh",
    ".gnupg",
    "credentials",
    "secrets",
    "private_keys",
    "node_modules",
    ".git",
    ".gptpro",
}

SECRET_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".mobileprovision",
    ".keystore",
}


def secret_detectors(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in SECRET_PATTERNS if pattern.search(text))


def unsafe_path_reason(path: str) -> str | None:
    candidate = PurePosixPath(path)
    folded = {part.casefold() for part in candidate.parts}
    if folded & {item.casefold() for item in SECRET_PATH_PARTS}:
        return "secret-path"
    if candidate.suffix.casefold() in SECRET_SUFFIXES:
        return "secret-suffix"
    if candidate.name.casefold().startswith(".env"):
        return "environment-file"
    return None
