"""Stable, non-sensitive errors for the read-only MCP runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError(Exception):
    """A model-visible domain failure with a stable recovery contract."""

    code: str
    message: str
    retryable: bool = False
    recovery: str = "Start a new approved gptpro session if the problem persists."
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.code

    def envelope(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "recovery": self.recovery,
        }
        if self.details:
            error["details"] = dict(self.details)
        return error


class CancelledError(Exception):
    """Internal signal: cancellation won before disclosure was committed."""


def invalid_argument(message: str = "The tool arguments are invalid.") -> ToolError:
    return ToolError(
        "MCP_INVALID_ARGUMENT",
        message,
        retryable=True,
        recovery="Correct the arguments using the published tool input schema and retry.",
    )


def archive_invalid(code: str = "ARCHIVE_MEMBER_INVALID") -> ToolError:
    messages = {
        "ARCHIVE_LIMIT_EXCEEDED": "The immutable package archive exceeds a safety limit.",
        "CONTENT_DRIFT": "The immutable package bytes no longer match their approved hashes.",
        "PACKAGE_TAMPERED": "The approved package integrity check failed.",
    }
    return ToolError(
        code,
        messages.get(code, "The immutable package archive is invalid."),
        recovery="Revoke this session and prepare a new approved package.",
    )
