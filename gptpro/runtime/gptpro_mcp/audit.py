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
from .errors import CommitOutcomeUncertainError, ToolError
from .runtime_state import RuntimeStateError, RuntimeStateStore
from .schema import contract_for_schema, validate_tool_name
from .sensitive import secret_detector_names

LEGACY_AUDIT_SCHEMA_VERSION = 1
AUDIT_SCHEMA_VERSION = 2
LEGACY_ACCOUNTING_MODE = "legacy_tool_body_estimate"
ACCOUNTING_MODE = "complete_model_visible_result_v1"
MAX_AUDIT_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
UNADVERTISED_TOOL_LABEL = "<unadvertised>"


def _catalog_tools_for_schema_hash(tool_schema_sha256: str) -> frozenset[str]:
    for schema_version in (3, 4):
        contract = contract_for_schema(schema_version)
        if tool_schema_sha256 == contract["tool_schema_sha256"]:
            return frozenset(str(name) for name in contract["tool_names"])
    raise ValueError("tool schema hash is not an approved Web MCP catalog")


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
    if secret_detector_names(value):
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
    schema_version: int
    accounting_mode: str
    header_sha256: str
    head_sha256: str
    final_sequence: int
    tool_calls: int
    disclosed_bytes: int
    footer: bool
    close_reason: str | None
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
                "accounting_mode": ACCOUNTING_MODE,
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
            if tool not in _catalog_tools_for_schema_hash(self.binding.tool_schema_sha256):
                raise ValueError("tool is not in the package-bound catalog")
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

        committed: AuditSummary | None = None
        if self.runtime_store is None:
            try:
                self._commit_with_audit_lock(
                    grant=grant,
                    tool=tool,
                    request_id_sha256=request_id_sha256,
                    arguments_sha256=arguments_sha256,
                    metadata=sanitized,
                    calls_used=calls_used,
                    disclosed_bytes=disclosed_bytes,
                )
            except CommitOutcomeUncertainError:
                self._terminalize_uncertain_commit()
                raise
            return

        try:
            with self.runtime_store.locked() as transaction:
                state = transaction.read()
                activity_monotonic = self._validate_active_state(state, grant)
                committed = self._commit_with_audit_lock(
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
        except CommitOutcomeUncertainError:
            self._terminalize_uncertain_commit()
            raise
        except RuntimeStateError as exc:
            if committed is not None:
                self._terminalize_uncertain_commit()
                raise CommitOutcomeUncertainError(
                    calls_used=committed.tool_calls,
                    disclosed_bytes=committed.disclosed_bytes,
                ) from exc
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
                    **(
                        {"requested_tool_sha256": record["requested_tool_sha256"]}
                        if "requested_tool_sha256" in record
                        else {}
                    ),
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
            raw_tool = validate_tool_name(tool)
            allowed_tools = _catalog_tools_for_schema_hash(self.binding.tool_schema_sha256)
            audited_tool = raw_tool
            requested_tool_sha256: str | None = None
            if raw_tool not in allowed_tools:
                audited_tool = UNADVERTISED_TOOL_LABEL
                requested_tool_sha256 = hashlib.sha256(raw_tool.encode("utf-8")).hexdigest()
            _require_hash(request_id_sha256, "request id")
            _require_hash(arguments_sha256, "arguments")
            if not isinstance(error_code, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", error_code) is None:
                raise ValueError("error_code is invalid")
            if requested_tool_sha256 is not None and error_code != "MCP_INVALID_ARGUMENT":
                raise ValueError("unadvertised tool rejection code is invalid")
        except ValueError as exc:
            raise ToolError("AUDIT_WRITE_FAILED", "Rejected-call audit metadata is invalid.") from exc
        try:
            with self._locked():
                verified = self._verify_locked()
                self._require_current_accounting(verified.summary)
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
                    "tool": audited_tool,
                    "arguments_sha256": arguments_sha256,
                    "audit_metadata": {},
                    "error_code": error_code,
                    "disclosure_bytes": 0,
                    "cumulative_disclosed_bytes": verified.summary.disclosed_bytes,
                    "cumulative_tool_calls": calls_used,
                    "result": "rejected",
                    "previous_event_sha256": verified.summary.head_sha256,
                }
                if requested_tool_sha256 is not None:
                    record["requested_tool_sha256"] = requested_tool_sha256
                record["event_sha256"] = _event_hash(record)
                return self._append_record_verified(record, verified.summary)
        except CommitOutcomeUncertainError:
            self._terminalize_uncertain_commit()
            raise

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
    ) -> AuditSummary:
        with self._locked():
            verified = self._verify_locked()
            self._require_current_accounting(verified.summary)
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
            return self._append_record_verified(record, verified.summary)

    def _append_record_verified(
        self,
        record: dict[str, Any],
        before: AuditSummary,
    ) -> AuditSummary:
        """Append one exact record and classify failures without guessing.

        This runs while the audit lock is held.  If an exception occurs after
        bytes may have reached the file, the exact expected record is compared
        with a newly verified final chain.  An unchanged chain is a pre-append
        failure; an exact or indeterminate change is fail-closed ambiguity.
        """

        try:
            self._append_record(record)
        except Exception as exc:
            disposition, observed = self._classify_failed_append(record, before)
            if disposition == "absent":
                if isinstance(exc, ToolError):
                    raise
                raise ToolError(
                    "AUDIT_WRITE_FAILED",
                    "The disclosure audit could not be durably committed.",
                    recovery="Revoke this session and activate a new approved package session.",
                ) from exc
            raise CommitOutcomeUncertainError(
                calls_used=observed.tool_calls if observed is not None else None,
                disclosed_bytes=observed.disclosed_bytes if observed is not None else None,
            ) from exc
        try:
            observed = self._verify_locked().summary
        except ToolError as exc:
            raise CommitOutcomeUncertainError(
                calls_used=None,
                disclosed_bytes=None,
            ) from exc
        if (
            observed.head_sha256 != record["event_sha256"]
            or observed.final_sequence != record["sequence"]
            or observed.tool_calls != record["cumulative_tool_calls"]
            or observed.disclosed_bytes != record["cumulative_disclosed_bytes"]
        ):
            raise CommitOutcomeUncertainError(
                calls_used=observed.tool_calls,
                disclosed_bytes=observed.disclosed_bytes,
            )
        return observed

    def _classify_failed_append(
        self,
        record: Mapping[str, Any],
        before: AuditSummary,
    ) -> tuple[str, AuditSummary | None]:
        try:
            observed = self._verify_locked().summary
        except ToolError:
            return "indeterminate", None
        if (
            observed.head_sha256 == record.get("event_sha256")
            and observed.final_sequence == record.get("sequence")
            and observed.tool_calls == record.get("cumulative_tool_calls")
            and observed.disclosed_bytes == record.get("cumulative_disclosed_bytes")
        ):
            return "committed", observed
        if (
            observed.head_sha256 == before.head_sha256
            and observed.final_sequence == before.final_sequence
            and observed.tool_calls == before.tool_calls
            and observed.disclosed_bytes == before.disclosed_bytes
        ):
            return "absent", observed
        return "indeterminate", observed

    def _terminalize_uncertain_commit(self) -> None:
        """Best-effort persistent denial after a possibly committed call.

        Either the machine-global authorization becomes faulted or the audit is
        closed (normally both).  The caller also latches the in-process runtime,
        so no ambiguous call is automatically retried.
        """

        if self.runtime_store is not None:
            try:
                with self.runtime_store.locked() as transaction:
                    state = transaction.read()
                    if (
                        state is not None
                        and state.get("package_id") == self.binding.package_id
                        and state.get("session_id_sha256") == self.binding.session_id_sha256
                        and state.get("status") in {"activating", "active", "revoking"}
                    ):
                        updated = dict(state)
                        updated["status"] = "faulted"
                        updated["revision"] = int(state["revision"]) + 1
                        updated["updated_at"] = utc_text(datetime.now(timezone.utc))
                        transaction.write(updated)
            except (RuntimeStateError, ToolError, OSError, ValueError):
                pass
        try:
            self.append_footer("commit_outcome_uncertain")
        except (ToolError, OSError, ValueError):
            pass

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
        close_reason: str | None = None
        audit_schema_version: int | None = None
        accounting_mode: str | None = None
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
                audit_schema_version, accounting_mode = self._verify_header(record)
                last_at = parse_utc(record["created_at"])
            else:
                record_type = record.get("record_type")
                if footer:
                    raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit has records after its footer.")
                if record_type == "tool_call":
                    tool_calls = self._positive_counter(record.get("cumulative_tool_calls"), tool_calls)
                    previous_disclosed = disclosed_bytes
                    disclosed_bytes = self._nondecreasing_counter(record.get("cumulative_disclosed_bytes"), disclosed_bytes)
                    assert accounting_mode is not None
                    self._verify_tool_record(
                        record,
                        previous_disclosed,
                        accounting_mode=accounting_mode,
                    )
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
                    if not isinstance(record.get("reason"), str) or re.fullmatch(
                        r"[a-z][a-z0-9_-]{0,63}", record["reason"]
                    ) is None:
                        raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit footer reason is invalid.")
                    last_at = self._verified_timestamp(record.get("timestamp"), last_at)
                    footer = True
                    close_reason = record["reason"]
                else:
                    raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit record type is invalid.")
            records.append(record)
            previous = actual
        assert (
            last_at is not None
            and previous is not None
            and audit_schema_version is not None
            and accounting_mode is not None
        )
        summary = AuditSummary(
            schema_version=audit_schema_version,
            accounting_mode=accounting_mode,
            header_sha256=records[0]["event_sha256"],
            head_sha256=previous,
            final_sequence=len(records) - 1,
            tool_calls=tool_calls,
            disclosed_bytes=disclosed_bytes,
            footer=footer,
            close_reason=close_reason,
            last_committed_at=last_at,
        )
        return _VerifiedAudit(tuple(records), summary)

    def _verify_header(self, record: dict[str, Any]) -> tuple[int, str]:
        schema_version = record.get("audit_schema_version")
        if type(schema_version) is not int:
            raise ToolError(
                "AUDIT_CHAIN_INVALID",
                "The disclosure audit schema version must be an exact integer.",
            )
        if schema_version == LEGACY_AUDIT_SCHEMA_VERSION:
            accounting_mode = LEGACY_ACCOUNTING_MODE
        elif (
            schema_version == AUDIT_SCHEMA_VERSION
            and record.get("accounting_mode") == ACCOUNTING_MODE
        ):
            accounting_mode = ACCOUNTING_MODE
        else:
            raise ToolError(
                "AUDIT_CHAIN_INVALID",
                "The disclosure audit schema or accounting mode is unsupported.",
            )
        expected = {
            "record_type": "header",
            "audit_schema_version": schema_version,
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
        if schema_version == AUDIT_SCHEMA_VERSION:
            expected["accounting_mode"] = ACCOUNTING_MODE
        for key, value in expected.items():
            if record.get(key) != value:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header binding is invalid.")
        if set(record) != set(expected) | {"created_at", "event_sha256"}:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header shape is invalid.")
        try:
            parse_utc(str(record.get("created_at", "")))
        except ValueError as exc:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit header time is invalid.") from exc
        return schema_version, accounting_mode

    def _verify_tool_record(
        self,
        record: dict[str, Any],
        previous_disclosed: int,
        *,
        accounting_mode: str,
    ) -> None:
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
        try:
            allowed_tools = _catalog_tools_for_schema_hash(self.binding.tool_schema_sha256)
        except ValueError as exc:
            raise ToolError(
                "AUDIT_CHAIN_INVALID", "The disclosure audit tool schema is invalid."
            ) from exc
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
            if record.get("tool") not in allowed_tools or set(record) != common:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit tool-call shape is invalid.")
            try:
                if _sanitize_metadata(str(record.get("tool")), record.get("audit_metadata", {})) != record.get("audit_metadata"):
                    raise ValueError("audit metadata is not canonical")
            except ValueError as exc:
                raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit metadata is invalid.") from exc
        elif result == "rejected":
            unadvertised = record.get("tool") == UNADVERTISED_TOOL_LABEL
            expected = common | {"error_code"}
            if unadvertised:
                expected.add("requested_tool_sha256")
            if (
                set(record) != expected
                or call_bytes != 0
                or record.get("audit_metadata") != {}
                or (not unadvertised and record.get("tool") not in allowed_tools)
            ):
                raise ToolError("AUDIT_CHAIN_INVALID", "The rejected audit-call shape is invalid.")
            if not isinstance(record.get("error_code"), str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", record["error_code"]) is None:
                raise ToolError("AUDIT_CHAIN_INVALID", "The rejected audit error code is invalid.")
            if unadvertised:
                if accounting_mode != ACCOUNTING_MODE:
                    raise ToolError(
                        "AUDIT_CHAIN_INVALID",
                        "Legacy disclosure audits cannot contain unadvertised-tool records.",
                    )
                try:
                    _require_hash(record.get("requested_tool_sha256"), "requested tool")
                except ValueError as exc:
                    raise ToolError(
                        "AUDIT_CHAIN_INVALID",
                        "The rejected audit tool binding is invalid.",
                    ) from exc
                if record["error_code"] != "MCP_INVALID_ARGUMENT":
                    raise ToolError(
                        "AUDIT_CHAIN_INVALID",
                        "The unadvertised-tool rejection code is invalid.",
                    )
        else:
            raise ToolError("AUDIT_CHAIN_INVALID", "The disclosure audit result marker is invalid.")

    @staticmethod
    def _require_current_accounting(summary: AuditSummary) -> None:
        if (
            summary.schema_version != AUDIT_SCHEMA_VERSION
            or summary.accounting_mode != ACCOUNTING_MODE
        ):
            raise ToolError(
                "AUDIT_SCHEMA_UNSUPPORTED",
                "Legacy disclosure evidence is verification-only and cannot accept new calls.",
                recovery="Close the legacy session and activate a new approved package session.",
            )

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
    known_tools = set().union(
        *(_catalog_tools_for_schema_hash(contract_for_schema(version)["tool_schema_sha256"])
          for version in (3, 4))
    )
    if tool not in known_tools:
        raise ValueError("tool is not in an approved Web MCP catalog")
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
        if "fragments" in metadata:
            raw_fragments = metadata.get("fragments")
            if not isinstance(raw_fragments, list) or len(raw_fragments) > 16:
                raise ValueError("read fragment metadata is invalid")
            fragments: list[dict[str, Any]] = []
            for item in raw_fragments:
                if not isinstance(item, Mapping):
                    raise ValueError("read fragment metadata is invalid")
                range_index = _nonnegative_integer(item.get("range_index"), "range index")
                start_line = _positive_integer(item.get("start_line"), "fragment start")
                end_line = _positive_integer(item.get("end_line"), "fragment end")
                if end_line < start_line:
                    raise ValueError("read fragment range is invalid")
                fragments.append(
                    {
                        "range_index": range_index,
                        "start_line": start_line,
                        "end_line": end_line,
                        "fragment_sha256": _require_hash(
                            item.get("fragment_sha256"), "fragment"
                        ),
                    }
                )
            return {
                "result_sha256": result_sha,
                "path": _safe_path(metadata.get("path")),
                "file_sha256": _require_hash(metadata.get("file_sha256"), "file"),
                "fragments": fragments,
                "content_bytes": _nonnegative_integer(
                    metadata.get("content_bytes"), "content bytes"
                ),
            }
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
        content_bytes = _nonnegative_integer(metadata.get("content_bytes"), "content bytes")
        return {
            "result_sha256": result_sha,
            "path": _safe_path(metadata.get("path")),
            "file_sha256": _require_hash(metadata.get("file_sha256"), "file"),
            "requested": {"start_line": requested["start_line"], "end_line": requested["end_line"]},
            "returned": {key: int(returned[key]) for key in ("start_line", "end_line")},
            "fragment_sha256": _require_hash(metadata.get("fragment_sha256"), "fragment"),
            "content_bytes": content_bytes,
        }
    if tool == "gptpro_workspace_map":
        entries = []
        raw_entries = metadata.get("entries", [])
        if not isinstance(raw_entries, list) or len(raw_entries) > 200:
            raise ValueError("workspace-map metadata is invalid")
        for item in raw_entries:
            if not isinstance(item, Mapping) or item.get("kind") not in {"file", "directory"}:
                raise ValueError("workspace-map entry is invalid")
            cleaned = {"path": _safe_path(item.get("path")), "kind": item["kind"]}
            if item["kind"] == "file":
                cleaned.update(
                    {
                        "size": _nonnegative_integer(item.get("size"), "workspace file size"),
                        "sha256": _require_hash(item.get("sha256"), "workspace file"),
                    }
                )
            else:
                if item.get("size") is not None or item.get("sha256") is not None:
                    raise ValueError("workspace directory metadata is invalid")
                cleaned.update({"size": None, "sha256": None})
            entries.append(cleaned)
        return {
            "result_sha256": result_sha,
            "entries": entries,
            "result_bytes": _nonnegative_integer(metadata.get("result_bytes"), "result bytes"),
        }
    if tool == "gptpro_repo_diff":
        entries = []
        raw_entries = metadata.get("entries", [])
        if not isinstance(raw_entries, list) or len(raw_entries) > 100:
            raise ValueError("diff metadata is invalid")
        for item in raw_entries:
            if not isinstance(item, Mapping) or item.get("status") not in {
                "added", "modified", "deleted"
            }:
                raise ValueError("diff entry metadata is invalid")
            old_hash = item.get("old_sha256")
            if item["status"] == "added":
                if old_hash is not None:
                    raise ValueError("added diff metadata has an old hash")
            else:
                old_hash = _require_hash(old_hash, "old diff file")
            new_hash = item.get("new_sha256")
            if item["status"] == "deleted":
                if new_hash is not None:
                    raise ValueError("deleted diff metadata has a new hash")
            else:
                new_hash = _require_hash(new_hash, "new diff file")
            diff_hash = item.get("diff_sha256")
            if diff_hash is not None:
                diff_hash = _require_hash(diff_hash, "diff")
            entries.append(
                {
                    "path": _safe_path(item.get("path")),
                    "status": item["status"],
                    "old_sha256": old_hash,
                    "new_sha256": new_hash,
                    "diff_sha256": diff_hash,
                }
            )
        return {
            "result_sha256": result_sha,
            "entries": entries,
            "result_bytes": _nonnegative_integer(metadata.get("result_bytes"), "result bytes"),
        }
    if tool == "gptpro_artifact_read":
        artifact_id = metadata.get("artifact_id")
        if not isinstance(artifact_id, str) or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{0,63}", artifact_id
        ) is None:
            raise ValueError("artifact identity is invalid")
        returned = metadata.get("returned")
        if not isinstance(returned, Mapping):
            raise ValueError("artifact line range is invalid")
        start_line = _positive_integer(returned.get("start_line"), "artifact start")
        end_line = _nonnegative_integer(returned.get("end_line"), "artifact end")
        if end_line and end_line < start_line:
            raise ValueError("artifact line range is invalid")
        return {
            "result_sha256": result_sha,
            "artifact_id": artifact_id,
            "sha256": _require_hash(metadata.get("sha256"), "artifact"),
            "returned": {"start_line": start_line, "end_line": end_line},
            "fragment_sha256": _require_hash(metadata.get("fragment_sha256"), "fragment"),
            "content_bytes": _nonnegative_integer(
                metadata.get("content_bytes"), "content bytes"
            ),
        }
    if tool == "gptpro_analysis_status":
        events = []
        raw_events = metadata.get("events", [])
        if not isinstance(raw_events, list) or len(raw_events) > 50:
            raise ValueError("analysis status metadata is invalid")
        for item in raw_events:
            if not isinstance(item, Mapping):
                raise ValueError("analysis event metadata is invalid")
            events.append(
                {
                    "sequence": _positive_integer(item.get("sequence"), "analysis sequence"),
                    "event_id_sha256": _require_hash(
                        item.get("event_id_sha256"), "analysis event id"
                    ),
                    "event_sha256": _require_hash(item.get("event_sha256"), "analysis event"),
                }
            )
        return {
            "result_sha256": result_sha,
            "head_sha256": _require_hash(metadata.get("head_sha256"), "analysis head"),
            "events": events,
            "result_bytes": _nonnegative_integer(metadata.get("result_bytes"), "result bytes"),
        }
    query_hashes_raw = metadata.get("query_sha256s")
    if query_hashes_raw is not None:
        if not isinstance(query_hashes_raw, list) or not 1 <= len(query_hashes_raw) <= 8:
            raise ValueError("search query hash metadata is invalid")
        query_hashes = [_require_hash(value, "query") for value in query_hashes_raw]
        query_metadata: dict[str, Any] = {"query_sha256s": query_hashes}
    else:
        query_metadata = {"query_sha256": _require_hash(metadata.get("query_sha256"), "query")}
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
    result_bytes = _nonnegative_integer(metadata.get("result_bytes"), "search result bytes")
    return {
        "result_sha256": result_sha,
        **query_metadata,
        "matches": matches,
        "result_bytes": result_bytes,
    }


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} is invalid")
    return value


def _positive_integer(value: Any, label: str) -> int:
    result = _nonnegative_integer(value, label)
    if result < 1:
        raise ValueError(f"{label} is invalid")
    return result
