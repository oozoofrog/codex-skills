"""Private, one-active-package runtime state for the Web MCP lifecycle."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from .clock import parse_utc, utc_text
from .sensitive import OPENAI_TUNNEL_ID_TEXT

RUNTIME_SCHEMA_VERSION = 1
LIVE_STATUSES = frozenset({"activating", "active", "revoking"})
TERMINAL_STATUSES = frozenset({"revoked", "expired", "faulted"})
STATUSES = LIVE_STATUSES | TERMINAL_STATUSES

_TRANSITIONS: dict[str, frozenset[str]] = {
    "activating": frozenset({"active", "faulted", "revoked"}),
    "active": frozenset({"revoking", "expired", "faulted"}),
    "revoking": frozenset({"revoked", "faulted"}),
    "expired": frozenset({"revoked"}),
    "faulted": frozenset({"revoked"}),
    "revoked": frozenset(),
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
_PACKAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_STOP_REASON = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_SECRET_VALUE = re.compile(rf"(?:\bsk-[A-Za-z0-9_-]{{16,}}|\b{OPENAI_TUNNEL_ID_TEXT}\b)")
_SECRET_OBJECT_KEY = re.compile(
    rf"(?:sk-[A-Za-z0-9_-]{{16,}}|{OPENAI_TUNNEL_ID_TEXT})", re.IGNORECASE
)
_SAFE_TUNNEL_OBJECT_KEYS = frozenset(
    {
        "tunnel_runtime_alias",
        "tunnel_id_binding_sha256",
        "tunnel_profile_sha256",
        "tunnel_client_binary_sha256",
        "orphan_tunnel_termination_manually_confirmed",
        "orphan_tunnel_termination_confirmation_recorded_at",
    }
)
_MAX_STATE_NESTING = 64
_MAX_STATE_NODES = 4096
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "password",
        "raw_tunnel_id",
        "session_id",
        "session_secret",
        "token",
    }
)
_IMMUTABLE_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "package_id",
        "session_id_sha256",
        "handoff_dir",
        "manifest_sha256",
        "approval_event_sha256",
        "archive_sha256",
        "file_set_sha256",
        "tool_schema_sha256",
        "audit_schema_version",
        "disclosure_accounting",
        "analysis_header_sha256",
        "analysis_file",
        "protocol_profile",
        "transport",
        "delivery_channel",
        "connector_type",
        "tunnel_runtime_alias",
        "tunnel_id_binding_sha256",
        "tunnel_profile_sha256",
        "tunnel_client_binary_sha256",
        "mcp_target_sha256",
        "mcp_runtime_tree_sha256",
        "workspace_binding_confirmed",
        "activated_at",
        "expires_at",
        "idle_ttl_seconds",
        "revision",
        "status",
    }
)


@dataclass
class RuntimeStateError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


def default_runtime_root() -> Path:
    if sys.platform != "darwin":
        raise RuntimeStateError(
            "RUNTIME_UNSUPPORTED_PLATFORM",
            "The phase-3 runtime currently supports macOS only.",
        )
    try:
        import pwd

        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, TypeError) as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "The canonical macOS account home is unavailable.",
        ) from exc
    if not account_home.is_absolute() or account_home == Path(account_home.anchor):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "The canonical macOS account home is invalid.",
        )
    return account_home / "Library" / "Application Support" / "gptpro" / "runtime" / "v1"


def _open_directory_chain(path: Path, *, create: bool, final_mode: int | None = None) -> int:
    """Open every absolute directory component with openat + O_NOFOLLOW."""

    requested = Path(path).expanduser()
    if (
        not requested.is_absolute()
        or len(requested.parts) <= 1
        or any(component in {"", ".", ".."} for component in requested.parts[1:])
    ):
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Private runtime paths must be absolute.")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "O_NOFOLLOW is required for runtime state.")
    try:
        descriptor = os.open(requested.anchor, flags | nofollow)
    except OSError as exc:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Unable to open the filesystem root.") from exc
    try:
        for index, component in enumerate(requested.parts[1:], start=1):
            final = index == len(requested.parts) - 1
            try:
                child = os.open(component, flags | nofollow, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE", "A private runtime directory is missing."
                    )
                try:
                    os.mkdir(component, final_mode or 0o700, dir_fd=descriptor)
                    child = os.open(component, flags | nofollow, dir_fd=descriptor)
                    os.fchmod(child, final_mode or 0o700)
                    os.fsync(descriptor)
                except OSError as exc:
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE", "Unable to create a private runtime directory."
                    ) from exc
            except OSError as exc:
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE",
                    "A private runtime path contains a symlink or non-directory component.",
                ) from exc
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE", "A private runtime component is not a directory."
                )
            os.close(descriptor)
            descriptor = child
            if final and final_mode is not None and (
                metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != final_mode
            ):
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE",
                    f"The private runtime directory must be owner-only mode {final_mode:04o}.",
                )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def ensure_private_directory(path: Path, *, mode: int = 0o700) -> Path:
    """Create a private absolute directory without following any path symlink."""

    requested = Path(path).expanduser()
    descriptor = _open_directory_chain(requested, create=True, final_mode=mode)
    os.close(descriptor)
    return requested


def _directory_fd(path: Path) -> int:
    descriptor = _open_directory_chain(path, create=False)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        os.close(descriptor)
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The runtime directory owner is invalid.")
    return descriptor


def _validate_private_fd(descriptor: int, *, mode: int = 0o600) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            f"Private runtime files must be owner-only regular files with mode {mode:04o}.",
        )
    return metadata


def open_private_regular(
    path: Path,
    *,
    flags: int = os.O_RDONLY,
    create: bool = False,
    mode: int = 0o600,
) -> int:
    """Open one basename without following links and validate UID/link-count/mode."""

    path = Path(path)
    if path.name in {"", ".", ".."}:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The private file name is invalid.")
    ensure_private_directory(path.parent)
    directory = _directory_fd(path.parent)
    nofollow = getattr(os, "O_NOFOLLOW")
    opened = -1
    try:
        open_flags = flags | nofollow | getattr(os, "O_CLOEXEC", 0)
        if create:
            try:
                opened = os.open(path.name, open_flags | os.O_CREAT | os.O_EXCL, mode, dir_fd=directory)
                os.fchmod(opened, mode)
            except FileExistsError:
                opened = os.open(path.name, open_flags, dir_fd=directory)
        else:
            opened = os.open(path.name, open_flags, dir_fd=directory)
        _validate_private_fd(opened, mode=mode)
        return opened
    except RuntimeStateError:
        if opened >= 0:
            os.close(opened)
        raise
    except OSError as exc:
        if opened >= 0:
            os.close(opened)
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Unable to open a private runtime file.") from exc
    finally:
        os.close(directory)


def fsync_directory(path: Path, *, fsync: Any = os.fsync) -> None:
    descriptor = _directory_fd(path)
    try:
        fsync(descriptor)
    except OSError as exc:
        raise RuntimeStateError("RUNTIME_STATE_WRITE_FAILED", "Unable to sync runtime state.") from exc
    finally:
        os.close(descriptor)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime state is not safely serializable."
        ) from exc


def _pretty_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime state is not safely serializable."
        ) from exc


def _reject_secret_material(value: Any, *, path: str = "state") -> None:
    pending: list[tuple[Any, str, int]] = [(value, path, 0)]
    visited = 0
    while pending:
        current, current_path, depth = pending.pop()
        visited += 1
        if depth > _MAX_STATE_NESTING or visited > _MAX_STATE_NODES:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "Private runtime state exceeds structural limits."
            )
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "Private runtime state contains a non-string object key.",
                    )
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "Private runtime state contains an invalid Unicode object key.",
                    ) from exc
                if key not in _SAFE_TUNNEL_OBJECT_KEYS and _SECRET_OBJECT_KEY.search(key):
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "Private runtime state contains raw credentials in an object key.",
                    )
                normalized = key.casefold()
                if normalized in _FORBIDDEN_KEYS:
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        f"Private runtime state contains forbidden field {current_path}.{key}.",
                    )
                pending.append((child, f"{current_path}.{key}", depth + 1))
        elif isinstance(current, (list, tuple)):
            for index, child in enumerate(current):
                pending.append((child, f"{current_path}[{index}]", depth + 1))
        elif isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE", "Private runtime state contains invalid Unicode."
                ) from exc
            if _SECRET_VALUE.search(current):
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE", "Private runtime state contains raw credentials."
                )
        elif isinstance(current, float) and not math.isfinite(current):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "Private runtime state contains a non-finite number."
            )


def validate_active_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(state)
    if value.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise RuntimeStateError("SCHEMA_VERSION_UNSUPPORTED", "Runtime state schema is unsupported.")
    if value.get("status") not in STATUSES:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime authorization status is invalid.")
    if _PACKAGE_ID.fullmatch(str(value.get("package_id", ""))) is None:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime package identity is invalid.")
    if _SHA256.fullmatch(str(value.get("session_id_sha256", ""))) is None:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime session identity is invalid.")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime state revision is invalid.")
    handoff_dir = value.get("handoff_dir")
    if handoff_dir is not None and (not isinstance(handoff_dir, str) or not Path(handoff_dir).is_absolute()):
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime handoff location is invalid.")
    for key in (
        "manifest_sha256",
        "approval_event_sha256",
        "archive_sha256",
        "file_set_sha256",
        "tool_schema_sha256",
        "tunnel_profile_sha256",
        "tunnel_client_binary_sha256",
        "mcp_target_sha256",
        "mcp_runtime_tree_sha256",
        "protocol_trace_header_sha256",
        "analysis_header_sha256",
        "runtime_stop_receipt_event_sha256",
        "runtime_protocol_trace_artifact_sha256",
        "activation_stop_receipt_event_sha256",
        "activation_protocol_trace_artifact_sha256",
    ):
        if key in value and _SHA256.fullmatch(str(value[key])) is None:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", f"Runtime binding {key} is invalid.")
    timestamps: dict[str, datetime] = {}
    for key in (
        "activated_at",
        "expires_at",
        "updated_at",
        "runtime_stop_recorded_at",
        "activation_stop_recorded_at",
        "orphan_tunnel_termination_confirmation_recorded_at",
    ):
        if key in value:
            try:
                timestamps[key] = parse_utc(str(value[key]))
            except ValueError as exc:
                raise RuntimeStateError("RUNTIME_STATE_UNSAFE", f"Runtime timestamp {key} is invalid.") from exc
    required = {
        "handoff_dir",
        "manifest_sha256",
        "approval_event_sha256",
        "archive_sha256",
        "file_set_sha256",
        "tool_schema_sha256",
        "tunnel_profile_sha256",
        "tunnel_client_binary_sha256",
        "mcp_target_sha256",
        "mcp_runtime_tree_sha256",
        "activated_at",
        "expires_at",
        "updated_at",
        "idle_ttl_seconds",
        "activated_monotonic",
        "expires_monotonic",
        "last_activity_monotonic",
    }
    if "analysis_file" in value and value.get("analysis_file") != "mcp-analysis.jsonl":
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime analysis filename is invalid.")
    audit_contract_fields = {"audit_schema_version", "disclosure_accounting"}
    present_audit_contract = audit_contract_fields & set(value)
    if present_audit_contract and (
        present_audit_contract != audit_contract_fields
        or type(value.get("audit_schema_version")) is not int
        or value.get("audit_schema_version") != 2
        or value.get("disclosure_accounting") != "complete_model_visible_result_v1"
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime disclosure accounting contract is invalid."
        )
    analysis_final_fields = {
        "analysis_head_sha256",
        "analysis_final_sequence",
        "analysis_event_count",
        "analysis_closed",
        "analysis_close_reason",
    }
    present_analysis_final = analysis_final_fields & set(value)
    if present_analysis_final and present_analysis_final != analysis_final_fields:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime final analysis evidence is incomplete."
        )
    if present_analysis_final:
        if (
            value.get("status") not in TERMINAL_STATUSES
            or _SHA256.fullmatch(str(value.get("analysis_head_sha256", ""))) is None
            or isinstance(value.get("analysis_final_sequence"), bool)
            or not isinstance(value.get("analysis_final_sequence"), int)
            or value["analysis_final_sequence"] < 1
            or isinstance(value.get("analysis_event_count"), bool)
            or not isinstance(value.get("analysis_event_count"), int)
            or value["analysis_event_count"] < 0
            or value.get("analysis_closed") is not True
            or re.fullmatch(
                r"[a-z][a-z0-9_-]{0,63}", str(value.get("analysis_close_reason", ""))
            )
            is None
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "Runtime final analysis evidence is invalid."
            )
        terminal_reason_key = (
            "revoked_reason" if value.get("status") == "revoked" else "expired_reason"
        )
        if value.get("status") in {"revoked", "expired"} and (
            value.get(terminal_reason_key) != value.get("analysis_close_reason")
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE",
                "Runtime terminal reason conflicts with final analysis evidence.",
            )
    if not required.issubset(value):
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime state is missing a required binding.")
    idle_ttl = value["idle_ttl_seconds"]
    if isinstance(idle_ttl, bool) or not isinstance(idle_ttl, int) or not 1 <= idle_ttl <= 86_400:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime idle TTL is invalid.")
    monotonic_values: dict[str, float] = {}
    for key in ("activated_monotonic", "expires_monotonic", "last_activity_monotonic"):
        raw = value[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", f"Runtime monotonic deadline {key} is invalid."
            )
        monotonic_values[key] = float(raw)
    if (
        monotonic_values["activated_monotonic"] < 0
        or monotonic_values["expires_monotonic"] <= monotonic_values["activated_monotonic"]
        or not monotonic_values["activated_monotonic"]
        <= monotonic_values["last_activity_monotonic"]
        <= monotonic_values["expires_monotonic"]
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime monotonic deadlines are inconsistent."
        )
    if timestamps["expires_at"] <= timestamps["activated_at"]:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime session expiry is invalid.")
    _validate_optional_stop_evidence(value, prefix="runtime")
    _validate_optional_stop_evidence(value, prefix="activation")
    manual_orphan_confirmation = value.get(
        "orphan_tunnel_termination_manually_confirmed"
    )
    manual_orphan_confirmation_at = value.get(
        "orphan_tunnel_termination_confirmation_recorded_at"
    )
    if (
        manual_orphan_confirmation is not None
        or manual_orphan_confirmation_at is not None
    ) and (
        manual_orphan_confirmation is not True
        or "orphan_tunnel_termination_confirmation_recorded_at" not in timestamps
        or value.get("status") not in TERMINAL_STATUSES
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "Runtime manual orphan-termination confirmation is invalid.",
        )
    if value.get("runtime_child_stopped") is True and value.get("status") not in TERMINAL_STATUSES:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "Runtime child-stop evidence requires terminal authorization.",
        )
    if value.get("activation_child_stopped") is True and value.get("status") not in {
        "faulted",
        "revoked",
    }:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "Failed-activation child-stop evidence requires faulted or recovered-revoked authorization.",
        )
    activation_failure_code = value.get("activation_failure_code")
    if activation_failure_code is not None and (
        not isinstance(activation_failure_code, str)
        or _ERROR_CODE.fullmatch(activation_failure_code) is None
        or value.get("status") not in {"faulted", "revoked"}
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "Runtime activation-failure evidence is invalid.",
        )
    wall_duration = (timestamps["expires_at"] - timestamps["activated_at"]).total_seconds()
    monotonic_duration = (
        monotonic_values["expires_monotonic"] - monotonic_values["activated_monotonic"]
    )
    if abs(wall_duration - monotonic_duration) > 1.0:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime wall and monotonic session bounds disagree."
        )
    _reject_secret_material(value)
    return value


def _validate_optional_stop_evidence(value: Mapping[str, Any], *, prefix: str) -> None:
    required_fields = {
        f"{prefix}_child_stopped",
        f"{prefix}_child_returncode",
        f"{prefix}_forced_exact_child",
        f"{prefix}_stop_reason",
        f"{prefix}_stop_receipt_recorded",
        f"{prefix}_stop_recorded_at",
    }
    receipt_hash_key = f"{prefix}_stop_receipt_event_sha256"
    trace_hash_key = f"{prefix}_protocol_trace_artifact_sha256"
    evidence_fields = required_fields | {receipt_hash_key, trace_hash_key}
    present = evidence_fields & set(value)
    if not present:
        return
    if not required_fields.issubset(value):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime exact-child stop evidence is incomplete."
        )
    returncode = value[f"{prefix}_child_returncode"]
    reason = value[f"{prefix}_stop_reason"]
    receipt_recorded = value[f"{prefix}_stop_receipt_recorded"]
    if (
        value[f"{prefix}_child_stopped"] is not True
        or isinstance(returncode, bool)
        or not isinstance(returncode, int)
        or not isinstance(value[f"{prefix}_forced_exact_child"], bool)
        or not isinstance(reason, str)
        or _STOP_REASON.fullmatch(reason) is None
        or not isinstance(receipt_recorded, bool)
        or (receipt_recorded and receipt_hash_key not in value)
        or (not receipt_recorded and receipt_hash_key in value)
        or (not receipt_recorded and trace_hash_key in value)
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Runtime exact-child stop evidence is invalid."
        )


class RuntimeTransaction:
    def __init__(self, store: "RuntimeStateStore") -> None:
        self.store = store

    def read(self) -> dict[str, Any] | None:
        return self.store._read_unlocked()

    def write(self, value: Mapping[str, Any]) -> dict[str, Any]:
        state = validate_active_state(value)
        self.store._write_unlocked(state)
        return state


class RuntimeStateStore:
    """Secure active pointer with a cross-repository flock and exact transitions."""

    def __init__(self, root: Path | None = None, *, lock_timeout: float = 5.0) -> None:
        self.root = ensure_private_directory(root or default_runtime_root())
        self.active_path = self.root / "active.json"
        self.lock_path = self.root / "lock"
        self.sessions_path = self.root / "sessions"
        self.lock_timeout = lock_timeout

    @contextmanager
    def locked(self, *, timeout: float | None = None) -> Iterator[RuntimeTransaction]:
        descriptor = open_private_regular(self.lock_path, flags=os.O_RDWR, create=True)
        deadline = time.monotonic() + (self.lock_timeout if timeout is None else timeout)
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeStateError(
                            "LOCK_TIMEOUT", "The runtime authorization lock is busy.", retryable=True
                        )
                    time.sleep(0.01)
            yield RuntimeTransaction(self)
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def read(self) -> dict[str, Any] | None:
        with self.locked() as transaction:
            return transaction.read()

    def read_archived_session(self, session_id_sha256: str) -> dict[str, Any] | None:
        """Read one exact terminal session without trusting the active pointer.

        A new activation archives the previous terminal state before replacing
        ``active.json``.  Stop/status observers that are already bound to that
        previous session may therefore need its immutable archived evidence.
        The archive basename is derived only from a validated SHA-256 identity,
        and every directory/file property is revalidated under the runtime lock.
        """

        if not isinstance(session_id_sha256, str) or _SHA256.fullmatch(
            session_id_sha256
        ) is None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The archived runtime session hash is invalid."
            )
        with self.locked():
            try:
                directory = _directory_fd(self.sessions_path)
            except RuntimeStateError as exc:
                try:
                    self.sessions_path.lstat()
                except FileNotFoundError:
                    return None
                raise exc
            descriptor = -1
            try:
                directory_metadata = os.fstat(directory)
                if (
                    not stat.S_ISDIR(directory_metadata.st_mode)
                    or directory_metadata.st_uid != os.getuid()
                    or stat.S_IMODE(directory_metadata.st_mode) != 0o700
                ):
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "The archived runtime directory must be owner-only.",
                    )
                try:
                    descriptor = os.open(
                        f"{session_id_sha256}.json",
                        os.O_RDONLY
                        | getattr(os, "O_NOFOLLOW")
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory,
                    )
                except FileNotFoundError:
                    return None
                except OSError as exc:
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "Unable to open archived runtime state safely.",
                    ) from exc
                _validate_private_fd(descriptor)
                value = self._read_state_descriptor(descriptor)
                if (
                    value.get("session_id_sha256") != session_id_sha256
                    or value.get("status") not in TERMINAL_STATUSES
                ):
                    raise RuntimeStateError(
                        "RUNTIME_STATE_UNSAFE",
                        "Archived runtime state does not match its terminal session identity.",
                    )
                return value
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(directory)

    def begin_activation(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(candidate)
        value["schema_version"] = RUNTIME_SCHEMA_VERSION
        value["status"] = "activating"
        value.setdefault("revision", 1)
        value.setdefault("updated_at", utc_text(datetime.now(timezone.utc)))
        value = validate_active_state(value)
        with self.locked() as transaction:
            current = transaction.read()
            if current is not None and current["status"] in LIVE_STATUSES:
                raise RuntimeStateError(
                    "SESSION_CONFLICT", "Another package authorization is already live."
                )
            if current is not None:
                exact_child_stopped = (
                    current.get("runtime_child_stopped") is True
                    or current.get("activation_child_stopped") is True
                )
                manual_orphan_clearance = (
                    current.get("orphan_tunnel_termination_manually_confirmed") is True
                )
                try:
                    controller_live = self._controller_lease_is_live_unlocked(
                        str(current["session_id_sha256"])
                    )
                except RuntimeStateError as exc:
                    if not (exact_child_stopped or manual_orphan_clearance):
                        raise RuntimeStateError(
                            "CONTROLLER_ORPHANED",
                            "The previous terminal controller lease is unavailable and exact-child stop is unproven; use explicit recovery.",
                        ) from exc
                    controller_live = False
                if controller_live:
                    raise RuntimeStateError(
                        "SESSION_CONFLICT",
                        "The previous terminal session controller is still finalizing exact-child evidence.",
                    )
                if not (exact_child_stopped or manual_orphan_clearance):
                    raise RuntimeStateError(
                        "CONTROLLER_ORPHANED",
                        "The previous terminal controller exited without exact-child stop evidence; complete attended orphan-process review before activating another package.",
                    )
                self._archive_terminal_unlocked(current)
                value["revision"] = current["revision"] + 1
            return transaction.write(value)

    def _controller_lease_is_live_unlocked(self, session_id_sha256: str) -> bool:
        """Check one terminal controller lease while the runtime lock is held."""

        if _SHA256.fullmatch(session_id_sha256) is None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The terminal controller session hash is invalid."
            )
        path = self.root / f"controller-{session_id_sha256}.lock"
        descriptor = open_private_regular(path, flags=os.O_RDWR)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                return False
        finally:
            os.close(descriptor)

    def confirm_orphan_tunnel_termination(
        self, session_id_sha256: str
    ) -> dict[str, Any]:
        """Record an attended assertion without fabricating exact-child evidence."""

        if _SHA256.fullmatch(session_id_sha256) is None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The terminal controller session hash is invalid."
            )
        with self.locked() as transaction:
            current = transaction.read()
            if (
                current is None
                or current.get("session_id_sha256") != session_id_sha256
                or current.get("status") not in TERMINAL_STATUSES
            ):
                raise RuntimeStateError(
                    "SESSION_CONFLICT",
                    "Manual orphan-process review does not match a terminal authorization.",
                )
            if current.get("orphan_tunnel_termination_manually_confirmed") is True:
                return current
            updated = dict(current)
            updated["orphan_tunnel_termination_manually_confirmed"] = True
            updated["orphan_tunnel_termination_confirmation_recorded_at"] = utc_text(
                datetime.now(timezone.utc)
            )
            updated["revision"] = int(current["revision"]) + 1
            updated["updated_at"] = utc_text(datetime.now(timezone.utc))
            return transaction.write(updated)

    def transition(
        self,
        session_id_sha256: str,
        expected_status: str | set[str] | frozenset[str],
        target_status: str,
        *,
        updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected = {expected_status} if isinstance(expected_status, str) else set(expected_status)
        if target_status not in STATUSES:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Target authorization status is invalid.")
        with self.locked() as transaction:
            current = transaction.read()
            if current is None:
                raise RuntimeStateError("NO_ACTIVE_PACKAGE", "No runtime authorization exists.")
            if current["session_id_sha256"] != session_id_sha256:
                raise RuntimeStateError("SESSION_CONFLICT", "Runtime session identity does not match.")
            if current["status"] not in expected:
                raise RuntimeStateError("SESSION_CONFLICT", "Runtime authorization status changed.")
            if target_status not in _TRANSITIONS[current["status"]]:
                raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime transition is not permitted.")
            merged = dict(current)
            for key, value in dict(updates or {}).items():
                if key in _IMMUTABLE_BINDING_KEYS:
                    raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime identity fields are immutable.")
                merged[key] = value
            merged["status"] = target_status
            merged["revision"] = current["revision"] + 1
            merged["updated_at"] = utc_text(datetime.now(timezone.utc))
            return transaction.write(merged)

    def _read_unlocked(self) -> dict[str, Any] | None:
        try:
            descriptor = open_private_regular(self.active_path)
        except RuntimeStateError as exc:
            try:
                exists = self.active_path.lstat()
            except FileNotFoundError:
                return None
            del exists
            raise exc
        try:
            return self._read_state_descriptor(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _read_state_descriptor(descriptor: int) -> dict[str, Any]:
        metadata = os.fstat(descriptor)
        if metadata.st_size > 1024 * 1024:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime state is unexpectedly large.")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read()
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime state is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Runtime state must be an object.")
        return validate_active_state(value)

    def _write_unlocked(self, state: Mapping[str, Any]) -> None:
        data = _pretty_json(state)
        directory = _directory_fd(self.root)
        temporary = f".active.{secrets.token_hex(16)}.tmp"
        descriptor = -1
        try:
            try:
                current = os.stat("active.json", dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            if current is not None and (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
                or current.st_nlink != 1
                or stat.S_IMODE(current.st_mode) != 0o600
            ):
                raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Existing active state is unsafe.")
            descriptor = os.open(
                temporary,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW")
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=directory,
            )
            os.fchmod(descriptor, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short active-state write")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, "active.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        except RuntimeStateError:
            raise
        except OSError as exc:
            raise RuntimeStateError("RUNTIME_STATE_WRITE_FAILED", "Unable to commit runtime state.") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)

    def _archive_terminal_unlocked(self, state: Mapping[str, Any]) -> None:
        if state.get("status") not in TERMINAL_STATUSES:
            raise RuntimeStateError("SESSION_CONFLICT", "Only terminal sessions may be archived.")
        ensure_private_directory(self.sessions_path)
        target = self.sessions_path / f"{state['session_id_sha256']}.json"
        data = _pretty_json(state)
        directory = _directory_fd(self.sessions_path)
        temporary = f".session.{secrets.token_hex(16)}.tmp"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW"),
                0o600,
                dir_fd=directory,
            )
            os.fchmod(descriptor, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short terminal-state write")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, target.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        except OSError as exc:
            raise RuntimeStateError("RUNTIME_STATE_WRITE_FAILED", "Unable to archive terminal state.") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)


def state_fingerprint(state: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_canonical_json(dict(state))).hexdigest()
