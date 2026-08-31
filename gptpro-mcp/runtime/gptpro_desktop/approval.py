"""Machine-global, bounded standing approval for Desktop read-only consultations."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .state import (
    DesktopStateError,
    list_private_json,
    platform_state_root,
    read_private_json,
    secure_directory,
    write_private_json,
)

DESKTOP_APPROVAL_CONTRACT = "gptpro-standing-approval-v2"
DESKTOP_APPROVAL_SCHEMA_VERSION = 2
APPROVAL_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
ALLOWED_MODES = ("plan", "ask", "review", "debug", "architecture")
DEFAULT_VALIDITY_SECONDS = 7 * 24 * 3600
MAX_VALIDITY_SECONDS = 30 * 24 * 3600


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", f"{label} is invalid.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", f"{label} is invalid.") from exc
    if result.tzinfo is None:
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", f"{label} is invalid.")
    return result.astimezone(timezone.utc)


def desktop_approval_digest(profile: dict[str, Any]) -> str:
    return _sha256(_canonical_bytes({k: v for k, v in profile.items() if k != "profile_sha256"}))


def build_desktop_approval(
    *,
    name: str,
    approved_by: str,
    source: dict[str, str],
    connector: dict[str, Any],
    requested_model: str,
    allowed_modes: list[str],
    path_patterns: list[str],
    allow_dirty: bool,
    limits: dict[str, Any],
    valid_for_seconds: int = DEFAULT_VALIDITY_SECONDS,
) -> dict[str, Any]:
    if APPROVAL_NAME.fullmatch(name) is None:
        raise DesktopStateError(
            "DESKTOP_APPROVAL_NAME_INVALID", "Approval names must use lowercase safe characters."
        )
    if not approved_by.strip() or len(approved_by) > 128:
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The approving user is invalid.")
    if not 300 <= valid_for_seconds <= MAX_VALIDITY_SECONDS:
        raise DesktopStateError(
            "DESKTOP_APPROVAL_INVALID", "Approval validity must be between 5 minutes and 30 days."
        )
    modes = sorted(set(allowed_modes or ALLOWED_MODES))
    if not modes or any(mode not in ALLOWED_MODES for mode in modes):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "Allowed modes are invalid.")
    patterns = sorted(set(path_patterns or ["**"]))
    if not patterns or any(
        not pattern or pattern.startswith("/") or ".." in Path(pattern).parts
        for pattern in patterns
    ):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "Allowed path patterns are invalid.")
    if set(source) != {"package_id", "manifest_sha256", "approval_event_sha256"}:
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The source approval binding is invalid.")
    if any(not isinstance(source[key], str) or not source[key] for key in source):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The source approval binding is invalid.")
    created = _now()
    profile = {
        "schema_version": DESKTOP_APPROVAL_SCHEMA_VERSION,
        "contract": DESKTOP_APPROVAL_CONTRACT,
        "name": name,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "valid_until": (created + timedelta(seconds=valid_for_seconds))
        .isoformat()
        .replace("+00:00", "Z"),
        "revoked_at": None,
        "approved_by": approved_by.strip(),
        "source": dict(source),
        "scope": {
            "repository_scope": "all-local-git",
            "transport": "mcp-research",
            "delivery_channel": "desktop-ui",
            "connector_type": "secure-mcp-tunnel",
            "tunnel_profile_alias": connector.get("tunnel_profile_alias"),
            "tunnel_profile_sha256": connector.get("tunnel_profile_sha256"),
            "app_name": connector.get("app_name"),
            "workspace_label": connector.get("workspace_label"),
            "requested_model": requested_model,
            "allowed_modes": modes,
            "path_patterns": patterns,
            "allow_dirty": bool(allow_dirty),
            "external_artifacts_allowed": False,
            "limits": limits,
        },
    }
    profile["profile_sha256"] = desktop_approval_digest(profile)
    return validate_desktop_approval(profile, expected_name=name)


def validate_desktop_approval(
    profile: Any, *, expected_name: str | None = None
) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The approval is not a JSON object.")
    expected = {
        "schema_version",
        "contract",
        "name",
        "created_at",
        "valid_until",
        "revoked_at",
        "approved_by",
        "source",
        "scope",
        "profile_sha256",
    }
    name = profile.get("name")
    if (
        set(profile) != expected
        or profile.get("schema_version") != DESKTOP_APPROVAL_SCHEMA_VERSION
        or profile.get("contract") != DESKTOP_APPROVAL_CONTRACT
        or not isinstance(name, str)
        or APPROVAL_NAME.fullmatch(name) is None
        or (expected_name is not None and name != expected_name)
        or profile.get("profile_sha256") != desktop_approval_digest(profile)
    ):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The approval identity or hash is invalid.")
    created = _parse_time(profile.get("created_at"), "Approval creation time")
    expiry = _parse_time(profile.get("valid_until"), "Approval expiry")
    if not timedelta(seconds=300) <= expiry - created <= timedelta(
        seconds=MAX_VALIDITY_SECONDS
    ):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The approval lifetime is invalid.")
    if profile.get("revoked_at") is not None:
        _parse_time(profile.get("revoked_at"), "Approval revocation time")
    scope = profile.get("scope")
    if not isinstance(scope, dict) or scope.get("repository_scope") != "all-local-git":
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The repository scope is invalid.")
    if (
        scope.get("transport") != "mcp-research"
        or scope.get("delivery_channel") != "desktop-ui"
        or scope.get("connector_type") != "secure-mcp-tunnel"
        or scope.get("external_artifacts_allowed") is not False
        or type(scope.get("allow_dirty")) is not bool
    ):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The disclosure scope is invalid.")
    modes = scope.get("allowed_modes")
    patterns = scope.get("path_patterns")
    limits = scope.get("limits")
    if (
        not isinstance(modes, list)
        or not modes
        or any(mode not in ALLOWED_MODES for mode in modes)
        or not isinstance(patterns, list)
        or not patterns
        or not isinstance(limits, dict)
    ):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "The bounded disclosure rules are invalid.")
    return profile


def approval_directory(state_root: Path | None = None) -> Path:
    return (state_root or platform_state_root()) / "standing-approvals"


def store_desktop_approval(
    profile: dict[str, Any], *, state_root: Path | None = None
) -> Path:
    checked = validate_desktop_approval(profile)
    directory = approval_directory(state_root)
    secure_directory(directory, create=True)
    path = directory / f"{checked['name']}.json"
    if path.exists():
        raise DesktopStateError(
            "DESKTOP_APPROVAL_ALREADY_EXISTS", "Revoke the existing approval or choose a new name."
        )
    write_private_json(path, checked)
    return path


def load_desktop_approval(
    name: str, *, state_root: Path | None = None
) -> dict[str, Any]:
    if APPROVAL_NAME.fullmatch(name) is None:
        raise DesktopStateError("DESKTOP_APPROVAL_NAME_INVALID", "The approval name is invalid.")
    return validate_desktop_approval(
        read_private_json(approval_directory(state_root) / f"{name}.json"),
        expected_name=name,
    )


def list_desktop_approvals(*, state_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        records = list_private_json(approval_directory(state_root))
    except DesktopStateError as exc:
        if exc.code == "DESKTOP_STATE_NOT_FOUND":
            return []
        raise
    return [validate_desktop_approval(value, expected_name=name[:-5]) for name, value in records]


def revoke_desktop_approval(
    name: str, *, state_root: Path | None = None
) -> dict[str, Any]:
    profile = load_desktop_approval(name, state_root=state_root)
    if profile.get("revoked_at") is None:
        profile["revoked_at"] = _now().isoformat().replace("+00:00", "Z")
        profile["profile_sha256"] = desktop_approval_digest(profile)
        write_private_json(approval_directory(state_root) / f"{name}.json", profile)
    return validate_desktop_approval(profile, expected_name=name)


def _at_most(actual: Any, maximum: Any) -> bool:
    return (
        not isinstance(actual, bool)
        and isinstance(actual, int)
        and not isinstance(maximum, bool)
        and isinstance(maximum, int)
        and actual <= maximum
    )


def match_desktop_approval(
    profile: dict[str, Any], *, manifest: dict[str, Any]
) -> dict[str, Any]:
    checked = validate_desktop_approval(profile)
    if checked.get("revoked_at") is not None:
        raise DesktopStateError("DESKTOP_APPROVAL_REVOKED", "The standing approval is revoked.")
    if _parse_time(checked["valid_until"], "Approval expiry") <= _now():
        raise DesktopStateError("DESKTOP_APPROVAL_EXPIRED", "The standing approval has expired.")
    scope = checked["scope"]
    connector = manifest.get("connector", {})
    disclosure = manifest.get("mcp_disclosure", {})
    if (
        manifest.get("schema_version") != 4
        or manifest.get("transport", {}).get("resolved") != "mcp-research"
        or manifest.get("delivery", {}).get("channel") != "desktop-ui"
        or manifest.get("mode") not in scope["allowed_modes"]
        or manifest.get("requested_model") != scope["requested_model"]
        or connector.get("type") != scope["connector_type"]
        or connector.get("tunnel_profile_alias") != scope["tunnel_profile_alias"]
        or connector.get("tunnel_profile_sha256") != scope["tunnel_profile_sha256"]
        or connector.get("app_name") != scope["app_name"]
        or connector.get("workspace_label") != scope["workspace_label"]
        or manifest.get("supplements")
    ):
        raise DesktopStateError(
            "DESKTOP_APPROVAL_SCOPE_MISMATCH", "The package is outside the standing approval scope."
        )
    dirty = manifest.get("git", {}).get("dirty_paths")
    if dirty and not scope["allow_dirty"]:
        raise DesktopStateError(
            "DESKTOP_APPROVAL_DIRTY_REPOSITORY", "The standing approval excludes dirty repositories."
        )
    selected_paths = {
        entry.get("path") for entry in manifest.get("files", []) if isinstance(entry, dict)
    }
    if any(
        isinstance(item, dict)
        and item.get("status") == "??"
        and item.get("path") in selected_paths
        for item in (dirty or [])
    ):
        raise DesktopStateError(
            "DESKTOP_APPROVAL_UNTRACKED_FILE",
            "Machine-global standing approval never authorizes selected untracked files.",
        )
    for entry in manifest.get("files", []):
        path = entry.get("path")
        if not isinstance(path, str) or not any(
            fnmatch.fnmatchcase(path, pattern) for pattern in scope["path_patterns"]
        ):
            raise DesktopStateError(
                "DESKTOP_APPROVAL_PATH_MISMATCH", "A selected path is outside the standing approval."
            )
    limits = scope["limits"]
    totals = manifest.get("totals", {})
    package_limits = manifest.get("limits", {})
    comparisons = {
        "max_files": totals.get("included_files"),
        "max_bytes": totals.get("included_bytes"),
        "max_file_bytes": package_limits.get("max_file_bytes"),
        "max_task_bytes": len(str(manifest.get("task", "")).encode("utf-8")),
    }
    if any(not _at_most(value, limits.get(key)) for key, value in comparisons.items()):
        raise DesktopStateError(
            "DESKTOP_APPROVAL_BUDGET_EXCEEDED", "The package exceeds the standing approval budget."
        )
    approved_mcp = limits.get("mcp_limits")
    actual_mcp = disclosure.get("limits")
    if not isinstance(approved_mcp, dict) or not isinstance(actual_mcp, dict):
        raise DesktopStateError("DESKTOP_APPROVAL_INVALID", "MCP limits are missing.")
    if any(not _at_most(value, approved_mcp.get(key)) for key, value in actual_mcp.items()):
        raise DesktopStateError(
            "DESKTOP_APPROVAL_BUDGET_EXCEEDED", "The MCP disclosure exceeds the standing approval."
        )
    return {
        "contract": DESKTOP_APPROVAL_CONTRACT,
        "name": checked["name"],
        "profile_sha256": checked["profile_sha256"],
        "approved_by": checked["approved_by"],
        "valid_until": checked["valid_until"],
        "repository_scope": "all-local-git",
    }
