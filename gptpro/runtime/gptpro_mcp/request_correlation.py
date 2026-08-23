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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CORRELATION_SCHEMA_VERSION = 1
MAX_ADMIN_LOG_EVENTS = 2_000
MAX_ADMIN_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_IDENTIFIER_BYTES = 1_024

_TERMINAL_MESSAGES = {
    "dispatcher forwarded command to MCP server": "forwarded",
    "dispatcher received MCP upstream error; posted error response to control plane": "upstream_error",
    "dispatcher failed to connect to MCP transport; posted error response to control plane": "transport_error",
    "dispatcher posted terminal downstream error response to control plane": "downstream_error",
}


@dataclass
class RequestCorrelationError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.code


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, *, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = str(socket_path)

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(self._socket_path)
        except BaseException:
            connection.close()
            raise
        self.sock = connection


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
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Read one bounded in-memory admin snapshot and return only HMAC metadata."""

    path = Path(socket_path)
    if not path.is_absolute() or timeout <= 0:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_UNAVAILABLE",
            "The private Tunnel admin endpoint is unavailable.",
        )
    connection = _UnixHTTPConnection(path, timeout=timeout)
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
    except RequestCorrelationError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise RequestCorrelationError(
            "REQUEST_CORRELATION_UNAVAILABLE",
            "The private Tunnel admin log snapshot could not be read.",
        ) from exc
    finally:
        connection.close()
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

    previous_sequence = 0
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
            or sequence <= previous_sequence
        ):
            raise RequestCorrelationError(
                "REQUEST_CORRELATION_INVALID",
                "The private Tunnel admin log sequence is invalid.",
            )
        previous_sequence = sequence
        outcome = _TERMINAL_MESSAGES.get(event.get("message"))
        if outcome is None:
            continue
        attrs = event.get("attrs")
        if not isinstance(attrs, dict):
            continue
        outer_id = attrs.get("request_id")
        rpc_id = attrs.get("rpc_request_id")
        if outer_id is None or rpc_id is None:
            continue
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
        "capture_window_complete": bool(events) and events[0].get("seq") == 1,
        "admin_events_observed": len(events),
        "terminal_command_events": len(selected),
        "unique_outer_request_ids": len(outer_digests),
        "unique_connector_request_ids": len(connector_digests),
        "events": selected,
        "privacy": {
            "scope": "ephemeral_session_hmac_sha256",
            "raw_identifiers_persisted": False,
            "raw_payloads_persisted": False,
            "hmac_key_persisted": False,
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
            "scope": "ephemeral_session_hmac_sha256",
            "raw_identifiers_persisted": False,
            "raw_payloads_persisted": False,
            "hmac_key_persisted": False,
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
