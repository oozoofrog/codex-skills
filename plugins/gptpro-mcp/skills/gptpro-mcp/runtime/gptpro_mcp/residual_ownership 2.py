"""Owner-only residual MCP lifecycle responsibility receipts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any, Mapping

from .runtime_state import RuntimeStateError, ensure_private_directory


RECEIPT_SCHEMA = "gptpro-mcp-residual-ownership-v1"
RECEIPT_DIRECTORY = "residual-ownership"
MAX_RECEIPT_BYTES = 64 * 1024
TERMINAL_AUTHORIZATION_STATUSES = frozenset({"revoked", "expired"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")


def canonical_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        return (
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def state_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


def session_binding_sha256(session_id_sha256: str) -> str:
    if not isinstance(session_id_sha256, str) or _SHA256.fullmatch(session_id_sha256) is None:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "The residual ownership session identity is invalid."
        )
    return sha256_bytes(
        b"gptpro-mcp-residual-ownership-session-v1\0"
        + session_id_sha256.encode("ascii")
    )


def receipt_path(root: Path, session_binding: str) -> Path:
    if not isinstance(session_binding, str) or _SHA256.fullmatch(session_binding) is None:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "The residual ownership binding is invalid."
        )
    return Path(root) / RECEIPT_DIRECTORY / f"{session_binding}.json"


def _open_existing_directory(path: Path) -> int | None:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNAVAILABLE",
            "The residual ownership directory cannot be inspected.",
        ) from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "The residual ownership directory must be owner-only mode 0700.",
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNAVAILABLE",
            "The residual ownership directory cannot be opened safely.",
        ) from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "The residual ownership directory changed while it was opened.",
        )
    return descriptor


def read_receipt(root: Path, session_binding: str) -> tuple[dict[str, Any], str] | None:
    """Read an existing receipt without creating any runtime path."""

    path = receipt_path(root, session_binding)
    directory = _open_existing_directory(path.parent)
    if directory is None:
        return None
    descriptor = -1
    try:
        try:
            descriptor = os.open(
                path.name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW")
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNAVAILABLE",
                "The residual ownership receipt cannot be opened safely.",
            ) from exc
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_RECEIPT_BYTES
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE",
                "The residual ownership receipt must be an owner-only regular file.",
            )
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_RECEIPT_BYTES:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The residual ownership receipt is too large."
            )
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The residual ownership receipt is invalid JSON."
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The residual ownership receipt is not an object."
            )
        return value, sha256_bytes(payload)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _validate_component(value: Any, *, label: str, allow_unknown_version: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"version", "tree_sha256"}:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", f"The residual {label} binding is invalid."
        )
    version = value.get("version")
    if version is None:
        if not allow_unknown_version:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", f"The residual {label} version is missing."
            )
    elif not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", f"The residual {label} version is invalid."
        )
    tree = value.get("tree_sha256")
    if not isinstance(tree, str) or _SHA256.fullmatch(tree) is None:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", f"The residual {label} tree hash is invalid."
        )
    return {"version": version, "tree_sha256": tree}


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(value)
    required = {
        "schema",
        "ownership_transferred",
        "exact_child_stop_proven",
        "terminal_authorization_status",
        "session_binding_sha256",
        "runtime_state_sha256",
        "runtime_revision",
        "package_evidence",
        "previous_base",
        "next_base",
        "owner_component",
        "recorded_at",
    }
    if set(receipt) != required or receipt.get("schema") != RECEIPT_SCHEMA:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "The residual ownership receipt contract is invalid."
        )
    if receipt.get("ownership_transferred") is not True:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual ownership was not explicitly transferred."
        )
    if not isinstance(receipt.get("exact_child_stop_proven"), bool):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual exact-child evidence is invalid."
        )
    if receipt.get("terminal_authorization_status") not in TERMINAL_AUTHORIZATION_STATUSES:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual authorization is not terminal."
        )
    for key in ("session_binding_sha256", "runtime_state_sha256"):
        if not isinstance(receipt.get(key), str) or _SHA256.fullmatch(receipt[key]) is None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", f"Residual receipt field {key} is invalid."
            )
    revision = receipt.get("runtime_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual runtime revision is invalid."
        )
    package = receipt.get("package_evidence")
    if not isinstance(package, dict) or set(package) != {"kind", "terminal_receipt_sha256"}:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual package evidence is invalid."
        )
    kind = package.get("kind")
    terminal_hash = package.get("terminal_receipt_sha256")
    if kind == "verified_terminal_receipt":
        if not isinstance(terminal_hash, str) or _SHA256.fullmatch(terminal_hash) is None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "Residual package receipt hash is invalid."
            )
    elif kind == "unavailable_confirmed":
        if terminal_hash is not None:
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE",
                "Unavailable package evidence may not invent a terminal receipt hash.",
            )
    else:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual package evidence kind is invalid."
        )
    _validate_component(receipt.get("previous_base"), label="previous base", allow_unknown_version=True)
    _validate_component(receipt.get("next_base"), label="next base", allow_unknown_version=False)
    _validate_component(receipt.get("owner_component"), label="owner component", allow_unknown_version=False)
    recorded_at = receipt.get("recorded_at")
    if not isinstance(recorded_at, str) or not recorded_at.endswith("Z") or len(recorded_at) > 64:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Residual receipt time is invalid."
        )
    return receipt


def receipt_matches(value: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    receipt = validate_receipt(value)
    for key, expected_value in expected.items():
        if receipt.get(key) != expected_value:
            return False
    return True


def write_receipt(
    root: Path, session_binding: str, value: Mapping[str, Any]
) -> tuple[dict[str, Any], str, bool]:
    """Atomically write once, or return an identical existing binding."""

    receipt = validate_receipt(value)
    path = receipt_path(root, session_binding)
    existing = read_receipt(root, session_binding)
    if existing is not None:
        existing_value, existing_sha256 = existing
        validate_receipt(existing_value)
        comparable = {key: value for key, value in receipt.items() if key != "recorded_at"}
        if receipt_matches(existing_value, comparable):
            return existing_value, existing_sha256, False
        raise RuntimeStateError(
            "GPTPRO_MCP_RESIDUAL_RECEIPT_STALE",
            "A residual ownership receipt already exists for different evidence.",
        )

    ensure_private_directory(Path(root), mode=0o700)
    ensure_private_directory(path.parent, mode=0o700)
    directory = _open_existing_directory(path.parent)
    if directory is None:  # pragma: no cover - ensure_private_directory just created it
        raise RuntimeStateError(
            "RUNTIME_STATE_UNAVAILABLE", "The residual ownership directory disappeared."
        )
    payload = canonical_json_bytes(receipt, pretty=True)
    temp_name = f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temp_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temp_name, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        except FileExistsError:
            try:
                os.unlink(temp_name, dir_fd=directory)
            except FileNotFoundError:
                pass
            current = read_receipt(root, session_binding)
            if current is None:
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNAVAILABLE",
                    "A concurrent residual receipt disappeared during adoption.",
                )
            current_value, current_sha256 = current
            comparable = {key: item for key, item in receipt.items() if key != "recorded_at"}
            if receipt_matches(current_value, comparable):
                return current_value, current_sha256, False
            raise RuntimeStateError(
                "GPTPRO_MCP_RESIDUAL_RECEIPT_STALE",
                "A concurrent residual ownership receipt binds different evidence.",
            )
        os.unlink(temp_name, dir_fd=directory)
        os.fsync(directory)
    except RuntimeStateError:
        raise
    except OSError as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNAVAILABLE",
            "The residual ownership receipt could not be committed atomically.",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temp_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        os.close(directory)
    committed = read_receipt(root, session_binding)
    if committed is None:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNAVAILABLE", "The residual ownership receipt was not persisted."
        )
    committed_value, committed_sha256 = committed
    if not receipt_matches(
        committed_value, {key: item for key, item in receipt.items() if key != "recorded_at"}
    ):
        raise RuntimeStateError(
            "GPTPRO_MCP_RESIDUAL_RECEIPT_STALE",
            "The persisted residual ownership receipt differs from the approved evidence.",
        )
    return committed_value, committed_sha256, True
