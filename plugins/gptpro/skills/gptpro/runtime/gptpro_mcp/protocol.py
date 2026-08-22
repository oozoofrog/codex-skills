"""Dependency-free legacy JSON-RPC/MCP stdio state machine."""

from __future__ import annotations

import copy
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TextIO

from .errors import CancelledError, ToolError
from .schema import SERVER_INSTRUCTIONS, SERVER_NAME, SERVER_VERSION, TOOL_CATALOG, TOOL_NAMES
from .tools import ToolRuntime, error_result

JSONRPC_VERSION = "2.0"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
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

    def __init__(self, tools: ToolRuntime, *, max_workers: int = 1) -> None:
        self._tools = tools
        self._state_lock = threading.Lock()
        self._writer_lock = threading.Lock()
        self._initialize_seen = False
        self._initialized = False
        self._protocol_version: str | None = None
        self._inflight: dict[tuple[str, Any], threading.Event] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gptpro-mcp")
        self._output: TextIO | None = None
        self._stderr: TextIO | None = None
        self._broken = threading.Event()

    def serve(self, input_stream: TextIO, output_stream: TextIO, stderr: TextIO) -> int:
        self._output = output_stream
        self._stderr = stderr
        try:
            while True:
                if self._broken.is_set():
                    break
                line = input_stream.readline(MAX_INPUT_FRAME_CHARS + 1)
                if not line:
                    break
                if len(line) > MAX_INPUT_FRAME_CHARS:
                    while line and not line.endswith("\n"):
                        line = input_stream.readline(MAX_INPUT_FRAME_CHARS + 1)
                    self._write(
                        _rpc_error(
                            None,
                            -32600,
                            "Invalid Request",
                            stable_code="MCP_FRAME_TOO_LARGE",
                        )
                    )
                    continue
                self.process_line(line)
        finally:
            self._executor.shutdown(wait=True, cancel_futures=False)
        return 0 if not self._broken.is_set() else 1

    def process_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, UnicodeError):
            self._write(_rpc_error(None, -32700, "Parse error", stable_code="MCP_PROTOCOL_ERROR"))
            return
        if not isinstance(message, dict):
            self._write(_rpc_error(None, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"))
            return
        if message.get("jsonrpc") != JSONRPC_VERSION or not isinstance(message.get("method"), str):
            request_id = message.get("id") if _valid_id(message.get("id")) else None
            self._write(_rpc_error(request_id, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"))
            return
        has_id = "id" in message
        request_id = message.get("id")
        if has_id and not _valid_id(request_id):
            self._write(_rpc_error(None, -32600, "Invalid Request", stable_code="MCP_PROTOCOL_ERROR"))
            return
        params = message.get("params", {})
        if not isinstance(params, dict):
            if has_id:
                self._write(
                    _rpc_error(request_id, -32602, "Invalid params", stable_code="MCP_INVALID_ARGUMENT")
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
                if self._initialize_seen:
                    self._initialized = True
            return
        if method == "notifications/cancelled":
            request_id = params.get("requestId")
            if _valid_id(request_id):
                with self._state_lock:
                    event = self._inflight.get(_request_key(request_id))
                if event is not None:
                    event.set()
            return
        # Unknown notifications are intentionally ignored without a response.

    def _request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        if method == "ping":
            self._write(_rpc_result(request_id, {}))
            return
        if method == "initialize":
            self._initialize(request_id, params)
            return
        if method in {"notifications/initialized", "notifications/cancelled"}:
            self._write(
                _rpc_error(request_id, -32601, "Method not found", stable_code="MCP_METHOD_NOT_SUPPORTED")
            )
            return
        with self._state_lock:
            ready = self._initialized
        if method in {"tools/list", "tools/call"} and not ready:
            self._write(
                _rpc_error(
                    request_id,
                    -32600,
                    "Client is not initialized",
                    stable_code="MCP_PROTOCOL_ERROR",
                )
            )
            return
        if method == "tools/list":
            if params:
                self._write(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code="MCP_INVALID_ARGUMENT",
                    )
                )
                return
            self._write(_rpc_result(request_id, {"tools": copy.deepcopy(list(TOOL_CATALOG))}))
            return
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if set(params) != {"name", "arguments"} or name not in TOOL_NAMES or not isinstance(arguments, dict):
                self._write(
                    _rpc_error(
                        request_id,
                        -32602,
                        "Invalid params",
                        stable_code="MCP_INVALID_ARGUMENT",
                    )
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
                self._write(
                    _rpc_error(
                        request_id,
                        -32600,
                        "Duplicate request id",
                        stable_code="MCP_PROTOCOL_ERROR",
                    )
                )
                return
            if busy:
                self._write(
                    _rpc_error(
                        request_id,
                        -32000,
                        "Server busy",
                        stable_code="MCP_SERVER_BUSY",
                    )
                )
                return
            self._executor.submit(self._tool_worker, key, request_id, name, arguments, cancel)
            return
        self._write(
            _rpc_error(request_id, -32601, "Method not found", stable_code="MCP_METHOD_NOT_SUPPORTED")
        )

    def _initialize(self, request_id: Any, params: dict[str, Any]) -> None:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            self._write(
                _rpc_error(request_id, -32602, "Invalid params", stable_code="MCP_INVALID_ARGUMENT")
            )
            return
        with self._state_lock:
            if self._initialize_seen:
                duplicate = True
            else:
                duplicate = False
                self._initialize_seen = True
                self._protocol_version = (
                    requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PREFERRED_PROTOCOL_VERSION
                )
                negotiated = self._protocol_version
        if duplicate:
            self._write(
                _rpc_error(request_id, -32600, "Duplicate initialize", stable_code="MCP_PROTOCOL_ERROR")
            )
            return
        self._write(
            _rpc_result(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": SERVER_INSTRUCTIONS,
                },
            )
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
            result = self._tools.call(name, arguments, cancelled=cancel, request_id=request_id)
        except CancelledError:
            return
        except ToolError as exc:
            if cancel.is_set():
                return
            result = error_result(exc)
        except Exception:
            self._log("MCP_INTERNAL_ERROR")
            if cancel.is_set():
                return
            self._write(
                _rpc_error(
                    request_id,
                    -32603,
                    "Internal error",
                    stable_code="MCP_PROTOCOL_ERROR",
                )
            )
            return
        finally:
            with self._state_lock:
                self._inflight.pop(key, None)
        self._write(_rpc_result(request_id, result))

    def _write(self, message: dict[str, Any]) -> None:
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
            with self._writer_lock:
                self._output.write(encoded + "\n")
                self._output.flush()
        except (BrokenPipeError, OSError, UnicodeError):
            self._broken.set()
            with self._state_lock:
                events = list(self._inflight.values())
            for event in events:
                event.set()
            self._log("MCP_BROKEN_PIPE")

    def _log(self, stable_code: str) -> None:
        if self._stderr is None:
            return
        try:
            self._stderr.write(f"gptpro-mcp: {stable_code}\n")
            self._stderr.flush()
        except (BrokenPipeError, OSError):
            pass
