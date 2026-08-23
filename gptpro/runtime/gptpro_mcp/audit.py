"""Durable fail-before-return disclosure audit for one approved MCP session."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping

from .authorization import AuthorizationGrant
from .clock import Clock, ClockAnchor, parse_utc, utc_text
from .errors import ToolError
from .runtime_state import RuntimeStateError, RuntimeStateStore

AUDIT_SCHEMA_VERSION = 1
MAX_AUDIT_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RAW_SECRET = re.compile(r"(?:\bsk-[A-Za-z0-9_-]{16,}|\btunnel_[A-Za-z0-9_-]{16,128}\b)")


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
        raise ToolError(
            "AUDIT_CHAIN_INVALID", "The disclosure audit contains unsafe JSON values."
        ) from exc


def _event_hash(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "event_sha256"}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return value


def _safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("audit path is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("audit path is invalid") from exc
    if len(encoded) > 4096:
        raise ValueError("audit path is invalid")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or "\\" in value or "\0" in value or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError("audit path must be a relative canonical POSIX path")
    if _RAW_SECRET.search(value):
        raise ValueError("audit path contains forbidden secret-like material")
    return value


@dataclass(frozen=True)
class AuditBinding:
    package_id: str
    session_id_sha256: str
    manifest_sha256: str
    approval_event_sha256: str
    archive_sha256: str
    file_set_sha256: str
    tool_schema_sha256: str
    limits_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, str) or not 1 <= len(self.package_id) <= 128:
            raise ValueError("package_id is invalid")
        for name in (
            "session_id_sha256",
            "manifest_sha256",
            "approval_event_sha256",
            "archive_sha256",
            "file_set_sha256",
            "tool_schema_sha256",
            "limits_sha256",
        ):
            _require_hash(getattr(self, name), name)


@dataclass(frozen=True)
class AuditSummary:
    header_sha256: str
    head_sha256: str
    final_sequence: int
    tool_calls: int
    disclosed_bytes: int
    footer: bool
    last_committed_at: datetime


@dataclass(frozen=True)
class _VerifiedAudit:
    records: tuple[dict[str, Any], ...]
    summary: AuditSummary


class AuditLog:
    """Append-only JSONL hash chain that commits metadata before a result is returned."""

    def __init__(
        self,
        path: Path,
        binding: AuditBinding,
        *,
        runtime_store: RuntimeStateStore | None = None,
        clock: Clock | None = None,
        lock_timeout: float = 5.0,
        file_fsync: Callable[[int], None] = os.fsync,
        directory_fsync: Callable[[int], None] = os.fsync,
    ) -> None:
        self.path = Path(path)
        self.binding = binding
        self.runtime_store = runtime_store
        self.clock = clock or Clock()
        self.anchor: ClockAnchor = self.clock.anchor()
        self.lock_timeout = lock_timeout
        self._file_fsync = file_fsync
        self._directory_fsync = directory_fsync
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._validate_parent()

    def create_header(self) -> str:
        with self._locked():
            if self.path.exists() or self.path.is_symlink():
                raise ToolError(
                    "AUDIT_CHAIN_INVALID",
                    "The disclosure audit already exists or is unsafe.",
                    recovery="Revoke this session and activate a new package session.",
                )
            now = self.anchor.effective_now()
            record: dict[str, Any] = {
                "record_type": "header",
                "audit_schema_version": AUDIT_SCHEMA_VERSION,
                "sequence": 0,
                "created_at": utc_text(now),
                "package_id": self.binding.package_id,
                "session_id_sha256": self.binding.session_id_sha256,
                "manifest_sha256": self.binding.manifest_sha256,
                "approval_event_sha256": self.binding.approval_event_sha256,
                "archive_sha256": self.binding.archive_sha256,
                "file_set_sha256": self.binding.file_set_sha256,
                "tool_schema_sha256": self.binding.tool_schema_sha256,
                "limits_sha256": self.binding.limits_sha256,
                "previous_event_sha256": None,
            }
            record["event_sha256"] = _event_hash(record)
            self._create_file(record)
            return record["event_sha256"]

    def verify(self) -> AuditSummary:
        with self._locked():
            return self._verify_locked().summary

    def commit_before_return(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        audit_metadata: dict[str, Any],
        calls_used: int,
        disclosed_bytes: int,
    ) -> None:
        """Implement the Phase-2 DisclosureCommitter protocol without storing bodies."""

        try:
            _require_hash(request_id_sha256, "request id")
            _require_hash(arguments_sha256, "arguments")
            sanitized = _sanitize_metadata(tool, audit_metadata)
            if isinstance(calls_used, bool) or not isinstance(calls_used, int) or calls_used < 1:
                raise ValueError("calls_used is invalid")
            if isinstance(disclosed_bytes, bool) or not isinstance(disclosed_bytes, int) or disclosed_bytes < 0:
                raise ValueError("disclosed_bytes is invalid")
        except ValueError as exc:
            raise ToolError(
                "AUDIT_WRITE_FAILED",
                "Disclosure audit metadata is invalid.",
                recovery="Revoke this session and activate a new approved package session.",
            ) from exc

        if self.runtime_store is None:
            self._commit_with_audit_lock(
                grant=grant,
                tool=tool,
                request_id_sha256=request_id_sha256,
                arguments_sha256=arguments_sha256,
                metadata=sanitized,
                calls_used=calls_used,
                disclosed_bytes=disclosed_bytes,
            )
            return

        try:
            with self.runtime_store.locked() as transaction:
                state = transaction.read()
                activity_monotonic = self._validate_active_state(state, grant)
                self._commit_with_audit_lock(
                    grant=grant,
                    tool=tool,
                    request_id_sha256=request_id_sha256,
                    arguments_sha256=arguments_sha256,
                    metadata=sanitized,
                    calls_used=calls_used,
                    disclosed_bytes=disclosed_bytes,
                )
                if state is None:
                    raise RuntimeStateError("NO_ACTIVE_PACKAGE", "No active authorization exists.")
                updated = dict(state)
                updated["last_activity_monotonic"] = activity_monotonic
                updated["revision"] = int(state["revision"]) + 1
                transaction.write(updated)
        except RuntimeStateError as exc:
            raise ToolError(
                exc.code,
                "The active disclosure authorization is unavailable.",
                retryable=exc.retryable,
                recovery="Stop this session and activate a new approved package session.",
            ) from exc

    def append_footer(self, reason: str) -> AuditSummary:
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", reason):
            raise ValueError("footer reason is invalid")
        with self._locked():
            verified = self._verify_locked()
            if verified.summary.footer:
                return verified.summary
            now = self.anchor.effective_now(persisted_floor=verified.summary.last_committed_at)
            record: dict[str, Any] = {
                "record_type": "footer",
                "sequence": verified.summary.final_sequence + 1,
                "timestamp": utc_text(now),
                "reason": reason,
                "tool_calls": verified.summary.tool_calls,
                "disclosed_bytes": verified.summary.disclosed_bytes,
                "previous_event_sha256": verified.summary.head_sha256,
            }
            record["event_sha256"] = _event_hash(record)
            self._append_record(record)
            return self._verify_locked().summary

    def diagnostic_tool_records(self) -> tuple[dict[str, Any], ...]:
        """Return only already-audited hashes/counters needed for correlation."""

        with self._locked():
            verified = self._verify_locked()
            return tuple(
                {
                    "audit_sequence": record["sequence"],
                    "tool": record["tool"],
                    "jsonrpc_request_id_sha256": record[
                        "jsonrpc_request_id_sha256"
                    ],
                    "arguments_sha256": record["arguments_sha256"],
                    "disclosure_bytes": record["disclosure_bytes"],
                    "result": record["result"],
                }
                for record in verified.records
                if record.get("record_type") == "tool_call"
            )

    def append_rejection(
        self,
        *,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        error_code: str,
        calls_used: int,
    ) -> AuditSummary:
        """Durably record a rejected/cancelled call without repository disclosure."""

        try:
            if tool not in {"gptpro_package_info", "gptpro_repo_read", "gptpro_repo_search"}:
                raise ValueError("tool is not in the read-only catalog")
            _require_hash(request_id_sha256, "request id")
            _require_hash(arguments_sha256, "arguments")
            if not isinstance(error_code, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", error_code) is None:
                raise ValueError("error_code is invalid")
        except ValueError as exc:
            raise ToolError("AUDIT_WRITE_FAILED", "Rejected-call audit metadata is invalid.") from exc
        with self._locked():
            verified = self._verify_locked()
            if verified.summary.footer:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit is already closed.")
            if (
                isinstance(calls_used, bool)
                or not isinstance(calls_used, int)
                or calls_used != verified.summary.tool_calls + 1
            ):
                raise ToolError("AUDIT_WRITE_FAILED", "Rejected-call audit counter is invalid.")
            now = self.anchor.effective_now(persisted_floor=verified.summary.last_committed_at)
            record: dict[str, Any] = {
                "record_type": "tool_call",
                "sequence": verified.summary.final_sequence + 1,
                "timestamp": utc_text(now),
                "package_id": self.binding.package_id,
                "session_id_sha256": self.binding.session_id_sha256,
                "jsonrpc_request_id_sha256": request_id_sha256,
                "tool": tool,
                "arguments_sha256": arguments_sha256,
                "audit_metadata": {},
                "error_code": error_code,
                "disclosure_bytes": 0,
                "cumulative_disclosed_bytes": verified.summary.disclosed_bytes,
                "cumulative_tool_calls": calls_used,
                "result": "rejected",
                "previous_event_sha256": verified.summary.head_sha256,
            }
            record["event_sha256"] = _event_hash(record)
            self._append_record(record)
            return self._verify_locked().summary

    def _commit_with_audit_lock(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        metadata: dict[str, Any],
        calls_used: int,
        disclosed_bytes: int,
    ) -> None:
        with self._locked():
            verified = self._verify_locked()
            if verified.summary.footer:
                raise ToolError(
                    "AUDIT_CHAIN_INVALID",
                    "The disclosure audit is already closed.",
                    recovery="Activate a new approved package session.",
                )
            now = self.anchor.effective_now(persisted_floor=verified.summary.last_committed_at)
            grant.validate(grant.package_id, now=now)
            limits = grant.limits
            if calls_used != verified.summary.tool_calls + 1 or calls_used > limits["max_tool_calls"]:
                raise ToolError(
                    "CALL_LIMIT_EXCEEDED",
                    "The committed disclosure call count is invalid or exhausted.",
                    recovery="Stop this session and obtain approval for a new session.",
                )
            if (
                disclosed_bytes < verified.summary.disclosed_bytes
                or disclosed_bytes > limits["max_session_disclosure_bytes"]
            ):
                raise ToolError(
                    "DISCLOSURE_BUDGET_EXCEEDED",
                    "The committed disclosure budget is invalid or exhausted.",
                    recovery="Stop this session and obtain approval for a new session.",
                )
            call_bytes = disclosed_bytes - verified.summary.disclosed_bytes
            record: dict[str, Any] = {
                "record_type": "tool_call",
                "sequence": verified.summary.final_sequence + 1,
                "timestamp": utc_text(now),
                "package_id": self.binding.package_id,
                "session_id_sha256": self.binding.session_id_sha256,
                "jsonrpc_request_id_sha256": request_id_sha256,
                "tool": tool,
                "arguments_sha256": arguments_sha256,
                "audit_metadata": metadata,
                "disclosure_bytes": call_bytes,
                "cumulative_disclosed_bytes": disclosed_bytes,
                "cumulative_tool_calls": calls_used,
                "result": "committed_for_return",
                "previous_event_sha256": verified.summary.head_sha256,
            }
            record["event_sha256"] = _event_hash(record)
            try:
                self._append_record(record)
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(
                    "AUDIT_WRITE_FAILED",
                    "The disclosure audit could not be durably committed.",
                    recovery="Revoke this session and activate a new approved package session.",
                ) from exc

    def _validate_active_state(
        self, state: dict[str, Any] | None, grant: AuthorizationGrant
    ) -> float:
        if state is None or state.get("status") != "active":
            raise RuntimeStateError("NO_ACTIVE_PACKAGE", "No active authorization exists.")
        for key, expected in (
            ("package_id", grant.package_id),
            ("session_id_sha256", grant.session_id_sha256),
            ("manifest_sha256", grant.manifest_sha256),
            ("archive_sha256", grant.archive_sha256),
        ):
            if state.get(key) != expected:
                raise RuntimeStateError("SESSION_CONFLICT", "Active authorization binding changed.")
        observed_monotonic = self.clock.monotonic()
        if (
            isinstance(observed_monotonic, bool)
            or not isinstance(observed_monotonic, (int, float))
            or not math.isfinite(observed_monotonic)
        ):
            raise RuntimeStateError("RUNTIME_STATE_UNSAFE", "The monotonic runtime clock is invalid.")
        activated_monotonic = state.get("activated_monotonic")
        expires_monotonic = state.get("expires_monotonic")
        last_activity_monotonic = state.get("last_activity_monotonic")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (
                activated_monotonic,
                expires_monotonic,
                last_activity_monotonic,
            )
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The persisted monotonic session bounds are invalid."
            )
        current_monotonic = float(observed_monotonic)
        if current_monotonic < float(activated_monotonic) or current_monotonic < float(
            last_activity_monotonic
        ):
            raise RuntimeStateError(
                "RUNTIME_STATE_UNSAFE", "The monotonic runtime clock moved behind session state."
            )
        if current_monotonic >= float(expires_monotonic):
            raise RuntimeStateError("SESSION_EXPIRED", "Active authorization expired.")
        idle = state.get("idle_ttl_seconds")
        if isinstance(idle, int) and not isinstance(idle, bool):
            if current_monotonic >= float(last_activity_monotonic) + idle:
                raise RuntimeStateError("IDLE_TIMEOUT", "Active authorization reached its idle timeout.")

        expires_at = state.get("expires_at")
        if isinstance(expires_at, str):
            summary = self._verify_locked_without_lock()
            now = self.anchor.effective_now(persisted_floor=summary.last_committed_at)
            if now >= parse_utc(expires_at):
                raise RuntimeStateError("SESSION_EXPIRED", "Active authorization expired.")
        return current_monotonic

    def _verify_locked_without_lock(self) -> AuditSummary:
        """Read-only helper used while the caller already owns the global lock."""

        with self._locked():
            return self._verify_locked().summary

    @contextmanager
    def _locked(self) -> Iterator[None]:
        descriptor = self._open_regular(self.lock_path, flags=os.O_RDWR, create=True)
        deadline = time.monotonic() + self.lock_timeout
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ToolError(
                            "LOCK_TIMEOUT",
                            "The disclosure audit is busy.",
                            retryable=True,
                            recovery="Retry after the current bounded tool call finishes.",
                        )
                    time.sleep(0.01)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _validate_parent(self) -> None:
        try:
            metadata = self.path.parent.lstat()
        except OSError as exc:
            raise ToolError(
                "AUDIT_WRITE_FAILED", "The disclosure audit directory is unavailable."
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ToolError(
                "AUDIT_WRITE_FAILED",
                "The disclosure audit directory is not owner-controlled.",
            )

    def _open_regular(
        self,
        path: Path,
        *,
        flags: int,
        create: bool = False,
        exclusive: bool = False,
    ) -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise ToolError("AUDIT_WRITE_FAILED", "O_NOFOLLOW is required for disclosure audit files.")
        open_flags = flags | nofollow | getattr(os, "O_CLOEXEC", 0)
        descriptor = -1
        try:
            if create:
                try:
                    descriptor = os.open(path, open_flags | os.O_CREAT | os.O_EXCL, 0o600)
                    os.fchmod(descriptor, 0o600)
                except FileExistsError:
                    if exclusive:
                        raise ToolError(
                            "AUDIT_CHAIN_INVALID",
                            "The disclosure audit already exists.",
                            recovery="Activate a new package session.",
                        )
                    descriptor = os.open(path, open_flags)
            else:
                descriptor = os.open(path, open_flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ToolError(
                    "AUDIT_CHAIN_INVALID",
                    "The disclosure audit is not an owner-only regular file.",
                    recovery="Revoke this session and inspect the package audit state.",
                )
            return descriptor
        except ToolError:
            if descriptor >= 0:
                os.close(descriptor)
            raise
        except OSError as exc:
            if descriptor >= 0:
                os.close(descriptor)
            raise ToolError("AUDIT_WRITE_FAILED", "Unable to open the disclosure audit safely.") from exc

    def _create_file(self, record: dict[str, Any]) -> None:
        descriptor = -1
        directory = -1
        try:
            descriptor = self._open_regular(
                self.path,
                flags=os.O_WRONLY | os.O_APPEND,
                create=True,
                exclusive=True,
            )
            self._write_all(descriptor, _canonical_json(record) + b"\n")
            self._file_fsync(descriptor)
            directory = os.open(
                self.path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW"),
            )
            self._directory_fsync(directory)
        except ToolError:
            raise
        except OSError as exc:
            raise ToolError(
                "AUDIT_WRITE_FAILED",
                "The disclosure audit header could not be durably committed.",
                recovery="Revoke this session and activate a new package session.",
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory >= 0:
                os.close(directory)

    def _append_record(self, record: dict[str, Any]) -> None:
        descriptor = -1
        try:
            descriptor = self._open_regular(self.path, flags=os.O_WRONLY | os.O_APPEND)
            self._write_all(descriptor, _canonical_json(record) + b"\n")
            self._file_fsync(descriptor)
        except ToolError:
            raise
        except OSError as exc:
            raise ToolError(
                "AUDIT_WRITE_FAILED",
                "The disclosure audit record could not be durably committed.",
                recovery="Revoke this session and activate a new package session.",
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _write_all(descriptor: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short audit write")
            view = view[written:]

    def _verify_locked(self) -> _VerifiedAudit:
        descriptor = self._open_regular(self.path, flags=os.O_RDONLY)
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_size <= 0 or metadata.st_size > MAX_AUDIT_BYTES:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit size is invalid.")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read()
        finally:
            os.close(descriptor)
        if not payload.endswith(b"\n"):
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit is truncated.")
        records: list[dict[str, Any]] = []
        previous: str | None = None
        tool_calls = 0
        disclosed_bytes = 0
        last_at: datetime | None = None
        footer = False
        for sequence, raw_line in enumerate(payload.splitlines()):
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit contains invalid JSON.") from exc
            try:
                canonical = _canonical_json(record)
            except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
                raise ToolError(
                    "AUDIT_CHAIN_INVALID",
                    "The disclosure audit contains unsafe JSON values.",
                ) from exc
            if not isinstance(record, dict) or canonical != raw_line:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit is not canonical JSONL.")
            if record.get("sequence") != sequence or record.get("previous_event_sha256") != previous:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit sequence is invalid.")
            try:
                actual = _event_hash(record)
            except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
                raise ToolError(
                    "AUDIT_CHAIN_INVALID",
                    "The disclosure audit hash input is unsafe.",
                ) from exc
            if record.get("event_sha256") != actual:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit hash chain is invalid.")
            if sequence == 0:
                self._verify_header(record)
                last_at = parse_utc(record["created_at"])
            else:
                record_type = record.get("record_type")
                if footer:
                    raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit has records after its footer.")
                if record_type == "tool_call":
                    tool_calls = self._positive_counter(record.get("cumulative_tool_calls"), tool_calls)
                    previous_disclosed = disclosed_bytes
                    disclosed_bytes = self._nondecreasing_counter(record.get("cumulative_disclosed_bytes"), disclosed_bytes)
                    self._verify_tool_record(record, previous_disclosed)
                    last_at = self._verified_timestamp(record.get("timestamp"), last_at)
                elif record_type == "footer":
                    expected_footer_keys = {
                        "record_type",
                        "sequence",
                        "timestamp",
                        "reason",
                        "tool_calls",
                        "disclosed_bytes",
                        "previous_event_sha256",
                        "event_sha256",
                    }
                    if set(record) != expected_footer_keys:
                        raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit footer shape is invalid.")
                    if record.get("tool_calls") != tool_calls or record.get("disclosed_bytes") != disclosed_bytes:
                        raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit footer totals are invalid.")
                    last_at = self._verified_timestamp(record.get("timestamp"), last_at)
                    footer = True
                else:
                    raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit record type is invalid.")
            records.append(record)
            previous = actual
        assert last_at is not None and previous is not None
        summary = AuditSummary(
            header_sha256=records[0]["event_sha256"],
            head_sha256=previous,
            final_sequence=len(records) - 1,
            tool_calls=tool_calls,
            disclosed_bytes=disclosed_bytes,
            footer=footer,
            last_committed_at=last_at,
        )
        return _VerifiedAudit(tuple(records), summary)

    def _verify_header(self, record: dict[str, Any]) -> None:
        expected = {
            "record_type": "header",
            "audit_schema_version": AUDIT_SCHEMA_VERSION,
            "sequence": 0,
            "package_id": self.binding.package_id,
            "session_id_sha256": self.binding.session_id_sha256,
            "manifest_sha256": self.binding.manifest_sha256,
            "approval_event_sha256": self.binding.approval_event_sha256,
            "archive_sha256": self.binding.archive_sha256,
            "file_set_sha256": self.binding.file_set_sha256,
            "tool_schema_sha256": self.binding.tool_schema_sha256,
            "limits_sha256": self.binding.limits_sha256,
            "previous_event_sha256": None,
        }
        for key, value in expected.items():
            if record.get(key) != value:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header binding is invalid.")
        if set(record) != set(expected) | {"created_at", "event_sha256"}:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header shape is invalid.")
        try:
            parse_utc(str(record.get("created_at", "")))
        except ValueError as exc:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header time is invalid.") from exc

    def _verify_tool_record(self, record: dict[str, Any], previous_disclosed: int) -> None:
        common = {
            "record_type",
            "sequence",
            "timestamp",
            "package_id",
            "session_id_sha256",
            "jsonrpc_request_id_sha256",
            "tool",
            "arguments_sha256",
            "audit_metadata",
            "disclosure_bytes",
            "cumulative_disclosed_bytes",
            "cumulative_tool_calls",
            "result",
            "previous_event_sha256",
            "event_sha256",
        }
        if record.get("package_id") != self.binding.package_id or record.get("session_id_sha256") != self.binding.session_id_sha256:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit tool binding is invalid.")
        if record.get("tool") not in {"gptpro_package_info", "gptpro_repo_read", "gptpro_repo_search"}:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit tool name is invalid.")
        try:
            _require_hash(record.get("jsonrpc_request_id_sha256"), "request id")
            _require_hash(record.get("arguments_sha256"), "arguments")
        except ValueError as exc:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit hashes are invalid.") from exc
        call_bytes = record.get("disclosure_bytes")
        if (
            isinstance(call_bytes, bool)
            or not isinstance(call_bytes, int)
            or call_bytes < 0
            or previous_disclosed + call_bytes != record.get("cumulative_disclosed_bytes")
        ):
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit call byte count is invalid.")
        result = record.get("result")
        if result == "committed_for_return":
            if set(record) != common:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit tool-call shape is invalid.")
            try:
                if _sanitize_metadata(str(record.get("tool")), record.get("audit_metadata", {})) != record.get("audit_metadata"):
                    raise ValueError("audit metadata is not canonical")
            except ValueError as exc:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit metadata is invalid.") from exc
        elif result == "rejected":
            if set(record) != common | {"error_code"} or call_bytes != 0 or record.get("audit_metadata") != {}:
                raise ToolError("AUDIT_CHAIN_INVALID", "The rejected audit-call shape is invalid.")
            if not isinstance(record.get("error_code"), str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", record["error_code"]) is None:
                raise ToolError("AUDIT_CHAIN_INVALID", "The rejected audit error code is invalid.")
        else:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit result marker is invalid.")

    @staticmethod
    def _positive_counter(value: Any, previous: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value != previous + 1:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure call counter is invalid.")
        return value

    @staticmethod
    def _nondecreasing_counter(value: Any, previous: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < previous:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure byte counter is invalid.")
        return value

    @staticmethod
    def _verified_timestamp(value: Any, previous: datetime | None) -> datetime:
        try:
            timestamp = parse_utc(str(value or ""))
        except ValueError as exc:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit time is invalid.") from exc
        if previous is not None and timestamp < previous:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit time moved backwards.")
        return timestamp


def _sanitize_metadata(tool: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    if tool not in {"gptpro_package_info", "gptpro_repo_read", "gptpro_repo_search"}:
        raise ValueError("tool is not in the read-only catalog")
    if not isinstance(metadata, Mapping):
        raise ValueError("audit metadata must be an object")
    result_sha = _require_hash(metadata.get("result_sha256"), "result")
    if tool == "gptpro_package_info":
        paths = []
        raw_paths = metadata.get("paths", [])
        if not isinstance(raw_paths, list) or len(raw_paths) > 200:
            raise ValueError("path metadata is invalid")
        for item in raw_paths:
            if not isinstance(item, Mapping):
                raise ValueError("path metadata is invalid")
            size = item.get("size")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError("path size is invalid")
            paths.append(
                {"path": _safe_path(item.get("path")), "size": size, "sha256": _require_hash(item.get("sha256"), "file")}
            )
        return {"result_sha256": result_sha, "paths": paths}
    if tool == "gptpro_repo_read":
        returned = metadata.get("returned")
        requested = metadata.get("requested")
        if not isinstance(requested, Mapping) or not isinstance(returned, Mapping):
            raise ValueError("line range metadata is invalid")
        if isinstance(requested.get("start_line"), bool) or not isinstance(requested.get("start_line"), int):
            raise ValueError("requested start line is invalid")
        if requested.get("end_line") is not None and (
            isinstance(requested.get("end_line"), bool) or not isinstance(requested.get("end_line"), int)
        ):
            raise ValueError("requested end line is invalid")
        for key in ("start_line", "end_line"):
            if isinstance(returned.get(key), bool) or not isinstance(returned.get(key), int):
                raise ValueError("returned line range is invalid")
        content_bytes = metadata.get("content_bytes")
        if isinstance(content_bytes, bool) or not isinstance(content_bytes, int) or content_bytes < 0:
            raise ValueError("content byte metadata is invalid")
        return {
            "result_sha256": result_sha,
            "path": _safe_path(metadata.get("path")),
            "file_sha256": _require_hash(metadata.get("file_sha256"), "file"),
            "requested": {"start_line": requested["start_line"], "end_line": requested["end_line"]},
            "returned": {key: int(returned[key]) for key in ("start_line", "end_line")},
            "fragment_sha256": _require_hash(metadata.get("fragment_sha256"), "fragment"),
            "content_bytes": content_bytes,
        }
    query_hash = _require_hash(metadata.get("query_sha256"), "query")
    matches = []
    raw_matches = metadata.get("matches", [])
    if not isinstance(raw_matches, list) or len(raw_matches) > 100:
        raise ValueError("search match metadata is invalid")
    for item in raw_matches:
        if not isinstance(item, Mapping):
            raise ValueError("search match metadata is invalid")
        cleaned: dict[str, Any] = {"path": _safe_path(item.get("path"))}
        for key in ("line", "start_line", "end_line"):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("search line metadata is invalid")
            cleaned[key] = value
        cleaned["file_sha256"] = _require_hash(item.get("file_sha256"), "file")
        cleaned["excerpt_sha256"] = _require_hash(item.get("excerpt_sha256"), "excerpt")
        matches.append(cleaned)
    result_bytes = metadata.get("result_bytes")
    if isinstance(result_bytes, bool) or not isinstance(result_bytes, int) or result_bytes < 0:
        raise ValueError("search result byte metadata is invalid")
    return {
        "result_sha256": result_sha,
        "query_sha256": query_hash,
        "matches": matches,
        "result_bytes": result_bytes,
    }
