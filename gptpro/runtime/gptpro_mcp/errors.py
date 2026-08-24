"""Stable, non-sensitive errors for the bounded repository MCP runtime."""

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


class UnknownToolError(ToolError):
    """A well-formed tool name that is absent from the advertised catalog."""


class CommitOutcomeUncertainError(ToolError):
    """An internal fail-closed signal after an audit append may have committed.

    The counters are deliberately attributes rather than model-visible details.
    They let the single-session executor reconcile its volatile budget without
    exposing request identifiers or audit record hashes on the wire.
    """

    def __init__(
        self,
        *,
        calls_used: int | None,
        disclosed_bytes: int | None,
    ) -> None:
        super().__init__(
            "COMMIT_OUTCOME_UNCERTAIN",
            "The disclosure audit may have committed, but the complete commit outcome is unavailable.",
            retryable=False,
            recovery="Stop this session, verify its audit, and activate a new approved package.",
        )
        self.committed_calls_used = calls_used
        self.committed_disclosed_bytes = disclosed_bytes


def invalid_argument(message: str = "The tool arguments are invalid.") -> ToolError:
    return ToolError(
        "MCP_INVALID_ARGUMENT",
        message,
        retryable=True,
        recovery="Correct the arguments using the published tool input schema and retry.",
    )


def unknown_tool() -> UnknownToolError:
    return UnknownToolError(
        "MCP_INVALID_ARGUMENT",
        "The requested tool name is not in the approved static catalog.",
        retryable=True,
        recovery="Choose a tool from the published tools/list catalog and retry.",
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
