"""Crash-recoverable state/receipt pair commits for one handoff package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

from .package_lock import package_lifecycle_lock, package_lock_path
from .runtime_state import RuntimeStateError, fsync_directory

JOURNAL_SCHEMA_VERSION = 1
MAX_JOURNAL_BYTES = 8 * 1024 * 1024
_OPERATION = re.compile(r"[a-z][a-z0-9_-]{0,63}")
FaultInjector = Callable[[str], None]


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
            "RUNTIME_STATE_UNSAFE", "Package lifecycle JSON is not safely serializable."
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
            "RUNTIME_STATE_UNSAFE", "Package lifecycle JSON is not safely serializable."
        ) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _journal_path(handoff_dir: Path) -> Path:
    return package_lock_path(handoff_dir).with_suffix(".journal.json")


def lifecycle_journal_pending(handoff_dir: Path) -> bool:
    """Check for a journal without creating the private lock directory."""

    handoff = Path(handoff_dir).expanduser().resolve(strict=True)
    lock_root = handoff.parent / ".gptpro-lifecycle-locks"
    try:
        metadata = lock_root.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        return True
    identity = hashlib.sha256(str(handoff).encode("utf-8")).hexdigest()
    path = lock_root / f"{identity}.journal.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _read_regular(path: Path, *, maximum: int = MAX_JOURNAL_BYTES) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "A lifecycle file is unavailable.") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or metadata.st_size > maximum
    ):
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "A lifecycle file is unsafe.")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "A lifecycle file cannot be read.") from exc


def _atomic_private_write(path: Path, data: bytes) -> None:
    if len(data) > MAX_JOURNAL_BYTES:
        raise RuntimeStateError("RUNTIME_STATE_WRITE_FAILED", "A lifecycle write is too large.")
    parent = path.parent
    temporary = parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short lifecycle write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        fsync_directory(parent)
    except RuntimeStateError:
        raise
    except OSError as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_WRITE_FAILED", "Unable to commit package lifecycle evidence."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _load_object(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", f"The {label} is invalid JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeStateError("RUNTIME_STATE_UNSAFE", f"The {label} must be an object.")
    return value


def _journal_checksum(document: Mapping[str, Any]) -> str:
    return _sha256(_canonical_json({key: value for key, value in document.items() if key != "journal_sha256"}))


def _validate_pair_identity(state: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    if (
        state.get("package_id") != receipt.get("package_id")
        or state.get("schema_version") != receipt.get("schema_version")
    ):
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "Package state and receipt identities disagree."
        )


def recover_lifecycle_pair(handoff_dir: Path) -> bool:
    """Roll an interrupted exact journal forward; never infer unjournaled state."""

    handoff = Path(handoff_dir).expanduser().resolve(strict=True)
    with package_lifecycle_lock(handoff):
        journal_path = _journal_path(handoff)
        try:
            journal_bytes = _read_regular(journal_path)
        except RuntimeStateError:
            try:
                journal_path.lstat()
            except FileNotFoundError:
                return False
            raise
        journal = _load_object(journal_bytes, label="package lifecycle journal")
        if (
            journal.get("journal_schema_version") != JOURNAL_SCHEMA_VERSION
            or journal.get("handoff_sha256") != _sha256(str(handoff).encode("utf-8"))
            or journal.get("journal_sha256") != _journal_checksum(journal)
            or _OPERATION.fullmatch(str(journal.get("operation", ""))) is None
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The package lifecycle journal binding is invalid."
            )
        prior = journal.get("prior")
        next_pair = journal.get("next")
        if not isinstance(prior, dict) or not isinstance(next_pair, dict):
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The lifecycle journal pair is invalid.")
        next_state = next_pair.get("state")
        next_receipt = next_pair.get("receipt")
        if not isinstance(next_state, dict) or not isinstance(next_receipt, dict):
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The lifecycle journal payload is invalid.")
        _validate_pair_identity(next_state, next_receipt)
        next_state_bytes = _pretty_json(next_state)
        next_receipt_bytes = _pretty_json(next_receipt)
        if (
            next_pair.get("state_sha256") != _sha256(next_state_bytes)
            or next_pair.get("receipt_sha256") != _sha256(next_receipt_bytes)
        ):
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The lifecycle journal hashes are invalid.")

        state_path = handoff / "state.json"
        receipt_path = handoff / "receipt.json"
        current_state_hash = _sha256(_read_regular(state_path))
        current_receipt_hash = _sha256(_read_regular(receipt_path))
        if current_state_hash not in {prior.get("state_sha256"), next_pair["state_sha256"]}:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Package state diverged during recovery.")
        if current_receipt_hash not in {
            prior.get("receipt_sha256"),
            next_pair["receipt_sha256"],
        }:
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "Package receipt diverged during recovery.")

        _atomic_private_write(state_path, next_state_bytes)
        _atomic_private_write(receipt_path, next_receipt_bytes)
        if (
            _sha256(_read_regular(state_path)) != next_pair["state_sha256"]
            or _sha256(_read_regular(receipt_path)) != next_pair["receipt_sha256"]
        ):
            raise RuntimeStateError("RUNTIME_STATE_WRITE_FAILED", "Lifecycle recovery did not persist.")
        journal_path.unlink()
        fsync_directory(journal_path.parent)
        return True


def commit_lifecycle_pair(
    handoff_dir: Path,
    *,
    operation: str,
    state: Mapping[str, Any],
    receipt: Mapping[str, Any],
    fault_injector: FaultInjector | None = None,
) -> None:
    """Journal and atomically converge the two package lifecycle documents."""

    if _OPERATION.fullmatch(operation) is None:
        raise ValueError("package lifecycle operation is invalid")
    handoff = Path(handoff_dir).expanduser().resolve(strict=True)
    with package_lifecycle_lock(handoff):
        recover_lifecycle_pair(handoff)
        state_path = handoff / "state.json"
        receipt_path = handoff / "receipt.json"
        prior_state = _read_regular(state_path)
        prior_receipt = _read_regular(receipt_path)
        next_state = dict(state)
        next_receipt = dict(receipt)
        _validate_pair_identity(next_state, next_receipt)
        next_state_bytes = _pretty_json(next_state)
        next_receipt_bytes = _pretty_json(next_receipt)
        journal: dict[str, Any] = {
            "journal_schema_version": JOURNAL_SCHEMA_VERSION,
            "handoff_sha256": _sha256(str(handoff).encode("utf-8")),
            "operation": operation,
            "prior": {
                "state_sha256": _sha256(prior_state),
                "receipt_sha256": _sha256(prior_receipt),
            },
            "next": {
                "state": next_state,
                "receipt": next_receipt,
                "state_sha256": _sha256(next_state_bytes),
                "receipt_sha256": _sha256(next_receipt_bytes),
            },
        }
        journal["journal_sha256"] = _journal_checksum(journal)
        journal_path = _journal_path(handoff)
        _atomic_private_write(journal_path, _pretty_json(journal))
        if fault_injector is not None:
            fault_injector("journal")
        _atomic_private_write(state_path, next_state_bytes)
        if fault_injector is not None:
            fault_injector("state")
        _atomic_private_write(receipt_path, next_receipt_bytes)
        if fault_injector is not None:
            fault_injector("receipt")
        journal_path.unlink()
        fsync_directory(journal_path.parent)
