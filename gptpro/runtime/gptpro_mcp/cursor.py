"""Opaque, package- and session-bound pagination cursors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from .authorization import AuthorizationGrant
from .errors import ToolError
from .schema import canonical_json_bytes, contract_for_schema

CURSOR_VERSION = 1
MAX_CURSOR_BYTES = 4096


def arguments_sha256(arguments: dict[str, Any]) -> str:
    bound = {key: value for key, value in arguments.items() if key != "cursor"}
    return hashlib.sha256(canonical_json_bytes(bound)).hexdigest()


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError
    result = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if result.tzinfo is None:
        raise ValueError
    return result


class CursorCodec:
    def __init__(self, grant: AuthorizationGrant) -> None:
        self._grant = grant

    def encode(
        self,
        *,
        tool: str,
        arguments_hash: str,
        next_position: dict[str, Any],
    ) -> str:
        schema_version = self._grant.manifest.get("schema_version")
        if schema_version not in {3, 4}:
            raise ToolError("CURSOR_INVALID", "The pagination cursor schema is unsupported.")
        schema_hash = contract_for_schema(int(schema_version))["tool_schema_sha256"]
        payload = {
            "v": CURSOR_VERSION,
            "session_id_sha256": self._grant.session_id_sha256,
            "package_id": self._grant.package_id,
            "tool": tool,
            "arguments_sha256": arguments_hash,
            "next_position": next_position,
            "tool_schema_sha256": schema_hash,
            "expires_at": _utc_text(self._grant.expires_at),
        }
        body = canonical_json_bytes(payload)
        mac = hmac.new(self._grant.session_nonce, body, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(body + mac).rstrip(b"=").decode("ascii")
        if len(token) > MAX_CURSOR_BYTES:
            raise ToolError(
                "RESULT_LIMIT_EXCEEDED",
                "The pagination cursor exceeds the result safety limit.",
                retryable=True,
                recovery="Request a smaller page or range.",
            )
        return token

    def decode(
        self,
        token: Any,
        *,
        tool: str,
        arguments_hash: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= MAX_CURSOR_BYTES:
                raise ValueError
            padding = "=" * (-len(token) % 4)
            raw = base64.b64decode(token + padding, altchars=b"-_", validate=True)
            if len(raw) <= hashlib.sha256().digest_size:
                raise ValueError
            body, supplied_mac = raw[:-32], raw[-32:]
            expected_mac = hmac.new(self._grant.session_nonce, body, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied_mac, expected_mac):
                raise ValueError
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or canonical_json_bytes(payload) != body:
                raise ValueError
            expiry = _parse_utc(payload.get("expires_at"))
            current = now or datetime.now(timezone.utc)
            if expiry > self._grant.expires_at or current >= expiry:
                raise ValueError
            schema_version = self._grant.manifest.get("schema_version")
            if schema_version not in {3, 4}:
                raise ValueError
            schema_hash = contract_for_schema(int(schema_version))["tool_schema_sha256"]
            if (
                payload.get("v") != CURSOR_VERSION
                or payload.get("session_id_sha256") != self._grant.session_id_sha256
                or payload.get("package_id") != self._grant.package_id
                or payload.get("tool") != tool
                or payload.get("arguments_sha256") != arguments_hash
                or payload.get("tool_schema_sha256") != schema_hash
                or not isinstance(payload.get("next_position"), dict)
            ):
                raise ValueError
            return dict(payload["next_position"])
        except (
            ValueError,
            TypeError,
            RecursionError,
            binascii.Error,
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ToolError(
                "CURSOR_INVALID",
                "The pagination cursor is malformed, expired, or bound to another request.",
                retryable=True,
                recovery="Restart from the original tool call without a cursor.",
            ) from exc
