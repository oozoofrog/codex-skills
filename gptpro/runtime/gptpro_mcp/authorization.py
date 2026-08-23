"""Injected authorization boundary for the archive-only MCP core.

Phase 2 intentionally owns no user-global state.  Phase 3 supplies an
AuthorizationProvider that revalidates the active approval on every call.
"""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .errors import ToolError
from .schema import PROTOCOL_PROFILE, tool_schema_sha256, validate_limits

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AuthorizationGrant:
    """One already-approved package capability supplied by a trusted layer."""

    package_id: str
    manifest: dict[str, Any]
    archive_path: Path
    archive_sha256: str
    manifest_sha256: str
    session_id_sha256: str
    session_nonce: bytes
    expires_at: datetime
    idle_expires_at: datetime
    approved: bool = True
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", copy.deepcopy(self.manifest))
        object.__setattr__(self, "archive_path", Path(self.archive_path))
        if not isinstance(self.package_id, str) or not 1 <= len(self.package_id) <= 128:
            raise ValueError("package_id is invalid")
        for name, value in (
            ("archive_sha256", self.archive_sha256),
            ("manifest_sha256", self.manifest_sha256),
            ("session_id_sha256", self.session_id_sha256),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError(f"{name} is invalid")
        if not isinstance(self.session_nonce, bytes) or len(self.session_nonce) < 32:
            raise ValueError("session_nonce must contain at least 32 random bytes")
        if self.expires_at.tzinfo is None or self.idle_expires_at.tzinfo is None:
            raise ValueError("authorization expiry values must be timezone-aware")
        if self.idle_expires_at > self.expires_at:
            raise ValueError("idle expiry must not exceed session expiry")

    @property
    def limits(self) -> dict[str, int]:
        disclosure = self.manifest.get("mcp_disclosure")
        if not isinstance(disclosure, dict):
            raise ToolError(
                "PACKAGE_TAMPERED",
                "The approved package disclosure contract is missing.",
                recovery="Revoke this session and prepare a new approved package.",
            )
        try:
            return validate_limits(disclosure.get("limits"))
        except (TypeError, ValueError) as exc:
            raise ToolError(
                "PACKAGE_TAMPERED",
                "The approved package limits are invalid.",
                recovery="Revoke this session and prepare a new approved package.",
            ) from exc

    def validate(self, requested_package_id: str, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        if not self.active:
            raise ToolError(
                "NO_ACTIVE_PACKAGE",
                "No approved repository package is active.",
                recovery="Activate the exact approved package before calling content tools.",
            )
        if requested_package_id != self.package_id:
            raise ToolError(
                "PACKAGE_MISMATCH",
                "The requested package is not the active approved package.",
                recovery="Use package_info with the active approved package ID.",
            )
        if not self.approved:
            raise ToolError(
                "PACKAGE_NOT_APPROVED",
                "The repository package has not been approved for MCP disclosure.",
                recovery="Obtain package-specific approval before activation.",
            )
        if current >= self.expires_at:
            raise ToolError(
                "SESSION_EXPIRED",
                "The approved package session has expired.",
                recovery="Stop this session and activate a newly approved package.",
            )
        if current >= self.idle_expires_at:
            raise ToolError(
                "IDLE_TIMEOUT",
                "The approved package session reached its idle timeout.",
                recovery="Stop this session and activate a newly approved package.",
            )
        manifest = self.manifest
        transport = manifest.get("transport")
        delivery = manifest.get("delivery")
        connector = manifest.get("connector")
        if manifest.get("schema_version") != 3 or manifest.get("package_id") != self.package_id:
            raise ToolError(
                "SCHEMA_VERSION_UNSUPPORTED",
                "The active package is not a schema-3 MCP package.",
                recovery="Prepare a new package with explicit mcp-read transport.",
            )
        if not isinstance(transport, dict) or (
            transport.get("requested"), transport.get("resolved")
        ) != ("mcp-read", "mcp-read"):
            raise ToolError(
                "CHANNEL_NOT_APPROVED",
                "The package was not approved for mcp-read transport.",
                recovery="Prepare and approve a new explicit mcp-read package.",
            )
        if delivery != {"channel": "browser", "approval_required": True}:
            raise ToolError(
                "CHANNEL_NOT_APPROVED",
                "The package browser delivery channel is not approved.",
                recovery="Prepare and approve a package for the browser delivery channel.",
            )
        if not isinstance(connector, dict) or (
            connector.get("type") != "secure-mcp-tunnel"
            or connector.get("protocol_profile") != PROTOCOL_PROFILE
        ):
            raise ToolError(
                "CONNECTOR_NOT_APPROVED",
                "The package connector does not match the Secure MCP Tunnel profile.",
                recovery="Prepare and approve a package for this connector profile.",
            )
        if connector.get("tool_schema_sha256") != tool_schema_sha256():
            raise ToolError(
                "TOOL_SCHEMA_MISMATCH",
                "The approved tool catalog differs from this runtime.",
                recovery="Refresh the runtime and prepare a new package.",
            )
        self.limits


class AuthorizationProvider(Protocol):
    """Phase-3 integration point; implementations must fail closed."""

    def resolve(self, package_id: str) -> AuthorizationGrant:
        """Return and revalidate the one active grant for package_id."""


class DenyAllAuthorizationProvider:
    """Safe default for a server started before lifecycle integration exists."""

    def resolve(self, package_id: str) -> AuthorizationGrant:
        del package_id
        raise ToolError(
            "NO_ACTIVE_PACKAGE",
            "No approved repository package is active.",
            recovery="Activate the exact approved package before calling content tools.",
        )


class StaticAuthorizationProvider:
    """Deterministic injection helper for unit and compatibility fixtures only."""

    def __init__(self, grant: AuthorizationGrant | None = None) -> None:
        self._lock = threading.Lock()
        self._grant = grant

    def replace(self, grant: AuthorizationGrant | None) -> None:
        with self._lock:
            self._grant = grant

    def resolve(self, package_id: str) -> AuthorizationGrant:
        with self._lock:
            grant = self._grant
        if grant is None:
            return DenyAllAuthorizationProvider().resolve(package_id)
        grant.validate(package_id)
        return grant
