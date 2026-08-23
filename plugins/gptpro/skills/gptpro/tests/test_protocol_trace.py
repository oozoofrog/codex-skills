from __future__ import annotations

import io
import json
import os
import fcntl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.protocol import LegacyMcpServer, SUPPORTED_PROTOCOL_VERSIONS
from runtime.gptpro_mcp.protocol_trace import (
    MAX_TRACE_EVENTS,
    ProtocolTrace,
    ProtocolTraceBinding,
    ProtocolTraceError,
    SAFE_PROTOCOL_VERSIONS,
)


class NoDisclosureRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        raise AssertionError("handshake-only transcript must not call a repository tool")


class ProtocolTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.binding = ProtocolTraceBinding(
            package_id="20260822T145628Z-ask-049dda58",
            session_id_sha256="1" * 64,
            manifest_sha256="2" * 64,
            approval_event_sha256="3" * 64,
            archive_sha256="4" * 64,
            file_set_sha256="5" * 64,
            tool_schema_sha256="6" * 64,
            audit_header_sha256="7" * 64,
            tunnel_profile_sha256="8" * 64,
            tunnel_client_binary_sha256="9" * 64,
            mcp_target_sha256="a" * 64,
            mcp_runtime_tree_sha256="b" * 64,
        )
        self.trace = ProtocolTrace(self.root, self.binding)
        self.trace.open_or_create()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def transcript(self, messages: list[object], *, trace=None, runtime=None):
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in messages))
        output = io.StringIO()
        stderr = io.StringIO()
        server = LegacyMcpServer(runtime or NoDisclosureRuntime(), trace=trace or self.trace)
        result = server.serve(source, output, stderr)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        return result, responses, stderr.getvalue()

    def test_handshake_sequence_is_ordered_sanitized_and_zero_disclosure(self) -> None:
        runtime = NoDisclosureRuntime()
        secret_version = "2099-01-01-client-secret-do-not-store"
        result, responses, stderr = self.transcript(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "secret-request-id",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": secret_version,
                        "clientInfo": {"name": "private-client", "version": "secret"},
                        "capabilities": {"private": "/Users/private/repo"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": "discover-secret-id",
                    "method": "server/discover",
                    "params": {
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2025-06-18",
                            "query": "repository-content-secret",
                        }
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": "secret-cancelled-request-id"},
                },
            ],
            runtime=runtime,
        )
        self.assertEqual(0, result)
        self.assertEqual(0, runtime.calls)
        self.assertEqual("", stderr)
        self.assertEqual(["secret-request-id", "discover-secret-id", 2, 3], [r["id"] for r in responses])

        summary = self.trace.verify()
        decisions = [event for event in summary.events if event["stage"] == "decision"]
        processed = [event for event in summary.events if event["stage"] == "processed"]
        responses_flushed = [event for event in summary.events if event["stage"] == "response"]
        self.assertEqual(
            [
                "initialize",
                "server_discover",
                "initialize",
                "tools_list",
            ],
            [event["method"] for event in decisions],
        )
        self.assertEqual(
            [
                "accepted",
                "method_not_supported",
                "accepted",
                "tools_listed",
            ],
            [event["outcome"] for event in decisions],
        )
        self.assertEqual(
            [
                "initialized_notification",
                "initialized_notification",
                "initialized_notification",
                "cancelled_notification",
            ],
            [event["method"] for event in processed],
        )
        self.assertEqual(
            ["accepted", "ignored", "accepted", "ignored"],
            [event["outcome"] for event in processed],
        )
        self.assertEqual(
            ["ready", "uninitialized", "ready", "ready"],
            [event["readiness_after"] for event in processed],
        )
        self.assertEqual("unsupported", decisions[0]["requested_version_class"])
        self.assertNotIn("requested_version", decisions[0])
        self.assertEqual("2025-11-25", decisions[0]["negotiated_version"])
        self.assertEqual("supported_legacy", decisions[1]["requested_version_class"])
        self.assertEqual("2025-06-18", decisions[1]["requested_version"])
        self.assertEqual("supported_legacy", decisions[2]["requested_version_class"])
        self.assertEqual("2024-11-05", decisions[2]["requested_version"])
        self.assertEqual("2024-11-05", decisions[2]["negotiated_version"])
        self.assertEqual(
            ["initialize", "server_discover", "initialize", "tools_list"],
            [event["method"] for event in responses_flushed],
        )
        self.assertTrue(all(event["outcome"] == "response_flushed" for event in responses_flushed))
        self.assertTrue(summary.closed)
        self.assertEqual("stdio_eof", summary.close_reason)

        persisted = self.trace.path.read_text(encoding="ascii")
        for forbidden in (
            secret_version,
            "secret-request-id",
            "discover-secret-id",
            "private-client",
            "/Users/private/repo",
            "repository-content-secret",
            "secret-cancelled-request-id",
            "clientInfo",
            "capabilities",
            "query",
        ):
            self.assertNotIn(forbidden, persisted)
        self.assertEqual(0o600, self.trace.path.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.trace.lock_path.stat().st_mode & 0o777)

    def test_trace_caps_at_sixty_four_events(self) -> None:
        for _ in range(MAX_TRACE_EVENTS + 10):
            self.trace.record(
                method="ping",
                stage="decision",
                outcome="pong",
                readiness_before="uninitialized",
                readiness_after="uninitialized",
            )
        summary = self.trace.verify()
        self.assertEqual(MAX_TRACE_EVENTS, summary.event_count)
        self.assertTrue(summary.truncated)
        self.assertEqual("trace_truncated", summary.events[-1]["outcome"])
        self.assertEqual(MAX_TRACE_EVENTS + 1, len(self.trace.path.read_text().splitlines()))
        closed = self.trace.close("stdio_eof")
        self.assertTrue(closed.closed)
        self.assertEqual(MAX_TRACE_EVENTS + 2, len(self.trace.path.read_text().splitlines()))

    def test_open_trace_is_explicitly_unclean_until_footer_is_written(self) -> None:
        recorded = self.trace.record(
            method="ping",
            stage="decision",
            outcome="pong",
            readiness_before="uninitialized",
            readiness_after="uninitialized",
        )
        self.assertFalse(recorded.closed)
        self.assertIsNone(recorded.close_reason)
        verified = self.trace.verify()
        self.assertFalse(verified.closed)
        self.assertEqual(recorded.head_sha256, verified.head_sha256)

    def test_parent_shutdown_footer_requires_the_normal_eof_path(self) -> None:
        source = io.StringIO("")
        output = io.StringIO()
        stderr = io.StringIO()
        server = LegacyMcpServer(NoDisclosureRuntime(), trace=self.trace)
        server.note_parent_shutdown()

        self.assertEqual(0, server.serve(source, output, stderr))
        summary = self.trace.verify()
        self.assertTrue(summary.closed)
        self.assertEqual("parent_shutdown", summary.close_reason)
        self.assertEqual("", stderr.getvalue())

    def test_response_flush_gap_is_preserved_as_ambiguous_protocol_break(self) -> None:
        class FlushFailure(io.StringIO):
            def flush(self) -> None:
                raise BrokenPipeError("simulated local stdio failure")

        source = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": "secret", "method": "ping"}) + "\n")
        output = FlushFailure()
        stderr = io.StringIO()
        server = LegacyMcpServer(NoDisclosureRuntime(), trace=self.trace)
        server.note_parent_shutdown()
        result = server.serve(source, output, stderr)

        self.assertEqual(1, result)
        summary = self.trace.verify()
        self.assertEqual(["decision"], [event["stage"] for event in summary.events])
        self.assertEqual(["pong"], [event["outcome"] for event in summary.events])
        self.assertTrue(summary.closed)
        # A protocol failure takes precedence over an observed parent stop.
        self.assertEqual("protocol_broken", summary.close_reason)
        self.assertNotIn("secret", self.trace.path.read_text(encoding="ascii"))
        self.assertEqual("gptpro-mcp: MCP_BROKEN_PIPE\n", stderr.getvalue())

    def test_notification_mutation_precedes_processed_trace_and_failure_breaks_server(self) -> None:
        class FailProcessedTrace:
            def __init__(self) -> None:
                self.events: list[dict[str, object]] = []

            def record(self, **kwargs):
                self.events.append(dict(kwargs))
                if kwargs.get("stage") == "processed":
                    raise ProtocolTraceError(
                        "PROTOCOL_TRACE_UNAVAILABLE", "simulated trace failure"
                    )

            def close(self, reason):
                del reason

        initialized_trace = FailProcessedTrace()
        initialized_server = LegacyMcpServer(
            NoDisclosureRuntime(), trace=initialized_trace
        )
        initialized_server._stderr = io.StringIO()
        initialized_server._initialize_seen = True
        initialized_server._notification("notifications/initialized", {})
        self.assertTrue(initialized_server._initialized)
        self.assertTrue(initialized_server._broken.is_set())
        self.assertEqual("processed", initialized_trace.events[-1]["stage"])
        self.assertEqual("ready", initialized_trace.events[-1]["readiness_after"])

        cancellation_trace = FailProcessedTrace()
        cancellation_server = LegacyMcpServer(
            NoDisclosureRuntime(), trace=cancellation_trace
        )
        cancellation_server._stderr = io.StringIO()
        cancelled = threading.Event()
        secret_id = "secret-cancellation-request-id"
        cancellation_server._inflight[("str", secret_id)] = cancelled
        cancellation_server._notification(
            "notifications/cancelled", {"requestId": secret_id}
        )
        self.assertTrue(cancelled.is_set())
        self.assertTrue(cancellation_server._broken.is_set())
        self.assertEqual("processed", cancellation_trace.events[-1]["stage"])
        self.assertEqual("accepted", cancellation_trace.events[-1]["outcome"])
        self.assertNotIn(secret_id, json.dumps(cancellation_trace.events))

    def test_negotiated_version_allowlist_tracks_server_support(self) -> None:
        self.assertEqual(set(SUPPORTED_PROTOCOL_VERSIONS), set(SAFE_PROTOCOL_VERSIONS))

    def test_pre_ready_same_version_initialize_replay_trace_is_exact_and_zero_disclosure(self) -> None:
        runtime = NoDisclosureRuntime()
        result, _, _ = self.transcript(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "first-secret-id",
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "duplicate-secret-id",
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                },
            ],
            runtime=runtime,
        )
        self.assertEqual(0, result)
        self.assertEqual(0, runtime.calls)
        summary = self.trace.verify()
        self.assertEqual(
            [
                ("decision", "accepted"),
                ("response", "response_flushed"),
                ("decision", "initialize_replayed"),
                ("response", "response_flushed"),
            ],
            [(event["stage"], event["outcome"]) for event in summary.events],
        )
        decisions = [event for event in summary.events if event["stage"] == "decision"]
        self.assertEqual(
            ["2024-11-05", "2024-11-05"],
            [event["requested_version"] for event in decisions],
        )
        self.assertEqual("2024-11-05", decisions[0]["negotiated_version"])
        self.assertEqual("2024-11-05", decisions[1]["negotiated_version"])
        persisted = self.trace.path.read_text(encoding="ascii")
        self.assertNotIn("first-secret-id", persisted)
        self.assertNotIn("duplicate-secret-id", persisted)

    def test_request_scoped_initialize_trace_is_sanitized(self) -> None:
        class RecordingRuntime:
            def __init__(self) -> None:
                self.calls = 0

            def call(self, name, arguments, **kwargs):
                del name, arguments, kwargs
                self.calls += 1
                return {"content": [], "structuredContent": {"ok": True}}

        runtime = RecordingRuntime()
        secret_package = "20260822T173606Z-secret-package"
        result, responses, _ = self.transcript(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "first-secret-id",
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "replay-secret-id",
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "call-secret-id",
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_package_info",
                        "arguments": {"package_id": secret_package},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": "next-secret-id",
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
            ],
            runtime=runtime,
        )
        self.assertEqual(0, result)
        self.assertEqual(1, runtime.calls)
        self.assertEqual("2025-11-25", responses[3]["result"]["protocolVersion"])
        summary = self.trace.verify()
        request_scoped = [
            event
            for event in summary.events
            if event["outcome"] == "request_scoped_initialized"
        ]
        self.assertEqual(1, len(request_scoped))
        self.assertEqual("tools_call", request_scoped[0]["method"])
        self.assertEqual("processed", request_scoped[0]["stage"])
        self.assertEqual("initialize_acknowledged", request_scoped[0]["readiness_before"])
        self.assertEqual("ready", request_scoped[0]["readiness_after"])
        persisted = self.trace.path.read_text(encoding="ascii")
        for secret in (
            "first-secret-id",
            "replay-secret-id",
            "call-secret-id",
            "next-secret-id",
            secret_package,
            "gptpro_package_info",
        ):
            self.assertNotIn(secret, persisted)

    def test_ready_reinitialize_and_tool_meta_trace_remain_sanitized(self) -> None:
        class RecordingRuntime:
            def __init__(self) -> None:
                self.calls = 0

            def call(self, name, arguments, **kwargs):
                del name, arguments, kwargs
                self.calls += 1
                return {"content": [], "structuredContent": {"ok": True}}

        runtime = RecordingRuntime()
        secrets = (
            "first-secret-id",
            "replay-secret-id",
            "call-secret-id",
            "secret-package-id",
            "secret-progress-token",
            "gptpro_package_info",
        )
        result, _, _ = self.transcript(
            [
                {
                    "jsonrpc": "2.0",
                    "id": secrets[0],
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": secrets[1],
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": secrets[2],
                    "method": "tools/call",
                    "params": {
                        "name": secrets[5],
                        "arguments": {"package_id": secrets[3]},
                        "_meta": {"progressToken": secrets[4]},
                    },
                },
            ],
            runtime=runtime,
        )
        self.assertEqual(0, result)
        self.assertEqual(1, runtime.calls)
        decisions = [
            event for event in self.trace.verify().events if event["stage"] == "decision"
        ]
        self.assertEqual(
            ["accepted", "initialize_replayed", "tool_dispatched"],
            [event["outcome"] for event in decisions],
        )
        persisted = self.trace.path.read_text(encoding="ascii")
        for secret in secrets:
            self.assertNotIn(secret, persisted)

    def test_unknown_method_and_unsafe_values_never_persist_raw_text(self) -> None:
        raw_method = "private/method/with/credential-tunnel_secret_value"
        result, _, _ = self.transcript(
            [{"jsonrpc": "2.0", "id": 1, "method": raw_method, "params": {}}]
        )
        self.assertEqual(0, result)
        self.assertEqual("unknown", self.trace.verify().events[0]["method"])
        self.assertNotIn(raw_method, self.trace.path.read_text(encoding="ascii"))
        before = self.trace.path.read_bytes()
        with self.assertRaises(ValueError):
            self.trace.record(
                method=raw_method,
                stage="decision",
                outcome="accepted",
                readiness_before="uninitialized",
                readiness_after="uninitialized",
            )
        self.assertEqual(before, self.trace.path.read_bytes())

        invalid_combinations = (
            ("ping", "response", "pong"),
            ("ping", "decision", "response_flushed"),
            ("trace_control", "decision", "accepted"),
            ("ping", "decision", "trace_truncated"),
            ("ping", "processed", "request_scoped_initialized"),
        )
        for method, stage, outcome in invalid_combinations:
            with self.subTest(method=method, stage=stage, outcome=outcome):
                with self.assertRaises(ValueError):
                    self.trace.record(
                        method=method,
                        stage=stage,
                        outcome=outcome,
                        readiness_before="uninitialized",
                        readiness_after="uninitialized",
                    )
        self.assertEqual(before, self.trace.path.read_bytes())

    def test_binding_mode_and_hash_tamper_fail_closed(self) -> None:
        different = ProtocolTrace(
            self.root,
            ProtocolTraceBinding(
                package_id=self.binding.package_id,
                session_id_sha256=self.binding.session_id_sha256,
                manifest_sha256="4" * 64,
                approval_event_sha256=self.binding.approval_event_sha256,
                archive_sha256=self.binding.archive_sha256,
                file_set_sha256=self.binding.file_set_sha256,
                tool_schema_sha256=self.binding.tool_schema_sha256,
                audit_header_sha256=self.binding.audit_header_sha256,
                tunnel_profile_sha256=self.binding.tunnel_profile_sha256,
                tunnel_client_binary_sha256=self.binding.tunnel_client_binary_sha256,
                mcp_target_sha256=self.binding.mcp_target_sha256,
                mcp_runtime_tree_sha256=self.binding.mcp_runtime_tree_sha256,
            ),
        )
        with self.assertRaises(ProtocolTraceError) as mismatch:
            different.verify()
        self.assertEqual("PROTOCOL_TRACE_BINDING_MISMATCH", mismatch.exception.code)

        lines = self.trace.path.read_text(encoding="ascii").splitlines()
        header = json.loads(lines[0])
        header["package_id"] = "different-package"
        self.trace.path.write_text(json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(self.trace.path, 0o600)
        with self.assertRaises(ProtocolTraceError) as tampered:
            self.trace.verify()
        self.assertEqual("PROTOCOL_TRACE_BINDING_MISMATCH", tampered.exception.code)

        os.chmod(self.trace.path, 0o644)
        with self.assertRaises(ProtocolTraceError) as unsafe:
            self.trace.verify()
        self.assertEqual("PROTOCOL_TRACE_UNSAFE", unsafe.exception.code)

    def test_trace_and_lock_reject_hardlink_or_symlink_substitution(self) -> None:
        alias = self.root / "trace-alias"
        os.link(self.trace.path, alias)
        try:
            with self.assertRaises(ProtocolTraceError) as hardlinked:
                self.trace.verify()
            self.assertEqual("PROTOCOL_TRACE_UNSAFE", hardlinked.exception.code)
        finally:
            alias.unlink()

        self.trace.lock_path.unlink()
        target = self.root / "lock-target"
        target.write_bytes(b"")
        target.chmod(0o600)
        self.trace.lock_path.symlink_to(target)
        with self.assertRaises(ProtocolTraceError) as symlinked:
            self.trace.verify()
        self.assertEqual("PROTOCOL_TRACE_UNSAFE", symlinked.exception.code)

    def test_trace_failure_stops_before_tool_dispatch_and_logs_only_stable_code(self) -> None:
        class FailingTrace:
            def record(self, **kwargs):
                del kwargs
                raise ProtocolTraceError(
                    "PROTOCOL_TRACE_UNAVAILABLE",
                    "/Users/private token tunnel_secret must not be reflected",
                )

            def close(self, reason):
                del reason

        runtime = NoDisclosureRuntime()
        result, responses, stderr = self.transcript(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_repo_read",
                        "arguments": {"path": "/Users/private"},
                    },
                }
            ],
            trace=FailingTrace(),
            runtime=runtime,
        )
        self.assertEqual(1, result)
        self.assertEqual([], responses)
        self.assertEqual(0, runtime.calls)
        self.assertEqual("gptpro-mcp: MCP_PROTOCOL_TRACE_FAILED\n", stderr)
        self.assertNotIn("private", stderr)

    def test_lock_timeout_and_read_only_verify_fail_without_mutation(self) -> None:
        for unsafe_timeout in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(lock_timeout=unsafe_timeout):
                with self.assertRaises(ValueError):
                    ProtocolTrace(self.root, self.binding, lock_timeout=unsafe_timeout)

        descriptor = os.open(self.trace.lock_path, os.O_RDWR)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = ProtocolTrace(self.root, self.binding, lock_timeout=0.02)
        try:
            with self.assertRaises(ProtocolTraceError) as raised:
                blocked.record(
                    method="ping",
                    stage="decision",
                    outcome="pong",
                    readiness_before="uninitialized",
                    readiness_after="uninitialized",
                )
            self.assertEqual("PROTOCOL_TRACE_LOCK_TIMEOUT", raised.exception.code)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

        self.trace.lock_path.unlink()
        before = set(self.root.iterdir())
        with self.assertRaises(ProtocolTraceError):
            self.trace.verify()
        self.assertEqual(before, set(self.root.iterdir()))

    def test_diagnostic_command_help_has_no_runtime_side_effect(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SKILL_ROOT / "scripts" / "gptpro.py"),
                "mcp-protocol-trace",
                "--help",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--handoff-dir", result.stdout)


if __name__ == "__main__":
    unittest.main()
