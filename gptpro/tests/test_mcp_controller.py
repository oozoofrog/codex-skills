from __future__ import annotations

import hashlib
import inspect
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

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
    PARENT_SHUTDOWN_CONTRACT_ENV,
    RUNTIME_DIRECTORY_ENV,
    SESSION_CAPABILITY_ENV,
    decode_session_capability,
    new_session_capability,
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


class ForceKilledFakeProcess(FakeProcess):
    def terminate(self) -> None:
        self.events.append("terminate")

    def kill(self) -> None:
        self.events.append("kill")
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd="force-killed-tunnel", timeout=timeout)
        return self.returncode


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
        self.activation_stops: list[tuple[str, str, int, bool]] = []
        self.remote_stop_threads: list[threading.Thread] = []
        self.remote_stop_results: list[bool] = []
        self.remote_stop_errors: list[BaseException] = []

    def tearDown(self) -> None:
        for thread in self.remote_stop_threads:
            thread.join(timeout=1.0)
        self.temp.cleanup()

    def schedule_remote_stop(self, socket_path: Path, session_hash: str) -> None:
        started = threading.Event()

        def stop() -> None:
            started.set()
            try:
                accepted = request_cooperative_stop(socket_path, session_hash)
            except BaseException as exc:
                self.remote_stop_errors.append(exc)
                return
            self.remote_stop_results.append(accepted)
            if accepted:
                self.events.append("remote_stop_accepted")

        thread = threading.Thread(target=stop)
        self.remote_stop_threads.append(thread)
        thread.start()
        self.assertTrue(started.wait(timeout=1.0))

    def assert_remote_stops_accepted(self) -> None:
        for thread in self.remote_stop_threads:
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
        self.assertEqual([], self.remote_stop_errors)
        self.assertTrue(self.remote_stop_results)
        self.assertTrue(all(self.remote_stop_results))

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

    def hooks(
        self,
        *,
        on_active=None,
        complete_error: BaseException | None = None,
        complete_callback=None,
        emergency_deny: bool = False,
    ) -> ControllerHooks:
        def begin(session_hash: str):
            self.events.append("begin")
            self.store.begin_activation(self.candidate(session_hash))
            return {"audit_header_sha256": digest(b"header")}

        def complete(
            session_hash: str,
            header_hash: str,
            on_published,
        ):
            self.events.append("complete")
            self.assertEqual(digest(b"header"), header_hash)
            if complete_error is not None:
                raise complete_error
            self.store.transition(session_hash, "activating", "active")
            on_published()
            if complete_callback is not None:
                complete_callback(session_hash)

        def fail(session_hash: str, error_code: str):
            self.events.append(f"fail:{error_code}")
            current = self.store.read()
            if current is not None and current["status"] in {"activating", "active"}:
                self.store.transition(session_hash, current["status"], "faulted")

        def revoke(reason: str):
            self.events.append(f"revoke:{reason}")
            state = self.store.read()
            assert state is not None
            if emergency_deny:
                self.store.transition(state["session_id_sha256"], "active", "faulted")
                return {
                    "authorization_denied": True,
                    "authorization_status": "faulted",
                    "revocation_receipt_recorded": False,
                    "authorization_revoked": False,
                }
            self.store.transition(state["session_id_sha256"], "active", "revoking")
            self.store.transition(state["session_id_sha256"], "revoking", "revoked")
            return {
                "authorization_denied": True,
                "authorization_status": "revoked",
                "revocation_receipt_recorded": True,
                "authorization_revoked": True,
            }

        def record(
            session_hash: str,
            reason: str,
            child_returncode: int,
            forced_exact_child: bool,
        ):
            self.events.append("record")
            self.recorded.append((session_hash, reason))
            self.assertIsInstance(child_returncode, int)
            self.assertIsInstance(forced_exact_child, bool)
            receipt_recorded = self.store.read()["status"] == "revoked"
            return {
                "exact_child_stop_recorded": True,
                "runtime_stop_receipt_recorded": receipt_recorded,
            }

        def record_activation_stop(
            session_hash: str,
            reason: str,
            child_returncode: int,
            forced_exact_child: bool,
        ):
            self.events.append("record_activation_stop")
            self.assertIn(self.store.read()["status"], {"faulted", "revoked"})
            self.activation_stops.append(
                (session_hash, reason, child_returncode, forced_exact_child)
            )
            return {
                "exact_child_stop_recorded": True,
                "activation_stop_receipt_recorded": True,
            }

        return ControllerHooks(
            begin_activation=begin,
            complete_activation=complete,
            fail_activation=fail,
            revoke_authorization=revoke,
            record_stopped=record,
            record_activation_stopped=record_activation_stop,
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
            self.schedule_remote_stop(
                session.control_socket, session.session_id_sha256
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={"CONTROL_PLANE_API_KEY": "sk-" + "x" * 32},
            hooks=self.hooks(on_active=on_active),
            health_poll_interval=0.01,
            parent_shutdown_contract_supported=True,
        )
        self.assert_remote_stops_accepted()

        self.assertEqual("stopped", result.status)
        self.assertTrue(result.control_plane_poll_confirmed)
        self.assertTrue(result.authorization_denied)
        self.assertEqual("revoked", result.authorization_status)
        self.assertTrue(result.revocation_receipt_recorded)
        self.assertTrue(result.authorization_revoked)
        self.assertTrue(result.terminated_exact_child)
        self.assertTrue(result.stopped_recorded)
        self.assertTrue(result.exact_child_stop_recorded)
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
        self.assertEqual("1", extra_env[PARENT_SHUTDOWN_CONTRACT_ENV])
        self.assertNotIn(capability, repr(result))
        self.assertNotIn("sk-", repr(result))
        self.assertEqual(self.store.root / "control.sock", control_socket_path(self.store.root))
        self.assertEqual([tunnel.process.pid, tunnel.process.pid], tunnel.health_pids)

    def test_remote_stop_during_readiness_cancels_before_activation(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        original_health = tunnel.health

        def stop_during_health(files, *, env, expected_pid):
            self.assertTrue(
                request_cooperative_stop(
                    control_socket_path(self.store.root), session_hash
                )
            )
            return original_health(files, env=env, expected_pid=expected_pid)

        tunnel.health = stop_during_health  # type: ignore[method-assign]
        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(on_active=lambda session: self.events.append("active")),
                ready_timeout=2.0,
                health_poll_interval=1.0,
                capability_factory=lambda: capability,
            )

        self.assertEqual("ACTIVATION_CANCELLED", raised.exception.code)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertNotIn("complete", self.events)
        self.assertNotIn("active", self.events)
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual("remote_stop", self.activation_stops[0][1])
        self.assertLess(
            self.events.index("terminate"), self.events.index("record_activation_stop")
        )

    def test_stop_racing_with_activation_publication_is_linearized(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])

        def stop_after_commit(committed_session: str) -> None:
            self.assertEqual(session_hash, committed_session)
            self.schedule_remote_stop(
                control_socket_path(self.store.root), session_hash
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=self.hooks(
                complete_callback=stop_after_commit,
                on_active=lambda session: self.events.append("active"),
            ),
            capability_factory=lambda: capability,
        )
        self.assert_remote_stops_accepted()

        self.assertEqual("stopped", result.status)
        self.assertEqual("remote_stop", result.stop_reason)
        self.assertEqual("revoked", result.authorization_status)
        self.assertIn("active", self.events)
        self.assertLess(
            self.events.index("active"), self.events.index("remote_stop_accepted")
        )

    def test_signal_during_activation_commit_is_accepted_after_publication(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        base_hooks = self.hooks(on_active=lambda session: self.events.append("active"))

        def complete_with_signal(
            committed_session: str,
            header_hash: str,
            on_published,
        ) -> None:
            self.assertEqual(session_hash, committed_session)
            self.assertEqual(digest(b"header"), header_hash)
            self.events.append("signal_sent")
            os.kill(os.getpid(), signal.SIGTERM)
            self.store.transition(committed_session, "activating", "active")
            self.events.append("commit")
            on_published()

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=complete_with_signal,
            fail_activation=base_hooks.fail_activation,
            revoke_authorization=base_hooks.revoke_authorization,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
            on_active=base_hooks.on_active,
        )
        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=hooks,
            capability_factory=lambda: capability,
        )

        self.assertEqual("signal_term", result.stop_reason)
        self.assertEqual("revoked", result.authorization_status)
        self.assertLess(self.events.index("commit"), self.events.index("active"))
        self.assertLess(self.events.index("active"), self.events.index("revoke:signal_term"))

    def test_child_exit_during_activation_commit_prevents_active_announcement(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        base_hooks = self.hooks(on_active=lambda session: self.events.append("active"))

        def complete_after_child_exit(
            committed_session: str,
            header_hash: str,
            on_published,
        ) -> None:
            self.assertEqual(session_hash, committed_session)
            self.assertEqual(digest(b"header"), header_hash)
            self.events.append("complete")
            self.store.transition(committed_session, "activating", "active")
            tunnel.process.returncode = 7
            self.events.append("child_exited")
            on_published()

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=complete_after_child_exit,
            fail_activation=base_hooks.fail_activation,
            revoke_authorization=base_hooks.revoke_authorization,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
            on_active=base_hooks.on_active,
        )

        with self.assertRaises(ControllerError) as raised:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=hooks,
                capability_factory=lambda: capability,
            )

        self.assertEqual("TUNNEL_EXITED", raised.exception.code)
        self.assertNotIn("active", self.events)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual("child_exit", self.activation_stops[0][1])
        self.assertEqual(7, self.activation_stops[0][2])

    def test_external_revoke_after_commit_is_not_reclassified_as_activation_failure(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        base_hooks = self.hooks(on_active=lambda session: self.events.append("active"))

        def complete_then_external_revoke(
            committed_session: str,
            header_hash: str,
            on_published,
        ) -> None:
            self.assertEqual(session_hash, committed_session)
            self.assertEqual(digest(b"header"), header_hash)
            self.events.append("complete")
            self.store.transition(committed_session, "activating", "active")
            on_published()
            self.store.transition(committed_session, "active", "revoking")
            self.store.transition(committed_session, "revoking", "revoked")
            self.events.append("external_revoke")
            self.schedule_remote_stop(
                control_socket_path(self.store.root), committed_session
            )

        def idempotent_revoke(reason: str) -> dict[str, object]:
            self.events.append(f"revoke:{reason}")
            self.assertEqual("revoked", self.store.read()["status"])
            return {
                "authorization_denied": True,
                "authorization_status": "revoked",
                "revocation_receipt_recorded": True,
                "authorization_revoked": True,
            }

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=complete_then_external_revoke,
            fail_activation=base_hooks.fail_activation,
            revoke_authorization=idempotent_revoke,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
            on_active=base_hooks.on_active,
        )
        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=hooks,
            capability_factory=lambda: capability,
        )
        self.assert_remote_stops_accepted()

        self.assertEqual("revoked", result.authorization_status)
        self.assertTrue(result.stopped_recorded)
        self.assertFalse(result.activation_stop_receipt_recorded)
        self.assertIn("active", self.events)
        self.assertLess(self.events.index("active"), self.events.index("external_revoke"))
        self.assertFalse(any(event.startswith("fail:") for event in self.events))

    def test_external_revoke_in_progress_after_locked_announcement_remains_normal_stop(self) -> None:
        capability = new_session_capability()
        session_hash = capability[2]
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        base_hooks = self.hooks(on_active=lambda session: self.events.append("active"))

        def complete_then_begin_external_revoke(
            committed_session: str,
            header_hash: str,
            on_published,
        ) -> None:
            self.assertEqual(session_hash, committed_session)
            self.assertEqual(digest(b"header"), header_hash)
            self.events.append("complete")
            self.store.transition(committed_session, "activating", "active")
            on_published()
            self.store.transition(committed_session, "active", "revoking")
            self.events.append("external_revoking")
            self.schedule_remote_stop(
                control_socket_path(self.store.root), committed_session
            )

        def finish_external_revoke(reason: str) -> dict[str, object]:
            self.events.append(f"revoke:{reason}")
            self.assertEqual("revoking", self.store.read()["status"])
            self.store.transition(session_hash, "revoking", "revoked")
            return {
                "authorization_denied": True,
                "authorization_status": "revoked",
                "revocation_receipt_recorded": True,
                "authorization_revoked": True,
            }

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=complete_then_begin_external_revoke,
            fail_activation=base_hooks.fail_activation,
            revoke_authorization=finish_external_revoke,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
            on_active=base_hooks.on_active,
        )
        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=hooks,
            capability_factory=lambda: capability,
        )
        self.assert_remote_stops_accepted()

        self.assertEqual("revoked", result.authorization_status)
        self.assertTrue(result.stopped_recorded)
        self.assertFalse(result.activation_stop_receipt_recorded)
        self.assertIn("active", self.events)
        self.assertLess(self.events.index("active"), self.events.index("external_revoking"))
        self.assertFalse(any(event.startswith("fail:") for event in self.events))

    def test_keyboard_interrupt_during_readiness_records_failure_stop_then_propagates(self) -> None:
        tunnel = FakeTunnel(self.events, [KeyboardInterrupt()])

        with self.assertRaises(KeyboardInterrupt):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
            )

        self.assertEqual("faulted", self.store.read()["status"])
        self.assertIn("fail:ACTIVATION_CANCELLED", self.events)
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual("user_interrupt", self.activation_stops[0][1])
        self.assertLess(self.events.index("terminate"), self.events.index("record_activation_stop"))

    def test_listener_failure_code_is_persisted_before_cleanup(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.selectors.DefaultSelector",
                side_effect=OSError("selector unavailable"),
            ),
            self.assertRaises(ControllerError) as raised,
        ):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
            )

        self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
        self.assertIn("fail:CONTROL_LISTENER_FAILED", self.events)
        self.assertEqual("faulted", self.store.read()["status"])

    def test_post_spawn_listener_failure_keeps_listener_cause_and_reason(self) -> None:
        spawned = threading.Event()
        supervisor_holder = {}
        tunnel = FakeTunnel(self.events, [self.check(ok=False)])
        original_spawn = tunnel.spawn_run
        original_health = tunnel.health

        class BreakAfterSpawnSelector:
            def register(self, fileobj, events) -> None:
                del fileobj, events

            def select(self, timeout=None):
                del timeout
                if not spawned.wait(timeout=2.0):
                    raise AssertionError("Tunnel child did not start")
                raise OSError("selector failed after spawn")

            def close(self) -> None:
                return None

        def spawn(*args, **kwargs):
            process = original_spawn(*args, **kwargs)
            spawned.set()
            return process

        def health(*args, **kwargs):
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                supervisor = supervisor_holder.get("value")
                if supervisor is not None and supervisor.failure_code is not None:
                    break
                time.sleep(0.005)
            return original_health(*args, **kwargs)

        def supervisor_factory(**kwargs):
            from runtime.gptpro_mcp.supervisor import ForegroundSupervisor

            supervisor = ForegroundSupervisor(**kwargs)
            supervisor_holder["value"] = supervisor
            return supervisor

        tunnel.spawn_run = spawn  # type: ignore[method-assign]
        tunnel.health = health  # type: ignore[method-assign]
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.selectors.DefaultSelector",
                side_effect=BreakAfterSpawnSelector,
            ),
            self.assertRaises(ControllerError) as raised,
        ):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
                supervisor_factory=supervisor_factory,
            )

        self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
        self.assertIn("fail:CONTROL_LISTENER_FAILED", self.events)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual("listener_failure", self.activation_stops[0][1])

    def test_listener_bind_failure_code_is_persisted_before_cleanup(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.ForegroundSupervisor._bind_control_socket",
                side_effect=OSError("bind unavailable"),
            ),
            self.assertRaises(ControllerError) as raised,
        ):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
            )

        self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
        self.assertIn("fail:CONTROL_LISTENER_FAILED", self.events)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertNotIn("spawn", self.events)

    def test_listener_thread_start_failure_code_is_persisted_before_cleanup(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.threading.Thread.start",
                side_effect=RuntimeError("thread unavailable"),
            ),
            self.assertRaises(ControllerError) as raised,
        ):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
            )

        self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
        self.assertIn("fail:CONTROL_LISTENER_FAILED", self.events)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertNotIn("spawn", self.events)

    def test_transient_failure_denial_is_retried_before_activation_stop_record(self) -> None:
        tunnel = FakeTunnel(
            self.events, [self.check(ok=True, poll=False)]
        )
        base_hooks = self.hooks()
        attempts = 0

        def fail_once(session_hash: str, error_code: str) -> None:
            nonlocal attempts
            attempts += 1
            self.events.append(f"fail_attempt:{attempts}:{error_code}")
            if attempts == 1:
                raise ControllerError(
                    "RUNTIME_STATE_WRITE_FAILED",
                    "simulated transient machine-global denial failure",
                )
            self.store.transition(session_hash, "activating", "faulted")

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=base_hooks.complete_activation,
            fail_activation=fail_once,
            revoke_authorization=base_hooks.revoke_authorization,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
        )
        with self.assertRaises(ControllerError):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=hooks,
            )

        self.assertEqual(2, attempts)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertEqual(1, len(self.activation_stops))
        self.assertLess(
            self.events.index("fail_attempt:2:TUNNEL_CONTROL_PLANE_UNCONFIRMED"),
            self.events.index("record_activation_stop"),
        )

    def test_third_denial_attempt_still_records_terminal_activation_child(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=False)])
        base_hooks = self.hooks()
        attempts = 0

        def fail_twice(session_hash: str, error_code: str) -> None:
            nonlocal attempts
            attempts += 1
            self.events.append(f"fail_attempt:{attempts}:{error_code}")
            if attempts < 3:
                raise ControllerError(
                    "RUNTIME_STATE_WRITE_FAILED",
                    "simulated repeated machine-global denial failure",
                )
            self.store.transition(session_hash, "activating", "faulted")

        hooks = ControllerHooks(
            begin_activation=base_hooks.begin_activation,
            complete_activation=base_hooks.complete_activation,
            fail_activation=fail_twice,
            revoke_authorization=base_hooks.revoke_authorization,
            record_stopped=base_hooks.record_stopped,
            record_activation_stopped=base_hooks.record_activation_stopped,
        )
        with self.assertRaises(ControllerError):
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=hooks,
            )

        self.assertEqual(3, attempts)
        self.assertEqual("faulted", self.store.read()["status"])
        self.assertEqual(1, len(self.activation_stops))
        self.assertLess(
            self.events.index(
                "fail_attempt:3:TUNNEL_CONTROL_PLANE_UNCONFIRMED"
            ),
            self.events.index("record_activation_stop"),
        )

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
            self.schedule_remote_stop(
                session.control_socket, session.session_id_sha256
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
        self.assert_remote_stops_accepted()

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
            self.schedule_remote_stop(
                session.control_socket, session.session_id_sha256
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
        self.assert_remote_stops_accepted()

        self.assertTrue(result.authorization_revoked)
        self.assertTrue(result.stopped_recorded)
        self.assertEqual("unavailable", result.request_correlation["status"])
        self.assertEqual(
            "REQUEST_CORRELATION_UNAVAILABLE",
            result.request_correlation["code"],
        )
        self.assertNotIn("unsafe raw detail", repr(result))

    def test_emergency_faulted_deny_is_not_revocation_and_skips_diagnostic_capture(self) -> None:
        tunnel = FakeTunnel(
            self.events,
            [self.check(ok=True, poll=True)],
            correlation={"schema_version": 1, "status": "captured", "events": []},
        )

        def on_active(session) -> None:
            self.schedule_remote_stop(
                session.control_socket, session.session_id_sha256
            )

        result = run_foreground(
            tunnel_client=tunnel,
            runtime_store=self.store,
            tunnel_profile="gptpro-web",
            child_environment={},
            hooks=self.hooks(on_active=on_active, emergency_deny=True),
            health_poll_interval=0.01,
            request_correlation_diagnostic=True,
        )
        self.assert_remote_stops_accepted()

        self.assertTrue(result.authorization_denied)
        self.assertEqual("faulted", result.authorization_status)
        self.assertFalse(result.revocation_receipt_recorded)
        self.assertFalse(result.authorization_revoked)
        self.assertTrue(result.exact_child_stop_recorded)
        self.assertFalse(result.stopped_recorded)
        self.assertIsNone(result.request_correlation)
        self.assertNotIn("capture_correlation", self.events)

    def test_readiness_timeout_faults_then_records_only_activation_child_stop(self) -> None:
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
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual("controller_exit", self.activation_stops[0][1])
        self.assertEqual(0, self.activation_stops[0][2])
        self.assertFalse(self.activation_stops[0][3])
        self.assertLess(self.events.index("terminate"), self.events.index("record_activation_stop"))

    def test_unconfirmed_exact_child_stop_never_records_stopped_evidence(self) -> None:
        tunnel = FakeTunnel(self.events, [self.check(ok=True, poll=True)])
        tunnel.process = StubbornFakeProcess(self.events)

        def on_active(session) -> None:
            self.schedule_remote_stop(
                session.control_socket, session.session_id_sha256
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
        self.assert_remote_stops_accepted()

        self.assertEqual("revoked", self.store.read()["status"])
        self.assertNotIn("record", self.events)
        self.assertEqual([], self.recorded)
        self.assertLess(self.events.index("revoke:remote_stop"), self.events.index("terminate"))
        self.assertLess(self.events.index("terminate"), self.events.index("kill"))

    def test_failed_activation_records_forced_exact_child_only_after_kill_returncode(self) -> None:
        tunnel = FakeTunnel(
            self.events, [self.check(ok=False, code="TUNNEL_NOT_READY")]
        )
        tunnel.process = ForceKilledFakeProcess(self.events)
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
                stop_timeout=0.01,
                monotonic=lambda: clock[0],
                sleep=lambda interval: clock.__setitem__(0, clock[0] + interval),
            )

        self.assertEqual("TUNNEL_READY_TIMEOUT", raised.exception.code)
        self.assertEqual(1, len(self.activation_stops))
        self.assertEqual(-9, self.activation_stops[0][2])
        self.assertTrue(self.activation_stops[0][3])
        self.assertLess(self.events.index("kill"), self.events.index("record_activation_stop"))

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
                if returncode is not None:
                    self.assertEqual("child_exit", self.activation_stops[0][1])

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

        with self.assertRaises(ControllerError) as shutdown_flag:
            run_foreground(
                tunnel_client=tunnel,
                runtime_store=self.store,
                tunnel_profile="gptpro-web",
                child_environment={},
                hooks=self.hooks(),
                parent_shutdown_contract_supported="true",  # type: ignore[arg-type]
            )
        self.assertEqual("MCP_INVALID_ARGUMENT", shutdown_flag.exception.code)
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
