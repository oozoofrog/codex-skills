from __future__ import annotations

import http.server
import json
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.request_correlation import (
    RequestCorrelationError,
    capture_request_correlation,
    derive_request_correlation_key,
    sanitize_admin_log_payload,
    unavailable_request_correlation,
)


class RequestCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = derive_request_correlation_key(b"c" * 32)

    @staticmethod
    def payload(*events: dict[str, object]) -> bytes:
        return json.dumps({"events": list(events)}, separators=(",", ":")).encode()

    @staticmethod
    def event(
        sequence: int,
        *,
        outer_id: str,
        rpc_id: str | int,
        connector_id: str | None = None,
    ) -> dict[str, object]:
        attrs: dict[str, object] = {
            "request_id": outer_id,
            "rpc_request_id": rpc_id,
            "tunnel_id": "tunnel_raw_secret",
            "shard_token": "raw-shard-secret",
            "api_key": "sk-raw-secret-value",
        }
        if connector_id is not None:
            attrs["cmd_request_id"] = connector_id
        return {
            "seq": sequence,
            "time": "2026-08-23T00:00:00Z",
            "level": "INFO",
            "message": "dispatcher forwarded command to MCP server",
            "attrs": attrs,
        }

    def test_same_identifiers_have_session_scoped_equal_digests_without_raw_values(self) -> None:
        raw_outer = "req-sensitive-123"
        raw_rpc = "rpc-sensitive-456"
        raw_connector = "connector-sensitive-789"
        report = sanitize_admin_log_payload(
            self.payload(
                self.event(
                    1,
                    outer_id=raw_outer,
                    rpc_id=raw_rpc,
                    connector_id=raw_connector,
                ),
                self.event(
                    2,
                    outer_id=raw_outer,
                    rpc_id=raw_rpc,
                    connector_id=raw_connector,
                ),
            ),
            hmac_key=self.key,
        )

        self.assertEqual("captured", report["status"])
        self.assertTrue(report["capture_window_complete"])
        self.assertEqual(2, report["terminal_command_events"])
        self.assertEqual(1, report["unique_outer_request_ids"])
        self.assertEqual(1, report["unique_connector_request_ids"])
        first, second = report["events"]
        self.assertEqual(
            first["outer_request_id_hmac_sha256"],
            second["outer_request_id_hmac_sha256"],
        )
        self.assertEqual(
            first["rpc_request_id_hmac_sha256"],
            second["rpc_request_id_hmac_sha256"],
        )
        serialized = json.dumps(report, sort_keys=True)
        for forbidden in (
            raw_outer,
            raw_rpc,
            raw_connector,
            "tunnel_raw_secret",
            "raw-shard-secret",
            "sk-raw-secret-value",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertFalse(report["privacy"]["raw_identifiers_persisted"])
        self.assertFalse(report["privacy"]["raw_payloads_persisted"])
        self.assertFalse(report["privacy"]["hmac_key_persisted"])
        self.assertFalse(report["privacy"]["raw_http_logging_enabled"])

    def test_different_sessions_and_outer_ids_do_not_share_digests(self) -> None:
        payload = self.payload(self.event(1, outer_id="outer-a", rpc_id=7))
        first = sanitize_admin_log_payload(payload, hmac_key=self.key)["events"][0]
        second = sanitize_admin_log_payload(
            payload,
            hmac_key=derive_request_correlation_key(b"d" * 32),
        )["events"][0]
        third = sanitize_admin_log_payload(
            self.payload(self.event(1, outer_id="outer-b", rpc_id=7)),
            hmac_key=self.key,
        )["events"][0]

        self.assertNotEqual(
            first["outer_request_id_hmac_sha256"],
            second["outer_request_id_hmac_sha256"],
        )
        self.assertNotEqual(
            first["outer_request_id_hmac_sha256"],
            third["outer_request_id_hmac_sha256"],
        )
        self.assertEqual(
            first["jsonrpc_request_id_sha256"],
            second["jsonrpc_request_id_sha256"],
        )

    def test_unknown_messages_are_ignored_and_incomplete_window_is_explicit(self) -> None:
        ignored = self.event(9, outer_id="ignored", rpc_id="ignored")
        ignored["message"] = "unrelated diagnostic"
        report = sanitize_admin_log_payload(
            self.payload(
                ignored,
                self.event(10, outer_id="selected", rpc_id="rpc"),
            ),
            hmac_key=self.key,
        )
        self.assertFalse(report["capture_window_complete"])
        self.assertEqual(1, report["terminal_command_events"])

    def test_allowlisted_terminal_error_messages_have_stable_outcomes(self) -> None:
        messages = (
            (
                "dispatcher received MCP upstream error; posted error response to control plane",
                "upstream_error",
            ),
            (
                "dispatcher failed to connect to MCP transport; posted error response to control plane",
                "transport_error",
            ),
            (
                "dispatcher posted terminal downstream error response to control plane",
                "downstream_error",
            ),
        )
        events = []
        for sequence, (message, _) in enumerate(messages, 1):
            event = self.event(
                sequence,
                outer_id=f"outer-{sequence}",
                rpc_id=sequence,
            )
            event["message"] = message
            events.append(event)

        report = sanitize_admin_log_payload(
            self.payload(*events),
            hmac_key=self.key,
        )

        self.assertEqual(
            [expected for _, expected in messages],
            [event["outcome"] for event in report["events"]],
        )

    def test_invalid_sequence_identifier_and_key_fail_closed(self) -> None:
        with self.assertRaisesRegex(RequestCorrelationError, "REQUEST_CORRELATION_INVALID"):
            sanitize_admin_log_payload(
                self.payload(
                    self.event(2, outer_id="a", rpc_id=1),
                    self.event(1, outer_id="b", rpc_id=2),
                ),
                hmac_key=self.key,
            )
        invalid = self.event(1, outer_id="a", rpc_id=1)
        invalid["attrs"]["request_id"] = {"not": "opaque"}
        with self.assertRaisesRegex(RequestCorrelationError, "REQUEST_CORRELATION_INVALID"):
            sanitize_admin_log_payload(self.payload(invalid), hmac_key=self.key)
        with self.assertRaisesRegex(RequestCorrelationError, "REQUEST_CORRELATION_KEY_INVALID"):
            sanitize_admin_log_payload(self.payload(), hmac_key=b"short")

    def test_unavailable_report_contains_only_stable_code_and_privacy_flags(self) -> None:
        report = unavailable_request_correlation("unsafe raw value")
        self.assertEqual("REQUEST_CORRELATION_UNAVAILABLE", report["code"])
        self.assertEqual([], report["events"])
        self.assertFalse(report["privacy"]["raw_identifiers_persisted"])

    def test_capture_reads_only_the_bounded_private_unix_admin_route(self) -> None:
        response_body = self.payload(
            self.event(1, outer_id="outer-private", rpc_id="rpc-private")
        )
        requested_paths: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                requested_paths.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "admin.sock"
            server = socketserver.UnixStreamServer(str(socket_path), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                report = capture_request_correlation(
                    socket_path,
                    hmac_key=self.key,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(["/api/logs?limit=2000"], requested_paths)
        self.assertEqual("captured", report["status"])
        self.assertNotIn("outer-private", json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
