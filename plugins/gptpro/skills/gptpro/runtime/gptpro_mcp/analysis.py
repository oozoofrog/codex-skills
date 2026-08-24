"""Owner-only append-only context-note ledger for schema-4 research."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from .errors import ToolError
from .runtime_state import RuntimeStateError, fsync_directory, open_private_regular
from .schema import canonical_json_bytes

ANALYSIS_SCHEMA_VERSION = 1
ANALYSIS_LEDGER_NAME = "mcp-analysis.jsonl"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_CLOSE_REASON = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_RAW_SECRET = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{16,}|\btunnel_[A-Za-z0-9_-]{16,128}\b|"
    r"\bgh[opusr]_[A-Za-z0-9]{20,}\b|"
    r"(?i:\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|auth[_-]?token)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=:-]{12,}))"
)
def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _event_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes({key: value for key, value in record.items() if key != "event_sha256"})
    ).hexdigest()


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ToolError("ANALYSIS_LEDGER_INVALID", f"{label} is not a lowercase SHA-256 value.")
    return value


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger write was incomplete.")
        offset += written


@dataclass(frozen=True)
class AnalysisBinding:
    package_id: str
    session_id_sha256: str
    manifest_sha256: str
    approval_event_sha256: str
    tool_schema_sha256: str
    limits_sha256: str
    max_events: int
    max_event_bytes: int
    max_ledger_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, str) or not 1 <= len(self.package_id) <= 128:
            raise ValueError("package_id is invalid")
        for name in (
            "session_id_sha256",
            "manifest_sha256",
            "approval_event_sha256",
            "tool_schema_sha256",
            "limits_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError(f"{name} is invalid")
        if not 1 <= self.max_events <= 512:
            raise ValueError("max_events is invalid")
        if not 256 <= self.max_event_bytes <= 64 * 1024:
            raise ValueError("max_event_bytes is invalid")
        if not self.max_event_bytes <= self.max_ledger_bytes <= 8 * 1_048_576:
            raise ValueError("max_ledger_bytes is invalid")


@dataclass(frozen=True)
class AnalysisSummary:
    header_sha256: str
    head_sha256: str
    final_sequence: int
    event_count: int
    closed: bool
    close_reason: str | None
    bytes_used: int


@dataclass(frozen=True)
class AnalysisAppendResult:
    event_id: str
    sequence: int
    event_sha256: str
    head_sha256: str
    idempotent_replay: bool


class AnalysisLedger:
    def __init__(self, path: Path, binding: AnalysisBinding) -> None:
        self.path = Path(path)
        self.binding = binding
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        try:
            unsafe_parent = not self.path.parent.is_dir() or self.path.parent.is_symlink()
        except OSError as exc:
            raise ToolError(
                "ANALYSIS_LEDGER_IO_FAILED",
                "The analysis ledger filesystem operation failed.",
            ) from exc
        if unsafe_parent:
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger parent is unsafe.")

    def create_header(self) -> str:
        with self._locked():
            if self.path.exists() or self.path.is_symlink():
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger already exists.")
            record: dict[str, Any] = {
                "record_type": "header",
                "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
                "sequence": 0,
                "created_at": _utc_now(),
                "package_id": self.binding.package_id,
                "session_id_sha256": self.binding.session_id_sha256,
                "manifest_sha256": self.binding.manifest_sha256,
                "approval_event_sha256": self.binding.approval_event_sha256,
                "tool_schema_sha256": self.binding.tool_schema_sha256,
                "limits_sha256": self.binding.limits_sha256,
                "max_events": self.binding.max_events,
                "max_event_bytes": self.binding.max_event_bytes,
                "max_ledger_bytes": self.binding.max_ledger_bytes,
                "previous_event_sha256": None,
            }
            record["event_sha256"] = _event_hash(record)
            payload = canonical_json_bytes(record) + b"\n"
            descriptor = open_private_regular(
                self.path,
                flags=os.O_WRONLY | os.O_EXCL,
                create=True,
            )
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            fsync_directory(self.path.parent)
            return record["event_sha256"]

    def verify(self) -> AnalysisSummary:
        with self._locked():
            records, size = self._read_verified_locked()
            return self._summary(records, size)

    def read_events(self) -> tuple[tuple[dict[str, Any], ...], AnalysisSummary]:
        with self._locked():
            records, size = self._read_verified_locked()
            return (
                tuple(dict(record) for record in records if record.get("record_type") == "event"),
                self._summary(records, size),
            )

    def append_codex_note(
        self,
        *,
        event_id: str,
        expected_head_sha256: str,
        summary: str,
        approval_event_sha256: str,
    ) -> AnalysisAppendResult:
        if not isinstance(event_id, str) or _EVENT_ID.fullmatch(event_id) is None:
            raise ToolError("ANALYSIS_EVENT_INVALID", "note event_id is invalid.")
        _require_hash(expected_head_sha256, "expected analysis head")
        _require_hash(approval_event_sha256, "note approval event")
        if not isinstance(summary, str) or not 1 <= len(summary) <= 16384:
            raise ToolError("ANALYSIS_EVENT_INVALID", "The Codex context note is invalid.")
        if _RAW_SECRET.search(summary):
            raise ToolError(
                "ANALYSIS_SECRET_REJECTED",
                "Secret-like material is not accepted in the analysis ledger.",
            )
        payload = {
            "actor": "codex",
            "event_id": event_id,
            "kind": "context_note",
            "summary": summary,
            "details": "",
            "citations": [],
            "approval_event_sha256": approval_event_sha256,
        }
        return self._append(payload, expected_head_sha256=expected_head_sha256)

    def close(self, *, reason: str) -> AnalysisSummary:
        if not isinstance(reason, str) or _CLOSE_REASON.fullmatch(reason) is None:
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis close reason is invalid.")
        with self._locked():
            records, size = self._read_verified_locked()
            summary = self._summary(records, size)
            if summary.closed:
                return summary
            footer: dict[str, Any] = {
                "record_type": "footer",
                "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
                "sequence": summary.final_sequence + 1,
                "closed_at": _utc_now(),
                "reason": reason,
                "event_count": summary.event_count,
                "previous_event_sha256": summary.head_sha256,
            }
            footer["event_sha256"] = _event_hash(footer)
            self._append_record_locked(footer, current_size=size)
            records.append(footer)
            return self._summary(records, size + len(canonical_json_bytes(footer)) + 1)

    def _append(
        self,
        payload: dict[str, Any],
        *,
        expected_head_sha256: str,
    ) -> AnalysisAppendResult:
        try:
            payload_bytes = canonical_json_bytes(payload)
        except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
            raise ToolError("ANALYSIS_EVENT_INVALID", "The analysis event is not canonical JSON.") from exc
        if len(payload_bytes) > self.binding.max_event_bytes:
            raise ToolError("ANALYSIS_EVENT_LIMIT_EXCEEDED", "The analysis event exceeds its byte limit.")
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        with self._locked():
            records, size = self._read_verified_locked()
            current = self._summary(records, size)
            if current.closed:
                raise ToolError("ANALYSIS_LEDGER_CLOSED", "The analysis ledger is closed.")
            for record in records:
                if record.get("record_type") == "event" and record.get("event_id") == payload["event_id"]:
                    if record.get("payload_sha256") != payload_sha256:
                        raise ToolError(
                            "ANALYSIS_EVENT_CONFLICT",
                            "The event_id is already bound to different analysis content.",
                        )
                    return AnalysisAppendResult(
                        event_id=payload["event_id"],
                        sequence=int(record["sequence"]),
                        event_sha256=str(record["event_sha256"]),
                        head_sha256=current.head_sha256,
                        idempotent_replay=True,
                    )
            if expected_head_sha256 != current.head_sha256:
                raise ToolError(
                    "ANALYSIS_HEAD_CONFLICT",
                    "The analysis ledger changed; refresh its status before appending.",
                    retryable=True,
                    recovery="Call gptpro_analysis_status and retry with its current head.",
                )
            if current.event_count >= self.binding.max_events:
                raise ToolError("ANALYSIS_EVENT_LIMIT_EXCEEDED", "The analysis event limit is exhausted.")
            record: dict[str, Any] = {
                "record_type": "event",
                "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
                "sequence": current.final_sequence + 1,
                "appended_at": _utc_now(),
                **payload,
                "payload_sha256": payload_sha256,
                "previous_event_sha256": current.head_sha256,
            }
            record["event_sha256"] = _event_hash(record)
            self._append_record_locked(record, current_size=size)
            return AnalysisAppendResult(
                event_id=payload["event_id"],
                sequence=int(record["sequence"]),
                event_sha256=str(record["event_sha256"]),
                head_sha256=str(record["event_sha256"]),
                idempotent_replay=False,
            )

    def _append_record_locked(self, record: dict[str, Any], *, current_size: int) -> None:
        payload = canonical_json_bytes(record) + b"\n"
        if current_size + len(payload) > self.binding.max_ledger_bytes:
            raise ToolError("ANALYSIS_LEDGER_LIMIT_EXCEEDED", "The analysis ledger byte limit is exhausted.")
        descriptor = open_private_regular(self.path, flags=os.O_WRONLY | os.O_APPEND)
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fsync_directory(self.path.parent)

    def _read_verified_locked(self) -> tuple[list[dict[str, Any]], int]:
        descriptor = open_private_regular(self.path, flags=os.O_RDONLY)
        try:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(65_536, self.binding.max_ledger_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > self.binding.max_ledger_bytes:
                    raise ToolError("ANALYSIS_LEDGER_LIMIT_EXCEEDED", "The analysis ledger is oversized.")
        finally:
            os.close(descriptor)
        data = b"".join(chunks)
        if not data or not data.endswith(b"\n"):
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger is truncated.")
        records: list[dict[str, Any]] = []
        try:
            for line in data.splitlines():
                record = json.loads(line.decode("utf-8"))
                if not isinstance(record, dict) or canonical_json_bytes(record) != line:
                    raise ValueError
                records.append(record)
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger is invalid.") from exc
        self._validate_records(records)
        return records, len(data)

    def _validate_records(self, records: list[dict[str, Any]]) -> None:
        if not records or records[0].get("record_type") != "header":
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger header is missing.")
        header = records[0]
        header_fields = {
            "record_type",
            "analysis_schema_version",
            "sequence",
            "created_at",
            "package_id",
            "session_id_sha256",
            "manifest_sha256",
            "approval_event_sha256",
            "tool_schema_sha256",
            "limits_sha256",
            "max_events",
            "max_event_bytes",
            "max_ledger_bytes",
            "previous_event_sha256",
            "event_sha256",
        }
        if set(header) != header_fields or not isinstance(header.get("created_at"), str):
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger header shape is invalid.")
        expected_header = {
            "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
            "sequence": 0,
            "package_id": self.binding.package_id,
            "session_id_sha256": self.binding.session_id_sha256,
            "manifest_sha256": self.binding.manifest_sha256,
            "approval_event_sha256": self.binding.approval_event_sha256,
            "tool_schema_sha256": self.binding.tool_schema_sha256,
            "limits_sha256": self.binding.limits_sha256,
            "max_events": self.binding.max_events,
            "max_event_bytes": self.binding.max_event_bytes,
            "max_ledger_bytes": self.binding.max_ledger_bytes,
            "previous_event_sha256": None,
        }
        if any(header.get(key) != value for key, value in expected_header.items()):
            raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger binding is invalid.")
        previous: str | None = None
        previous_time: datetime | None = None
        event_ids: set[str] = set()
        footer_seen = False
        event_count = 0
        for sequence, record in enumerate(records):
            if record.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION:
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger schema is invalid.")
            if record.get("sequence") != sequence or record.get("previous_event_sha256") != previous:
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger chain is invalid.")
            if record.get("event_sha256") != _event_hash(record):
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger hash is invalid.")
            kind = record.get("record_type")
            if sequence == 0 and kind != "header":
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger header is invalid.")
            timestamp_key = (
                "created_at" if kind == "header" else "appended_at" if kind == "event" else "closed_at"
            )
            try:
                timestamp = _parse_utc(record.get(timestamp_key))
            except (TypeError, ValueError) as exc:
                raise ToolError(
                    "ANALYSIS_LEDGER_INVALID", "The analysis ledger timestamp is invalid."
                ) from exc
            if previous_time is not None and timestamp < previous_time:
                raise ToolError(
                    "ANALYSIS_LEDGER_INVALID", "The analysis ledger timestamp moved backwards."
                )
            previous_time = timestamp
            if kind == "event":
                if footer_seen:
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger has data after its footer.")
                event_id = record.get("event_id")
                if not isinstance(event_id, str) or _EVENT_ID.fullmatch(event_id) is None or event_id in event_ids:
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis event identity is invalid.")
                event_ids.add(event_id)
                event_count += 1
                actor = record.get("actor")
                common_fields = {
                    "record_type", "analysis_schema_version", "sequence", "appended_at",
                    "actor", "event_id", "kind", "summary", "details", "citations",
                    "payload_sha256", "previous_event_sha256", "event_sha256",
                }
                expected_fields = (
                    common_fields | {"approval_event_sha256"}
                    if actor == "codex"
                    else set()
                )
                if (
                    set(record) != expected_fields
                    or not isinstance(record.get("summary"), str)
                    or not isinstance(record.get("details"), str)
                    or not isinstance(record.get("citations"), list)
                    or record.get("citations") != []
                    or _RAW_SECRET.search(record["summary"])
                    or _RAW_SECRET.search(record["details"])
                ):
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis event shape is invalid.")
                if actor == "codex" and (
                    record.get("kind") != "context_note"
                    or not 1 <= len(record["summary"]) <= 16384
                    or _SHA256.fullmatch(str(record.get("approval_event_sha256", ""))) is None
                    or record.get("details") != ""
                ):
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The Codex context-note event is invalid.")
                payload_bytes = canonical_json_bytes(
                    {
                        key: record[key]
                        for key in (
                            "actor",
                            "event_id",
                            "kind",
                            "summary",
                            "details",
                            "citations",
                            "approval_event_sha256",
                        )
                        if key in record
                    }
                )
                if (
                    len(payload_bytes) > self.binding.max_event_bytes
                    or record.get("payload_sha256") != hashlib.sha256(payload_bytes).hexdigest()
                ):
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis payload hash is invalid.")
            elif kind == "footer":
                footer_fields = {
                    "record_type", "analysis_schema_version", "sequence", "closed_at", "reason",
                    "event_count", "previous_event_sha256", "event_sha256",
                }
                if (
                    set(record) != footer_fields
                    or footer_seen
                    or sequence != len(records) - 1
                    or record.get("event_count") != event_count
                    or not isinstance(record.get("reason"), str)
                    or _CLOSE_REASON.fullmatch(record["reason"]) is None
                ):
                    raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger footer is invalid.")
                footer_seen = True
            elif kind != "header" or sequence != 0:
                raise ToolError("ANALYSIS_LEDGER_INVALID", "The analysis ledger record type is invalid.")
            previous = str(record["event_sha256"])
        if event_count > self.binding.max_events:
            raise ToolError("ANALYSIS_LEDGER_LIMIT_EXCEEDED", "The analysis ledger has too many events.")

    @staticmethod
    def _summary(records: list[dict[str, Any]], size: int) -> AnalysisSummary:
        return AnalysisSummary(
            header_sha256=str(records[0]["event_sha256"]),
            head_sha256=str(records[-1]["event_sha256"]),
            final_sequence=int(records[-1]["sequence"]),
            event_count=sum(record.get("record_type") == "event" for record in records),
            closed=records[-1].get("record_type") == "footer",
            close_reason=(
                str(records[-1]["reason"])
                if records[-1].get("record_type") == "footer"
                else None
            ),
            bytes_used=size,
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        descriptor = -1
        try:
            descriptor = open_private_regular(
                self.lock_path,
                flags=os.O_RDWR,
                create=True,
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
                descriptor = -1
        except ToolError:
            raise
        except (OSError, RuntimeStateError) as exc:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise ToolError(
                "ANALYSIS_LEDGER_IO_FAILED",
                "The analysis ledger filesystem operation failed.",
            ) from exc
