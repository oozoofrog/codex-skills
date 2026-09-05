"""Exact and bounded standing approvals for Desktop Electron disclosure."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .package import PackageError, _matches, verify_package
from .receipts import ReceiptError, append_receipt, load_receipt
from .schema import CHAT_HISTORY_MODE, DELIVERY_CHANNEL, INLINE_FORMAT, MAX_OUTBOUND_BYTES
from .state import package_lock, read_json, secure_directory, sha256_file, state_root, write_json


class ApprovalError(Exception):
    def __init__(self, code: str, message: str, *, recovery: str = "Obtain a new approval for the exact displayed scope.") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False
        self.recovery = recovery


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def load_state(handoff: Path, package_id: str) -> dict[str, Any]:
    try:
        value = read_json(handoff / "state.json")
    except Exception as exc:
        raise ApprovalError("STATE_INVALID", "The package state cannot be verified.") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 6 or value.get("package_id") != package_id:
        raise ApprovalError("STATE_INVALID", "The package state identity differs.")
    return value


def save_state(handoff: Path, state: dict[str, Any]) -> None:
    expected_revision = state.get("revision")
    if not isinstance(expected_revision, int) or expected_revision < 1:
        raise ApprovalError("STATE_INVALID", "The package state revision is invalid.")
    current = load_state(handoff, str(state.get("package_id", "")))
    if current.get("revision") != expected_revision:
        raise ApprovalError(
            "STATE_REVISION_CONFLICT",
            "The package state changed concurrently; the stale update was rejected.",
            recovery="Re-read the package state. Do not retry a submission whose dispatch status is uncertain.",
        )
    state["revision"] = expected_revision + 1
    write_json(handoff / "state.json", state)


def approve_exact(
    handoff_value: Path,
    *,
    confirm_transmission: bool,
    confirm_disclosure: bool,
    expires_minutes: int = 120,
) -> dict[str, Any]:
    if not confirm_transmission or not confirm_disclosure:
        raise ApprovalError("APPROVAL_CONFIRMATION_REQUIRED", "Both transmission and maximum disclosure must be explicitly confirmed.")
    if not 1 <= expires_minutes <= 24 * 60:
        raise ApprovalError("APPROVAL_EXPIRY_INVALID", "Exact approval expiry must be between 1 minute and 24 hours.")
    initial = verify_package(handoff_value)
    handoff = Path(initial["handoff_dir"])
    with package_lock(handoff):
        verified = verify_package(handoff)
        manifest = verified["manifest"]
        if manifest.get("delivery", {}).get("chat_history_mode") != CHAT_HISTORY_MODE:
            raise ApprovalError(
                "CHAT_HISTORY_APPROVAL_REQUIRED",
                "This package does not match the current normal Chat disclosure contract.",
            )
        state = load_state(handoff, manifest["package_id"])
        if state.get("phase") not in {"prepared", "approved"}:
            raise ApprovalError("PACKAGE_PHASE_INVALID", "This package can no longer receive a new exact approval.")
        approval = {
            "type": "exact-package-v2",
            "recorded_at": timestamp(utc_now()),
            "expires_at": timestamp(utc_now() + timedelta(minutes=expires_minutes)),
            "manifest_sha256": verified["manifest_sha256"],
            "prompt_sha256": manifest["hashes"]["prompt_sha256"],
            "system_prompt_sha256": manifest["hashes"]["system_prompt_sha256"],
            "outbound_sha256": manifest["hashes"]["outbound_sha256"],
            "outbound_bytes": manifest["disclosure"]["outbound_bytes"],
            "model_intent": manifest["model_intent"],
            "channel": DELIVERY_CHANNEL,
            "chat_history_mode": CHAT_HISTORY_MODE,
            "inline_format": INLINE_FORMAT,
        }
        state["approval"] = approval
        state["phase"] = "approved"
        save_state(handoff, state)
        append_receipt(
            handoff / "receipt.json",
            manifest["package_id"],
            "approved",
            {
                "approval_type": approval["type"],
                "expires_at": approval["expires_at"],
                "manifest_sha256": approval["manifest_sha256"],
                "outbound_sha256": approval["outbound_sha256"],
                "outbound_bytes": approval["outbound_bytes"],
                "system_prompt_sha256": approval["system_prompt_sha256"],
                "model_intent": approval["model_intent"],
                "channel": approval["channel"],
                "chat_history_mode": CHAT_HISTORY_MODE,
                "inline_format": INLINE_FORMAT,
            },
        )
    return {"ok": True, "operation": "approve", "package_id": manifest["package_id"], "phase": "approved", "approval": approval}


def approvals_root(root: Path | None = None) -> Path:
    return secure_directory((root or state_root()) / "approvals")


def create_standing(
    handoff_value: Path,
    *,
    confirm_transmission: bool,
    confirm_disclosure: bool,
    expires_hours: int,
    modes: list[str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if not confirm_transmission or not confirm_disclosure:
        raise ApprovalError("APPROVAL_CONFIRMATION_REQUIRED", "Standing transmission and maximum disclosure must be explicitly confirmed.")
    if not 1 <= expires_hours <= 24 * 30:
        raise ApprovalError("APPROVAL_EXPIRY_INVALID", "Standing approval expiry must be between 1 hour and 30 days.")
    verified = verify_package(handoff_value)
    manifest = verified["manifest"]
    if manifest.get("delivery", {}).get("chat_history_mode") != CHAT_HISTORY_MODE:
        raise ApprovalError(
            "CHAT_HISTORY_APPROVAL_REQUIRED",
            "This package does not match the current normal Chat disclosure contract.",
        )
    allowed_modes = sorted(set(modes or [manifest["mode"]]))
    if not allowed_modes or any(value not in {"plan", "ask", "review", "debug", "architecture"} for value in allowed_modes):
        raise ApprovalError("APPROVAL_SCOPE_INVALID", "The standing approval mode scope is invalid.")
    now = utc_now()
    approval_id = f"desktop-v4-{now.strftime('%Y%m%dT%H%M%SZ')}-{manifest['repository']['root_sha256'][:12]}"
    selection = manifest["selection"]
    path_rules = {
        "include_patterns": list(selection.get("include_patterns", [])),
        "exact_paths": sorted({item["path"] for item in manifest["files"]} | set(manifest["diff"].get("deleted_paths", []))) if selection.get("file_list_sha256") else [],
        "exclude_patterns": list(selection.get("exclude_patterns", [])),
    }
    approval = {
        "schema": "gptpro-standing-approval-v4",
        "approval_id": approval_id,
        "created_at": timestamp(now),
        "expires_at": timestamp(now + timedelta(hours=expires_hours)),
        "revoked_at": None,
        "repository_root_sha256": manifest["repository"]["root_sha256"],
        "path_rules": path_rules,
        "tracked_only": manifest["selection"]["tracked_only"],
        "supplement_labels": [item["label"] for item in manifest["supplements"]],
        "modes": allowed_modes,
        "max_outbound_bytes": MAX_OUTBOUND_BYTES,
        "model_intent": manifest["model_intent"],
        "inline_format": INLINE_FORMAT,
        "channel": DELIVERY_CHANNEL,
        "chat_history_mode": CHAT_HISTORY_MODE,
    }
    path = approvals_root(root) / f"{approval_id}.json"
    if path.exists() or path.is_symlink():
        raise ApprovalError("APPROVAL_EXISTS", "The generated standing approval identity already exists.")
    write_json(path, approval)
    return {"ok": True, "operation": "standing-approval-create", "approval_id": approval_id, "approval_file": str(path), "expires_at": approval["expires_at"], "scope": {"path_rules": path_rules, "tracked_only": approval["tracked_only"], "modes": allowed_modes, "channel": approval["channel"], "chat_history_mode": CHAT_HISTORY_MODE}}


def load_standing(path: Path) -> dict[str, Any]:
    try:
        value = read_json(path)
    except Exception as exc:
        raise ApprovalError("STANDING_APPROVAL_INVALID", "The standing approval cannot be verified.") from exc
    required = {
        "schema",
        "approval_id",
        "created_at",
        "expires_at",
        "revoked_at",
        "repository_root_sha256",
        "path_rules",
        "tracked_only",
        "supplement_labels",
        "modes",
        "max_outbound_bytes",
        "model_intent",
        "inline_format",
        "channel",
        "chat_history_mode",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != "gptpro-standing-approval-v4":
        raise ApprovalError("STANDING_APPROVAL_INVALID", "The standing approval contract is invalid.")
    if not re.fullmatch(r"desktop-v4-[A-Za-z0-9T-]+", str(value.get("approval_id", ""))):
        raise ApprovalError("STANDING_APPROVAL_INVALID", "The standing approval identity is invalid.")
    if (
        value.get("channel") != DELIVERY_CHANNEL
        or value.get("chat_history_mode") != CHAT_HISTORY_MODE
        or value.get("inline_format") != INLINE_FORMAT
        or value.get("max_outbound_bytes") != MAX_OUTBOUND_BYTES
    ):
        raise ApprovalError("STANDING_APPROVAL_INVALID", "The standing approval inline delivery contract is invalid.")
    return value


def standing_files(root: Path | None = None) -> list[Path]:
    directory = approvals_root(root)
    return sorted(path for path in directory.glob("desktop-v4-*.json") if path.is_file() and not path.is_symlink())


def standing_matches(approval: dict[str, Any], manifest: dict[str, Any]) -> tuple[bool, str]:
    expiry = parse_time(approval.get("expires_at"))
    if approval.get("revoked_at") is not None:
        return False, "revoked"
    if expiry is None or expiry <= utc_now():
        return False, "expired"
    rules = approval.get("path_rules")
    if not isinstance(rules, dict) or set(rules) != {"include_patterns", "exact_paths", "exclude_patterns"}:
        return False, "path-rules"
    patterns = rules.get("include_patterns")
    exact_paths = rules.get("exact_paths")
    excludes = rules.get("exclude_patterns")
    if not all(isinstance(value, list) and all(isinstance(item, str) for item in value) for value in (patterns, exact_paths, excludes)):
        return False, "path-rules"

    manifest_paths = {item["path"] for item in manifest["files"]} | set(manifest["diff"].get("deleted_paths", []))
    paths_allowed = all(
        (path in exact_paths or _matches(path, patterns)) and not _matches(path, excludes)
        for path in manifest_paths
    )
    checks = (
        (approval.get("repository_root_sha256") == manifest["repository"]["root_sha256"], "repository"),
        (manifest["mode"] in approval.get("modes", []), "mode"),
        (approval.get("channel") == DELIVERY_CHANNEL, "channel"),
        (approval.get("chat_history_mode") == manifest.get("delivery", {}).get("chat_history_mode") == CHAT_HISTORY_MODE, "chat-history"),
        (approval.get("inline_format") == manifest.get("disclosure", {}).get("inline_format") == INLINE_FORMAT, "inline-format"),
        (approval.get("model_intent") == manifest.get("model_intent"), "model"),
        (paths_allowed, "paths"),
        (not approval.get("tracked_only") or all(item["tracked"] for item in manifest["files"]), "tracked"),
        (set(item["label"] for item in manifest["supplements"]).issubset(set(approval.get("supplement_labels", []))), "supplements"),
        (int(manifest["disclosure"]["outbound_bytes"]) <= int(approval.get("max_outbound_bytes", -1)) <= MAX_OUTBOUND_BYTES, "outbound-bytes"),
    )
    for valid, reason in checks:
        if not valid:
            return False, reason
    return True, "matched"


def apply_standing(handoff_value: Path, *, approval_id: str | None, root: Path | None = None) -> dict[str, Any]:
    initial = verify_package(handoff_value)
    handoff = Path(initial["handoff_dir"])
    with package_lock(handoff):
        verified = verify_package(handoff)
        manifest = verified["manifest"]
        candidates = standing_files(root)
        if approval_id:
            candidates = [path for path in candidates if path.stem == approval_id]
            if not candidates:
                raise ApprovalError("STANDING_APPROVAL_NOT_FOUND", "The requested standing approval does not exist.")
        failures: list[str] = []
        for path in candidates:
            approval = load_standing(path)
            matches, reason = standing_matches(approval, manifest)
            if not matches:
                failures.append(reason)
                continue
            state = load_state(handoff, manifest["package_id"])
            if state.get("phase") not in {"prepared", "approved"}:
                raise ApprovalError("PACKAGE_PHASE_INVALID", "The package can no longer receive standing approval.")
            binding = {
                "type": "standing-v4",
                "approval_id": approval["approval_id"],
                "approval_sha256": sha256_file(path),
                "expires_at": approval["expires_at"],
                "manifest_sha256": verified["manifest_sha256"],
                "outbound_sha256": manifest["hashes"]["outbound_sha256"],
                "outbound_bytes": manifest["disclosure"]["outbound_bytes"],
                "system_prompt_sha256": manifest["hashes"]["system_prompt_sha256"],
                "model_intent": manifest["model_intent"],
                "channel": DELIVERY_CHANNEL,
                "chat_history_mode": CHAT_HISTORY_MODE,
                "inline_format": INLINE_FORMAT,
            }
            state["approval"] = binding
            state["phase"] = "approved"
            save_state(handoff, state)
            append_receipt(
                handoff / "receipt.json",
                manifest["package_id"],
                "approved",
                {
                    "approval_type": "standing-v4",
                    "approval_id": approval["approval_id"],
                    "approval_sha256": binding["approval_sha256"],
                    "expires_at": binding["expires_at"],
                    "manifest_sha256": binding["manifest_sha256"],
                    "outbound_sha256": binding["outbound_sha256"],
                    "outbound_bytes": binding["outbound_bytes"],
                    "system_prompt_sha256": binding["system_prompt_sha256"],
                    "model_intent": binding["model_intent"],
                    "channel": DELIVERY_CHANNEL,
                    "chat_history_mode": CHAT_HISTORY_MODE,
                    "inline_format": INLINE_FORMAT,
                },
            )
            return {"ok": True, "matched": True, "approval_id": approval["approval_id"], "expires_at": approval["expires_at"]}
    raise ApprovalError(
        "APPROVAL_REQUIRED",
        "No active standing approval covers this exact repository, paths, supplements, mode, model, inline limit, and Electron channel.",
        recovery="Review the prepared package, then run approve or standing-approval-create. No prompt was sent.",
    )


def verify_active_approval(handoff_value: Path) -> dict[str, Any]:
    verified = verify_package(handoff_value)
    handoff = Path(verified["handoff_dir"])
    manifest = verified["manifest"]
    state = load_state(handoff, manifest["package_id"])
    approval = state.get("approval")
    if state.get("phase") not in {
        "approved",
        "dispatching",
        "submitted",
        "imported",
        "evaluated",
        "submission_ambiguous",
        "submission_rejected",
    } or not isinstance(approval, dict):
        raise ApprovalError("APPROVAL_REQUIRED", "The exact Schema-6 package is not approved.")
    approval_type = approval.get("type")
    exact_keys = {
        "type", "recorded_at", "expires_at", "manifest_sha256", "prompt_sha256",
        "system_prompt_sha256", "outbound_sha256", "outbound_bytes",
        "model_intent", "channel", "chat_history_mode", "inline_format",
    }
    standing_keys = {
        "type", "approval_id", "approval_sha256", "expires_at", "manifest_sha256",
        "outbound_sha256", "outbound_bytes", "system_prompt_sha256", "model_intent",
        "channel", "chat_history_mode", "inline_format",
    }
    if (
        (approval_type == "exact-package-v2" and set(approval) != exact_keys)
        or (approval_type == "standing-v4" and set(approval) != standing_keys)
        or approval_type not in {"exact-package-v2", "standing-v4"}
    ):
        raise ApprovalError("APPROVAL_INVALID", "The Schema-6 approval contract is invalid.")
    if (
        approval.get("manifest_sha256") != verified["manifest_sha256"]
        or approval.get("channel") != DELIVERY_CHANNEL
        or approval.get("chat_history_mode") != CHAT_HISTORY_MODE
        or manifest.get("delivery", {}).get("chat_history_mode") != CHAT_HISTORY_MODE
        or approval.get("inline_format") != INLINE_FORMAT
        or manifest.get("disclosure", {}).get("inline_format") != INLINE_FORMAT
        or approval.get("outbound_sha256") != manifest.get("hashes", {}).get("outbound_sha256")
        or approval.get("outbound_bytes") != manifest.get("disclosure", {}).get("outbound_bytes")
        or approval.get("system_prompt_sha256") != manifest.get("hashes", {}).get("system_prompt_sha256")
        or approval.get("model_intent") != manifest.get("model_intent")
        or (
            approval_type == "exact-package-v2"
            and (
                approval.get("prompt_sha256") != manifest.get("hashes", {}).get("prompt_sha256")
                or parse_time(approval.get("recorded_at")) is None
            )
        )
    ):
        raise ApprovalError("APPROVAL_INVALID", "The approval no longer matches the package or Electron channel.")
    try:
        receipt = load_receipt(handoff / "receipt.json", package_id=manifest["package_id"])
    except ReceiptError as exc:
        raise ApprovalError("APPROVAL_RECEIPT_INVALID", "The package approval receipt cannot be verified.") from exc
    approved_events = [event for event in receipt["events"] if event.get("event") == "approved"]
    if not approved_events:
        raise ApprovalError("APPROVAL_RECEIPT_INVALID", "The package has no durable approval receipt.")
    event = approved_events[-1]
    expected_event = {
        "approval_type": approval.get("type"),
        "expires_at": approval.get("expires_at"),
        "manifest_sha256": approval.get("manifest_sha256"),
        "outbound_sha256": approval.get("outbound_sha256"),
        "outbound_bytes": approval.get("outbound_bytes"),
        "system_prompt_sha256": approval.get("system_prompt_sha256"),
        "model_intent": approval.get("model_intent"),
        "channel": DELIVERY_CHANNEL,
        "chat_history_mode": CHAT_HISTORY_MODE,
        "inline_format": INLINE_FORMAT,
    }
    if approval.get("type") == "standing-v4":
        expected_event.update(
            {
                "approval_id": approval.get("approval_id"),
                "approval_sha256": approval.get("approval_sha256"),
            }
        )
    if any(event.get(key) != value for key, value in expected_event.items()):
        raise ApprovalError("APPROVAL_RECEIPT_INVALID", "The durable approval receipt differs from package state.")
    expiry = parse_time(approval.get("expires_at"))
    if expiry is None or expiry <= utc_now():
        raise ApprovalError("APPROVAL_EXPIRED", "The package approval has expired.")
    if approval.get("type") == "standing-v4":
        identifier = approval.get("approval_id")
        candidates = [path for path in standing_files() if path.stem == identifier]
        if len(candidates) != 1 or sha256_file(candidates[0]) != approval.get("approval_sha256"):
            raise ApprovalError("STANDING_APPROVAL_INVALID", "The standing approval binding changed or disappeared.")
        standing = load_standing(candidates[0])
        matches, reason = standing_matches(standing, manifest)
        if not matches:
            raise ApprovalError("STANDING_APPROVAL_SCOPE_MISMATCH", f"The standing approval no longer matches: {reason}.")
    return {"verified": verified, "state": state, "approval": approval}


def list_standing(root: Path | None = None) -> dict[str, Any]:
    approvals = []
    for path in standing_files(root):
        value = load_standing(path)
        expiry = parse_time(value["expires_at"])
        status = "revoked" if value["revoked_at"] else "expired" if expiry is None or expiry <= utc_now() else "active"
        approvals.append({
            "approval_id": value["approval_id"],
            "status": status,
            "expires_at": value["expires_at"],
            "repository_root_sha256": value["repository_root_sha256"],
            "path_rule_count": len(value["path_rules"]["include_patterns"]) + len(value["path_rules"]["exact_paths"]),
            "modes": value["modes"],
            "tracked_only": value["tracked_only"],
            "channel": value["channel"],
            "chat_history_mode": value["chat_history_mode"],
        })
    return {"ok": True, "operation": "standing-approval-list", "approvals": approvals}


def revoke_standing(approval_id: str, *, root: Path | None = None) -> dict[str, Any]:
    candidates = [path for path in standing_files(root) if path.stem == approval_id]
    if len(candidates) != 1:
        raise ApprovalError("STANDING_APPROVAL_NOT_FOUND", "The standing approval does not exist.")
    value = load_standing(candidates[0])
    if value["revoked_at"] is None:
        value["revoked_at"] = timestamp(utc_now())
        write_json(candidates[0], value)
    return {"ok": True, "operation": "standing-approval-revoke", "approval_id": approval_id, "status": "revoked", "revoked_at": value["revoked_at"]}
