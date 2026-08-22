"""Bounded, sanitized protocol-sequence evidence for one MCP session."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .runtime_state import RuntimeStateError, fsync_directory, open_private_regular

TRACE_SCHEMA_VERSION = 1
TRACE_FILE_NAME = "mcp-protocol-trace.jsonl"
MAX_TRACE_EVENTS = 64
MAX_TRACE_BYTES = 128 * 1024

SAFE_METHODS = frozenset(
    {
        "invalid_frame",
        "initialize",
        "initialized_notification",
        "server_discover",
        "tools_list",
        "tools_call",
        "ping",
        "cancelled_notification",
        "trace_control",
        "unknown",
    }
)
SAFE_STAGES = frozenset({"decision", "processed", "response"})
SAFE_OUTCOMES = frozenset(
    {
        "accepted",
        "ignored",
        "pong",
        "method_not_supported",
        "invalid_request",
        "invalid_params",
        "not_initialized",
        "tools_listed",
        "tool_dispatched",
        "duplicate_initialize",
        "server_busy",
        "parse_error",
        "frame_too_large",
        "response_flushed",
        "trace_truncated",
    }
)
SAFE_READINESS = frozenset({"uninitialized", "initialize_acknowledged", "ready"})
SAFE_VERSION_CLASSES = frozenset(
    {"missing", "malformed", "supported_preferred", "supported_legacy", "unsupported"}
)
SAFE_PROTOCOL_VERSIONS = frozenset(
    {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"}
)
SAFE_CLOSE_REASONS = frozenset({"stdio_eof", "protocol_broken"})
SAFE_TRACE_FAILURE_CODES = frozenset(
    {
        "PROTOCOL_TRACE_BINDING_MISMATCH",
        "PROTOCOL_TRACE_INVALID",
        "PROTOCOL_TRACE_LOCK_TIMEOUT",
        "PROTOCOL_TRACE_UNAVAILABLE",
        "PROTOCOL_TRACE_UNSAFE",
    }
)

_METHOD_CLASSIFICATION = {
    "initialize": "initialize",
    "notifications/initialized": "initialized_notification",
    "server/discover": "server_discover",
    "tools/list": "tools_list",
    "tools/call": "tools_call",
    "ping": "ping",
    "notifications/cancelled": "cancelled_notification",
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PACKAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


@dataclass
class ProtocolTraceError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ProtocolTraceBinding:
    package_id: str
    session_id_sha256: str
    manifest_sha256: str
    approval_event_sha256: str
    archive_sha256: str
    file_set_sha256: str
    tool_schema_sha256: str
    audit_header_sha256: str
    tunnel_profile_sha256: str
    tunnel_client_binary_sha256: str
    mcp_target_sha256: str
    mcp_runtime_tree_sha256: str

    def __post_init__(self) -> None:
        if _PACKAGE_ID.fullmatch(self.package_id) is None:
            raise ValueError("package identity is invalid")
        for name in (
            "session_id_sha256",
            "manifest_sha256",
            "approval_event_sha256",
            "archive_sha256",
            "file_set_sha256",
            "tool_schema_sha256",
            "audit_header_sha256",
            "tunnel_profile_sha256",
            "tunnel_client_binary_sha256",
            "mcp_target_sha256",
            "mcp_runtime_tree_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} is invalid")


@dataclass(frozen=True)
class ProtocolTraceSummary:
    header_sha256: str
    head_sha256: str
    event_count: int
    truncated: bool
    closed: bool
    close_reason: str | None
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ProtocolTraceArtifactIdentity:
    sha256: str
    byte_count: int


def classify_method(method: Any) -> str:
    if not isinstance(method, str):
        return "invalid_frame"
    return _METHOD_CLASSIFICATION.get(method, "unknown")


def classify_requested_version(
    requested: Any,
    *,
    supported_versions: tuple[str, ...],
    preferred_version: str,
) -> str:
    if requested is None:
        return "missing"
    if not isinstance(requested, str):
        return "malformed"
    if requested == preferred_version:
        return "supported_preferred"
    if requested in supported_versions:
        return "supported_legacy"
    return "unsupported"


def safe_requested_version(requested: Any) -> str | None:
    return requested if isinstance(requested, str) and requested in SAFE_PROTOCOL_VERSIONS else None


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolTraceError(
            "PROTOCOL_TRACE_UNSAFE", "Protocol trace data is not safely serializable."
        ) from exc


def _event_hash(record: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "event_sha256"}
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _write_all(descriptor: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        count = os.write(descriptor, payload[written:])
        if count <= 0:
            raise OSError("short write")
        written += count


class ProtocolTrace:
    """Package-local JSONL hash chain containing only bounded protocol enums."""

    def __init__(
        self,
        handoff_dir: Path,
        binding: ProtocolTraceBinding,
        *,
        lock_timeout: float = 5.0,
    ) -> None:
        root = Path(handoff_dir)
        if not root.is_absolute() or root.name in {"", ".", ".."}:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_UNSAFE", "The protocol trace directory is invalid."
            )
        if (
            not isinstance(lock_timeout, (int, float))
            or isinstance(lock_timeout, bool)
            or not math.isfinite(lock_timeout)
            or lock_timeout <= 0
        ):
            raise ValueError("lock timeout must be positive")
        self.handoff_dir = root
        self.binding = binding
        self.lock_timeout = float(lock_timeout)
        self.path = root / TRACE_FILE_NAME
        self.lock_path = root / f".{TRACE_FILE_NAME}.lock"

    def open_or_create(self) -> ProtocolTraceSummary:
        with self._locked(create=True):
            descriptor = self._open_trace(create=True, writable=True)
            try:
                raw = self._read(descriptor)
                if not raw:
                    header = self._header()
                    self._append_record(descriptor, header)
                    fsync_directory(self.handoff_dir)
                    return self._summary((header,))
                return self._summary(self._parse_and_verify(raw))
            finally:
                os.close(descriptor)

    def record(
        self,
        *,
        method: str,
        stage: str,
        outcome: str,
        readiness_before: str,
        readiness_after: str,
        requested_version_class: str | None = None,
        requested_version: str | None = None,
        negotiated_version: str | None = None,
    ) -> ProtocolTraceSummary:
        self._validate_event_values(
            method=method,
            stage=stage,
            outcome=outcome,
            readiness_before=readiness_before,
            readiness_after=readiness_after,
            requested_version_class=requested_version_class,
            requested_version=requested_version,
            negotiated_version=negotiated_version,
        )
        with self._locked(create=False):
            descriptor = self._open_trace(create=False, writable=True)
            try:
                records = self._parse_and_verify(self._read(descriptor))
                summary = self._summary(records)
                if summary.closed:
                    raise ProtocolTraceError(
                        "PROTOCOL_TRACE_CLOSED", "The protocol trace is already closed."
                    )
                if summary.truncated:
                    return summary
                if summary.event_count >= MAX_TRACE_EVENTS - 1:
                    record = self._event_record(
                        records,
                        method="trace_control",
                        stage="decision",
                        outcome="trace_truncated",
                        readiness_before=readiness_before,
                        readiness_after=readiness_before,
                    )
                else:
                    record = self._event_record(
                        records,
                        method=method,
                        stage=stage,
                        outcome=outcome,
                        readiness_before=readiness_before,
                        readiness_after=readiness_after,
                        requested_version_class=requested_version_class,
                        requested_version=requested_version,
                        negotiated_version=negotiated_version,
                    )
                self._append_record(descriptor, record)
                return self._summary((*records, record))
            finally:
                os.close(descriptor)

    def close(self, reason: str) -> ProtocolTraceSummary:
        if reason not in SAFE_CLOSE_REASONS:
            raise ValueError("trace close reason is unsafe")
        with self._locked(create=False):
            descriptor = self._open_trace(create=False, writable=True)
            try:
                records = self._parse_and_verify(self._read(descriptor))
                summary = self._summary(records)
                if summary.closed:
                    if summary.close_reason != reason:
                        raise ProtocolTraceError(
                            "PROTOCOL_TRACE_INVALID", "The protocol trace close reason changed."
                        )
                    return summary
                footer: dict[str, Any] = {
                    "record_type": "footer",
                    "sequence": summary.event_count + 1,
                    "closed": True,
                    "close_reason": reason,
                    "event_count": summary.event_count,
                    "truncated": summary.truncated,
                    "previous_event_sha256": records[-1]["event_sha256"],
                }
                footer["event_sha256"] = _event_hash(footer)
                self._append_record(descriptor, footer)
                return self._summary((*records, footer))
            finally:
                os.close(descriptor)

    def verify(self) -> ProtocolTraceSummary:
        with self._locked(create=False):
            descriptor = self._open_trace(create=False, writable=False)
            try:
                return self._summary(self._parse_and_verify(self._read(descriptor)))
            finally:
                os.close(descriptor)

    def fingerprint(self) -> ProtocolTraceArtifactIdentity:
        """Hash safe owner-only bytes without interpreting malformed JSONL."""

        with self._locked(create=False):
            descriptor = self._open_trace(create=False, writable=False)
            try:
                raw = self._read(descriptor)
                return ProtocolTraceArtifactIdentity(
                    sha256=hashlib.sha256(raw).hexdigest(),
                    byte_count=len(raw),
                )
            finally:
                os.close(descriptor)

    def _header(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "record_type": "header",
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "sequence": 0,
            "package_id": self.binding.package_id,
            "session_id_sha256": self.binding.session_id_sha256,
            "manifest_sha256": self.binding.manifest_sha256,
            "approval_event_sha256": self.binding.approval_event_sha256,
            "archive_sha256": self.binding.archive_sha256,
            "file_set_sha256": self.binding.file_set_sha256,
            "tool_schema_sha256": self.binding.tool_schema_sha256,
            "audit_header_sha256": self.binding.audit_header_sha256,
            "tunnel_profile_sha256": self.binding.tunnel_profile_sha256,
            "tunnel_client_binary_sha256": self.binding.tunnel_client_binary_sha256,
            "mcp_target_sha256": self.binding.mcp_target_sha256,
            "mcp_runtime_tree_sha256": self.binding.mcp_runtime_tree_sha256,
            "max_events": MAX_TRACE_EVENTS,
            "previous_event_sha256": None,
        }
        record["event_sha256"] = _event_hash(record)
        return record

    def _event_record(
        self,
        records: tuple[dict[str, Any], ...],
        *,
        method: str,
        stage: str,
        outcome: str,
        readiness_before: str,
        readiness_after: str,
        requested_version_class: str | None = None,
        requested_version: str | None = None,
        negotiated_version: str | None = None,
    ) -> dict[str, Any]:
        event_count = sum(record.get("record_type") == "event" for record in records)
        record: dict[str, Any] = {
            "record_type": "event",
            "sequence": event_count + 1,
            "method": method,
            "stage": stage,
            "outcome": outcome,
            "readiness_before": readiness_before,
            "readiness_after": readiness_after,
            "previous_event_sha256": records[-1]["event_sha256"],
        }
        if requested_version_class is not None:
            record["requested_version_class"] = requested_version_class
        if requested_version is not None:
            record["requested_version"] = requested_version
        if negotiated_version is not None:
            record["negotiated_version"] = negotiated_version
        record["event_sha256"] = _event_hash(record)
        return record

    def _open_trace(self, *, create: bool, writable: bool) -> int:
        try:
            flags = os.O_RDWR | os.O_APPEND if writable else os.O_RDONLY
            return open_private_regular(
                self.path,
                flags=flags,
                create=create,
                mode=0o600,
            )
        except RuntimeStateError as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_UNSAFE",
                "The owner-only protocol trace path is unavailable.",
            ) from exc

    def _read(self, descriptor: int) -> bytes:
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_size > MAX_TRACE_BYTES:
                raise ProtocolTraceError(
                    "PROTOCOL_TRACE_INVALID", "The protocol trace exceeds its size limit."
                )
            os.lseek(descriptor, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise ProtocolTraceError(
                        "PROTOCOL_TRACE_INVALID", "The protocol trace changed while being read."
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            extra = os.read(descriptor, 1)
            final_metadata = os.fstat(descriptor)
            if (
                extra
                or final_metadata.st_size != metadata.st_size
                or final_metadata.st_mtime_ns != metadata.st_mtime_ns
                or final_metadata.st_ctime_ns != metadata.st_ctime_ns
            ):
                raise ProtocolTraceError(
                    "PROTOCOL_TRACE_INVALID", "The protocol trace changed while being read."
                )
            raw = b"".join(chunks)
        except ProtocolTraceError:
            raise
        except OSError as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_UNAVAILABLE", "The protocol trace could not be read."
            ) from exc
        if len(raw) > MAX_TRACE_BYTES:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace exceeds its size limit."
            )
        return raw

    def _append_record(self, descriptor: int, record: Mapping[str, Any]) -> None:
        payload = _canonical_json(record) + b"\n"
        try:
            os.lseek(descriptor, 0, os.SEEK_END)
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        except OSError as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_UNAVAILABLE", "The protocol trace could not be persisted."
            ) from exc

    def _parse_and_verify(self, raw: bytes) -> tuple[dict[str, Any], ...]:
        if not raw or not raw.endswith(b"\n"):
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace is incomplete."
            )
        try:
            lines = raw.decode("ascii", "strict").splitlines()
            records = tuple(json.loads(line) for line in lines)
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace is malformed."
            ) from exc
        if not records or len(records) > MAX_TRACE_EVENTS + 2:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace record count is invalid."
            )
        if not all(isinstance(record, dict) for record in records):
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace contains an invalid record."
            )
        if records[0] != self._header():
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_BINDING_MISMATCH",
                "The protocol trace does not match this package session.",
            )
        previous = records[0]["event_sha256"]
        event_count = 0
        footer_seen = False
        truncated = False
        for index, record in enumerate(records[1:], start=1):
            if record.get("record_type") == "footer":
                if footer_seen or index != len(records) - 1:
                    raise ProtocolTraceError(
                        "PROTOCOL_TRACE_INVALID", "The protocol trace footer is misplaced."
                    )
                self._validate_footer(record, event_count=event_count, truncated=truncated)
                footer_seen = True
            else:
                if footer_seen:
                    raise ProtocolTraceError(
                        "PROTOCOL_TRACE_INVALID", "The protocol trace contains data after closure."
                    )
                event_count += 1
                self._validate_event(record, sequence=event_count)
                if record.get("outcome") == "trace_truncated":
                    if event_count != MAX_TRACE_EVENTS:
                        raise ProtocolTraceError(
                            "PROTOCOL_TRACE_INVALID", "The trace truncation marker is misplaced."
                        )
                    truncated = True
            if record.get("previous_event_sha256") != previous:
                raise ProtocolTraceError(
                    "PROTOCOL_TRACE_INVALID", "The protocol trace hash chain is invalid."
                )
            if record.get("event_sha256") != _event_hash(record):
                raise ProtocolTraceError(
                    "PROTOCOL_TRACE_INVALID", "The protocol trace event hash is invalid."
                )
            previous = record["event_sha256"]
        return records

    def _validate_event(self, record: dict[str, Any], *, sequence: int) -> None:
        required = {
            "record_type",
            "sequence",
            "method",
            "stage",
            "outcome",
            "readiness_before",
            "readiness_after",
            "previous_event_sha256",
            "event_sha256",
        }
        optional = {"requested_version_class", "requested_version", "negotiated_version"}
        keys = set(record)
        if not required <= keys or not keys <= required | optional:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace event shape is invalid."
            )
        if record.get("record_type") != "event" or record.get("sequence") != sequence:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace sequence is invalid."
            )
        try:
            self._validate_event_values(
                method=record.get("method"),
                stage=record.get("stage"),
                outcome=record.get("outcome"),
                readiness_before=record.get("readiness_before"),
                readiness_after=record.get("readiness_after"),
                requested_version_class=record.get("requested_version_class"),
                requested_version=record.get("requested_version"),
                negotiated_version=record.get("negotiated_version"),
            )
        except ValueError as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace contains an unsafe enum."
            ) from exc
        if record.get("outcome") == "trace_truncated" and (
            record.get("method") != "trace_control" or record.get("stage") != "decision"
        ):
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The trace truncation marker is invalid."
            )

    @staticmethod
    def _validate_footer(record: dict[str, Any], *, event_count: int, truncated: bool) -> None:
        required = {
            "record_type",
            "sequence",
            "closed",
            "close_reason",
            "event_count",
            "truncated",
            "previous_event_sha256",
            "event_sha256",
        }
        if set(record) != required or any(
            (
                record.get("record_type") != "footer",
                record.get("sequence") != event_count + 1,
                record.get("closed") is not True,
                record.get("close_reason") not in SAFE_CLOSE_REASONS,
                record.get("event_count") != event_count,
                record.get("truncated") is not truncated,
            )
        ):
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_INVALID", "The protocol trace footer is invalid."
            )

    @staticmethod
    def _validate_event_values(
        *,
        method: Any,
        stage: Any,
        outcome: Any,
        readiness_before: Any,
        readiness_after: Any,
        requested_version_class: Any = None,
        requested_version: Any = None,
        negotiated_version: Any = None,
    ) -> None:
        if not isinstance(method, str) or method not in SAFE_METHODS:
            raise ValueError("method enum is unsafe")
        if not isinstance(stage, str) or stage not in SAFE_STAGES:
            raise ValueError("stage enum is unsafe")
        if not isinstance(outcome, str) or outcome not in SAFE_OUTCOMES:
            raise ValueError("outcome enum is unsafe")
        if (stage == "response") != (outcome == "response_flushed"):
            raise ValueError("response stage and outcome are inconsistent")
        if (method == "trace_control") != (outcome == "trace_truncated"):
            raise ValueError("trace-control event is inconsistent")
        if (
            not isinstance(readiness_before, str)
            or not isinstance(readiness_after, str)
            or readiness_before not in SAFE_READINESS
            or readiness_after not in SAFE_READINESS
        ):
            raise ValueError("readiness enum is unsafe")
        if requested_version_class is not None and (
            not isinstance(requested_version_class, str)
            or requested_version_class not in SAFE_VERSION_CLASSES
        ):
            raise ValueError("requested-version classification is unsafe")
        for version in (requested_version, negotiated_version):
            if version is not None and (
                not isinstance(version, str) or version not in SAFE_PROTOCOL_VERSIONS
            ):
                raise ValueError("protocol version is unsafe")

    @staticmethod
    def _summary(records: tuple[dict[str, Any], ...]) -> ProtocolTraceSummary:
        events = tuple(dict(record) for record in records if record.get("record_type") == "event")
        footer = records[-1] if records[-1].get("record_type") == "footer" else None
        truncated = bool(events and events[-1].get("outcome") == "trace_truncated")
        return ProtocolTraceSummary(
            header_sha256=records[0]["event_sha256"],
            head_sha256=records[-1]["event_sha256"],
            event_count=len(events),
            truncated=truncated,
            closed=footer is not None,
            close_reason=footer.get("close_reason") if footer is not None else None,
            events=events,
        )

    @contextmanager
    def _locked(self, *, create: bool) -> Iterator[None]:
        try:
            descriptor = open_private_regular(
                self.lock_path,
                flags=os.O_RDWR,
                create=create,
                mode=0o600,
            )
        except RuntimeStateError as exc:
            raise ProtocolTraceError(
                "PROTOCOL_TRACE_UNSAFE", "The protocol trace lock is unavailable."
            ) from exc
        deadline = time.monotonic() + self.lock_timeout
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ProtocolTraceError(
                            "PROTOCOL_TRACE_LOCK_TIMEOUT", "The protocol trace lock is busy."
                        )
                    time.sleep(0.01)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
