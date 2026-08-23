from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.controller import (
    ControllerError,
    ControllerHooks,
    control_socket_path,
    run_foreground,
)
from runtime.gptpro_mcp.live import (
    RUNTIME_DIRECTORY_ENV,
    SESSION_CAPABILITY_ENV,
    decode_session_capability,
)
from runtime.gptpro_mcp.runtime_state import RuntimeStateStore
from runtime.gptpro_mcp.supervisor import request_cooperative_stop
from runtime.gptpro_mcp.tunnel_client import TunnelCheck, TunnelClientError


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class FakeProcess:
    def __init__(self, events: list[str], *, returncode: int | None = None) -> None:
        self.events = events
        self.returncode = returncode
        self.pid = 4242

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.events.append("terminate")
        self.returncode = 0

    def kill(self) -> None:
        self.events.append("kill")
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class StubbornFakeProcess(FakeProcess):
    def terminate(self) -> None:
        self.events.append("terminate")

    def kill(self) -> None:
        self.events.append("kill")

    def wait(self, timeout: float | None = None) -> int:
        raise subprocess.TimeoutExpired(cmd="stubborn-tunnel", timeout=timeout)


class FakeTunnel:
    def __init__(
        self,
        events: list[str],
        checks: list[TunnelCheck | BaseException],
        *,
        process_returncode: int | None = None,
        correlation: dict | BaseException | None = None,
    ) -> None:
        self.events = events
        self.checks = list(checks)
        self.process = FakeProcess(events, returncode=process_returncode)
        self.spawn: dict[str, object] = {}
        self.health_pids: list[int] = []
        self.correlation = correlation
        self.correlation_keys: list[bytes] = []
        self.correlation_pids: list[int] = []

    def spawn_run(self, profile: str, **kwargs):
        self.events.append("spawn")
        self.spawn = {"profile": profile, **kwargs}
        return self.process

    def health(self, files, *, env, expected_pid):
        del files, env
        self.health_pids.append(expected_pid)
        self.events.append("health")
        value = self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]
        if isinstance(value, BaseException):
            raise value
        return value

    def capture_request_correlation(self, files, *, hmac_key, expected_peer_pid):
        del files
        self.events.append("capture_correlation")
        self.correlation_keys.append(hmac_key)
        self.correlation_pids.append(expected_peer_pid)
        if isinstance(self.correlation, BaseException):
            raise self.correlation
        return self.correlation or {
            "schema_version": 1,
            "status": "captured",
            "events": [],
        }


class ControllerTests(unittest.TestCase):
    def test_default_readiness_window_exceeds_one_long_poll(self) -> None:
        default = inspect.signature(run_foreground).parameters["ready_timeout"].default
        self.assertEqual(60.0, default)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.handoff = self.base / "handoff"
        self.handoff.mkdir(mode=0o700)
        self.store = RuntimeStateStore(self.base / "runtime")
        self.events: list[str] = []
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.monotonic_now = time.monotonic()
        self.recorded: list[tuple[str, str]] = []

    def tearDown(self) -> None:
        self.temp.cleanup()

    def candidate(self, session_hash: str) -> dict:
        return {
            "package_id": "controller-package",
            "session_id_sha256": session_hash,
            "handoff_dir": str(self.handoff.resolve()),
            "manifest_sha256": digest(b"manifest"),
            "approval_event_sha256": digest(b"approval"),
            "archive_sha256": digest(b"archive"),
            "file_set_sha256": digest(b"files"),
            "tool_schema_sha256": digest(b"tools"),
            "tunnel_profile_sha256": digest(b"tunnel-profile"),
            "tunnel_client_binary_sha256": digest(b"tunnel-client-binary"),
            "mcp_target_sha256": digest(b"mcp-target"),
            "mcp_runtime_tree_sha256": digest(b"mcp-runtime-tree"),
            "activated_at": self.now.isoformat().replace("+00:00", "Z"),
            "expires_at": (self.now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "idle_ttl_seconds": 900,
            "activated_monotonic": self.monotonic_now,
            "expires_monotonic": self.monotonic_now + 3600,
            "last_activity_monotonic": self.monotonic_now,
        }

    def hooks(self, *, on_active=None, complete_error: BaseException | None = None) -> ControllerHooks:
        def begin(session_hash: str):
            self.events.append("begin")
            self.store.begin_activation(self.candidate(session_hash))
            return {"audit_header_sha256": digest(b"header")}

        def complete(session_hash: str, header_hash: str):
            self.events.append("complete")
            self.assertEqual(digest(b"header"), header_hash)
            if complete_error is not None:
                raise complete_error
            self.store.transition(session_hash, "activating", "active")

        def fail(session_hash: str, error_code: str):
            self.events.append(f"fail:{error_code}")
            current = self.store.read()
            if current is not None and current["status"] in {"activating", "active"}:
                self.store.transition(session_hash, current["status"], "faulted")

        def revoke(reason: str):
            self.events.append(f"revoke:{reason}")
            state = self.store.read()
            assert state is not None
            self.store.transition(state["session_id_sha256"], "active", "revoking")
            self.store.transition(state["session_id_sha256"], "revoking", "revoked")

        def record(session_hash: str, reason: str):
            self.events.append("record")
            self.recorded.append((session_hash, reason))

        return ControllerHooks(
            begin_activation=begin,
            complete_activation=complete,
            fail_activation=fail,
            revoke_authorization=revoke,
            record_stopped=record,
            on_active=on_active,
        )

    @staticmethod
    def check(*, ok: bool, poll: bool = False, code: str | None = None) -> TunnelCheck:
        return TunnelCheck(
            ok=ok,
            code=code,
            retryable=not ok,
            profile_sha256=digest(b"profile"),
            control_plane_poll_confirmed=poll,
        )

    def test_success_requires_control_plane_health_then_revokes_before_exact_stop(self) -> None:
        tunnel = FakeTunnel(
            self.events,
            [self.check(ok=False, code="TUNNEL_NOT_READY"), self.check(ok=True, poll=True)],
        )

        def on_active(session) -> None:
            self.events.append("active")
            self.assertEqual("active", self.store.read()["status"])
            self.assertTrue(
                request_cooperative_stop(session.control_socket, session.session_id_sha256)
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={"CONTROL_PLANE_API_KEY": "sk-" + "x" * 32},
            hooks=self.hooks(on_active=on_active),
            health_poll_interval=0.01,
        )

        self.assertEqual("stopped", result.status)
        self.assertTrue(result.control_plane_poll_confirmed)
        self.assertTrue(result.authorization_revoked)
        self.assertTrue(result.terminated_exact_child)
        self.assertTrue(result.stopped_recorded)
        self.assertEqual("remote_stop", result.stop_reason)
        self.assertEqual("revoked", self.store.read()["status"])
        self.assertLess(self.events.index("complete"), self.events.index("active"))
        self.assertLess(self.events.index("revoke:remote_stop"), self.events.index("terminate"))
        self.assertLess(self.events.index("terminate"), self.events.index("record"))

        extra_env = tunnel.spawn["extra_env"]
        self.assertIsInstance(extra_env, dict)
        capability = extra_env[SESSION_CAPABILITY_ENV]
        raw = decode_session_capability(capability)
        self.assertEqual(result.session_id_sha256, digest(raw))
        self.assertEqual(str(self.store.root), extra_env[RUNTIME_DIRECTORY_ENV])
        self.assertNotIn(capability, repr(result))
        self.assertNotIn("sk-", repr(result))
        self.assertEqual(self.store.root / "control.sock", control_socket_path(self.store.root))
        self.assertEqual([tunnel.process.pid, tunnel.process.pid], tunnel.health_pids)

    def test_optional_request_correlation_is_hmaced_after_revoke_before_exact_stop(self) -> None:
        tunnel = FakeTunnel(
            self.events,
            [self.check(ok=True, poll=True)],
            correlation={
                "schema_version": 1,
                "status": "captured",
                "events": [{"outer_request_id_hmac_sha256": digest(b"outer")}],
            },
        )

        def on_active(session) -> None:
            self.assertTrue(
                request_cooperative_stop(session.control_socket, session.session_id_sha256)
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=self.hooks(on_active=on_active),
            health_poll_interval=0.01,
            request_correlation_diagnostic=True,
        )

        self.assertTrue(tunnel.spawn["request_correlation_diagnostic"])
        self.assertEqual(1, len(tunnel.correlation_keys))
        self.assertEqual(32, len(tunnel.correlation_keys[0]))
        self.assertEqual([tunnel.process.pid], tunnel.correlation_pids)
        self.assertEqual("captured", result.request_correlation["status"])
        self.assertLess(
            self.events.index("revoke:remote_stop"),
            self.events.index("capture_correlation"),
        )
        self.assertLess(
            self.events.index("capture_correlation"),
            self.events.index("terminate"),
        )

    def test_request_correlation_failure_does_not_block_revoke_or_exact_stop(self) -> None:
        tunnel = FakeTunnel(
            self.events,
            [self.check(ok=True, poll=True)],
            correlation=TunnelClientError(
                "REQUEST_CORRELATION_UNAVAILABLE",
                "unsafe raw detail must not escape",
            ),
        )

        def on_active(session) -> None:
            self.assertTrue(
                request_cooperative_stop(session.control_socket, session.session_id_sha256)
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=self.hooks(on_active=on_active),
            health_poll_interval=0.01,
            request_correlation_diagnostic=True,
        )

        self.assertTrue(result.authorization_revoked)
        self.assertTrue(result.stopped_recorded)
        self.assertEqual("unavailable", result.request_correlation["status"])
        self.assertEqual(
            "REQUEST_CORRELATION_UNAVAILABLE",
            result.request_correlation["code"],
        )
        self.assertNotIn("unsafe raw detail", repr(result))

    def test_readiness_timeout_faults_before_terminating_and_does_not_record_stop(self) -> None:
        tunnel = FakeTunnel(
            self.events, [self.check(ok=False, code="TUNNEL_NOT_READY")]
        )
        clock = [0.0]

        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
                ready_timeout=0.05,
                health_poll_interval=0.01,
                monotonic=lambda: clock[0],
                sleep=lambda interval: clock.__setitem__(0, clock[0] + interval),
            )
        self.assertEqual("TUNNEL_READY_TIMEOUT", raised.exception.code)
        self.assertEqual("faulted", self.store.read()["status"])
        fail_index = next(i for i, event in enumerate(self.events) if event.startswith("fail:"))
        self.assertLess(fail_index, self.events.index("terminate"))
        self.assertNotIn("record", self.events)

    def test_unconfirmed_exact_child_stop_never_records_stopped_evidence(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        tunnel.process = StubbornFakeProcess(self.events)

        def on_active(session) -> None:
            self.assertTrue(
                request_cooperative_stop(session.control_socket, session.session_id_sha256)
            )

        with self.assertRaises(ControllerError):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(on_active=on_active),
                health_poll_interval=0.01,
                stop_timeout=0.01,
            )

        self.assertEqual("revoked", self.store.read()["status"])
        self.assertNotIn("record", self.events)
        self.assertEqual([], self.recorded)
        self.assertLess(self.events.index("revoke:remote_stop"), self.events.index("terminate"))
        self.assertLess(self.events.index("terminate"), self.events.index("kill"))

    def test_child_exit_and_unconfirmed_poll_fail_closed(self) -> None:
        scenarios = (
            (7, self.check(ok=True, poll=True), "TUNNEL_EXITED"),
            (None, self.check(ok=True, poll=False), "TUNNEL_CONTROL_PLANE_UNCONFIRMED"),
        )
        for returncode, check, expected in scenarios:
            with self.subTest(expected=expected):
                self.tearDown()
                self.setUp()
                tunnel = FakeTunnel(
                    self.events, [check], process_returncode=returncode
                )
                with self.assertRaises(ControllerError) as raised:
                    run_foreground(
                        tunnel_client=tunnel,
                        runtime_store=self.store,
                        tunnel_profile="gptpro-web",
                        child_environment={},
                        hooks=self.hooks(),
                        ready_timeout=0.1,
                        health_poll_interval=0.01,
                    )
                self.assertEqual(expected, raised.exception.code)
                self.assertEqual("faulted", self.store.read()["status"])
                self.assertNotIn("complete", self.events)

    def test_retryable_health_exception_is_retried_but_complete_failure_is_faulted(self) -> None:
        tunnel = FakeTunnel(
            self.events,
            [
                TunnelClientError("TUNNEL_NOT_READY", "not ready", retryable=True),
                self.check(ok=True, poll=True),
            ],
        )
        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(complete_error=RuntimeError("receipt failed")),
                ready_timeout=0.2,
                health_poll_interval=0.01,
            )
        self.assertEqual("MCP_ACTIVATION_FAILED", raised.exception.code)
        self.assertEqual(2, self.events.count("health"))
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertLess(self.events.index("complete"), self.events.index("fail:MCP_ACTIVATION_FAILED"))
        self.assertLess(self.events.index("fail:MCP_ACTIVATION_FAILED"), self.events.index("terminate"))

    def test_invalid_input_never_begins_or_spawns(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="bad profile",
                child_environment={},
                hooks=self.hooks(),
            )
        self.assertEqual("MCP_INVALID_ARGUMENT", raised.exception.code)
        self.assertEqual([], self.events)
        self.assertIsNone(self.store.read())

        with self.assertRaises(ControllerError) as diagnostic_flag:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
                request_correlation_diagnostic="true",  # type: ignore[arg-type]
            )
        self.assertEqual("MCP_INVALID_ARGUMENT", diagnostic_flag.exception.code)
        self.assertEqual([], self.events)
        self.assertIsNone(self.store.read())

    def test_mismatched_capability_factory_is_rejected_before_begin(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
                capability_factory=lambda: (
                    b"a" * 32,
                    "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI",
                    digest(b"a" * 32),
                ),
            )
        self.assertEqual("SESSION_CONFLICT", raised.exception.code)
        self.assertEqual([], self.events)
        self.assertIsNone(self.store.read())


if __name__ == "__main__":
    unittest.main()
