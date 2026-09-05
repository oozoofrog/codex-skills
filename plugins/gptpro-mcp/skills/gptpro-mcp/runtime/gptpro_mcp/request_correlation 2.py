"""Privacy-preserving correlation for the official Tunnel admin log buffer.

Raw admin-log bytes and identifiers exist only in process memory long enough to
validate and HMAC the allowlisted fields.  This module never writes them to a
file and never enables raw HTTP logging.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

CORRELATION_SCHEMA_VERSION = 1
MAX_ADMIN_LOG_EVENTS = 2_000
MAX_ADMIN_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_IDENTIFIER_BYTES = 1_024
REQUEST_CORRELATION_CONTRACT_ID = (
    "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
)

_TERMINAL_MESSAGES: dict[str, tuple[str, str]] = {
    "dispatcher forwarded command to MCP server": ("forwarded", "INFO"),
    "dispatcher received MCP upstream error; posted error response to control plane": (
        "upstream_error",
        "WARN",
    ),
    "dispatcher failed to connect to MCP transport; posted error response to control plane": (
        "transport_error",
        "WARN",
    ),
    "dispatcher posted terminal downstream error response to control plane": (
        "downstream_error",
        "WARN",
    ),
}


@dataclass
class RequestCorrelationError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.code


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        socket_path: Path,
        *,
        timeout: float,
        expected_peer_pid: int,
        peer_pid_reader: Callable[[socket.socket], int],
    ) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = str(socket_path)
        self._expected_peer_pid = expected_peer_pid
        self._peer_pid_reader = peer_pid_reader

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(self._socket_path)
            if self._peer_pid_reader(connection) != self._expected_peer_pid:
                raise RequestCorrelationError(
                    "REQUEST_CORRELATION_PEER_UNVERIFIED",
                    "The private Tunnel admin socket peer is not the exact child process.",
                )
        except BaseException:
            connection.close()
            raise
        self.sock = connection

    def abort(self) -> None:
        connection = self.sock
        if connection is None:
            return
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            connection.close()
        except OSError:
            pass


def _darwin_unix_peer_pid(connection: socket.socket) -> int:
    """Return LOCAL_PEERPID for one connected Darwin Unix-domain socket."""

    if sys.platform != "darwin":
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_PEER_UNVERIFIED",
            "The private Tunnel admin socket peer cannot be verified on this platform.",
        )
    try:
        raw = connection.getsockopt(
            getattr(socket, "SOL_LOCAL", 0),
            getattr(socket, "LOCAL_PEERPID", 2),
            struct.calcsize("i"),
        )
        peer_pid = struct.unpack("i", raw)[0]
    except (OSError, TypeError, ValueError, struct.error) as exc:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_PEER_UNVERIFIED",
            "The private Tunnel admin socket peer could not be verified.",
        ) from exc
    if peer_pid <= 0:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_PEER_UNVERIFIED",
            "The private Tunnel admin socket peer could not be verified.",
        )
    return peer_pid


def derive_request_correlation_key(session_capability: bytes) -> bytes:
    """Derive an ephemeral domain-separated key from the live capability."""

    if not isinstance(session_capability, bytes) or len(session_capability) != 32:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_KEY_INVALID",
            "The request-correlation key source is invalid.",
        )
    return hmac.new(
        session_capability,
        b"gptpro-request-correlation-key-v1",
        hashlib.sha256,
    ).digest()


def capture_request_correlation(
    socket_path: Path,
    *,
    hmac_key: bytes,
    expected_peer_pid: int,
    timeout: float = 2.0,
    _peer_pid_reader: Callable[[socket.socket], int] = _darwin_unix_peer_pid,
) -> dict[str, Any]:
    """Read one bounded in-memory admin snapshot and return only HMAC metadata."""

    path = Path(socket_path)
    if (
        not path.is_absolute()
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
        or isinstance(expected_peer_pid, bool)
        or not isinstance(expected_peer_pid, int)
        or expected_peer_pid <= 0
    ):
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_UNAVAILABLE",
            "The private Tunnel admin endpoint is unavailable.",
        )
    connection = _UnixHTTPConnection(
        path,
        timeout=float(timeout),
        expected_peer_pid=expected_peer_pid,
        peer_pid_reader=_peer_pid_reader,
    )
    deadline = time.monotonic() + float(timeout)
    watchdog_stop = threading.Event()
    deadline_expired = threading.Event()

    def abort_at_deadline() -> None:
        if watchdog_stop.wait(max(0.0, deadline - time.monotonic())):
            return
        deadline_expired.set()
        connection.abort()

    watchdog = threading.Thread(
        target=abort_at_deadline,
        name="gptpro-request-correlation-deadline",
        daemon=True,
    )
    watchdog.start()
    caught: BaseException | None = None
    body = b""
    try:
        connection.request(
            "GET",
            f"/api/logs?limit={MAX_ADMIN_LOG_EVENTS}",
            headers={"Accept": "application/json", "Connection": "close"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_UNAVAILABLE",
                "The private Tunnel admin log snapshot was rejected.",
            )
        body = response.read(MAX_ADMIN_RESPONSE_BYTES + 1)
    except (RequestCorrelationError, OSError, TimeoutError, http.client.HTTPException) as exc:
        caught = exc
    finally:
        watchdog_stop.set()
        connection.close()
        watchdog.join(timeout=1.0)
    if deadline_expired.is_set():
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_TIMEOUT",
            "The private Tunnel admin log snapshot exceeded its total deadline.",
        ) from caught
    if isinstance(caught, RequestCorrelationError):
        raise caught
    if caught is not None:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_UNAVAILABLE",
            "The private Tunnel admin log snapshot could not be read.",
        ) from caught
    if len(body) > MAX_ADMIN_RESPONSE_BYTES:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_RESPONSE_TOO_LARGE",
            "The private Tunnel admin log snapshot exceeded its bound.",
        )
    return sanitize_admin_log_payload(body, hmac_key=hmac_key)


def sanitize_admin_log_payload(payload: bytes, *, hmac_key: bytes) -> dict[str, Any]:
    """Convert an official admin-log snapshot into equality-only diagnostics."""

    if not isinstance(hmac_key, bytes) or len(hmac_key) != 32:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_KEY_INVALID",
            "The request-correlation key is invalid.",
        )
    if not isinstance(payload, bytes) or len(payload) > MAX_ADMIN_RESPONSE_BYTES:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_RESPONSE_TOO_LARGE",
            "The private Tunnel admin log snapshot exceeded its bound.",
        )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_INVALID",
            "The private Tunnel admin log snapshot is invalid.",
        ) from exc
    events = document.get("events") if isinstance(document, dict) else None
    if not isinstance(events, list) or len(events) > MAX_ADMIN_LOG_EVENTS:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_INVALID",
            "The private Tunnel admin log event list is invalid.",
        )

    sequences: list[int] = []
    selected: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_INVALID",
                "The private Tunnel admin log contains an invalid event.",
            )
        sequence = event.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
            or (sequences and sequence <= sequences[-1])
        ):
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_CONTRACT_MISMATCH",
                "The private Tunnel admin log sequence violates the pinned contract.",
            )
        sequences.append(sequence)
        contract = _TERMINAL_MESSAGES.get(event.get("message"))
        if contract is None:
            continue
        outcome, expected_level = contract
        if (
            event.get("level") != expected_level
            or not isinstance(event.get("time"), str)
            or not event["time"]
            or len(event["time"]) > 128
        ):
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_CONTRACT_MISMATCH",
                "A private Tunnel admin event violates the pinned contract.",
            )
        attrs = event.get("attrs")
        if not isinstance(attrs, dict) or attrs.get("component") != "dispatcher":
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_CONTRACT_MISMATCH",
                "A private Tunnel admin event violates the pinned contract.",
            )
        outer_id = attrs.get("request_id")
        rpc_id = attrs.get("rpc_request_id")
        if outer_id is None or rpc_id is None:
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_CONTRACT_MISMATCH",
                "A private Tunnel admin event violates the pinned contract.",
            )
        item = {
            "ordinal": len(selected) + 1,
            "outcome": outcome,
            "outer_request_id_hmac_sha256": _identifier_hmac(
                hmac_key, "outer_request_id", outer_id
            ),
            "rpc_request_id_hmac_sha256": _identifier_hmac(
                hmac_key, "rpc_request_id", rpc_id
            ),
            "jsonrpc_request_id_sha256": hashlib.sha256(
                _canonical_identifier(rpc_id)
            ).hexdigest(),
        }
        connector_id = attrs.get("cmd_request_id")
        if connector_id is not None:
            item["connector_request_id_hmac_sha256"] = _identifier_hmac(
                hmac_key, "connector_request_id", connector_id
            )
        selected.append(item)

    outer_digests = {
        item["outer_request_id_hmac_sha256"] for item in selected
    }
    connector_digests = {
        item["connector_request_id_hmac_sha256"]
        for item in selected
        if "connector_request_id_hmac_sha256" in item
    }
    return {
        "schema_version": CORRELATION_SCHEMA_VERSION,
        "status": "captured",
        "source": "tunnel_client_private_admin_log",
        "private_contract": REQUEST_CORRELATION_CONTRACT_ID,
        "capture_window_complete": bool(sequences)
        and sequences == list(range(1, len(sequences) + 1)),
        "admin_events_observed": len(events),
        "terminal_command_events": len(selected),
        "terminal_error_events": sum(
            item["outcome"] != "forwarded" for item in selected
        ),
        "unique_outer_request_ids": len(outer_digests),
        "unique_connector_request_ids": len(connector_digests),
        "events": selected,
        "privacy": {
            "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
            "raw_identifiers_persisted": False,
            "raw_payloads_persisted": False,
            "hmac_key_persisted": False,
            "stable_join_hashes_exposed_in_terminal": False,
            "raw_http_logging_enabled": False,
        },
    }


def unavailable_request_correlation(code: str) -> dict[str, Any]:
    safe_code = (
        code
        if isinstance(code, str)
        and code
        and len(code) <= 64
        and code.replace("_", "").isalnum()
        and code.upper() == code
        else "REQUEST_CORRELATION_UNAVAILABLE"
    )
    return {
        "schema_version": CORRELATION_SCHEMA_VERSION,
        "status": "unavailable",
        "code": safe_code,
        "events": [],
        "privacy": {
            "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
            "raw_identifiers_persisted": False,
            "raw_payloads_persisted": False,
            "hmac_key_persisted": False,
            "stable_join_hashes_exposed_in_terminal": False,
            "raw_http_logging_enabled": False,
        },
    }


def _identifier_hmac(key: bytes, label: str, value: object) -> str:
    domain = b"gptpro-request-correlation-v1\0" + label.encode("ascii") + b"\0"
    return hmac.new(key, domain + _canonical_identifier(value), hashlib.sha256).hexdigest()


def _canonical_identifier(value: object) -> bytes:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_INVALID",
            "A Tunnel correlation identifier has an invalid type.",
        )
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_INVALID",
            "A Tunnel correlation identifier is invalid.",
        ) from exc
    if not encoded or len(encoded) > MAX_IDENTIFIER_BYTES:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_INVALID",
            "A Tunnel correlation identifier exceeded its bound.",
        )
    return encoded
