"""Dependency-free legacy JSON-RPC/MCP stdio state machine."""

from __future__ import annotations

import copy
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TextIO

from .errors import CancelledError, ToolError, UnknownToolError
from .protocol_trace import (
    ProtocolTrace,
    ProtocolTraceError,
    classify_method,
    classify_requested_version,
    safe_requested_version,
)
from .schema import contract_for_schema, validate_tool_name
from .tools import ToolRuntime, error_result

JSONRPC_VERSION = "2.0"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
PREFERRED_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
MAX_INPUT_FRAME_CHARS = 262_144
MAX_INFLIGHT_REQUESTS = 1


def _rpc_error(request_id: Any, code: int, message: str, *, stable_code: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message, "data": {"code": stable_code}},
    }


def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _valid_id(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError:
            return False
        return True
    return isinstance(value, (int, float)) and (not isinstance(value, float) or math.isfinite(value))


def _request_key(value: Any) -> tuple[str, Any]:
    return type(value).__name__, value


class LegacyMcpServer:
    """Line-framed server with an independent reader and cancellable workers."""

    def __init__(
        self,
        tools: ToolRuntime,
        *,
        max_workers: int = 1,
        trace: ProtocolTrace | None = None,
        contract: dict[str, Any] | None = None,
    ) -> None:
        self._tools = tools
        self._trace = trace
        selected = dict(contract or contract_for_schema(3))
        self._tool_catalog = tuple(copy.deepcopy(selected["tool_catalog"]))
        self._tool_names = frozenset(selected["tool_names"])
        self._server_name = str(selected["server_name"])
        self._server_version = str(selected["server_version"])
        self._server_instructions = str(selected["server_instructions"])
        self._state_lock = threading.Lock()
        self._writer_lock = threading.Lock()
        self._initialize_seen = False
        self._initialize_replay_used = False
        self._initialized = False
        self._discovery_seen = False
        self._request_scoped_compat = False
        self._initialize_requested_supported = False
        self._protocol_version: str | None = None
        self._inflight: dict[tuple[str, Any], threading.Event] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gptpro-mcp")
        self._output: TextIO | None = None
        self._stderr: TextIO | None = None
        self._broken = threading.Event()
        # The active Tunnel closes this process's stdin before forwarding
        # SIGTERM.  Keep the handler side effect to one atomic Python
        # assignment; the normal read-loop/finally path remains responsible
        # for proving EOF and writing the trace footer.
        self._parent_shutdown_requested = False
        self._input_eof_observed = False

    def note_parent_shutdown(self) -> None:
        """Record an attended parent stop without doing I/O in a signal handler."""

        self._parent_shutdown_requested = True

    def serve(self, input_stream: TextIO, output_stream: TextIO, stderr: TextIO) -> int:
        self._output = output_stream
        self._stderr = stderr
        try:
            while True:
                if self._broken.is_set():
                    break
                line = input_stream.readline(MAX_INPUT_FRAME_CHARS + 1)
                if not line:
                    self._input_eof_observed = True
                    break
                if len(line) > MAX_INPUT_FRAME_CHARS:
                    while line and not line.endswith("\n"):
                        line = input_stream.readline(MAX_INPUT_FRAME_CHARS + 1)
                    if not self._record_trace(
                        "invalid_frame",
                        "frame_too_large",
                        readiness_before=self._readiness(),
                        readiness_after=self._readiness(),
                    ):
                        break
                    self._write_traced(
                        _rpc_error(
                            None,
                            -32600,
                            "Invalid Request",
                            stable_code="MCP_FRAME_TOO_LARGE",
                        ),
                        "invalid_frame",
                    )
                    continue
                self.process_line(line)
        finally:
            self._executor.shutdown(wait=True, cancel_futures=False)
            if self._trace is not None:
                try:
                    if self._broken.is_set() or not self._input_eof_observed:
                        close_reason = "protocol_broken"
                    elif self._parent_shutdown_requested:
                        close_reason = "parent_shutdown"
                    else:
                        close_reason = "stdio_eof"
                    self._trace.close(close_reason)
                except (ProtocolTraceError, ValueError):
                    self._broken.set()
                    self._log("MCP_PROTOCOL_TRACE_FAILED")
        return 0 if not self._broken.is_set() else 1

    def process_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError):
            readiness = self._readiness()
            if not self._record_trace(
                "invalid_frame",
                "parse_error",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(None, -32700, "Parse error", stable_code="MCP_PROTOCOL_ERROR"),
                "invalid_frame",
            )
            return
        if not isinstance(message, dict):
            readiness = self._readiness()
            if not self._record_trace(
                "invalid_frame",
                "invalid_request",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(None, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"),
                "invalid_frame",
            )
            return
        if message.get("jsonrpc") != JSONRPC_VERSION or not isinstance(message.get("method"), str):
            request_id = message.get("id") if _valid_id(message.get("id")) else None
            readiness = self._readiness()
            if not self._record_trace(
                classify_method(message.get("method")),
                "invalid_request",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(request_id, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"),
                classify_method(message.get("method")),
            )
            return
        has_id = "id" in message
        request_id = message.get("id")
        if has_id and not _valid_id(request_id):
            readiness = self._readiness()
            if not self._record_trace(
                classify_method(message.get("method")),
                "invalid_request",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(None, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"),
                classify_method(message.get("method")),
            )
            return
        params = message.get("params", {})
        if not isinstance(params, dict):
            readiness = self._readiness()
            if not self._record_trace(
                classify_method(message.get("method")),
                "invalid_params",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            if has_id:
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code="MCP_INVALID_ARGUMENT",
                    ),
                    classify_method(message.get("method")),
                )
            return
        method = message["method"]
        if not has_id:
            self._notification(method, params)
            return
        self._request(request_id, method, params)

    def _notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "notifications/initialized":
            with self._state_lock:
                before = self._readiness_locked()
                accepted = self._initialize_seen
                if accepted:
                    self._initialized = True
                after = self._readiness_locked()
            if not self._record_trace(
                "initialized_notification",
                "accepted" if accepted else "ignored",
                stage="processed",
                readiness_before=before,
                readiness_after=after,
            ):
                return
            return
        if method == "notifications/cancelled":
            request_id = params.get("requestId")
            event: threading.Event | None = None
            if _valid_id(request_id):
                with self._state_lock:
                    event = self._inflight.get(_request_key(request_id))
            readiness = self._readiness()
            if event is not None:
                event.set()
            if not self._record_trace(
                "cancelled_notification",
                "accepted" if event is not None else "ignored",
                stage="processed",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            return
        # Unknown notifications are intentionally ignored without a response.
        readiness = self._readiness()
        self._record_trace(
            "unknown",
            "ignored",
            stage="processed",
            readiness_before=readiness,
            readiness_after=readiness,
        )

    def _request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        if method == "ping":
            readiness = self._readiness()
            if not self._record_trace(
                "ping",
                "pong",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(_rpc_result(request_id, {}), "ping")
            return
        if method == "initialize":
            self._initialize(request_id, params)
            return
        if method == "server/discover":
            # This server intentionally remains legacy-only. Close any earlier
            # lifecycle before returning Method not found. The shared Tunnel
            # stdio child may then deliver one probe initialize and one identical
            # connector initialize before the readiness notification.
            metadata = params.get("_meta")
            discover_requested = (
                metadata.get("io.modelcontextprotocol/protocolVersion")
                if isinstance(metadata, dict)
                else None
            )
            discover_version_class = classify_requested_version(
                discover_requested,
                supported_versions=SUPPORTED_PROTOCOL_VERSIONS,
                preferred_version=PREFERRED_PROTOCOL_VERSION,
            )
            with self._state_lock:
                before = self._readiness_locked()
            if not self._record_trace(
                "server_discover",
                "method_not_supported",
                readiness_before=before,
                readiness_after="uninitialized",
                requested_version_class=discover_version_class,
                requested_version=safe_requested_version(discover_requested),
            ):
                return
            with self._state_lock:
                self._initialize_seen = False
                self._initialize_replay_used = False
                self._initialized = False
                self._discovery_seen = True
                self._request_scoped_compat = False
                self._initialize_requested_supported = False
                self._protocol_version = None
            self._write_traced(
                _rpc_error(
                    request_id,
                    -32601,
                    "Method not found",
                    stable_code="MCP_METHOD_NOT_SUPPORTED",
                ),
                "server_discover",
            )
            return
        if method in {"notifications/initialized", "notifications/cancelled"}:
            readiness = self._readiness()
            if not self._record_trace(
                classify_method(method),
                "method_not_supported",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(
                    request_id,
                    -32601,
                    "Method not found",
                    stable_code="MCP_METHOD_NOT_SUPPORTED",
                ),
                classify_method(method),
            )
            return
        with self._state_lock:
            ready = self._initialized
        if method == "tools/call" and not ready and self._valid_tool_call_params(
            params, require_advertised=True
        ):
            with self._state_lock:
                before = self._readiness_locked()
                request_scoped_compat = (
                    self._initialize_seen
                    and self._initialize_replay_used
                    and not self._initialized
                    and not self._discovery_seen
                    and self._initialize_requested_supported
                    and self._protocol_version in SUPPORTED_PROTOCOL_VERSIONS
                )
                if request_scoped_compat:
                    self._initialized = True
                    self._request_scoped_compat = True
                after = self._readiness_locked()
            if request_scoped_compat:
                if not self._record_trace(
                    "tools_call",
                    "request_scoped_initialized",
                    stage="processed",
                    readiness_before=before,
                    readiness_after=after,
                ):
                    return
                ready = True
        if method in {"tools/list", "tools/call"} and not ready:
            readiness = self._readiness()
            if not self._record_trace(
                classify_method(method),
                "not_initialized",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_error(
                    request_id,
                    -32600,
                    "Client is not initialized",
                    stable_code="MCP_PROTOCOL_ERROR",
                ),
                classify_method(method),
            )
            return
        if method == "tools/list":
            if params:
                readiness = self._readiness()
                if not self._record_trace(
                    "tools_list",
                    "invalid_params",
                    readiness_before=readiness,
                    readiness_after=readiness,
                ):
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code="MCP_INVALID_ARGUMENT",
                    ),
                    "tools_list",
                )
                return
            readiness = self._readiness()
            if not self._record_trace(
                "tools_list",
                "tools_listed",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                return
            self._write_traced(
                _rpc_result(request_id, {"tools": copy.deepcopy(list(self._tool_catalog))}),
                "tools_list",
            )
            return
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not self._valid_tool_call_params(params):
                readiness = self._readiness()
                if not self._record_trace(
                    "tools_call",
                    "invalid_params",
                    readiness_before=readiness,
                    readiness_after=readiness,
                ):
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code="MCP_INVALID_ARGUMENT",
                    ),
                    "tools_call",
                )
                return
            key = _request_key(request_id)
            cancel = threading.Event()
            with self._state_lock:
                duplicate = key in self._inflight
                busy = not duplicate and len(self._inflight) >= MAX_INFLIGHT_REQUESTS
                if not duplicate and not busy:
                    self._inflight[key] = cancel
            if duplicate:
                readiness = self._readiness()
                if not self._record_trace(
                    "tools_call",
                    "invalid_request",
                    readiness_before=readiness,
                    readiness_after=readiness,
                ):
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32600,
                        "Duplicate request id",
                        stable_code="MCP_PROTOCOL_ERROR",
                    ),
                    "tools_call",
                )
                return
            if busy:
                readiness = self._readiness()
                if not self._record_trace(
                    "tools_call",
                    "server_busy",
                    readiness_before=readiness,
                    readiness_after=readiness,
                ):
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32000,
                        "Server busy",
                        stable_code="MCP_SERVER_BUSY",
                    ),
                    "tools_call",
                )
                return
            readiness = self._readiness()
            if not self._record_trace(
                "tools_call",
                "tool_dispatched",
                readiness_before=readiness,
                readiness_after=readiness,
            ):
                with self._state_lock:
                    self._inflight.pop(key, None)
                cancel.set()
                return
            self._executor.submit(self._tool_worker, key, request_id, name, arguments, cancel)
            return
        readiness = self._readiness()
        if not self._record_trace(
            "unknown",
            "method_not_supported",
            readiness_before=readiness,
            readiness_after=readiness,
        ):
            return
        self._write_traced(
            _rpc_error(
                request_id,
                -32601,
                "Method not found",
                stable_code="MCP_METHOD_NOT_SUPPORTED",
            ),
            "unknown",
        )

    def _initialize(self, request_id: Any, params: dict[str, Any]) -> None:
        requested = params.get("protocolVersion")
        requested_class = classify_requested_version(
            requested,
            supported_versions=SUPPORTED_PROTOCOL_VERSIONS,
            preferred_version=PREFERRED_PROTOCOL_VERSION,
        )
        if not isinstance(requested, str):
            readiness = self._readiness()
            if not self._record_trace(
                "initialize",
                "invalid_params",
                readiness_before=readiness,
                readiness_after=readiness,
                requested_version_class=requested_class,
                requested_version=safe_requested_version(requested),
            ):
                return
            self._write_traced(
                _rpc_error(
                    request_id,
                    -32602,
                    "Invalid params",
                    stable_code="MCP_INVALID_ARGUMENT",
                ),
                "initialize",
            )
            return
        with self._state_lock:
            before = self._readiness_locked()
            duplicate = self._initialize_seen
            replayable = (
                duplicate
                and (
                    (
                        before == "initialize_acknowledged"
                        and not self._initialize_replay_used
                    )
                    or (
                        before == "ready"
                        and (
                            self._request_scoped_compat
                            or not self._discovery_seen
                        )
                    )
                )
                and requested == self._protocol_version
            )
            if not duplicate:
                negotiated = (
                    requested
                    if requested in SUPPORTED_PROTOCOL_VERSIONS
                    else PREFERRED_PROTOCOL_VERSION
                )
            elif replayable:
                negotiated = self._protocol_version
        if duplicate:
            if replayable:
                if not self._record_trace(
                    "initialize",
                    "initialize_replayed",
                    readiness_before=before,
                    readiness_after=before,
                    requested_version_class=requested_class,
                    requested_version=safe_requested_version(requested),
                    negotiated_version=negotiated,
                ):
                    return
                if before == "initialize_acknowledged":
                    with self._state_lock:
                        self._initialize_replay_used = True
                self._write_traced(
                    _rpc_result(request_id, self._initialize_result(negotiated)),
                    "initialize",
                )
                return
            if not self._record_trace(
                "initialize",
                "duplicate_initialize",
                readiness_before=before,
                readiness_after=before,
                requested_version_class=requested_class,
                requested_version=safe_requested_version(requested),
            ):
                return
            self._write_traced(
                _rpc_error(
                    request_id,
                    -32600,
                    "Duplicate initialize",
                    stable_code="MCP_PROTOCOL_ERROR",
                ),
                "initialize",
            )
            return
        if not self._record_trace(
            "initialize",
            "accepted",
            readiness_before=before,
            readiness_after="initialize_acknowledged",
            requested_version_class=requested_class,
            requested_version=safe_requested_version(requested),
            negotiated_version=negotiated,
        ):
            return
        with self._state_lock:
            self._initialize_seen = True
            self._initialize_replay_used = False
            self._initialized = False
            self._request_scoped_compat = False
            self._initialize_requested_supported = requested in SUPPORTED_PROTOCOL_VERSIONS
            self._protocol_version = negotiated
        self._write_traced(
            _rpc_result(request_id, self._initialize_result(negotiated)),
            "initialize",
        )

    def _initialize_result(self, negotiated: str) -> dict[str, Any]:
        return {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self._server_name, "version": self._server_version},
            "instructions": self._server_instructions,
        }

    def _valid_tool_call_params(
        self,
        params: dict[str, Any],
        *,
        require_advertised: bool = False,
    ) -> bool:
        allowed_keys = {"name", "arguments", "_meta"}
        try:
            name = validate_tool_name(params.get("name"))
        except ValueError:
            return False
        return (
            set(params).issubset(allowed_keys)
            and (not require_advertised or name in self._tool_names)
            and isinstance(params.get("arguments", {}), dict)
            and ("_meta" not in params or isinstance(params.get("_meta"), dict))
        )

    def _tool_worker(
        self,
        key: tuple[str, Any],
        request_id: Any,
        name: str,
        arguments: dict[str, Any],
        cancel: threading.Event,
    ) -> None:
        try:
            try:
                result = self._tools.call(
                    name,
                    arguments,
                    cancelled=cancel,
                    request_id=request_id,
                )
            except CancelledError:
                return
            except UnknownToolError as exc:
                if cancel.is_set():
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code=exc.code,
                    ),
                    "tools_call",
                )
                return
            except ToolError as exc:
                if cancel.is_set():
                    return
                result = error_result(exc)
            except Exception:
                self._log("MCP_INTERNAL_ERROR")
                if cancel.is_set():
                    return
                self._write_traced(
                    _rpc_error(
                        request_id,
                        -32603,
                        "Internal error",
                        stable_code="MCP_PROTOCOL_ERROR",
                    ),
                    "tools_call",
                )
                return
            self._write_traced(_rpc_result(request_id, result), "tools_call")
        finally:
            with self._state_lock:
                if self._inflight.get(key) is cancel:
                    self._inflight.pop(key, None)

    def _write_traced(self, message: dict[str, Any], method: str) -> None:
        if self._broken.is_set() or self._output is None:
            return
        encoded = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        try:
            # Keep the local flush and its sanitized evidence in one ordering
            # critical section so concurrent workers cannot invert them.
            with self._writer_lock:
                self._output.write(encoded + "\n")
                self._output.flush()
                readiness = self._readiness()
                self._record_trace(
                    method,
                    "response_flushed",
                    stage="response",
                    readiness_before=readiness,
                    readiness_after=readiness,
                )
        except (BrokenPipeError, OSError, UnicodeError):
            self._broken.set()
            with self._state_lock:
                events = list(self._inflight.values())
            for event in events:
                event.set()
            self._log("MCP_BROKEN_PIPE")

    def _readiness(self) -> str:
        with self._state_lock:
            return self._readiness_locked()

    def _readiness_locked(self) -> str:
        if self._initialized:
            return "ready"
        if self._initialize_seen:
            return "initialize_acknowledged"
        return "uninitialized"

    def _record_trace(
        self,
        method: str,
        outcome: str,
        *,
        stage: str = "decision",
        readiness_before: str,
        readiness_after: str,
        requested_version_class: str | None = None,
        requested_version: str | None = None,
        negotiated_version: str | None = None,
    ) -> bool:
        if self._trace is None:
            return True
        try:
            self._trace.record(
                method=method,
                stage=stage,
                outcome=outcome,
                readiness_before=readiness_before,
                readiness_after=readiness_after,
                requested_version_class=requested_version_class,
                requested_version=requested_version,
                negotiated_version=negotiated_version,
            )
            return True
        except (ProtocolTraceError, ValueError):
            self._broken.set()
            with self._state_lock:
                events = list(self._inflight.values())
            for event in events:
                event.set()
            self._log("MCP_PROTOCOL_TRACE_FAILED")
            return False

    def _log(self, stable_code: str) -> None:
        if self._stderr is None:
            return
        try:
            self._stderr.write(f"gptpro-mcp: {stable_code}\n")
            self._stderr.flush()
        except (BrokenPipeError, OSError):
            pass
