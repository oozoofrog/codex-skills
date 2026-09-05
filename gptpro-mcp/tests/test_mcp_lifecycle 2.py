from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.util
import json
import multiprocessing
import os
import py_compile
import shlex
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.audit import (
    ACCOUNTING_MODE,
    AUDIT_SCHEMA_VERSION,
    LEGACY_ACCOUNTING_MODE,
    LEGACY_AUDIT_SCHEMA_VERSION,
    AuditBinding,
    AuditLog,
)
from runtime.gptpro_mcp.authorization import AuthorizationGrant
from runtime.gptpro_mcp.clock import Clock
from runtime.gptpro_mcp.errors import ToolError
from runtime.gptpro_mcp import supervisor as supervisor_module
from runtime.gptpro_mcp.live import ControllerLease
from runtime.gptpro_mcp.runtime_state import (
    RuntimeStateError,
    RuntimeStateStore,
    default_runtime_root,
    ensure_private_directory,
    validate_active_state,
)
from runtime.gptpro_mcp.schema import DEFAULT_LIMITS, PROTOCOL_PROFILE, tool_schema_sha256
from runtime.gptpro_mcp.supervisor import ForegroundSupervisor, request_cooperative_stop
from runtime.gptpro_mcp import tunnel_client as tunnel_client_module
from runtime.gptpro_mcp.tunnel_client import (
    ProfileControllerLease,
    TunnelCapabilities,
    TunnelCheck,
    TunnelClient,
    TunnelClientError,
    TunnelRuntimeFiles,
    inspect_tunnel_profile,
    loopback_url_from_file,
    popen_with_signal_mask,
    prepare_runtime_files,
    runtime_key_environment,
    tunnel_binding_from_reference,
    tunnel_binding_from_profile,
    validate_control_plane_base_url,
    validate_loopback_base_url,
    validate_unix_health_base_url,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def state_candidate(session_hash: str, handoff: Path, *, package_id: str = "package-one") -> dict:
    now = datetime.now(timezone.utc)
    monotonic_now = time.monotonic()
    return {
        "schema_version": 1,
        "revision": 1,
        "status": "activating",
        "package_id": package_id,
        "session_id_sha256": session_hash,
        "handoff_dir": str(handoff.resolve()),
        "manifest_sha256": digest(b"manifest"),
        "approval_event_sha256": digest(b"approval"),
        "archive_sha256": digest(b"archive"),
        "file_set_sha256": digest(b"files"),
        "tool_schema_sha256": tool_schema_sha256(),
        "mcp_target_sha256": digest(b"mcp-target"),
        "tunnel_profile_sha256": digest(b"tunnel-profile"),
        "tunnel_client_binary_sha256": digest(b"tunnel-client-binary"),
        "mcp_runtime_tree_sha256": digest(b"mcp-runtime-tree"),
        "activated_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "idle_ttl_seconds": 900,
        "activated_monotonic": monotonic_now,
        "expires_monotonic": monotonic_now + 3600,
        "last_activity_monotonic": monotonic_now,
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "disclosure_accounting": ACCOUNTING_MODE,
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }


def _activation_worker(root: str, handoff: str, session_hash: str, start, queue) -> None:
    start.wait(5)
    try:
        RuntimeStateStore(Path(root)).begin_activation(state_candidate(session_hash, Path(handoff)))
        queue.put("ok")
    except RuntimeStateError as exc:
        queue.put(exc.code)


class RuntimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "runtime"
        self.handoff = self.base / "handoff"
        self.handoff.mkdir(mode=0o700)
        self.session = digest(b"session-one")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_disclosure_accounting_binding_is_paired_and_immutable(self) -> None:
        candidate = state_candidate(self.session, self.handoff)
        candidate.pop("disclosure_accounting")
        with self.assertRaises(RuntimeStateError) as incomplete:
            validate_active_state(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", incomplete.exception.code)

        candidate["disclosure_accounting"] = ACCOUNTING_MODE
        validated = validate_active_state(candidate)
        self.assertEqual(AUDIT_SCHEMA_VERSION, validated["audit_schema_version"])
        self.assertEqual(ACCOUNTING_MODE, validated["disclosure_accounting"])

        store = RuntimeStateStore(self.root)
        store.begin_activation(candidate)
        with self.assertRaises(RuntimeStateError) as mutation:
            store.transition(
                self.session,
                "activating",
                "active",
                updates={"disclosure_accounting": "legacy_tool_body_estimate"},
            )
        self.assertEqual("RUNTIME_STATE_UNSAFE", mutation.exception.code)
        self.assertEqual("activating", store.read()["status"])

    def test_private_modes_one_active_guard_and_exact_transitions(self) -> None:
        store = RuntimeStateStore(self.root)
        created = store.begin_activation(state_candidate(self.session, self.handoff))
        self.assertEqual("activating", created["status"])
        self.assertEqual(0o700, self.root.stat().st_mode & 0o777)
        self.assertEqual(0o600, store.active_path.stat().st_mode & 0o777)
        self.assertEqual(0o600, store.lock_path.stat().st_mode & 0o777)
        with self.assertRaises(RuntimeStateError) as raised:
            store.begin_activation(state_candidate(digest(b"second"), self.handoff))
        self.assertEqual("SESSION_CONFLICT", raised.exception.code)

        active = store.transition(self.session, "activating", "active")
        self.assertEqual("active", active["status"])
        with self.assertRaises(RuntimeStateError):
            store.transition(
                self.session,
                "active",
                "revoking",
                updates={"archive_sha256": digest(b"different-archive")},
            )
        revoking = store.transition(self.session, "active", "revoking")
        self.assertEqual("revoking", revoking["status"])
        terminal = store.transition(self.session, "revoking", "revoked")
        self.assertEqual("revoked", terminal["status"])
        self.assertNotIn("protocol_trace_header_sha256", terminal)
        reloaded_terminal = store.read()
        self.assertIsNotNone(reloaded_terminal)
        self.assertEqual("revoked", reloaded_terminal["status"])
        self.assertNotIn("protocol_trace_header_sha256", reloaded_terminal)
        with self.assertRaises(RuntimeStateError):
            store.transition(self.session, "revoked", "active")

        stopped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with store.locked() as transaction:
            current = transaction.read()
            current.update(
                {
                    "runtime_child_stopped": True,
                    "runtime_child_returncode": 0,
                    "runtime_forced_exact_child": False,
                    "runtime_stop_reason": "user_requested",
                    "runtime_stop_receipt_recorded": False,
                    "runtime_stop_recorded_at": stopped_at,
                    "revision": current["revision"] + 1,
                    "updated_at": stopped_at,
                }
            )
            transaction.write(current)
        next_session = digest(b"next")
        store.begin_activation(state_candidate(next_session, self.handoff, package_id="package-two"))
        archived = self.root / "sessions" / f"{self.session}.json"
        self.assertTrue(archived.is_file())
        self.assertEqual(0o600, archived.stat().st_mode & 0o777)

    def test_terminal_session_cannot_be_archived_while_controller_lease_is_live(self) -> None:
        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        store.transition(self.session, "activating", "revoked")
        next_session = digest(b"next-after-cleanup")

        with ControllerLease(store, self.session):
            with self.assertRaises(RuntimeStateError) as raised:
                store.begin_activation(
                    state_candidate(
                        next_session,
                        self.handoff,
                        package_id="package-two",
                    )
                )

        self.assertEqual("SESSION_CONFLICT", raised.exception.code)
        self.assertEqual(self.session, store.read()["session_id_sha256"])
        with self.assertRaises(RuntimeStateError) as orphaned:
            store.begin_activation(
                state_candidate(next_session, self.handoff, package_id="package-two")
            )
        self.assertEqual("CONTROLLER_ORPHANED", orphaned.exception.code)
        store.confirm_orphan_tunnel_termination(self.session)
        activated = store.begin_activation(
            state_candidate(next_session, self.handoff, package_id="package-two")
        )
        self.assertEqual(next_session, activated["session_id_sha256"])

    def test_archived_session_read_is_exact_owner_only_and_fail_closed(self) -> None:
        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        stopped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        store.transition(
            self.session,
            "activating",
            "faulted",
            updates={
                "activation_child_stopped": True,
                "activation_child_returncode": -15,
                "activation_forced_exact_child": False,
                "activation_stop_reason": "controller_exit",
                "activation_stop_receipt_recorded": False,
                "activation_stop_recorded_at": stopped_at,
            },
        )
        next_session = digest(b"next-archive-reader")
        store.begin_activation(
            state_candidate(next_session, self.handoff, package_id="package-two")
        )

        archived = store.read_archived_session(self.session)
        self.assertIsNotNone(archived)
        self.assertEqual(self.session, archived["session_id_sha256"])
        self.assertTrue(archived["activation_child_stopped"])
        self.assertIsNone(store.read_archived_session(digest(b"not-archived")))
        with self.assertRaises(RuntimeStateError) as invalid:
            store.read_archived_session("../active")
        self.assertEqual("RUNTIME_STATE_UNSAFE", invalid.exception.code)

        archive_path = store.sessions_path / f"{self.session}.json"
        archive_path.chmod(0o644)
        with self.assertRaises(RuntimeStateError) as permissive:
            store.read_archived_session(self.session)
        self.assertEqual("RUNTIME_STATE_UNSAFE", permissive.exception.code)
        archive_path.chmod(0o600)

        hardlink = self.base / "archive-hardlink.json"
        os.link(archive_path, hardlink)
        with self.assertRaises(RuntimeStateError) as linked:
            store.read_archived_session(self.session)
        self.assertEqual("RUNTIME_STATE_UNSAFE", linked.exception.code)
        hardlink.unlink()

    def test_terminal_session_without_stop_evidence_requires_a_safe_released_lease(self) -> None:
        for condition in ("missing", "unsafe"):
            with self.subTest(condition=condition):
                root = self.base / condition
                store = RuntimeStateStore(root)
                session = digest(f"terminal-{condition}".encode())
                store.begin_activation(state_candidate(session, self.handoff))
                store.transition(session, "activating", "revoked")
                if condition == "unsafe":
                    lease = ControllerLease(store, session).acquire()
                    lease.close()
                    lease.path.chmod(0o644)

                with self.assertRaises(RuntimeStateError) as raised:
                    store.begin_activation(
                        state_candidate(
                            digest(f"next-{condition}".encode()),
                            self.handoff,
                            package_id="package-two",
                        )
                    )

                self.assertEqual("CONTROLLER_ORPHANED", raised.exception.code)
                self.assertEqual(session, store.read()["session_id_sha256"])

    def test_manual_orphan_confirmation_is_additive_and_not_exact_child_evidence(self) -> None:
        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        store.transition(self.session, "activating", "revoked")
        lease = ControllerLease(store, self.session).acquire()
        lease.close()

        confirmed = store.confirm_orphan_tunnel_termination(self.session)
        self.assertTrue(confirmed["orphan_tunnel_termination_manually_confirmed"])
        self.assertNotIn("runtime_child_stopped", confirmed)
        self.assertNotIn("activation_child_stopped", confirmed)
        self.assertEqual(
            confirmed,
            store.confirm_orphan_tunnel_termination(self.session),
        )

    def test_positive_exact_child_stop_allows_archive_when_terminal_lease_is_missing(self) -> None:
        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        stopped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        store.transition(
            self.session,
            "activating",
            "faulted",
            updates={
                "activation_child_stopped": True,
                "activation_child_returncode": -15,
                "activation_forced_exact_child": False,
                "activation_stop_reason": "controller_exit",
                "activation_stop_receipt_recorded": False,
                "activation_stop_recorded_at": stopped_at,
            },
        )

        next_session = digest(b"next-after-positive-stop")
        activated = store.begin_activation(
            state_candidate(next_session, self.handoff, package_id="package-two")
        )
        self.assertEqual(next_session, activated["session_id_sha256"])

    def test_runtime_root_rejects_preexisting_intermediate_symlink(self) -> None:
        target = self.base / "target"
        (target / "runtime").mkdir(parents=True, mode=0o700)
        link = self.base / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeStateError) as raised:
            RuntimeStateStore(link / "runtime")
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    def test_private_directory_creation_reopens_same_directory_race(self) -> None:
        target = self.base / "shared" / "runtime"
        runtime_state_module = sys.modules[RuntimeStateStore.__module__]
        original_mkdir = runtime_state_module.os.mkdir

        def racing_mkdir(path, mode=0o777, *, dir_fd=None):
            original_mkdir(path, mode, dir_fd=dir_fd)
            if path == "runtime":
                raise FileExistsError("simulated same-directory creation race")

        with mock.patch.object(runtime_state_module.os, "mkdir", side_effect=racing_mkdir):
            self.assertEqual(target, ensure_private_directory(target))

        metadata = target.stat()
        self.assertEqual(os.getuid(), metadata.st_uid)
        self.assertEqual(0o700, stat.S_IMODE(metadata.st_mode))

    def test_private_directory_creation_race_rejects_symlink_winner(self) -> None:
        target = self.base / "shared-link" / "runtime"
        decoy = self.base / "decoy"
        decoy.mkdir(mode=0o700)
        runtime_state_module = sys.modules[RuntimeStateStore.__module__]
        original_mkdir = runtime_state_module.os.mkdir

        def racing_mkdir(path, mode=0o777, *, dir_fd=None):
            if path == "runtime":
                os.symlink(decoy, path, dir_fd=dir_fd, target_is_directory=True)
                raise FileExistsError("simulated symlink creation race")
            original_mkdir(path, mode, dir_fd=dir_fd)

        with mock.patch.object(runtime_state_module.os, "mkdir", side_effect=racing_mkdir):
            with self.assertRaises(RuntimeStateError) as raised:
                ensure_private_directory(target)
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    @unittest.skipUnless(sys.platform == "darwin", "macOS canonical runtime root")
    def test_default_runtime_root_ignores_caller_home_environment(self) -> None:
        import pwd

        canonical_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        with mock.patch.dict(os.environ, {"HOME": str(self.base / "attacker-home")}):
            self.assertEqual(
                canonical_home
                / "Library"
                / "Application Support"
                / "gptpro"
                / "runtime"
                / "v1",
                default_runtime_root(),
            )

    def test_symlink_hardlink_and_mode_drift_are_rejected(self) -> None:
        target = self.base / "target"
        target.mkdir(mode=0o700)
        symlink_root = self.base / "runtime-link"
        symlink_root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeStateError):
            RuntimeStateStore(symlink_root)

        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        hardlink = self.base / "active-hardlink"
        os.link(store.active_path, hardlink)
        with self.assertRaises(RuntimeStateError):
            store.read()
        hardlink.unlink()

        store.active_path.chmod(0o644)
        with self.assertRaises(RuntimeStateError):
            store.read()
        store.active_path.chmod(0o600)

        store.active_path.unlink()
        other = self.base / "other.json"
        other.write_text("{}", encoding="utf-8")
        other.chmod(0o600)
        store.active_path.symlink_to(other)
        with self.assertRaises(RuntimeStateError):
            store.read()

    def test_concurrent_activation_allows_exactly_one_package(self) -> None:
        RuntimeStateStore(self.root)
        context = multiprocessing.get_context("fork")
        start = context.Event()
        queue = context.Queue()
        processes = [
            context.Process(
                target=_activation_worker,
                args=(str(self.root), str(self.handoff), digest(f"session-{index}".encode()), start, queue),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        start.set()
        results = [queue.get(timeout=5) for _ in processes]
        for process in processes:
            process.join(timeout=5)
            self.assertEqual(0, process.exitcode)
        self.assertEqual(["SESSION_CONFLICT", "ok"], sorted(results))

    def test_raw_credentials_are_not_accepted_in_active_state(self) -> None:
        store = RuntimeStateStore(self.root)
        candidate = state_candidate(self.session, self.handoff)
        candidate["runtime_api_key"] = "sk-" + "x" * 32
        with self.assertRaises(RuntimeStateError) as raised:
            store.begin_activation(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    def test_exact_child_stop_evidence_is_complete_typed_and_survives_recovery(self) -> None:
        store = RuntimeStateStore(self.root)
        store.begin_activation(state_candidate(self.session, self.handoff))
        stopped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        faulted = store.transition(
            self.session,
            "activating",
            "faulted",
            updates={
                "activation_child_stopped": True,
                "activation_child_returncode": -15,
                "activation_forced_exact_child": False,
                "activation_stop_reason": "controller_exit",
                "activation_stop_receipt_recorded": False,
                "activation_stop_recorded_at": stopped_at,
            },
        )
        self.assertTrue(faulted["activation_child_stopped"])
        recovered = store.transition(self.session, "faulted", "revoked")
        self.assertTrue(recovered["activation_child_stopped"])

        invalid_cases = {
            "incomplete": {"activation_child_stopped": True},
            "boolean-returncode": {
                "activation_child_stopped": True,
                "activation_child_returncode": True,
                "activation_forced_exact_child": False,
                "activation_stop_reason": "controller_exit",
                "activation_stop_receipt_recorded": False,
                "activation_stop_recorded_at": stopped_at,
            },
            "orphan-receipt-hash": {
                "activation_stop_receipt_event_sha256": digest(b"orphan")
            },
        }
        for label, evidence in invalid_cases.items():
            with self.subTest(label=label):
                candidate = state_candidate(digest(label.encode()), self.handoff)
                candidate["status"] = "faulted"
                candidate.update(evidence)
                with self.assertRaises(RuntimeStateError) as raised:
                    validate_active_state(candidate)
                self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

        nonterminal = state_candidate(digest(b"nonterminal-stop"), self.handoff)
        nonterminal.update(
            {
                "runtime_child_stopped": True,
                "runtime_child_returncode": 0,
                "runtime_forced_exact_child": False,
                "runtime_stop_reason": "user_requested",
                "runtime_stop_receipt_recorded": False,
                "runtime_stop_recorded_at": stopped_at,
            }
        )
        with self.assertRaises(RuntimeStateError) as raised:
            validate_active_state(nonterminal)
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    def test_pathological_json_is_reported_as_bounded_runtime_state_error(self) -> None:
        store = RuntimeStateStore(self.root)
        store.active_path.write_text('{"value":' + "9" * 5000 + "}\n", encoding="utf-8")
        store.active_path.chmod(0o600)
        with self.assertRaises(RuntimeStateError) as raised:
            store.read()
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

        store.active_path.write_text("[" * 1100 + "0" + "]" * 1100, encoding="utf-8")
        store.active_path.chmod(0o600)
        with self.assertRaises(RuntimeStateError) as nested:
            store.read()
        self.assertEqual("RUNTIME_STATE_UNSAFE", nested.exception.code)

        deeply_nested: object = 0
        for _ in range(1100):
            deeply_nested = [deeply_nested]
        candidate = state_candidate(self.session, self.handoff)
        candidate["unknown_nested_value"] = deeply_nested
        with self.assertRaises(RuntimeStateError) as structural:
            validate_active_state(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", structural.exception.code)

        candidate = state_candidate(self.session, self.handoff)
        candidate["unknown_text"] = "\ud800"
        with self.assertRaises(RuntimeStateError) as unicode_error:
            validate_active_state(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", unicode_error.exception.code)

        candidate = state_candidate(self.session, self.handoff)
        candidate["unknown_number"] = float("nan")
        with self.assertRaises(RuntimeStateError) as number_error:
            validate_active_state(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", number_error.exception.code)

        for unsafe_key in (
            "\ud800",
            "sk-" + "k" * 32,
            "prefix:sk-" + "k" * 32,
            "tunnel_" + "4" * 32,
            "prefix:tunnel_" + "5" * 32,
        ):
            candidate = state_candidate(self.session, self.handoff)
            candidate[unsafe_key] = "value"
            store.active_path.write_text(
                json.dumps(candidate, ensure_ascii=True), encoding="utf-8"
            )
            store.active_path.chmod(0o600)
            with self.assertRaises(RuntimeStateError) as key_error:
                store.read()
            self.assertEqual("RUNTIME_STATE_UNSAFE", key_error.exception.code)

        candidate = state_candidate(self.session, self.handoff)
        candidate[7] = "value"
        with self.assertRaises(RuntimeStateError) as non_string_key:
            validate_active_state(candidate)
        self.assertEqual("RUNTIME_STATE_UNSAFE", non_string_key.exception.code)

    def test_clock_rollback_does_not_extend_effective_time(self) -> None:
        wall = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        monotonic = [10.0]
        anchor = Clock(wall=lambda: wall[0], monotonic=lambda: monotonic[0]).anchor()
        wall[0] -= timedelta(hours=1)
        monotonic[0] += 60
        self.assertEqual(datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc), anchor.effective_now())


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.path = self.root / "mcp-audit.jsonl"
        self.session = digest(b"audit-session")
        self.package = "audit-package"
        self.binding = AuditBinding(
            package_id=self.package,
            session_id_sha256=self.session,
            manifest_sha256=digest(b"manifest"),
            approval_event_sha256=digest(b"approval"),
            archive_sha256=digest(b"archive"),
            file_set_sha256=digest(b"files"),
            tool_schema_sha256=tool_schema_sha256(),
            limits_sha256=digest(json.dumps(DEFAULT_LIMITS, sort_keys=True).encode()),
        )
        self.manifest = {
            "schema_version": 3,
            "package_id": self.package,
            "transport": {"requested": "mcp-read", "resolved": "mcp-read"},
            "delivery": {"channel": "browser", "approval_required": True},
            "connector": {
                "type": "secure-mcp-tunnel",
                "protocol_profile": PROTOCOL_PROFILE,
                "tool_schema_sha256": tool_schema_sha256(),
            },
            "mcp_disclosure": {"limits": dict(DEFAULT_LIMITS)},
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def grant(self, *, expires: timedelta = timedelta(hours=1)) -> AuthorizationGrant:
        now = datetime.now(timezone.utc)
        return AuthorizationGrant(
            package_id=self.package,
            manifest=self.manifest,
            archive_path=self.root / "context.zip",
            archive_sha256=self.binding.archive_sha256,
            manifest_sha256=self.binding.manifest_sha256,
            session_id_sha256=self.session,
            session_nonce=b"n" * 32,
            expires_at=now + expires,
            idle_expires_at=now + min(expires, timedelta(minutes=30)),
        )

    @staticmethod
    def read_metadata() -> dict:
        return {
            "result_sha256": digest(b"result"),
            "path": "README.md",
            "file_sha256": digest(b"file"),
            "requested": {"start_line": 1, "end_line": None},
            "returned": {"start_line": 1, "end_line": 2},
            "fragment_sha256": digest(b"fragment"),
            "content_bytes": 12,
        }

    def commit(self, log: AuditLog, *, calls: int = 1, disclosed: int = 21) -> None:
        log.commit_before_return(
            grant=self.grant(),
            tool="gptpro_repo_read",
            request_id_sha256=digest(b"request"),
            arguments_sha256=digest(b"arguments"),
            audit_metadata=self.read_metadata(),
            calls_used=calls,
            disclosed_bytes=disclosed,
        )

    def downgrade_header_to_legacy(self) -> None:
        record = json.loads(self.path.read_text(encoding="utf-8"))
        record["audit_schema_version"] = LEGACY_AUDIT_SCHEMA_VERSION
        record.pop("accounting_mode")
        record.pop("event_sha256")
        canonical = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        record["event_sha256"] = digest(canonical)
        self.path.write_text(
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.path.chmod(0o600)

    def test_current_accounting_is_bound_and_legacy_is_verification_only(self) -> None:
        log = AuditLog(self.path, self.binding)
        log.create_header()
        current = log.verify()
        self.assertEqual(AUDIT_SCHEMA_VERSION, current.schema_version)
        self.assertEqual(ACCOUNTING_MODE, current.accounting_mode)

        self.downgrade_header_to_legacy()
        legacy = log.verify()
        self.assertEqual(LEGACY_AUDIT_SCHEMA_VERSION, legacy.schema_version)
        self.assertEqual(LEGACY_ACCOUNTING_MODE, legacy.accounting_mode)
        with self.assertRaises(ToolError) as raised:
            self.commit(log)
        self.assertEqual("AUDIT_SCHEMA_UNSUPPORTED", raised.exception.code)

        final = log.append_footer("user_requested")
        self.assertTrue(final.footer)
        self.assertEqual(LEGACY_ACCOUNTING_MODE, final.accounting_mode)
        self.assertEqual(LEGACY_ACCOUNTING_MODE, log.verify().accounting_mode)

    def test_audit_schema_version_requires_an_exact_json_integer(self) -> None:
        for index, invalid in enumerate((True, False, 1.0, 2.0, "2")):
            with self.subTest(value=invalid):
                path = self.root / f"invalid-schema-version-{index}.jsonl"
                log = AuditLog(path, self.binding)
                log.create_header()
                record = json.loads(path.read_text(encoding="utf-8"))
                record["audit_schema_version"] = invalid
                if invalid in {True, 1.0}:
                    record.pop("accounting_mode", None)
                record.pop("event_sha256")
                record["event_sha256"] = digest(
                    json.dumps(
                        record,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                )
                path.write_text(
                    json.dumps(
                        record,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                path.chmod(0o600)
                with self.assertRaises(ToolError) as raised:
                    log.verify()
                self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)

    def test_header_tool_rejection_footer_chain_and_no_bodies_or_raw_query(self) -> None:
        log = AuditLog(self.path, self.binding)
        header = log.create_header()
        self.assertRegex(header, r"^[0-9a-f]{64}$")
        self.commit(log)
        rejected = log.append_rejection(
            tool="gptpro_repo_search",
            request_id_sha256=digest(b"request-2"),
            arguments_sha256=digest(b"args-2"),
            error_code="CANCELLED",
            calls_used=2,
        )
        self.assertEqual(2, rejected.tool_calls)
        self.assertEqual(21, rejected.disclosed_bytes)
        final = log.append_footer("user_requested")
        self.assertTrue(final.footer)
        self.assertEqual(3, final.final_sequence)
        payload = self.path.read_text(encoding="utf-8")
        for forbidden in ("repository body", "raw search query", "sk-", "tunnel_"):
            self.assertNotIn(forbidden, payload)
        records = tuple(json.loads(line) for line in payload.splitlines())
        committed = next(
            record
            for record in records
            if record.get("record_type") == "tool_call"
            and record.get("result") == "committed_for_return"
        )
        self.assertEqual(digest(b"request"), committed["jsonrpc_request_id_sha256"])
        self.assertEqual(digest(b"arguments"), committed["arguments_sha256"])
        with self.assertRaises(ToolError) as raised:
            self.commit(log, calls=3, disclosed=42)
        self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)

    def test_unadvertised_rejection_is_hash_bound_and_chain_continues(self) -> None:
        log = AuditLog(self.path, self.binding)
        log.create_header()
        unknown_tool = "gptpro_analysis_post"
        rejected = log.append_rejection(
            tool=unknown_tool,
            request_id_sha256=digest(b"request-unknown"),
            arguments_sha256=digest(b"arguments-unknown"),
            error_code="MCP_INVALID_ARGUMENT",
            calls_used=1,
        )
        self.assertEqual(1, rejected.tool_calls)
        self.assertEqual(0, rejected.disclosed_bytes)
        self.commit(log, calls=2, disclosed=21)
        verified = log.verify()
        self.assertEqual(2, verified.tool_calls)
        self.assertEqual(21, verified.disclosed_bytes)

        payload = self.path.read_text(encoding="utf-8")
        self.assertNotIn(unknown_tool, payload)
        records = [json.loads(line) for line in payload.splitlines()]
        self.assertEqual("<unadvertised>", records[1]["tool"])
        self.assertEqual(
            digest(unknown_tool.encode("utf-8")),
            records[1]["requested_tool_sha256"],
        )
        self.assertEqual("committed_for_return", records[2]["result"])
        diagnostic_records = log.diagnostic_tool_records()
        self.assertEqual(
            records[1]["requested_tool_sha256"],
            diagnostic_records[0]["requested_tool_sha256"],
        )
        self.assertNotIn("requested_tool_sha256", diagnostic_records[1])

        invalid_path = self.root / "invalid-unadvertised.jsonl"
        invalid = AuditLog(invalid_path, self.binding)
        invalid.create_header()
        with self.assertRaises(ToolError) as bad_code:
            invalid.append_rejection(
                tool=unknown_tool,
                request_id_sha256=digest(b"request-invalid"),
                arguments_sha256=digest(b"arguments-invalid"),
                error_code="CANCELLED",
                calls_used=1,
            )
        self.assertEqual("AUDIT_WRITE_FAILED", bad_code.exception.code)
        self.assertEqual(0, invalid.verify().tool_calls)

    def test_audit_tamper_truncate_hardlink_symlink_and_mode_are_rejected(self) -> None:
        log = AuditLog(self.path, self.binding)
        log.create_header()
        self.commit(log)
        payload = self.path.read_bytes()

        self.path.write_bytes(payload[:-1])
        self.path.chmod(0o600)
        with self.assertRaises(ToolError):
            log.verify()
        self.path.write_bytes(payload)
        self.path.chmod(0o600)

        hardlink = self.root / "audit-hardlink"
        os.link(self.path, hardlink)
        with self.assertRaises(ToolError):
            log.verify()
        hardlink.unlink()

        self.path.chmod(0o644)
        with self.assertRaises(ToolError):
            log.verify()
        self.path.chmod(0o600)

        target = self.root / "audit-target"
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(ToolError):
            log.verify()

    def test_pathological_json_is_reported_as_audit_chain_error(self) -> None:
        self.path.write_text('{"value":' + "9" * 5000 + "}\n", encoding="utf-8")
        self.path.chmod(0o600)
        with self.assertRaises(ToolError) as raised:
            AuditLog(self.path, self.binding).verify()
        self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)

        log = AuditLog(self.path, self.binding)
        self.path.unlink()
        log.create_header()
        payload = self.path.read_text(encoding="utf-8")
        self.path.write_text(
            payload.replace("{", '{"unknown_text":"\\ud800",', 1),
            encoding="utf-8",
        )
        self.path.chmod(0o600)
        with self.assertRaises(ToolError) as surrogate:
            log.verify()
        self.assertEqual("AUDIT_CHAIN_INVALID", surrogate.exception.code)

    def test_fsync_failure_blocks_return_and_secret_like_metadata_is_rejected(self) -> None:
        AuditLog(self.path, self.binding).create_header()

        def fail_fsync(descriptor: int) -> None:
            del descriptor
            raise OSError("injected fsync failure")

        failing = AuditLog(self.path, self.binding, file_fsync=fail_fsync)
        with self.assertRaises(ToolError) as raised:
            self.commit(failing)
        self.assertEqual("COMMIT_OUTCOME_UNCERTAIN", raised.exception.code)
        self.assertEqual(1, raised.exception.committed_calls_used)
        uncertain = AuditLog(self.path, self.binding).verify()
        self.assertEqual(1, uncertain.tool_calls)
        self.assertTrue(uncertain.footer)
        self.assertEqual("commit_outcome_uncertain", uncertain.close_reason)

        directory_failure_path = self.root / "directory-failure.jsonl"
        directory_failure = AuditLog(
            directory_failure_path,
            self.binding,
            directory_fsync=fail_fsync,
        )
        with self.assertRaises(ToolError) as directory_error:
            directory_failure.create_header()
        self.assertEqual("AUDIT_WRITE_FAILED", directory_error.exception.code)

        clean_path = self.root / "clean.jsonl"
        clean = AuditLog(clean_path, self.binding)
        clean.create_header()
        metadata = self.read_metadata()
        metadata["path"] = "tunnel_" + "6" * 32
        with self.assertRaises(ToolError) as secret:
            clean.commit_before_return(
                grant=self.grant(),
                tool="gptpro_repo_read",
                request_id_sha256=digest(b"request"),
                arguments_sha256=digest(b"arguments"),
                audit_metadata=metadata,
                calls_used=1,
                disclosed_bytes=1,
            )
        self.assertEqual("AUDIT_WRITE_FAILED", secret.exception.code)

    def test_recomputed_invalid_hash_and_backward_time_remain_chain_errors(self) -> None:
        def rewrite_record(path: Path, key: str, value: object) -> None:
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            records[1][key] = value
            payload = {name: item for name, item in records[1].items() if name != "event_sha256"}
            records[1]["event_sha256"] = digest(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            path.write_text(
                "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in records),
                encoding="utf-8",
            )
            path.chmod(0o600)

        invalid_hash_path = self.root / "invalid-hash.jsonl"
        invalid_hash = AuditLog(invalid_hash_path, self.binding)
        invalid_hash.create_header()
        self.commit(invalid_hash)
        rewrite_record(invalid_hash_path, "arguments_sha256", "not-a-hash")
        with self.assertRaises(ToolError) as bad_hash:
            invalid_hash.verify()
        self.assertEqual("AUDIT_CHAIN_INVALID", bad_hash.exception.code)

        backward_path = self.root / "backward.jsonl"
        backward = AuditLog(backward_path, self.binding)
        backward.create_header()
        self.commit(backward)
        rewrite_record(backward_path, "timestamp", "1970-01-01T00:00:00Z")
        with self.assertRaises(ToolError) as backward_time:
            backward.verify()
        self.assertEqual("AUDIT_CHAIN_INVALID", backward_time.exception.code)

    def test_active_binding_and_expiry_are_revalidated_before_commit(self) -> None:
        runtime_root = self.root / "runtime"
        store = RuntimeStateStore(runtime_root)
        candidate = state_candidate(self.session, self.root, package_id=self.package)
        candidate["manifest_sha256"] = self.binding.manifest_sha256
        candidate["archive_sha256"] = self.binding.archive_sha256
        store.begin_activation(candidate)
        store.transition(self.session, "activating", "active")
        log = AuditLog(self.path, self.binding, runtime_store=store)
        log.create_header()
        self.commit(log)
        store.transition(self.session, "active", "revoking")
        with self.assertRaises(ToolError) as raised:
            self.commit(log, calls=2, disclosed=42)
        self.assertEqual("NO_ACTIVE_PACKAGE", raised.exception.code)

        expired_path = self.root / "expired.jsonl"
        expired = AuditLog(expired_path, self.binding)
        expired.create_header()
        with self.assertRaises(ToolError) as expiry:
            expired.commit_before_return(
                grant=self.grant(expires=timedelta(seconds=-1)),
                tool="gptpro_repo_read",
                request_id_sha256=digest(b"request"),
                arguments_sha256=digest(b"arguments"),
                audit_metadata=self.read_metadata(),
                calls_used=1,
                disclosed_bytes=1,
            )
        self.assertEqual("SESSION_EXPIRED", expiry.exception.code)

    def test_postappend_runtime_state_failure_faults_and_closes_exact_audit(self) -> None:
        runtime_root = self.root / "postappend-runtime"
        store = RuntimeStateStore(runtime_root)
        candidate = state_candidate(self.session, self.root, package_id=self.package)
        candidate["manifest_sha256"] = self.binding.manifest_sha256
        candidate["archive_sha256"] = self.binding.archive_sha256
        store.begin_activation(candidate)
        store.transition(self.session, "activating", "active")
        log = AuditLog(self.path, self.binding, runtime_store=store)
        log.create_header()

        original_write = store._write_unlocked
        failed = False

        def write_then_report_failure(state) -> None:
            nonlocal failed
            original_write(state)
            if not failed and state.get("status") == "active":
                failed = True
                raise RuntimeStateError(
                    "RUNTIME_STATE_WRITE_FAILED",
                    "simulated post-append state sync failure",
                )

        with mock.patch.object(store, "_write_unlocked", side_effect=write_then_report_failure):
            with self.assertRaises(ToolError) as raised:
                self.commit(log)

        self.assertEqual("COMMIT_OUTCOME_UNCERTAIN", raised.exception.code)
        self.assertEqual(1, raised.exception.committed_calls_used)
        self.assertEqual(21, raised.exception.committed_disclosed_bytes)
        self.assertEqual("faulted", store.read()["status"])
        summary = log.verify()
        self.assertEqual(1, summary.tool_calls)
        self.assertEqual(21, summary.disclosed_bytes)
        self.assertTrue(summary.footer)
        self.assertEqual("commit_outcome_uncertain", summary.close_reason)


class TunnelClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.log = self.root / "argv.jsonl"
        self.environment_log = self.root / "environment.jsonl"
        self.control_plane_log = self.root / "control-plane.jsonl"
        self.doctor_tunnel = self.root / "doctor-tunnel.txt"
        self.doctor_target = self.root / "doctor-target.txt"
        self.profile_log = self.root / "profile-tunnel.log"
        self.binary = self.root / "tunnel-client"
        self.raw_tunnel = "tunnel_" + "a" * 32
        self.raw_runtime_key = "sk-" + "k" * 32
        self.expected_mcp_command = shlex.join(
            [
                str(Path(sys.executable).resolve()),
                "-I",
                "-S",
                "-B",
                f"-Xpycache_prefix={os.devnull}",
                str((SKILL_ROOT / "scripts" / "gptpro_mcp.py").resolve()),
                "serve",
            ]
        )
        self.doctor_tunnel.write_text(self.raw_tunnel, encoding="utf-8")
        self.doctor_target.write_text(self.expected_mcp_command, encoding="utf-8")
        self.binary.write_text(
            f"""#!{sys.executable}
import base64, json, os, signal, socket, sys, time
args = sys.argv[1:]
with open({str(self.log)!r}, 'a', encoding='utf-8') as handle:
    handle.write(json.dumps(args) + '\\n')
with open({str(self.environment_log)!r}, 'a', encoding='utf-8') as handle:
    handle.write(json.dumps(dict(os.environ), sort_keys=True) + '\\n')
if args == ['--version']:
    print('0.0.12+881c9a8fed7cccbe6607cd419863bbca506b8215 (git sha: 881c9a8fed7cccbe6607cd419863bbca506b8215)')
elif args[:2] == ['help', 'quickstart']:
    print('quickstart'); sys.exit(0)
elif args[:2] == ['init', '--help']:
    print('--profile --profile-dir --tunnel-id --control-plane-api-key-ref --control-plane-base-url --control-plane-url-path --health-listen-addr --mcp-command'); sys.exit(0)
elif args[:2] == ['doctor', '--help']:
    print('--profile --profile-dir --ca-bundle --control-plane.api-key --control-plane.base-url --control-plane.url-path --log.file --log.level --explain --json'); sys.exit(0)
elif args[:2] == ['run', '--help']:
    print('--profile --profile-dir --ca-bundle --control-plane.api-key --control-plane.base-url --control-plane.url-path --health.listen-addr --health.unix-socket --health.url-file --pid.file --log.file --log.level --mcp.max-concurrent-requests --mcp.command'); sys.exit(0)
elif args[:2] == ['health', '--help']:
    print('--url-file --pid-file --pid --require-control-plane-poll --json'); sys.exit(0)
elif args and args[0] == 'init':
    def value(flag): return args[args.index(flag) + 1]
    profile_path = os.path.join(value('--profile-dir'), value('--profile') + '.yaml')
    profile_text = (
        'config_version: 1\\n'
        'control_plane:\\n'
        '  base_url: "https://api.openai.com"\\n'
        '  url_path: "/"\\n'
        '  tunnel_id: ' + json.dumps(value('--tunnel-id')) + '\\n'
        '  api_key: "env:CONTROL_PLANE_API_KEY"\\n'
        'health:\\n'
        '  listen_addr: "127.0.0.1:0"\\n'
        'admin_ui:\\n'
        '  open_browser: false\\n'
        'log:\\n'
        '  level: info\\n'
        '  format: json\\n'
        'mcp:\\n'
        '  commands:\\n'
        '    - channel: main\\n'
        '      command: ' + json.dumps(value('--mcp-command')) + '\\n'
    )
    descriptor = os.open(profile_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle: handle.write(profile_text)
    print('official init output for ' + value('--tunnel-id'))
    print('official init key ' + os.environ.get('CONTROL_PLANE_API_KEY', ''), file=sys.stderr)
    sys.exit(0)
elif args and args[0] == 'doctor':
    def value(flag): return args[args.index(flag) + 1]
    with open({str(self.control_plane_log)!r}, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({{'base_url': value('--control-plane.base-url'), 'url_path': value('--control-plane.url-path')}}) + '\\n')
    with open({str(self.doctor_tunnel)!r}, encoding='utf-8') as handle: tunnel_id = handle.read()
    with open({str(self.doctor_target)!r}, encoding='utf-8') as handle: mcp_target = handle.read()
    print(json.dumps({{'result': 'ok', 'checks': [
        {{'id': 'tunnel_id', 'status': 'PASS', 'summary': tunnel_id}},
        {{'id': 'mcp_target', 'status': 'PASS', 'summary': mcp_target}}
    ]}})); sys.exit(0)
elif args and args[0] == 'health':
    def value(flag): return args[args.index(flag) + 1]
    if '--pid-file' in args or not value('--pid').isdigit(): sys.exit(3)
    print(json.dumps({{'ok': True}})); sys.exit(0)
elif args and args[0] == 'run':
    def value(flag): return args[args.index(flag) + 1]
    with open({str(self.control_plane_log)!r}, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({{'base_url': value('--control-plane.base-url'), 'url_path': value('--control-plane.url-path')}}) + '\\n')
    with open({str(self.doctor_tunnel)!r}, encoding='utf-8') as handle: tunnel_id = handle.read()
    log_destination = value('--log.file') or {str(self.profile_log)!r}
    with open(log_destination, 'a', encoding='utf-8') as handle: handle.write('warning for ' + tunnel_id + '\\n')
    print('warning for ' + tunnel_id, file=sys.stderr, flush=True)
    socket_path = value('--health.unix-socket')
    health_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    health_socket.bind(socket_path)
    health_socket.listen(1)
    encoded_path = base64.urlsafe_b64encode(socket_path.encode('utf-8')).rstrip(b'=').decode('ascii')
    with open(value('--health.url-file'), 'w', encoding='utf-8') as handle: handle.write('http+unix://' + encoded_path)
    with open(value('--pid.file'), 'w', encoding='utf-8') as handle: handle.write(str(os.getpid()))
    while True: time.sleep(1)
else:
    sys.exit(2)
""",
            encoding="utf-8",
        )
        self.binary.chmod(0o700)
        self.env = os.environ.copy()
        self.env.update(
            {
                "FAKE_TUNNEL_ID": self.raw_tunnel,
                "FAKE_RUNTIME_KEY": self.raw_runtime_key,
                "LC_CTYPE": "C.UTF-8",
                "LC_GITHUB_TOKEN": "ghp_" + "g" * 32,
                "CONTROL_PLANE_BASE_URL": "https://attacker.invalid/collect?secret=yes",
                "CONTROL_PLANE_URL_PATH": "/collect",
                "UNRELATED_SECRET": "sk-" + "u" * 32,
                "UNRELATED_SECRET_SHAPED_VALUE": "github_pat_" + "v" * 32,
                "SSL_CERT_FILE": "/tmp/attacker-ca.pem",
                "SSL_CERT_DIR": "/tmp/attacker-ca-directory",
                "PYTHONPATH": "/tmp/attacker-python-path",
                "PYTHONHOME": "/tmp/attacker-python-home",
                "PYTHONPYCACHEPREFIX": "/tmp/attacker-pycache",
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_profile(
        self,
        name: str,
        *,
        directory: Path | None = None,
        suffix: str = "",
    ) -> Path:
        profile_dir = directory or self.root / "profiles"
        profile_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        profile_dir.chmod(0o700)
        path = profile_dir / f"{name}.yaml"
        path.write_text(
            "config_version: 1\n"
            "control_plane:\n"
            '  base_url: "https://api.openai.com"\n'
            '  url_path: "/"\n'
            f"  tunnel_id: {json.dumps(self.raw_tunnel)}\n"
            '  api_key: "env:CONTROL_PLANE_API_KEY"\n'
            "health:\n"
            '  listen_addr: "127.0.0.1:0"\n'
            "admin_ui:\n"
            "  open_browser: false\n"
            "log:\n"
            "  level: info\n"
            "  format: json\n"
            "mcp:\n"
            "  commands:\n"
            "    - channel: main\n"
            f"      command: {json.dumps(self.expected_mcp_command)}\n"
            + suffix,
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def drift_profile_interpreter(self, path: Path, value: str = "/missing/python3") -> str:
        arguments = shlex.split(self.expected_mcp_command)
        arguments[0] = value
        drifted = shlex.join(arguments)
        document = path.read_text(encoding="utf-8").replace(
            json.dumps(self.expected_mcp_command),
            json.dumps(drifted),
        )
        path.write_text(document, encoding="utf-8")
        path.chmod(0o600)
        return drifted

    def test_capability_doctor_binding_health_and_run_argv_are_exact(self) -> None:
        client = TunnelClient(self.binary)
        with mock.patch.dict(os.environ, self.env, clear=True):
            capabilities = client.probe()
        self.assertTrue(capabilities.supported)
        self.assertTrue(capabilities.run_mcp_command_override)
        self.assertTrue(capabilities.health_require_control_plane_poll)
        self.assertTrue(capabilities.health_unix_socket)
        self.assertTrue(capabilities.health_exact_pid)
        package = "package-one"
        profile_dir = self.root / "profiles"
        initialized = client.init_profile_attended(
            "gptpro-web",
            env=self.env,
            tunnel_id_reference="env:FAKE_TUNNEL_ID",
            control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        self.assertTrue(initialized.ok)
        self.assertNotIn(self.raw_tunnel, repr(initialized))
        self.assertNotIn(self.raw_runtime_key, repr(initialized))
        binding = tunnel_binding_from_reference(
            package,
            "env:FAKE_TUNNEL_ID",
            environ=self.env,
        )
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY",
            environ=self.env,
            base_environment=self.env,
        )
        doctor = client.doctor(
            "gptpro-web",
            env=runtime_env,
            profile_dir=profile_dir,
            package_id=package,
            expected_tunnel_binding_sha256=binding,
            expected_mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
        )
        self.assertTrue(doctor.ok)
        self.assertTrue(doctor.tunnel_binding_matches)
        self.assertTrue(doctor.mcp_target_matches)
        self.assertEqual(64, len(doctor.mcp_target_sha256 or ""))
        self.assertEqual("automatic-doctor-json", doctor.profile_binding_verification)
        self.assertNotIn(self.raw_tunnel, repr(doctor))

        # Simulate profile drift after the successful doctor preflight. The run-time
        # command override must still pin the bundled stdio server rather than trust it.
        drifted_script = self.root / "drifted_mcp.py"
        drifted_script.write_text("# intentionally different profile target\n", encoding="utf-8")
        drifted_command = shlex.split(self.expected_mcp_command)
        drifted_command[-2] = str(drifted_script)
        self.doctor_target.write_text(
            shlex.join(drifted_command),
            encoding="utf-8",
        )
        files = prepare_runtime_files(self.root / "runtime", session_id_sha256=digest(b"run"))
        process = client.spawn_run(
            "gptpro-web",
            env=runtime_env,
            runtime_files=files,
            extra_env={
                "GPTPRO_MCP_SESSION_CAPABILITY": "A" * 43,
                "GPTPRO_MCP_RUNTIME_DIR": str(files.url_file.parent),
            },
            profile_dir=profile_dir,
            cwd=self.root,
        )
        try:
            self.assertEqual(process.pid, os.getpgid(process.pid))
            self.assertEqual(process.pid, os.getsid(process.pid))
            self.assertNotEqual(os.getpgrp(), os.getpgid(process.pid))
            deadline = time.monotonic() + 5
            while files.url_file.stat().st_size == 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            expected_url = validate_unix_health_base_url(
                loopback_url_from_file(files.url_file, expected_socket=files.socket_file),
                expected_socket=files.socket_file,
            )
            self.assertTrue(expected_url.startswith("http+unix://"))
            socket_metadata = files.socket_file.lstat()
            self.assertTrue(stat.S_ISSOCK(socket_metadata.st_mode))
            self.assertEqual(0, stat.S_IMODE(socket_metadata.st_mode) & 0o077)
            files.pid_file.write_text("1", encoding="utf-8")
            files.pid_file.chmod(0o600)
            mismatch = client.health(files, env=runtime_env, expected_pid=process.pid)
            self.assertFalse(mismatch.ok)
            self.assertEqual("TUNNEL_NOT_READY", mismatch.code)
            files.pid_file.write_text(str(process.pid), encoding="utf-8")
            files.pid_file.chmod(0o600)
            health = client.health(files, env=runtime_env, expected_pid=process.pid)
            self.assertTrue(health.ok)
            self.assertTrue(health.control_plane_poll_confirmed)
        finally:
            process.terminate()
            process.wait(timeout=5)

        diagnostic_files = prepare_runtime_files(
            self.root / "runtime-diagnostic",
            session_id_sha256=digest(b"diagnostic-run"),
        )
        diagnostic_process = client.spawn_run(
            "gptpro-web",
            env=runtime_env,
            runtime_files=diagnostic_files,
            extra_env={
                "GPTPRO_MCP_SESSION_CAPABILITY": "B" * 43,
                "GPTPRO_MCP_RUNTIME_DIR": str(diagnostic_files.url_file.parent),
            },
            profile_dir=profile_dir,
            cwd=self.root,
            request_correlation_diagnostic=True,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                diagnostic_files.url_file.stat().st_size == 0
                and diagnostic_process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            self.assertGreater(diagnostic_files.url_file.stat().st_size, 0)
        finally:
            diagnostic_process.terminate()
            diagnostic_process.wait(timeout=5)

        drifted = client.doctor(
            "gptpro-web",
            env=runtime_env,
            profile_dir=profile_dir,
            package_id=package,
            expected_tunnel_binding_sha256=binding,
            expected_mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
        )
        self.assertFalse(drifted.ok)
        self.assertEqual("TUNNEL_NOT_ASSOCIATED", drifted.code)
        self.assertNotEqual("automatic-doctor-json", drifted.profile_binding_verification)

        invocations = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        flat = json.dumps(invocations)
        self.assertNotIn("runtimes", flat)
        self.assertNotIn("pkill", flat)
        self.assertNotIn(self.raw_runtime_key, flat)
        init_argv = next(args for args in invocations if args and args[0] == "init" and "--help" not in args)
        self.assertNotIn("--force", init_argv)
        self.assertEqual(
            "env:CONTROL_PLANE_API_KEY",
            init_argv[init_argv.index("--control-plane-api-key-ref") + 1],
        )
        self.assertEqual(
            "https://api.openai.com",
            init_argv[init_argv.index("--control-plane-base-url") + 1],
        )
        self.assertEqual("/", init_argv[init_argv.index("--control-plane-url-path") + 1])
        self.assertEqual("127.0.0.1:0", init_argv[init_argv.index("--health-listen-addr") + 1])
        mcp_command = init_argv[init_argv.index("--mcp-command") + 1]
        self.assertIn("gptpro_mcp.py", mcp_command)
        self.assertTrue(mcp_command.endswith(" serve"))
        self.assertIn(" -I -S -B -Xpycache_prefix=/dev/null ", mcp_command)
        self.assertNotIn("|", mcp_command)
        health_argv = next(args for args in invocations if args and args[0] == "health" and "--help" not in args)
        self.assertNotIn("--profile", health_argv)
        self.assertNotIn("--pid-file", health_argv)
        self.assertIn("--require-control-plane-poll", health_argv)
        self.assertEqual(str(process.pid), health_argv[health_argv.index("--pid") + 1])
        doctor_argv = next(args for args in invocations if args and args[0] == "doctor" and "--help" not in args)
        self.assertEqual(str(profile_dir), doctor_argv[doctor_argv.index("--profile-dir") + 1])
        self.assertEqual(
            "https://api.openai.com",
            doctor_argv[doctor_argv.index("--control-plane.base-url") + 1],
        )
        self.assertEqual(
            "env:CONTROL_PLANE_API_KEY",
            doctor_argv[doctor_argv.index("--control-plane.api-key") + 1],
        )
        self.assertEqual("/", doctor_argv[doctor_argv.index("--control-plane.url-path") + 1])
        self.assertEqual("", doctor_argv[doctor_argv.index("--ca-bundle") + 1])
        self.assertEqual(os.devnull, doctor_argv[doctor_argv.index("--log.file") + 1])
        run_invocations = [
            args for args in invocations if args and args[0] == "run" and "--help" not in args
        ]
        self.assertEqual(2, len(run_invocations))
        run_argv, diagnostic_run_argv = run_invocations
        for required in (
            "--health.unix-socket",
            str(files.socket_file),
            "--control-plane.base-url",
            "https://api.openai.com",
            "--control-plane.api-key",
            "env:CONTROL_PLANE_API_KEY",
            "--control-plane.url-path",
            "--health.url-file",
            "--pid.file",
            "--log.file",
            "--log.level",
            "warn",
            "--mcp.max-concurrent-requests",
            "1",
            "--mcp.command",
        ):
            self.assertIn(required, run_argv)
        self.assertNotIn("--health.listen-addr", run_argv)
        self.assertEqual(
            f"channel=main,command={self.expected_mcp_command}",
            run_argv[run_argv.index("--mcp.command") + 1],
        )
        self.assertEqual("/", run_argv[run_argv.index("--control-plane.url-path") + 1])
        self.assertEqual("", run_argv[run_argv.index("--ca-bundle") + 1])
        self.assertEqual(os.devnull, run_argv[run_argv.index("--log.file") + 1])
        self.assertEqual(
            "info",
            diagnostic_run_argv[diagnostic_run_argv.index("--log.level") + 1],
        )
        self.assertEqual(
            os.devnull,
            diagnostic_run_argv[diagnostic_run_argv.index("--log.file") + 1],
        )
        self.assertFalse(self.profile_log.exists())
        self.assertFalse(any(files.url_file.parent.glob("*.log")))
        self.assertFalse(any(diagnostic_files.url_file.parent.glob("*.log")))
        for runtime_path in files.url_file.parent.iterdir():
            if runtime_path.is_file():
                self.assertNotIn(self.raw_tunnel.encode("utf-8"), runtime_path.read_bytes())

        environments = [
            json.loads(line)
            for line in self.environment_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(invocations), len(environments))
        forbidden = {
            "FAKE_TUNNEL_ID",
            "FAKE_RUNTIME_KEY",
            "LC_GITHUB_TOKEN",
            "CONTROL_PLANE_BASE_URL",
            "CONTROL_PLANE_URL_PATH",
            "UNRELATED_SECRET",
            "UNRELATED_SECRET_SHAPED_VALUE",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTHONPYCACHEPREFIX",
            "PATH",
        }
        for arguments, environment in zip(invocations, environments, strict=True):
            self.assertTrue(forbidden.isdisjoint(environment))
            is_actual_doctor = arguments and arguments[0] == "doctor" and "--help" not in arguments
            is_actual_init = arguments and arguments[0] == "init" and "--help" not in arguments
            is_actual_run = arguments and arguments[0] == "run" and "--help" not in arguments
            if not is_actual_doctor and not is_actual_init and not is_actual_run:
                self.assertNotIn("CONTROL_PLANE_API_KEY", environment)
            if not is_actual_run:
                self.assertNotIn("GPTPRO_MCP_SESSION_CAPABILITY", environment)
                self.assertNotIn("GPTPRO_MCP_RUNTIME_DIR", environment)
        doctor_environment = environments[invocations.index(doctor_argv)]
        self.assertEqual(self.raw_runtime_key, doctor_environment["CONTROL_PLANE_API_KEY"])
        init_environment = environments[invocations.index(init_argv)]
        self.assertEqual(self.raw_runtime_key, init_environment["CONTROL_PLANE_API_KEY"])
        run_environment = environments[invocations.index(run_argv)]
        self.assertEqual(self.raw_runtime_key, run_environment["CONTROL_PLANE_API_KEY"])
        self.assertEqual("A" * 43, run_environment["GPTPRO_MCP_SESSION_CAPABILITY"])
        self.assertEqual(str(files.url_file.parent), run_environment["GPTPRO_MCP_RUNTIME_DIR"])
        control_plane_choices = [
            json.loads(line)
            for line in self.control_plane_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertGreaterEqual(len(control_plane_choices), 2)
        self.assertTrue(
            all(
                choice == {"base_url": "https://api.openai.com", "url_path": "/"}
                for choice in control_plane_choices
            )
        )

    def test_profile_init_cli_emits_one_sanitized_json_document(self) -> None:
        profile_dir = self.root / "cli-profile"
        binary_sha256 = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SKILL_ROOT / "scripts" / "gptpro.py"),
                "--base-entrypoint",
                str((SKILL_ROOT.parent / "gptpro" / "scripts" / "gptpro.py").resolve()),
                "mcp-profile-init",
                "--tunnel-profile",
                "json-output",
                "--tunnel-id-ref",
                "env:FAKE_TUNNEL_ID",
                "--runtime-api-key-ref",
                "env:FAKE_RUNTIME_KEY",
                "--tunnel-client",
                str(self.binary),
                "--confirm-tunnel-client-sha256",
                binary_sha256,
                "--profile-dir",
                str(profile_dir),
                "--json",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual("mcp-profile-init", payload["operation"])
        self.assertEqual("", result.stderr)
        self.assertNotIn(self.raw_tunnel, result.stdout + result.stderr)
        self.assertNotIn(self.raw_runtime_key, result.stdout + result.stderr)

    def test_profile_check_classifies_only_interpreter_path_drift(self) -> None:
        profile_dir = self.root / "check-profile"
        path = self.write_profile("check", directory=profile_dir)
        current = inspect_tunnel_profile(
            "check",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        self.assertTrue(current.ready)
        self.assertFalse(current.refresh_required)
        self.assertFalse(current.reinit_required)

        drifted = self.drift_profile_interpreter(path)
        inspection = inspect_tunnel_profile(
            "check",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        self.assertFalse(inspection.ready)
        self.assertEqual("MCP_INTERPRETER_PATH_DRIFT", inspection.code)
        self.assertTrue(inspection.refresh_required)
        self.assertTrue(inspection.safe_to_refresh)
        self.assertFalse(inspection.reinit_required)
        self.assertNotIn(drifted, repr(inspection))
        self.assertNotIn(self.raw_tunnel, repr(inspection))

        unsafe_arguments = shlex.split(drifted)
        unsafe_arguments[1] = "-E"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                json.dumps(drifted), json.dumps(shlex.join(unsafe_arguments))
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)
        with self.assertRaises(TunnelClientError) as raised:
            inspect_tunnel_profile(
                "check",
                env=self.env,
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_UNSAFE", raised.exception.code)

    def test_profile_binding_is_secretless_package_specific_and_detects_late_change(self) -> None:
        profile_dir = self.root / "binding-profiles"
        profile = self.write_profile("binding-profile", directory=profile_dir)
        inspection = inspect_tunnel_profile(
            "binding-profile",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        package = "binding-package"
        bound = tunnel_binding_from_profile(
            package,
            "binding-profile",
            expected_profile_sha256=inspection.profile_sha256,
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        self.assertEqual(inspection.profile_sha256, bound.profile_sha256)
        self.assertEqual(
            tunnel_binding_from_reference(
                package,
                "env:FAKE_TUNNEL_ID",
                environ=self.env,
            ),
            bound.tunnel_id_binding_sha256,
        )
        self.assertNotIn(self.raw_tunnel, repr(bound))

        original_snapshot = tunnel_client_module._profile_security_snapshot

        def mutate_before_final_snapshot(*args, **kwargs):
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    self.raw_tunnel,
                    "tunnel_" + "b" * 32,
                ),
                encoding="utf-8",
            )
            profile.chmod(0o600)
            return original_snapshot(*args, **kwargs)

        with (
            mock.patch.object(
                tunnel_client_module,
                "_profile_security_snapshot",
                side_effect=mutate_before_final_snapshot,
            ),
            self.assertRaises(TunnelClientError) as changed,
        ):
            tunnel_binding_from_profile(
                package,
                "binding-profile",
                expected_profile_sha256=inspection.profile_sha256,
                env=self.env,
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_CHANGED", changed.exception.code)

    def test_profile_check_distinguishes_missing_profile_and_skill_root(self) -> None:
        missing_dir = self.root / "missing-profile"
        missing_dir.mkdir(mode=0o700)
        with self.assertRaises(TunnelClientError) as missing:
            inspect_tunnel_profile(
                "not-created",
                env=self.env,
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                profile_dir=missing_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_NOT_FOUND", missing.exception.code)
        self.assertNotIn(str(missing_dir), repr(missing.exception))
        self.assertNotIn(self.raw_tunnel, repr(missing.exception))

        profile_dir = self.root / "cross-root-profile"
        self.write_profile("cross-root", directory=profile_dir)
        other_script = self.root / "other-skill" / "scripts" / "gptpro_mcp.py"
        other_script.parent.mkdir(parents=True, mode=0o700)
        other_script.write_text("# alternate installed Skill root\n", encoding="utf-8")
        other_script.chmod(0o600)
        mismatch = inspect_tunnel_profile(
            "cross-root",
            env=self.env,
            mcp_script=other_script,
            profile_dir=profile_dir,
        )
        self.assertFalse(mismatch.ready)
        self.assertEqual("MCP_SKILL_ENTRYPOINT_MISMATCH", mismatch.code)
        self.assertFalse(mismatch.refresh_required)
        self.assertFalse(mismatch.safe_to_refresh)
        self.assertTrue(mismatch.reinit_required)
        self.assertNotIn(str(other_script), repr(mismatch))
        self.assertNotIn(self.raw_tunnel, repr(mismatch))

    def test_profile_controller_lease_is_owner_only_cloexec_and_exclusive(self) -> None:
        runtime_root = self.root / "profile-controller-runtime"
        runtime_root.mkdir(mode=0o700)
        first = ProfileControllerLease(runtime_root).acquire()
        try:
            self.assertEqual(0o600, stat.S_IMODE(first.path.stat().st_mode))
            self.assertIsNotNone(first._descriptor)
            descriptor_flags = fcntl.fcntl(first._descriptor, fcntl.F_GETFD)
            self.assertTrue(descriptor_flags & fcntl.FD_CLOEXEC)
            with self.assertRaises(RuntimeStateError) as conflict:
                ProfileControllerLease(runtime_root).acquire()
            self.assertEqual("PROFILE_OPERATION_CONFLICT", conflict.exception.code)
        finally:
            first.close()
        second = ProfileControllerLease(runtime_root).acquire()
        second.close()

        lock_path = runtime_root / "profile-controller.lock"
        lock_path.chmod(0o644)
        with self.assertRaises(RuntimeStateError) as unsafe:
            ProfileControllerLease(runtime_root).acquire()
        self.assertEqual("RUNTIME_STATE_UNSAFE", unsafe.exception.code)

    def test_profile_refresh_atomically_replaces_interpreter_only_drift(self) -> None:
        profile_dir = self.root / "refresh-profile"
        path = self.write_profile("refresh", directory=profile_dir)
        self.drift_profile_interpreter(path)
        before = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "refresh",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        refreshed = client.refresh_profile_attended(
            "refresh",
            env=self.env,
            tunnel_id_reference="env:FAKE_TUNNEL_ID",
            control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            expected_profile_sha256=inspection.profile_sha256,
            profile_dir=profile_dir,
        )
        self.assertTrue(refreshed.ok)
        self.assertTrue(refreshed.staging_cleanup_complete)
        self.assertNotEqual(before, path.read_bytes())
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertFalse(any(profile_dir.glob(".gptpro-refresh-*")))
        final = inspect_tunnel_profile(
            "refresh",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        self.assertTrue(final.ready)
        self.assertEqual(final.profile_sha256, refreshed.profile_sha256)
        self.assertNotIn(self.raw_tunnel, repr(refreshed))
        self.assertNotIn(self.raw_runtime_key, repr(refreshed))
        invocations = [
            json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()
        ]
        refresh_init = [
            arguments
            for arguments in invocations
            if arguments and arguments[0] == "init" and "refresh" in arguments
        ][-1]
        staged_dir = Path(refresh_init[refresh_init.index("--profile-dir") + 1])
        self.assertNotEqual(profile_dir, staged_dir)
        self.assertEqual(profile_dir, staged_dir.parent)

    def test_profile_refresh_rejects_hash_and_tunnel_drift_without_mutation(self) -> None:
        profile_dir = self.root / "rejected-refresh"
        path = self.write_profile("rejected", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "rejected",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        before_calls = len(self.log.read_text(encoding="utf-8").splitlines())
        with self.assertRaises(TunnelClientError) as changed:
            client.refresh_profile_attended(
                "rejected",
                env={**self.env, "FAKE_RUNTIME_KEY": ""},
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256="0" * 64,
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_CHANGED", changed.exception.code)
        self.assertEqual(before_calls, len(self.log.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(original, path.read_bytes())

        other_tunnel = "tunnel_" + "z" * 32
        with self.assertRaises(TunnelClientError) as mismatch:
            client.refresh_profile_attended(
                "rejected",
                env={**self.env, "OTHER_TUNNEL": other_tunnel},
                tunnel_id_reference="env:OTHER_TUNNEL",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_NOT_ASSOCIATED", mismatch.exception.code)
        self.assertEqual(before_calls, len(self.log.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(original, path.read_bytes())

    def test_profile_refresh_failure_preserves_original_and_removes_stage(self) -> None:
        profile_dir = self.root / "failed-refresh"
        path = self.write_profile("failed", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "failed",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        failed_result = mock.Mock(ok=False)
        with (
            mock.patch.object(client, "init_profile_attended", return_value=failed_result),
            self.assertRaises(TunnelClientError) as raised,
        ):
            client.refresh_profile_attended(
                "failed",
                env=self.env,
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_REFRESH_FAILED", raised.exception.code)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(any(profile_dir.glob(".gptpro-refresh-*")))

    def test_profile_refresh_rejects_staged_tunnel_change_without_mutation(self) -> None:
        profile_dir = self.root / "wrong-staged-tunnel"
        path = self.write_profile("wrong-staged", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "wrong-staged",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)

        def write_wrong_tunnel_profile(*args: object, **kwargs: object) -> mock.Mock:
            del args
            staging = Path(kwargs["profile_dir"])
            staged_path = self.write_profile("wrong-staged", directory=staging)
            staged_path.write_text(
                staged_path.read_text(encoding="utf-8").replace(
                    self.raw_tunnel, "tunnel_" + "z" * 32
                ),
                encoding="utf-8",
            )
            staged_path.chmod(0o600)
            return mock.Mock(ok=True)

        with (
            mock.patch.object(
                client,
                "init_profile_attended",
                side_effect=write_wrong_tunnel_profile,
            ),
            self.assertRaises(TunnelClientError) as raised,
        ):
            client.refresh_profile_attended(
                "wrong-staged",
                env=self.env,
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_NOT_ASSOCIATED", raised.exception.code)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(any(profile_dir.glob(".gptpro-refresh-*")))

    def test_profile_refresh_post_replace_failure_rolls_back_exact_bytes(self) -> None:
        profile_dir = self.root / "post-replace-failure"
        path = self.write_profile("post-replace", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "post-replace",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        calls = 0
        real_inspect = inspect_tunnel_profile

        def fail_final_inspection(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise TunnelClientError(
                    "TUNNEL_PROFILE_REFRESH_FAILED", "injected post-replace failure"
                )
            return real_inspect(*args, **kwargs)

        with (
            mock.patch(
                "runtime.gptpro_mcp.tunnel_client.inspect_tunnel_profile",
                side_effect=fail_final_inspection,
            ),
            self.assertRaises(TunnelClientError) as raised,
        ):
            client.refresh_profile_attended(
                "post-replace",
                env=self.env,
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_REFRESH_FAILED", raised.exception.code)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(any(profile_dir.glob(".gptpro-refresh-*")))

    def test_profile_refresh_reports_cleanup_separately_after_commit(self) -> None:
        profile_dir = self.root / "cleanup-reporting"
        path = self.write_profile("cleanup", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "cleanup",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        with mock.patch(
            "runtime.gptpro_mcp.tunnel_client._cleanup_profile_refresh_stage",
            return_value=False,
        ):
            refreshed = client.refresh_profile_attended(
                "cleanup",
                env=self.env,
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertTrue(refreshed.ok)
        self.assertFalse(refreshed.staging_cleanup_complete)
        self.assertNotEqual(original, path.read_bytes())
        self.assertTrue(any(profile_dir.glob(".gptpro-refresh-*")))

    def test_profile_refresh_failure_reports_retained_private_stage_without_secrets(self) -> None:
        profile_dir = self.root / "failed-cleanup-reporting"
        path = self.write_profile("failed-cleanup", directory=profile_dir)
        self.drift_profile_interpreter(path)
        original = path.read_bytes()
        inspection = inspect_tunnel_profile(
            "failed-cleanup",
            env=self.env,
            mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
            profile_dir=profile_dir,
        )
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)

        def leave_sensitive_stage(*args: object, **kwargs: object) -> mock.Mock:
            del args
            self.write_profile("failed-cleanup", directory=Path(kwargs["profile_dir"]))
            return mock.Mock(ok=False)

        with (
            mock.patch.object(
                client,
                "init_profile_attended",
                side_effect=leave_sensitive_stage,
            ),
            mock.patch(
                "runtime.gptpro_mcp.tunnel_client._cleanup_profile_refresh_stage",
                return_value=False,
            ),
            self.assertRaises(TunnelClientError) as raised,
        ):
            client.refresh_profile_attended(
                "failed-cleanup",
                env=self.env,
                tunnel_id_reference="env:FAKE_TUNNEL_ID",
                control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                expected_profile_sha256=inspection.profile_sha256,
                profile_dir=profile_dir,
            )
        self.assertEqual(
            "TUNNEL_PROFILE_STAGE_CLEANUP_REQUIRED", raised.exception.code
        )
        rendered_error = repr(raised.exception)
        self.assertNotIn(self.raw_tunnel, rendered_error)
        self.assertNotIn(self.raw_runtime_key, rendered_error)
        self.assertNotIn(str(profile_dir), rendered_error)
        self.assertEqual(original, path.read_bytes())
        retained = list(profile_dir.glob(".gptpro-refresh-*"))
        self.assertEqual(1, len(retained))
        self.assertIn(self.raw_tunnel, (retained[0] / "failed-cleanup.yaml").read_text())

    def test_profile_init_timeout_is_bounded_and_fails_closed(self) -> None:
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        client.timeout = 0.01
        with mock.patch(
            "runtime.gptpro_mcp.tunnel_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=[str(self.binary), "init"], timeout=0.01),
        ) as run:
            with self.assertRaises(TunnelClientError) as raised:
                client.init_profile_attended(
                    "timeout-profile",
                    env=self.env,
                    tunnel_id_reference="env:FAKE_TUNNEL_ID",
                    control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
                    mcp_script=SKILL_ROOT / "scripts" / "gptpro_mcp.py",
                    profile_dir=self.root / "timeout-profile",
                )
        self.assertEqual("TUNNEL_PROFILE_INIT_FAILED", raised.exception.code)
        kwargs = run.call_args.kwargs
        self.assertEqual(subprocess.DEVNULL, kwargs["stdin"])
        self.assertEqual(subprocess.DEVNULL, kwargs["stdout"])
        self.assertEqual(subprocess.DEVNULL, kwargs["stderr"])
        self.assertEqual(0.01, kwargs["timeout"])

    def test_bounded_capture_stops_output_flood_and_timed_out_exact_children(self) -> None:
        worker = self.root / "bounded-output-child"
        worker.write_text(
            f"""#!{sys.executable}
import os, signal, sys, time
pid_path, mode = sys.argv[1:3]
with open(pid_path, 'w', encoding='ascii') as handle:
    handle.write(str(os.getpid()))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == 'flood':
    chunk = (b'sk-' + b'S' * 40 + b'\\n') * 128
    while True:
        os.write(1, chunk)
        os.write(2, chunk)
time.sleep(60)
""",
            encoding="utf-8",
        )
        worker.chmod(0o700)
        client = TunnelClient(worker, timeout=2.0)

        for mode, timeout in (("flood", 2.0), ("timeout", 0.05)):
            with self.subTest(mode=mode):
                pid_path = self.root / f"{mode}.pid"
                client.timeout = timeout
                with (
                    mock.patch(
                        "runtime.gptpro_mcp.tunnel_client._MAX_COMMAND_OUTPUT_BYTES", 16 * 1024
                    ),
                    self.assertRaises(TunnelClientError) as raised,
                ):
                    client._run([str(pid_path), mode], env={})
                self.assertEqual("TUNNEL_CLIENT_UNSUPPORTED", raised.exception.code)
                self.assertNotIn("sk-", repr(raised.exception))
                self.assertIsNone(raised.exception.__cause__)
                child_pid = int(pid_path.read_text(encoding="ascii"))
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)

    def test_profile_network_execution_and_logging_expansions_fail_before_child(self) -> None:
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY", environ=self.env, base_environment=self.env
        )
        unsafe_fragments = {
            "custom-ca": 'ca_bundle: "/tmp/attacker-ca.pem"\n',
            "global-proxy": 'http_proxy: "https://proxy.invalid"\n',
            "control-plane-proxy": (
                "control_plane:\n  http_proxy: \"https://proxy.invalid\"\n"
            ),
            "control-plane-headers": (
                "control_plane:\n  extra_headers:\n    X-Test: secret\n"
            ),
            "remote-mcp": (
                "mcp:\n  server_urls:\n    - channel: main\n"
                "      url: \"https://attacker.invalid/mcp\"\n"
            ),
            "extra-command-channel": (
                "mcp:\n  commands:\n    - channel: tools\n      command: /bin/sh\n"
            ),
            "mcp-environment": "mcp:\n  env:\n    PYTHONPATH: /tmp/poison\n",
            "harpoon": "harpoon:\n  targets: []\n",
            "cloudflared": "cloudflared:\n  managed: true\n",
            "raw-http-log": "log:\n  http_raw_unsafe: true\n",
        }
        for index, (label, suffix) in enumerate(unsafe_fragments.items()):
            with self.subTest(label=label):
                name = f"unsafe-{index}"
                profile_dir = self.root / f"profiles-{index}"
                self.write_profile(name, directory=profile_dir, suffix=suffix)
                before = len(self.log.read_text(encoding="utf-8").splitlines())
                with self.assertRaises(TunnelClientError) as raised:
                    client.doctor(name, env=runtime_env, profile_dir=profile_dir)
                self.assertEqual("TUNNEL_PROFILE_UNSAFE", raised.exception.code)
                after = len(self.log.read_text(encoding="utf-8").splitlines())
                self.assertEqual(before, after)

        safe_dir = self.root / "safe-profile"
        safe_path = self.write_profile("safe", directory=safe_dir)
        checked = client.doctor("safe", env=runtime_env, profile_dir=safe_dir)
        self.assertTrue(checked.ok)
        safe_path.write_text(
            safe_path.read_text(encoding="utf-8")
            + 'control_plane:\n  http_proxy: "https://proxy.invalid"\n',
            encoding="utf-8",
        )
        safe_path.chmod(0o600)
        files = prepare_runtime_files(
            self.root / "r", session_id_sha256=digest(b"profile-drift")
        )
        before = len(self.log.read_text(encoding="utf-8").splitlines())
        with self.assertRaises(TunnelClientError) as raised:
            client.spawn_run(
                "safe",
                env=runtime_env,
                runtime_files=files,
                extra_env={
                    "GPTPRO_MCP_SESSION_CAPABILITY": "D" * 43,
                    "GPTPRO_MCP_RUNTIME_DIR": str(files.url_file.parent),
                },
                profile_dir=safe_dir,
            )
        self.assertEqual("TUNNEL_PROFILE_UNSAFE", raised.exception.code)
        after = len(self.log.read_text(encoding="utf-8").splitlines())
        self.assertEqual(before, after)

    def test_profile_directory_symlink_and_permissions_fail_closed(self) -> None:
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY", environ=self.env, base_environment=self.env
        )
        actual = self.root / "actual-profiles"
        self.write_profile("gptpro-web", directory=actual)
        profile_link = self.root / "profile-link"
        profile_link.symlink_to(actual, target_is_directory=True)
        before = len(self.log.read_text(encoding="utf-8").splitlines())
        with self.assertRaises(TunnelClientError) as linked:
            client.doctor("gptpro-web", env=runtime_env, profile_dir=profile_link)
        self.assertEqual("RUNTIME_STATE_UNSAFE", linked.exception.code)
        self.assertEqual(before, len(self.log.read_text(encoding="utf-8").splitlines()))

        actual.chmod(0o755)
        with self.assertRaises(TunnelClientError) as permissive:
            client.doctor("gptpro-web", env=runtime_env, profile_dir=actual)
        self.assertEqual("RUNTIME_STATE_UNSAFE", permissive.exception.code)

        safe_home = self.root / "default-home"
        safe_home.mkdir(mode=0o700)
        redirected = self.root / "redirected-config"
        redirected.mkdir(mode=0o700)
        (safe_home / ".config").symlink_to(redirected, target_is_directory=True)
        default_env = dict(runtime_env)
        default_env.pop("XDG_CONFIG_HOME", None)
        default_env["HOME"] = str(safe_home)
        with self.assertRaises(TunnelClientError) as default_link:
            client.doctor("gptpro-web", env=default_env)
        self.assertIn(
            default_link.exception.code,
            {"RUNTIME_STATE_UNSAFE", "TUNNEL_PROFILE_UNSAFE"},
        )

    def test_profile_directory_under_replaceable_ancestor_fails_before_key_bearing_child(
        self,
    ) -> None:
        client = TunnelClient(self.binary)
        self.assertTrue(client.probe().supported)
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY", environ=self.env, base_environment=self.env
        )
        shared_parent = self.root / "replaceable-profile-parent"
        profile_dir = shared_parent / "profiles"
        self.write_profile("gptpro-web", directory=profile_dir)
        shared_parent.chmod(0o777)
        before = len(self.log.read_text(encoding="utf-8").splitlines())

        with self.assertRaises(TunnelClientError) as raised:
            client.doctor("gptpro-web", env=runtime_env, profile_dir=profile_dir)

        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)
        self.assertEqual(before, len(self.log.read_text(encoding="utf-8").splitlines()))

    @unittest.skipUnless(sys.version_info >= (3, 11), "runtime requires Python 3.11+")
    def test_isolated_exact_command_runs_stdio_and_ignores_timestamp_valid_adjacent_pyc(self) -> None:
        requests = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-11-25"},
                    }
                ),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]
        ) + "\n"
        server = subprocess.run(
            shlex.split(self.expected_mcp_command),
            input=requests,
            text=True,
            capture_output=True,
            timeout=10,
            env={
                "PYTHONPATH": "/tmp/attacker-python-path",
                "PYTHONHOME": "/tmp/attacker-python-home",
                "PYTHONPYCACHEPREFIX": "/tmp/attacker-pycache",
            },
            check=False,
        )
        self.assertEqual(0, server.returncode, server.stderr)
        responses = [json.loads(line) for line in server.stdout.splitlines()]
        listed = next(item for item in responses if item.get("id") == 2)
        self.assertEqual(3, len(listed["result"]["tools"]))

        poison_root = self.root / "poison-runtime"
        poison_root.mkdir(mode=0o700)
        source = poison_root / "helper.py"
        poison_source = poison_root / "poison.py"
        entrypoint = poison_root / "gptpro_mcp.py"
        source.write_text("VALUE='SOURCE'\n", encoding="utf-8")
        poison_source.write_text("VALUE='POISON'\n", encoding="utf-8")
        entrypoint.write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent))\n"
            "import helper\nprint(helper.VALUE)\n",
            encoding="utf-8",
        )
        fixed_time = 1_770_000_000
        os.utime(source, (fixed_time, fixed_time))
        os.utime(poison_source, (fixed_time, fixed_time))
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir(mode=0o700)
        py_compile.compile(
            str(poison_source),
            cfile=str(cache),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        )
        baseline = subprocess.run(
            [sys.executable, str(entrypoint)],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual("POISON", baseline.stdout.strip())
        protected = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                f"-Xpycache_prefix={os.devnull}",
                str(entrypoint),
            ],
            text=True,
            capture_output=True,
            timeout=5,
            env={"PYTHONPYCACHEPREFIX": "/tmp/attacker-pycache"},
            check=False,
        )
        self.assertEqual(0, protected.returncode, protected.stderr)
        self.assertEqual("SOURCE", protected.stdout.strip())

    def test_required_health_capability_is_part_of_supported_contract(self) -> None:
        capabilities = TunnelCapabilities(
            binary_sha256=digest(b"binary"),
            version="tunnel-client v0.0.12",
            quickstart_help=True,
            init_profile=True,
            doctor_profile=True,
            foreground_run=True,
            run_mcp_command_override=True,
            health_require_control_plane_poll=False,
            health_unix_socket=True,
            health_exact_pid=True,
            warn_log_level=True,
        )
        self.assertFalse(capabilities.supported)

        missing_override = TunnelCapabilities(
            binary_sha256=digest(b"binary"),
            version="tunnel-client v0.0.12",
            quickstart_help=True,
            init_profile=True,
            doctor_profile=True,
            foreground_run=True,
            run_mcp_command_override=False,
            health_require_control_plane_poll=True,
            health_unix_socket=True,
            health_exact_pid=True,
            warn_log_level=True,
        )
        self.assertFalse(missing_override.supported)

        missing_unix_socket = TunnelCapabilities(
            binary_sha256=digest(b"binary"),
            version="tunnel-client v0.0.12",
            quickstart_help=True,
            init_profile=True,
            doctor_profile=True,
            foreground_run=True,
            run_mcp_command_override=True,
            health_require_control_plane_poll=True,
            health_unix_socket=False,
            health_exact_pid=True,
            warn_log_level=True,
        )
        self.assertFalse(missing_unix_socket.supported)

        missing_exact_pid = TunnelCapabilities(
            binary_sha256=digest(b"binary"),
            version="tunnel-client v0.0.12",
            quickstart_help=True,
            init_profile=True,
            doctor_profile=True,
            foreground_run=True,
            run_mcp_command_override=True,
            health_require_control_plane_poll=True,
            health_unix_socket=True,
            health_exact_pid=False,
            warn_log_level=True,
        )
        self.assertFalse(missing_exact_pid.supported)

    def test_private_request_correlation_contract_is_exact_version_only(self) -> None:
        exact = TunnelCapabilities(
            binary_sha256=digest(b"binary"),
            version=(
                "0.0.12+881c9a8fed7cccbe6607cd419863bbca506b8215 "
                "(git sha: 881c9a8fed7cccbe6607cd419863bbca506b8215)"
            ),
            quickstart_help=True,
            init_profile=True,
            doctor_profile=True,
            foreground_run=True,
            run_mcp_command_override=True,
            health_require_control_plane_poll=True,
            health_unix_socket=True,
            health_exact_pid=True,
            warn_log_level=True,
        )
        self.assertTrue(exact.supported)
        self.assertTrue(exact.request_correlation_contract_supported)
        self.assertTrue(exact.parent_shutdown_contract_supported)

        unknown = replace(exact, version="v99.0.0")
        self.assertTrue(unknown.supported)
        self.assertFalse(unknown.request_correlation_contract_supported)
        self.assertFalse(unknown.parent_shutdown_contract_supported)

    def test_probe_does_not_treat_pid_file_as_exact_pid_support(self) -> None:
        pid_file_only = self.root / "tunnel-client-pid-file-only"
        pid_file_only.write_text(
            self.binary.read_text(encoding="utf-8").replace(
                "--url-file --pid-file --pid --require-control-plane-poll --json",
                "--url-file --pid-file --require-control-plane-poll --json",
            ),
            encoding="utf-8",
        )
        pid_file_only.chmod(0o700)

        with mock.patch.dict(os.environ, self.env, clear=True):
            capabilities = TunnelClient(pid_file_only).probe()

        self.assertFalse(capabilities.health_exact_pid)
        self.assertFalse(capabilities.supported)

    def test_probe_requires_complete_option_tokens_for_every_capability(self) -> None:
        cases = (
            ("--tunnel-id", "--tunnel-id-legacy", "init_profile"),
            (
                "--profile --profile-dir --tunnel-id",
                "--profile --profile-dir-legacy --tunnel-id",
                "init_profile",
            ),
            ("--explain", "--explain-more", "doctor_profile"),
            (
                "--profile --profile-dir --ca-bundle --control-plane.api-key",
                "--profile --profile-dir-legacy --ca-bundle --control-plane.api-key",
                "doctor_profile",
            ),
            ("--pid.file", "--pid.file-legacy", "foreground_run"),
            (
                "--profile --profile-dir --ca-bundle --control-plane.api-key",
                "--profile --profile-dir-legacy --ca-bundle --control-plane.api-key",
                "foreground_run",
            ),
            ("--mcp.command", "--mcp.command-legacy", "run_mcp_command_override"),
            (
                "--require-control-plane-poll",
                "--require-control-plane-poll-legacy",
                "health_require_control_plane_poll",
            ),
            (
                "--health.unix-socket",
                "--health.unix-socket-legacy",
                "health_unix_socket",
            ),
            (
                "--url-file --pid-file --pid",
                "--url-file-legacy --pid-file --pid",
                "health_exact_pid",
            ),
            (
                "--require-control-plane-poll --json",
                "--require-control-plane-poll --json-legacy",
                "health_exact_pid",
            ),
            ("--log.level", "--log.level-legacy", "warn_log_level"),
        )
        original = self.binary.read_text(encoding="utf-8")
        for index, (option, longer, attribute) in enumerate(cases):
            with self.subTest(option=option):
                incompatible = self.root / f"tunnel-client-prefix-{index}"
                incompatible.write_text(
                    original.replace(option, longer), encoding="utf-8"
                )
                incompatible.chmod(0o700)
                with mock.patch.dict(os.environ, self.env, clear=True):
                    capabilities = TunnelClient(incompatible).probe()
                self.assertFalse(getattr(capabilities, attribute))
                self.assertFalse(capabilities.supported)

    def test_atomic_tunnel_binary_replacement_is_rejected_before_doctor_and_run(self) -> None:
        client = TunnelClient(self.binary)
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertTrue(client.probe().supported)
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY",
            environ=self.env,
            base_environment=self.env,
        )

        replacement = self.root / "replacement-tunnel-client"
        replacement.write_bytes(self.binary.read_bytes())
        replacement.chmod(0o700)
        os.replace(replacement, self.binary)

        with self.assertRaises(TunnelClientError) as doctor_error:
            client.doctor("gptpro-web", env=runtime_env)
        self.assertEqual("TUNNEL_CLIENT_UNSUPPORTED", doctor_error.exception.code)

        files = prepare_runtime_files(
            self.root / "replacement-runtime", session_id_sha256=digest(b"replacement")
        )
        with self.assertRaises(TunnelClientError) as run_error:
            client.spawn_run(
                "gptpro-web",
                env=runtime_env,
                runtime_files=files,
                extra_env={
                    "GPTPRO_MCP_SESSION_CAPABILITY": "B" * 43,
                    "GPTPRO_MCP_RUNTIME_DIR": str(files.url_file.parent),
                },
            )
        self.assertEqual("TUNNEL_CLIENT_UNSUPPORTED", run_error.exception.code)

    def test_mcp_target_binds_interpreter_and_script_bytes_and_inode_until_spawn(self) -> None:
        client = TunnelClient(self.binary)
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertTrue(client.probe().supported)
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY",
            environ=self.env,
            base_environment=self.env,
        )
        interpreter = self.root / "pinned-python"
        interpreter_bytes = Path(sys.executable).resolve().read_bytes()
        interpreter.write_bytes(interpreter_bytes)
        interpreter.chmod(0o700)
        scripts = self.root / "isolated" / "scripts"
        scripts.mkdir(parents=True)
        mcp_script = scripts / "gptpro_mcp.py"
        script_bytes = (SKILL_ROOT / "scripts" / "gptpro_mcp.py").read_bytes()
        mcp_script.write_bytes(script_bytes)
        command = shlex.join(
            [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                f"-Xpycache_prefix={os.devnull}",
                str(mcp_script),
                "serve",
            ]
        )
        self.doctor_target.write_text(command, encoding="utf-8")
        profile_dir = self.root / "identity-profiles"
        initialized = client.init_profile_attended(
            "identity-test",
            env=self.env,
            tunnel_id_reference="env:FAKE_TUNNEL_ID",
            control_plane_api_key_reference="env:FAKE_RUNTIME_KEY",
            mcp_script=mcp_script,
            profile_dir=profile_dir,
            python_executable=interpreter,
        )
        self.assertTrue(initialized.ok)
        package = "identity-package"
        binding = tunnel_binding_from_reference(
            package,
            "env:FAKE_TUNNEL_ID",
            environ=self.env,
        )

        def doctor_target() -> TunnelCheck:
            return client.doctor(
                "identity-test",
                env=runtime_env,
                profile_dir=profile_dir,
                package_id=package,
                expected_tunnel_binding_sha256=binding,
                expected_mcp_script=mcp_script,
                python_executable=interpreter,
            )

        initial = doctor_target()
        self.assertTrue(initial.ok)
        initial_digest = initial.mcp_target_sha256
        self.assertIsNotNone(initial_digest)

        interpreter_inode = interpreter.stat().st_ino
        interpreter.write_bytes(interpreter_bytes + b"\0")
        interpreter.chmod(0o700)
        self.assertEqual(interpreter_inode, interpreter.stat().st_ino)
        self.assertNotEqual(initial_digest, doctor_target().mcp_target_sha256)
        interpreter.write_bytes(interpreter_bytes)
        interpreter.chmod(0o700)
        self.assertEqual(interpreter_inode, interpreter.stat().st_ino)
        self.assertEqual(initial_digest, doctor_target().mcp_target_sha256)

        script_inode = mcp_script.stat().st_ino
        mcp_script.write_bytes(script_bytes + b"\n# identity drift\n")
        self.assertEqual(script_inode, mcp_script.stat().st_ino)
        self.assertNotEqual(initial_digest, doctor_target().mcp_target_sha256)
        mcp_script.write_bytes(script_bytes)
        self.assertEqual(script_inode, mcp_script.stat().st_ino)
        restored = doctor_target()
        self.assertEqual(initial_digest, restored.mcp_target_sha256)

        replacement = self.root / "replacement-python"
        replacement.write_bytes(interpreter_bytes)
        replacement.chmod(0o700)
        replacement_inode = replacement.stat().st_ino
        self.assertNotEqual(interpreter_inode, replacement_inode)
        os.replace(replacement, interpreter)
        self.assertEqual(replacement_inode, interpreter.stat().st_ino)
        files = prepare_runtime_files(
            self.root / "identity-runtime",
            session_id_sha256=digest(b"identity-runtime"),
        )
        with mock.patch(
            "runtime.gptpro_mcp.tunnel_client._bundled_mcp_command",
            return_value=command,
        ):
            with self.assertRaises(TunnelClientError) as raised:
                client.spawn_run(
                    "identity-test",
                    env=runtime_env,
                    runtime_files=files,
                    profile_dir=profile_dir,
                    expected_mcp_target_sha256=initial_digest,
                )
        self.assertEqual("MCP_RUNTIME_IDENTITY_CHANGED", raised.exception.code)

    def test_spawn_rejects_unsafe_or_ambiguous_runtime_paths(self) -> None:
        client = TunnelClient(self.binary)
        client.probe()
        with self.assertRaises(TunnelClientError):
            prepare_runtime_files(Path("relative-runtime"), session_id_sha256=digest(b"relative"))

        files = prepare_runtime_files(self.root / "unsafe-runtime", session_id_sha256=digest(b"unsafe"))
        files.pid_file.chmod(0o644)
        with self.assertRaises(TunnelClientError) as unsafe:
            client.spawn_run("gptpro-web", env=self.env, runtime_files=files)
        self.assertEqual("RUNTIME_STATE_UNSAFE", unsafe.exception.code)

        other = self.root / "other-runtime"
        other.mkdir(mode=0o700)
        other_pid = other / "pid"
        other_pid.touch(mode=0o600)
        split = TunnelRuntimeFiles(files.url_file, other_pid, files.socket_file)
        with self.assertRaises(TunnelClientError):
            client.spawn_run("gptpro-web", env=self.env, runtime_files=split)

        clean_files = prepare_runtime_files(
            self.root / "clean-runtime", session_id_sha256=digest(b"clean")
        )
        runtime_env = runtime_key_environment(
            "env:FAKE_RUNTIME_KEY", environ=self.env, base_environment=self.env
        )
        with self.assertRaises(TunnelClientError) as untrusted_environment:
            client.spawn_run(
                "gptpro-web",
                env=runtime_env,
                runtime_files=clean_files,
                extra_env={
                    "GPTPRO_MCP_SESSION_CAPABILITY": "C" * 43,
                    "GPTPRO_MCP_RUNTIME_DIR": str(clean_files.url_file.parent),
                    "UNRELATED_SECRET": "sk-" + "x" * 32,
                },
            )
        self.assertEqual("RUNTIME_STATE_UNSAFE", untrusted_environment.exception.code)

        with self.assertRaises(TunnelClientError) as invalid_shutdown_contract:
            client.spawn_run(
                "gptpro-web",
                env=runtime_env,
                runtime_files=clean_files,
                extra_env={
                    "GPTPRO_MCP_SESSION_CAPABILITY": "C" * 43,
                    "GPTPRO_MCP_RUNTIME_DIR": str(clean_files.url_file.parent),
                    "GPTPRO_MCP_PARENT_SHUTDOWN_CONTRACT": "true",
                },
            )
        self.assertEqual("RUNTIME_STATE_UNSAFE", invalid_shutdown_contract.exception.code)

    def test_runtime_file_preparation_retires_only_an_owned_stale_health_socket(self) -> None:
        runtime_root = self.root / "s"
        files = prepare_runtime_files(runtime_root, session_id_sha256=digest(b"stale-one"))
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous_umask = os.umask(0o077)
        try:
            stale.bind(str(files.socket_file))
        finally:
            os.umask(previous_umask)
            stale.close()
        self.assertTrue(files.socket_file.exists())
        prepared = prepare_runtime_files(runtime_root, session_id_sha256=digest(b"stale-two"))
        self.assertEqual(files.socket_file, prepared.socket_file)
        self.assertFalse(prepared.socket_file.exists())

        live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous_umask = os.umask(0o077)
        try:
            live.bind(str(prepared.socket_file))
        finally:
            os.umask(previous_umask)
        live.listen(1)
        try:
            with self.assertRaises(TunnelClientError) as conflict:
                prepare_runtime_files(runtime_root, session_id_sha256=digest(b"live"))
            self.assertEqual("SESSION_CONFLICT", conflict.exception.code)
        finally:
            live.close()
            prepared.socket_file.unlink(missing_ok=True)

    def test_loopback_and_secret_file_validation_fail_closed(self) -> None:
        self.assertEqual(
            "https://api.openai.com",
            validate_control_plane_base_url("https://api.openai.com"),
        )
        for rejected_control_plane in (
            "http://api.openai.com",
            "https://api.openai.com/",
            "https://api.openai.com/v1",
            "https://api.openai.com?next=/collect",
            "https://api.openai.com#fragment",
            "https://user:pass@api.openai.com",
            "https://api.openai.com:443",
            "https://api.openai.com.attacker.invalid",
        ):
            with self.subTest(control_plane=rejected_control_plane), self.assertRaises(
                TunnelClientError
            ) as rejected:
                validate_control_plane_base_url(rejected_control_plane)
            self.assertEqual("CONTROL_PLANE_ENDPOINT_REJECTED", rejected.exception.code)

        for accepted in (
            "http://127.0.0.1:9222",
            "https://localhost:9443/",
            "http://[::1]:8080",
        ):
            with self.subTest(accepted=accepted):
                self.assertTrue(validate_loopback_base_url(accepted))
        for rejected in (
            "http://example.com:9222",
            "http://localhost.evil:9222",
            "http://user:pass@localhost:9222",
            "file:///tmp/socket",
            "http://127.0.0.1/path",
            "http://127.0.0.1",
        ):
            with self.subTest(rejected=rejected), self.assertRaises(TunnelClientError):
                validate_loopback_base_url(rejected)

        socket_path = self.root / "health.sock"
        token = base64.urlsafe_b64encode(str(socket_path).encode("utf-8")).rstrip(b"=").decode("ascii")
        unix_url = f"http+unix://{token}"
        self.assertEqual(
            unix_url,
            validate_unix_health_base_url(unix_url, expected_socket=socket_path),
        )
        for rejected_unix in (
            unix_url + "/",
            unix_url + "?query=1",
            "http+unix://" + base64.urlsafe_b64encode(b"/tmp/other.sock").rstrip(b"=").decode("ascii"),
            "http://127.0.0.1:9222",
        ):
            with self.subTest(rejected_unix=rejected_unix), self.assertRaises(TunnelClientError):
                validate_unix_health_base_url(rejected_unix, expected_socket=socket_path)

        key = self.root / "key"
        key.write_text("sk-" + "z" * 32, encoding="utf-8")
        key.chmod(0o600)
        child = runtime_key_environment(
            "file:" + str(key),
            base_environment={
                "PATH": "/usr/bin:/bin",
                "LC_CTYPE": "C.UTF-8",
                "LC_GITHUB_TOKEN": "ghp_" + "g" * 32,
                "UNRELATED_SECRET": "sk-" + "u" * 32,
                "UNRELATED_SECRET_SHAPED_VALUE": "github_pat_" + "v" * 32,
                "SSL_CERT_FILE": "/tmp/attacker-ca.pem",
                "SSL_CERT_DIR": "/tmp/attacker-ca-directory",
                "PYTHONPATH": "/tmp/attacker-python-path",
            },
        )
        self.assertTrue(child["CONTROL_PLANE_API_KEY"].startswith("sk-"))
        self.assertEqual("C.UTF-8", child["LC_CTYPE"])
        self.assertNotIn("PATH", child)
        self.assertNotIn("LC_GITHUB_TOKEN", child)
        self.assertNotIn("UNRELATED_SECRET", child)
        self.assertNotIn("UNRELATED_SECRET_SHAPED_VALUE", child)
        self.assertNotIn("SSL_CERT_FILE", child)
        self.assertNotIn("SSL_CERT_DIR", child)
        self.assertNotIn("PYTHONPATH", child)
        hardlink = self.root / "key-hardlink"
        os.link(key, hardlink)
        with self.assertRaises(TunnelClientError):
            runtime_key_environment("file:" + str(key), base_environment={})
        hardlink.unlink()
        key.chmod(0o644)
        with self.assertRaises(TunnelClientError):
            runtime_key_environment("file:" + str(key), base_environment={})


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "runtime"
        self.root.mkdir(mode=0o700)
        self.session = digest(b"supervisor")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def sleeping_child(
        child_signal_mask: set[signal.Signals] | None = None,
    ) -> subprocess.Popen[bytes]:
        return popen_with_signal_mask(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            child_signal_mask=child_signal_mask,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_remote_stop_revokes_before_terminating_exact_owned_child(self) -> None:
        socket_path = self.root / "control.sock"
        observed: dict[str, object] = {}

        def factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            process = self.sleeping_child(child_signal_mask)
            observed["process"] = process
            return process

        def revoke(reason: str) -> None:
            process = observed["process"]
            assert isinstance(process, subprocess.Popen)
            observed["reason"] = reason
            observed["alive_when_revoked"] = process.poll() is None

        supervisor = ForegroundSupervisor(
            process_factory=factory,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=revoke,
        )
        outcome: dict[str, object] = {}
        thread = threading.Thread(target=lambda: outcome.setdefault("result", supervisor.run()))
        thread.start()
        deadline = time.monotonic() + 5
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        malformed = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        malformed.settimeout(2.0)
        try:
            malformed.connect(str(socket_path))
            malformed.sendall(("[" * 1100 + "0" + "]" * 1100 + "\n").encode("ascii"))
            rejected = json.loads(malformed.recv(1024).decode("utf-8"))
        finally:
            malformed.close()
        self.assertEqual({"accepted": False}, rejected)
        self.assertFalse(request_cooperative_stop(socket_path, digest(b"wrong")))
        fragmented = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        fragmented.settimeout(2.0)
        try:
            fragmented.connect(str(socket_path))
            request = (
                json.dumps(
                    {"command": "stop", "session_id_sha256": self.session},
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            midpoint = len(request) // 2
            fragmented.sendall(request[:midpoint])
            time.sleep(0.02)
            fragmented.sendall(request[midpoint:])
            accepted = json.loads(fragmented.recv(1024).decode("utf-8"))
        finally:
            fragmented.close()
        self.assertEqual({"accepted": True}, accepted)
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertTrue(observed["alive_when_revoked"])
        self.assertEqual("remote_stop", observed["reason"])
        result = outcome["result"]
        self.assertTrue(result.revoked)
        self.assertTrue(result.terminated)
        self.assertFalse(socket_path.exists())

    def test_after_start_failure_still_revokes_then_terminates_owned_child(self) -> None:
        observed: dict[str, object] = {}

        def factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            process = self.sleeping_child(child_signal_mask)
            observed["process"] = process
            return process

        def after_start(process: subprocess.Popen[bytes]) -> None:
            self.assertIs(process, observed["process"])
            raise RuntimeError("readiness failed")

        def revoke(reason: str) -> None:
            process = observed["process"]
            assert isinstance(process, subprocess.Popen)
            observed["revoked_while_alive"] = process.poll() is None
            observed["reason"] = reason

        supervisor = ForegroundSupervisor(
            process_factory=factory,
            after_start=after_start,
            control_socket=self.root / "failure.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=revoke,
        )
        with self.assertRaisesRegex(RuntimeError, "readiness failed"):
            supervisor.run()
        process = observed["process"]
        assert isinstance(process, subprocess.Popen)
        self.assertTrue(observed["revoked_while_alive"])
        self.assertIsNotNone(process.returncode)
        self.assertIsNotNone(supervisor.terminal_result)
        self.assertEqual(process.returncode, supervisor.terminal_result.child_returncode)

    def test_child_inherits_pre_gate_signal_mask_not_supervisor_gate_mask(self) -> None:
        pthread_sigmask = getattr(signal, "pthread_sigmask", None)
        if pthread_sigmask is None:
            self.skipTest("pthread_sigmask is required by the macOS phase-1 supervisor")
        stop_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        previous_mask = pthread_sigmask(signal.SIG_UNBLOCK, stop_signals)
        observed_mask: list[int] = []
        supervisor: ForegroundSupervisor

        def factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            return popen_with_signal_mask(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json,signal;"
                        "print(json.dumps(sorted(int(value) for value in "
                        "signal.pthread_sigmask(signal.SIG_BLOCK, []))), flush=True);"
                        "signal.pause()"
                    ),
                ],
                child_signal_mask=child_signal_mask,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

        def after_start(process: subprocess.Popen[bytes]) -> None:
            assert process.stdout is not None
            try:
                observed_mask.extend(json.loads(process.stdout.readline().decode("utf-8")))
            finally:
                process.stdout.close()
            supervisor.request_local_stop()

        supervisor = ForegroundSupervisor(
            process_factory=factory,
            after_start=after_start,
            control_socket=self.root / "child-signal-mask.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
            stop_timeout=1.0,
        )
        try:
            result = supervisor.run()
        finally:
            pthread_sigmask(signal.SIG_SETMASK, previous_mask)

        self.assertNotIn(int(signal.SIGTERM), observed_mask)
        self.assertNotIn(int(signal.SIGHUP), observed_mask)
        self.assertNotIn(int(signal.SIGINT), observed_mask)
        self.assertTrue(result.terminated)
        self.assertFalse(result.forced_exact_child)
        self.assertEqual(-int(signal.SIGTERM), result.child_returncode)

    def test_process_group_stop_cannot_terminate_child_before_revoke(self) -> None:
        socket_path = self.root / "group-isolation.sock"
        script = "\n".join(
            [
                "import json, os, signal, subprocess, sys",
                f"sys.path.insert(0, {str(SKILL_ROOT)!r})",
                "from runtime.gptpro_mcp.supervisor import ForegroundSupervisor",
                "from runtime.gptpro_mcp.tunnel_client import popen_with_signal_mask",
                "observed = {}",
                "supervisor = None",
                "def factory(child_signal_mask):",
                "    process = popen_with_signal_mask(",
                "        [sys.executable, '-c', 'import time; time.sleep(60)'],",
                "        child_signal_mask=child_signal_mask,",
                "        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,",
                "        stderr=subprocess.DEVNULL, start_new_session=True)",
                "    observed['process'] = process",
                "    return process",
                "def after_start(process):",
                "    observed['controller_pgid'] = os.getpgrp()",
                "    observed['child_pgid'] = os.getpgid(process.pid)",
                "    os.killpg(os.getpgrp(), signal.SIGTERM)",
                "def revoke(reason):",
                "    process = observed['process']",
                "    observed['reason'] = reason",
                "    observed['alive_at_revoke'] = process.poll() is None",
                "supervisor = ForegroundSupervisor(",
                "    process_factory=factory, after_start=after_start,",
                f"    control_socket={str(socket_path)!r},",
                f"    session_id_sha256={self.session!r},",
                "    revoke_before_terminate=revoke, stop_timeout=1.0)",
                "result = supervisor.run()",
                "observed['returncode'] = result.child_returncode",
                "print(json.dumps(observed, default=str), flush=True)",
            ]
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=10,
            start_new_session=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        observed = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(observed["alive_at_revoke"])
        self.assertEqual("signal_term", observed["reason"])
        self.assertNotEqual(observed["controller_pgid"], observed["child_pgid"])
        self.assertEqual(-int(signal.SIGTERM), observed["returncode"])

    def test_child_exit_reason_is_sealed_before_pending_stop_signal(self) -> None:
        class ExitedProcess:
            pid = 4242
            returncode = 0

            def __init__(self) -> None:
                self.sent = False

            def poll(self) -> int:
                if not self.sent:
                    self.sent = True
                    os.kill(os.getpid(), signal.SIGTERM)
                return 0

        reasons: list[str] = []
        process = ExitedProcess()
        supervisor = ForegroundSupervisor(
            process_factory=lambda child_signal_mask: process,  # type: ignore[arg-type,return-value]
            control_socket=self.root / "child-exit-reason.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=reasons.append,
        )

        result = supervisor.run()

        self.assertEqual(["child_exit"], reasons)
        self.assertEqual(0, result.child_returncode)
        self.assertFalse(result.terminated)
        self.assertFalse(result.forced_exact_child)

    def test_partial_signal_handler_install_is_rolled_back(self) -> None:
        original_signal = signal.signal
        original_term = signal.getsignal(signal.SIGTERM)
        original_hup = signal.getsignal(signal.SIGHUP)
        calls = 0

        def fail_second_install(signum: int, handler: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated signal install failure")
            return original_signal(signum, handler)

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=self.root / "ps.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.signal.signal",
                side_effect=fail_second_install,
            ),
            self.assertRaises(RuntimeStateError) as raised,
        ):
            supervisor.run()

        self.assertEqual("CONTROL_SIGNAL_UNSAFE", raised.exception.code)
        self.assertEqual("CONTROL_SIGNAL_UNSAFE", supervisor.failure_code)
        self.assertEqual(original_term, signal.getsignal(signal.SIGTERM))
        self.assertEqual(original_hup, signal.getsignal(signal.SIGHUP))
        self.assertFalse((self.root / "ps.sock").exists())

    def test_transient_signal_restore_failure_recovers_all_handlers(self) -> None:
        original_signal = signal.signal
        original_term = signal.getsignal(signal.SIGTERM)
        original_hup = signal.getsignal(signal.SIGHUP)
        calls = 0
        supervisor: ForegroundSupervisor

        def fail_first_restore(signum: int, handler: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("simulated first restore failure")
            return original_signal(signum, handler)

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            after_start=lambda process: supervisor.request_local_stop(),
            control_socket=self.root / "sr.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        with mock.patch(
            "runtime.gptpro_mcp.supervisor.signal.signal",
            side_effect=fail_first_restore,
        ):
            result = supervisor.run()

        self.assertIsNotNone(result.child_returncode)
        self.assertIsNone(supervisor.failure_code)
        self.assertEqual(original_term, signal.getsignal(signal.SIGTERM))
        self.assertEqual(original_hup, signal.getsignal(signal.SIGHUP))
        self.assertFalse((self.root / "sr.sock").exists())

    def test_persistent_signal_restore_failure_reports_stable_error_after_other_handler(self) -> None:
        original_signal = signal.signal
        original_term = signal.getsignal(signal.SIGTERM)
        original_hup = signal.getsignal(signal.SIGHUP)
        calls = 0
        supervisor: ForegroundSupervisor

        def fail_term_restores(signum: int, handler: object) -> object:
            nonlocal calls
            calls += 1
            if calls >= 3 and signum == signal.SIGTERM:
                raise OSError("simulated persistent restore failure")
            return original_signal(signum, handler)

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            after_start=lambda process: supervisor.request_local_stop(),
            control_socket=self.root / "spr.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        try:
            with (
                mock.patch(
                    "runtime.gptpro_mcp.supervisor.signal.signal",
                    side_effect=fail_term_restores,
                ),
                self.assertRaises(RuntimeStateError) as raised,
            ):
                supervisor.run()
        finally:
            original_signal(signal.SIGTERM, original_term)
            original_signal(signal.SIGHUP, original_hup)

        self.assertEqual("CONTROL_SIGNAL_UNSAFE", raised.exception.code)
        self.assertEqual("CONTROL_SIGNAL_UNSAFE", supervisor.failure_code)
        self.assertFalse((self.root / "spr.sock").exists())

    def test_listener_is_registered_before_early_factory_failure_without_hidden_thread_error(self) -> None:
        background_errors: list[object] = []
        previous_hook = threading.excepthook

        def capture_thread_error(arguments: object) -> None:
            background_errors.append(arguments)

        threading.excepthook = capture_thread_error
        try:
            for index in range(25):
                socket_path = self.root / f"early-{index}.sock"
                supervisor: ForegroundSupervisor

                def fail_factory(
                    child_signal_mask: set[signal.Signals] | None,
                ) -> subprocess.Popen[bytes]:
                    del child_signal_mask
                    self.assertTrue(supervisor._listener_ready.is_set())
                    self.assertIsNone(supervisor._listener_error)
                    raise RuntimeError("factory failed")

                supervisor = ForegroundSupervisor(
                    process_factory=fail_factory,
                    control_socket=socket_path,
                    session_id_sha256=self.session,
                    revoke_before_terminate=lambda reason: None,
                )
                with self.assertRaisesRegex(RuntimeError, "factory failed"):
                    supervisor.run()
                self.assertFalse(socket_path.exists())
                self.assertIsNotNone(supervisor.terminal_result)
                self.assertIsNone(supervisor.terminal_result.child_returncode)
        finally:
            threading.excepthook = previous_hook
        self.assertEqual([], background_errors)

    def test_listener_thread_start_failure_cleans_owned_socket_and_records_terminal_result(self) -> None:
        socket_path = self.root / "thread-start-failure.sock"
        revoked: list[str] = []
        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=revoked.append,
        )
        with (
            mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("no thread")),
            self.assertRaisesRegex(RuntimeError, "no thread"),
        ):
            supervisor.run()
        self.assertFalse(socket_path.exists())
        self.assertEqual(["controller_exit"], revoked)
        self.assertEqual("CONTROL_LISTENER_FAILED", supervisor.failure_code)
        self.assertIsNotNone(supervisor.terminal_result)
        self.assertTrue(supervisor.terminal_result.revoke_attempted)
        self.assertIsNone(supervisor.terminal_result.child_returncode)

    def test_preexisting_control_socket_is_never_unlinked_by_conflicting_supervisor(self) -> None:
        socket_path = self.root / "owned-by-other.sock"
        owner = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        owner.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        owner.listen(1)
        inode = socket_path.stat().st_ino
        try:
            supervisor = ForegroundSupervisor(
                process_factory=self.sleeping_child,
                control_socket=socket_path,
                session_id_sha256=self.session,
                revoke_before_terminate=lambda reason: None,
            )
            with self.assertRaises(RuntimeStateError) as raised:
                supervisor.run()
            self.assertEqual("SESSION_CONFLICT", raised.exception.code)
            self.assertEqual("SESSION_CONFLICT", supervisor.failure_code)
            self.assertTrue(socket_path.exists())
            self.assertEqual(inode, socket_path.stat().st_ino)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                client.connect(str(socket_path))
                accepted, _ = owner.accept()
                accepted.close()
            finally:
                client.close()
        finally:
            owner.close()
            socket_path.unlink(missing_ok=True)

    def test_replacement_before_first_post_bind_identity_is_never_adopted_or_unlinked(self) -> None:
        socket_path = self.root / "publish-race.sock"
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        real_metadata = supervisor_module._control_socket_metadata
        replacement_inode: int | None = None
        replacement_path: Path | None = None
        replaced = False
        factory_calls = 0

        def replace_on_first_post_bind_read(path: Path):
            nonlocal replacement_inode, replacement_path, replaced
            candidate = Path(path)
            if not replaced and candidate != socket_path:
                replaced = True
                replacement_path = candidate
                candidate.unlink(missing_ok=True)
                replacement.bind(str(candidate))
                os.chmod(candidate, 0o600)
                replacement.listen(1)
                replacement_inode = candidate.stat().st_ino
            return real_metadata(candidate)

        def process_factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            nonlocal factory_calls
            del child_signal_mask
            factory_calls += 1
            return self.sleeping_child()

        supervisor = ForegroundSupervisor(
            process_factory=process_factory,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        try:
            with (
                mock.patch.object(
                    supervisor_module,
                    "_control_socket_metadata",
                    side_effect=replace_on_first_post_bind_read,
                ),
                self.assertRaises(RuntimeStateError) as raised,
            ):
                supervisor.run()
            self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
            self.assertEqual(0, factory_calls)
            self.assertFalse(socket_path.exists())
            self.assertIsNotNone(replacement_path)
            self.assertTrue(replacement_path.exists())
            self.assertEqual(replacement_inode, replacement_path.stat().st_ino)
            self.assertIsNone(supervisor._control_socket_identity)
        finally:
            replacement.close()
            socket_path.unlink(missing_ok=True)
            if replacement_path is not None:
                replacement_path.unlink(missing_ok=True)

    def test_cleanup_preserves_same_uid_replacement_control_socket(self) -> None:
        socket_path = self.root / "replace.sock"
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        replacement_inode: int | None = None
        supervisor: ForegroundSupervisor

        def replace_before_termination(reason: str) -> None:
            nonlocal replacement_inode
            self.assertEqual("user_requested", reason)
            socket_path.unlink()
            replacement.bind(str(socket_path))
            os.chmod(socket_path, 0o600)
            replacement.listen(1)
            replacement_inode = socket_path.stat().st_ino

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            after_start=lambda process: supervisor.request_local_stop(),
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=replace_before_termination,
        )
        try:
            result = supervisor.run()
            self.assertIsNotNone(result.child_returncode)
            self.assertTrue(socket_path.exists())
            self.assertEqual(replacement_inode, socket_path.stat().st_ino)
        finally:
            replacement.close()
            socket_path.unlink(missing_ok=True)

    def test_post_bind_failure_preserves_same_uid_replacement_staging_socket(self) -> None:
        socket_path = self.root / "bind-replace.sock"
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        original_chmod = os.chmod
        replacement_inode: int | None = None
        replacement_path: Path | None = None

        def replace_then_fail(path, mode, *args, **kwargs) -> None:
            nonlocal replacement_inode, replacement_path
            candidate = Path(path)
            if candidate.parent != socket_path.parent or candidate == socket_path:
                original_chmod(path, mode, *args, **kwargs)
                return
            replacement_path = candidate
            candidate.unlink()
            replacement.bind(str(candidate))
            original_chmod(candidate, 0o600)
            replacement.listen(1)
            replacement_inode = candidate.stat().st_ino
            raise OSError("simulated post-bind setup failure")

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        try:
            with (
                mock.patch(
                    "runtime.gptpro_mcp.supervisor.os.chmod",
                    side_effect=replace_then_fail,
                ),
                self.assertRaisesRegex(OSError, "post-bind setup failure"),
            ):
                supervisor.run()
            self.assertFalse(socket_path.exists())
            self.assertIsNotNone(replacement_path)
            self.assertTrue(replacement_path.exists())
            self.assertEqual(replacement_inode, replacement_path.stat().st_ino)
        finally:
            replacement.close()
            if replacement_path is not None:
                replacement_path.unlink(missing_ok=True)

    def test_chmod_failure_removes_the_exact_socket_just_bound(self) -> None:
        socket_path = self.root / "chmod-fail.sock"
        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        with (
            mock.patch(
                "runtime.gptpro_mcp.supervisor.os.chmod",
                side_effect=OSError("simulated chmod failure"),
            ),
            self.assertRaisesRegex(OSError, "chmod failure"),
        ):
            supervisor.run()
        self.assertEqual("CONTROL_LISTENER_FAILED", supervisor.failure_code)
        self.assertFalse(socket_path.exists())

    def test_cleanup_does_not_unlink_a_replacement_after_identity_check(self) -> None:
        socket_path = self.root / "cleanup-race.sock"
        original = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        original.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        expected = socket_path.stat()
        real_rename = os.rename
        replacement_inode: int | None = None
        raced = False

        def replace_before_claim(src, dst, *args, **kwargs) -> None:
            nonlocal raced, replacement_inode
            if not raced:
                raced = True
                socket_path.unlink()
                replacement.bind(str(socket_path))
                os.chmod(socket_path, 0o600)
                replacement_inode = socket_path.stat().st_ino
            real_rename(src, dst, *args, **kwargs)

        try:
            with mock.patch.object(
                supervisor_module.os,
                "rename",
                side_effect=replace_before_claim,
            ):
                removed = supervisor_module._claim_and_unlink_control_socket_if_matches(
                    socket_path,
                    (expected.st_dev, expected.st_ino),
                )
            self.assertFalse(removed)
            self.assertTrue(socket_path.exists())
            self.assertEqual(replacement_inode, socket_path.stat().st_ino)
        finally:
            original.close()
            replacement.close()
            socket_path.unlink(missing_ok=True)

    def test_persistent_post_bind_metadata_failure_never_publishes_stale_socket(self) -> None:
        socket_path = self.root / "meta-fail.sock"
        real_metadata = supervisor_module._control_socket_metadata
        calls = 0

        def fail_post_bind_reads(path: Path):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("simulated post-bind metadata failure")
            return real_metadata(path)

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        with (
            mock.patch.object(
                supervisor_module,
                "_control_socket_metadata",
                side_effect=fail_post_bind_reads,
            ),
            self.assertRaises(RuntimeStateError) as raised,
        ):
            supervisor.run()

        self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
        self.assertEqual("CONTROL_LISTENER_FAILED", supervisor.failure_code)
        self.assertFalse(socket_path.exists())
        self.assertFalse(request_cooperative_stop(socket_path, self.session))
        staged = [path for path in self.root.iterdir() if stat.S_ISSOCK(path.lstat().st_mode)]
        self.assertEqual(1, len(staged))
        staged[0].unlink()

    def test_slow_control_frame_is_closed_before_supervisor_returns(self) -> None:
        socket_path = self.root / "slow-frame.sock"
        slow_client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        supervisor: ForegroundSupervisor

        def after_start(process: subprocess.Popen[bytes]) -> None:
            del process
            slow_client.connect(str(socket_path))
            slow_client.sendall(b"{")
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                with supervisor._connections_lock:
                    if supervisor._connections:
                        break
                time.sleep(0.01)
            with supervisor._connections_lock:
                self.assertEqual(1, len(supervisor._connections))
            supervisor.request_local_stop()

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            after_start=after_start,
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        try:
            result = supervisor.run()
        finally:
            slow_client.close()
        self.assertIsNotNone(result.child_returncode)
        self.assertFalse(socket_path.exists())
        self.assertFalse(
            any(
                thread.name == f"gptpro-control-{self.session[:12]}" and thread.is_alive()
                for thread in threading.enumerate()
            )
        )

    def test_control_client_uses_one_total_response_deadline(self) -> None:
        socket_path = self.root / "slow-response.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        listener.listen(1)

        def drip_response() -> None:
            connection, _ = listener.accept()
            try:
                connection.recv(4096)
                for chunk in (b"{", b'"accepted"', b":", b"true", b"}\n"):
                    connection.sendall(chunk)
                    time.sleep(0.08)
            except OSError:
                pass
            finally:
                connection.close()

        server_thread = threading.Thread(target=drip_response)
        server_thread.start()
        started = time.monotonic()
        try:
            self.assertFalse(
                request_cooperative_stop(socket_path, self.session, timeout=0.15)
            )
        finally:
            server_thread.join(timeout=1.0)
            listener.close()
            socket_path.unlink(missing_ok=True)
        self.assertLess(time.monotonic() - started, 0.75)
        self.assertFalse(server_thread.is_alive())

    def test_selector_construction_failure_is_foreground_and_leaves_no_thread_error(self) -> None:
        socket_path = self.root / "selector-failure.sock"
        background_errors: list[object] = []
        previous_hook = threading.excepthook
        threading.excepthook = lambda arguments: background_errors.append(arguments)
        try:
            supervisor = ForegroundSupervisor(
                process_factory=self.sleeping_child,
                control_socket=socket_path,
                session_id_sha256=self.session,
                revoke_before_terminate=lambda reason: None,
            )
            with (
                mock.patch(
                    "runtime.gptpro_mcp.supervisor.selectors.DefaultSelector",
                    side_effect=OSError("selector unavailable"),
                ),
                self.assertRaises(RuntimeStateError) as raised,
            ):
                supervisor.run()
            self.assertEqual("CONTROL_LISTENER_FAILED", raised.exception.code)
            self.assertEqual("CONTROL_LISTENER_FAILED", supervisor.failure_code)
            self.assertIsNotNone(supervisor.terminal_result)
            self.assertFalse(socket_path.exists())
        finally:
            threading.excepthook = previous_hook
        self.assertEqual([], background_errors)

    def test_remote_stop_accepted_before_spawn_never_creates_child(self) -> None:
        socket_path = self.root / "remote-pre-spawn.sock"
        spawned: list[bool] = []
        stop_results: list[bool] = []
        supervisor = ForegroundSupervisor(
            process_factory=lambda child_signal_mask: spawned.append(True),  # type: ignore[arg-type,return-value]
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        original_start = supervisor._start_process_if_running

        def accept_remote_then_start() -> bool:
            thread = threading.Thread(
                target=lambda: stop_results.append(
                    request_cooperative_stop(socket_path, self.session)
                )
            )
            thread.start()
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            return original_start()

        supervisor._start_process_if_running = accept_remote_then_start  # type: ignore[method-assign]
        with self.assertRaises(RuntimeStateError) as raised:
            supervisor.run()

        self.assertEqual("ACTIVATION_CANCELLED", raised.exception.code)
        self.assertEqual("ACTIVATION_CANCELLED", supervisor.failure_code)
        self.assertEqual([True], stop_results)
        self.assertEqual([], spawned)
        self.assertFalse(socket_path.exists())

    def test_remote_stop_during_factory_is_acknowledged_after_child_ownership(self) -> None:
        socket_path = self.root / "remote-in-factory.sock"
        events: list[str] = []
        stop_results: list[bool] = []
        stop_thread: threading.Thread | None = None
        supervisor: ForegroundSupervisor

        def factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            nonlocal stop_thread
            events.append("factory_enter")

            def stop() -> None:
                stop_results.append(
                    request_cooperative_stop(socket_path, self.session)
                )
                events.append("ack_returned")

            stop_thread = threading.Thread(target=stop)
            stop_thread.start()
            self.assertTrue(supervisor._remote_stop_pending.wait(timeout=2.0))
            self.assertTrue(stop_thread.is_alive())
            process = self.sleeping_child(child_signal_mask)
            events.append("child_owned")
            return process

        supervisor = ForegroundSupervisor(
            process_factory=factory,
            after_start=lambda process: events.append("after_start"),
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: events.append(f"revoke:{reason}"),
            stop_timeout=1.0,
        )

        with self.assertRaises(RuntimeStateError) as raised:
            supervisor.run()
        assert stop_thread is not None
        stop_thread.join(timeout=2.0)

        self.assertEqual("ACTIVATION_CANCELLED", raised.exception.code)
        self.assertFalse(stop_thread.is_alive())
        self.assertEqual([True], stop_results)
        self.assertNotIn("after_start", events)
        self.assertLess(events.index("child_owned"), events.index("ack_returned"))
        self.assertIn("revoke:remote_stop", events)

    def test_pending_remote_stop_prevents_activation_publication(self) -> None:
        published: list[bool] = []
        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=self.root / "pending-publish.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        supervisor._remote_stop_pending.set()

        def finish_stop() -> None:
            time.sleep(0.01)
            supervisor.request_local_stop("remote_stop")

        thread = threading.Thread(target=finish_stop)
        thread.start()
        result = supervisor.publish_activation_if_running(
            lambda: published.append(True)
        )
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertFalse(result)
        self.assertEqual([], published)
        self.assertTrue(supervisor.stop_requested)

    def test_signal_accepted_before_spawn_never_creates_child(self) -> None:
        socket_path = self.root / "signal-pre-spawn.sock"
        spawned: list[bool] = []
        supervisor = ForegroundSupervisor(
            process_factory=lambda child_signal_mask: spawned.append(True),  # type: ignore[arg-type,return-value]
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        original_start = supervisor._start_process_if_running

        def signal_then_start() -> bool:
            os.kill(os.getpid(), signal.SIGTERM)
            return original_start()

        supervisor._start_process_if_running = signal_then_start  # type: ignore[method-assign]
        with self.assertRaises(RuntimeStateError) as raised:
            supervisor.run()

        self.assertEqual("ACTIVATION_CANCELLED", raised.exception.code)
        self.assertEqual("ACTIVATION_CANCELLED", supervisor.failure_code)
        self.assertEqual([], spawned)
        self.assertFalse(socket_path.exists())

    def test_signal_sent_inside_factory_is_accepted_only_after_child_is_owned(self) -> None:
        socket_path = self.root / "signal-in-factory.sock"
        events: list[str] = []
        reasons: list[str] = []
        supervisor: ForegroundSupervisor

        def factory(
            child_signal_mask: set[signal.Signals] | None,
        ) -> subprocess.Popen[bytes]:
            events.append("factory_enter")
            os.kill(os.getpid(), signal.SIGTERM)
            self.assertFalse(supervisor.stop_requested)
            events.append("signal_pending")
            process = self.sleeping_child(child_signal_mask)
            events.append("child_owned")
            return process

        supervisor = ForegroundSupervisor(
            process_factory=factory,
            after_start=lambda process: events.append("after_start"),
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=reasons.append,
            stop_timeout=1.0,
        )

        with self.assertRaises(RuntimeStateError) as raised:
            supervisor.run()

        self.assertEqual("ACTIVATION_CANCELLED", raised.exception.code)
        self.assertEqual(["factory_enter", "signal_pending", "child_owned"], events)
        self.assertEqual(["signal_term"], reasons)
        self.assertIsNotNone(supervisor.terminal_result)
        self.assertTrue(supervisor.terminal_result.terminated)
        self.assertFalse(supervisor.terminal_result.forced_exact_child)

    def test_keyboard_interrupt_preserves_an_already_sealed_stop_reason(self) -> None:
        reasons: list[str] = []
        supervisor: ForegroundSupervisor

        def interrupt_after_remote_stop(process: subprocess.Popen[bytes]) -> None:
            del process
            supervisor.request_local_stop("remote_stop")
            raise KeyboardInterrupt

        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            after_start=interrupt_after_remote_stop,
            control_socket=self.root / "ki.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=reasons.append,
        )

        with self.assertRaises(KeyboardInterrupt):
            supervisor.run()

        self.assertEqual(["remote_stop"], reasons)
        self.assertNotEqual("ACTIVATION_CANCELLED", supervisor.failure_code)

    def test_stubborn_child_failure_still_removes_socket_and_restores_signals(self) -> None:
        class StubbornProcess:
            pid = 5151
            returncode = None

            @staticmethod
            def poll() -> None:
                return None

            @staticmethod
            def terminate() -> None:
                return None

            @staticmethod
            def wait(timeout: float | None = None) -> int:
                raise subprocess.TimeoutExpired(cmd="stubborn", timeout=timeout)

            @staticmethod
            def kill() -> None:
                raise RuntimeError("injected kill failure")

        socket_path = self.root / "stubborn.sock"
        supervisor: ForegroundSupervisor
        supervisor = ForegroundSupervisor(
            process_factory=lambda child_signal_mask: StubbornProcess(),
            after_start=lambda process: supervisor.request_local_stop(),
            control_socket=socket_path,
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
            stop_timeout=0.01,
        )
        previous = {signal.SIGTERM: signal.getsignal(signal.SIGTERM), signal.SIGHUP: signal.getsignal(signal.SIGHUP)}
        with self.assertRaisesRegex(RuntimeError, "injected kill failure"):
            supervisor.run()
        self.assertFalse(socket_path.exists())
        self.assertEqual(previous[signal.SIGTERM], signal.getsignal(signal.SIGTERM))
        self.assertEqual(previous[signal.SIGHUP], signal.getsignal(signal.SIGHUP))

    def test_local_stop_reason_is_bounded_machine_data(self) -> None:
        supervisor = ForegroundSupervisor(
            process_factory=self.sleeping_child,
            control_socket=self.root / "unused.sock",
            session_id_sha256=self.session,
            revoke_before_terminate=lambda reason: None,
        )
        with self.assertRaises(ValueError):
            supervisor.request_local_stop("free form reason")


if __name__ == "__main__":
    unittest.main()
