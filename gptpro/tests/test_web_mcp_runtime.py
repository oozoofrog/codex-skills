from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"
TUNNEL_ENV_NAME = "GPTPRO_RUNTIME_TEST_TUNNEL_ID"
TUNNEL_REFERENCE = f"env:{TUNNEL_ENV_NAME}"
RAW_TUNNEL_ID = "tunnel_" + "runtimetest" * 2
TUNNEL_PROFILE = "runtime-test"
APP_NAME = "GPT Pro Repository Reader"
WORKSPACE_LABEL = "Runtime Test Workspace"
MCP_TARGET_HASH = hashlib.sha256(b"runtime-test-mcp-target").hexdigest()
TUNNEL_PROFILE_HASH = hashlib.sha256(b"runtime-test-tunnel-profile").hexdigest()
TUNNEL_BINARY_HASH = hashlib.sha256(b"runtime-test-tunnel-binary").hexdigest()


class WebMcpRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Keep the canonical macOS runtime suffix below the Unix socket path limit.
        self.temporary = tempfile.TemporaryDirectory(prefix="gp.", dir="/tmp")
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.output_root = self.root / "handoffs"
        self.test_home = self.root / "home"
        self.runtime_root = (
            self.test_home
            / "Library"
            / "Application Support"
            / "gptpro"
            / "runtime"
            / "v1"
        )
        self.git("init")
        self.git("config", "user.name", "Runtime Test")
        self.git("config", "user.email", "runtime@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("VALUE = 42\n", encoding="utf-8")
        self.git("add", "src/main.py")
        self.git("commit", "-m", "fixture")
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.test_home)
        self.env[TUNNEL_ENV_NAME] = RAW_TUNNEL_ID
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.module = self.load_cli_module()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        runtime_state_module = sys.modules[self.module.RuntimeStateStore.__module__]
        with (
            mock.patch.dict(os.environ, self.env, clear=True),
            mock.patch.object(
                runtime_state_module,
                "default_runtime_root",
                return_value=self.runtime_root,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            try:
                returncode = self.module.main(list(args))
            except SystemExit as exc:
                returncode = int(exc.code or 0)
        result = subprocess.CompletedProcess(
            [sys.executable, str(SCRIPT), *args],
            returncode,
            stdout.getvalue(),
            stderr.getvalue(),
        )
        self.assertEqual(
            expected,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertNotIn(RAW_TUNNEL_ID, result.stdout + result.stderr)
        return result

    @staticmethod
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def use_runtime_home(self, name: str) -> Path:
        self.test_home = self.root / name
        self.env["HOME"] = str(self.test_home)
        self.runtime_root = (
            self.test_home
            / "Library"
            / "Application Support"
            / "gptpro"
            / "runtime"
            / "v1"
        )
        return self.runtime_root

    @staticmethod
    def load_cli_module():
        module_name = f"gptpro_runtime_test_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("Unable to import gptpro.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def prepare_and_approve(self, *, transport: str = "mcp-read") -> Path:
        arguments = [
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            transport,
            "--task",
            "Review the approved immutable snapshot.",
            "--output-root",
            str(self.output_root),
        ]
        if transport == "mcp-read":
            arguments.extend(
                [
                    "--tunnel-runtime-alias",
                    TUNNEL_PROFILE,
                    "--tunnel-id-ref",
                    TUNNEL_REFERENCE,
                    "--chatgpt-app-name",
                    APP_NAME,
                    "--chatgpt-workspace-label",
                    WORKSPACE_LABEL,
                    "--approval-ttl-seconds",
                    "600",
                    "--session-ttl-seconds",
                    "600",
                    "--idle-ttl-seconds",
                    "300",
                    "--max-tool-calls",
                    "8",
                ]
            )
        prepared = self.run_cli(*arguments)
        handoff = Path(json.loads(prepared.stdout)["handoff_dir"])
        approval = [
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "runtime-test-user",
            "--confirm-transmission",
        ]
        if transport == "mcp-read":
            approval.append("--confirm-mcp-disclosure")
        self.run_cli(*approval)
        return handoff

    def test_active_announcement_fails_immediately_on_stdout_backpressure(self) -> None:
        read_descriptor, write_descriptor = os.pipe()
        os.set_blocking(write_descriptor, False)
        try:
            while True:
                try:
                    os.write(write_descriptor, b"x" * 4096)
                except BlockingIOError:
                    break
            os.set_blocking(write_descriptor, True)
            writer = os.fdopen(write_descriptor, "w", encoding="utf-8", closefd=False)
            started = self.module.time.monotonic()
            try:
                with (
                    mock.patch.object(self.module.sys, "stdout", writer),
                    self.assertRaises(self.module.ControllerError) as raised,
                ):
                    self.module._write_atomic_json_line_nonblocking(
                        {"event": "mcp_active"},
                        error_code="ACTIVE_ANNOUNCEMENT_UNAVAILABLE",
                    )
            finally:
                writer.close()
            elapsed = self.module.time.monotonic() - started
        finally:
            os.close(write_descriptor)
            os.close(read_descriptor)

        self.assertEqual("ACTIVE_ANNOUNCEMENT_UNAVAILABLE", raised.exception.code)
        self.assertLess(elapsed, 0.5)

    def preflight(self, handoff: Path) -> tuple[dict, dict]:
        verified = self.module.verify_package(handoff)
        preflight = self.module.mcp_activation_preflight(
            verified,
            tunnel_profile=TUNNEL_PROFILE,
            observed_tunnel_binding_sha256=verified["manifest"]["connector"][
                "tunnel_id_binding_sha256"
            ],
            observed_tunnel_profile_sha256=TUNNEL_PROFILE_HASH,
            observed_tunnel_client_binary_sha256=TUNNEL_BINARY_HASH,
            observed_mcp_target_sha256=MCP_TARGET_HASH,
            observed_mcp_runtime_tree_sha256=self.module.mcp_runtime_tree_sha256(),
            profile_binding_verification="automatic-doctor-json",
            workspace_binding_confirmed=True,
        )
        return verified, preflight

    def activate(self, handoff: Path) -> tuple[object, str, dict]:
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        raw_nonce = os.urandom(32)
        session_hash = hashlib.sha256(raw_nonce).hexdigest()
        begun = self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        completed = self.module.complete_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            audit_header_sha256=begun["audit_header_sha256"],
            successful_control_plane_poll_observed=True,
        )
        return store, session_hash, completed

    def close_protocol_trace(self, handoff: Path, reason: str = "stdio_eof") -> object:
        """Model the exact MCP stdio child closing after its input reaches EOF."""

        verified = self.module.verify_package(handoff)
        return self.module.protocol_trace_for(verified).close(reason)

    def interrupt_before_audit_header(
        self, handoff: Path, *, runtime_root: Path | None = None
    ) -> tuple[object, str]:
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=runtime_root or self.runtime_root)
        session_hash = hashlib.sha256(os.urandom(32)).hexdigest()
        with mock.patch.object(
            self.module.AuditLog,
            "create_header",
            side_effect=SystemExit("simulated abrupt controller death"),
        ):
            with self.assertRaises(SystemExit):
                self.module.begin_mcp_activation(
                    verified,
                    store,
                    session_id_sha256=session_hash,
                    preflight=preflight,
                )
        self.assertEqual("activating", store.read()["status"])
        self.assertIsNone(self.load(handoff / "state.json")["mcp_session"])
        return store, session_hash

    def test_activation_is_poll_gated_and_failure_never_becomes_active(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(os.urandom(32)).hexdigest()
        begun = self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )

        with self.assertRaisesRegex(self.module.HandoffError, "successful control-plane poll"):
            self.module.complete_mcp_activation(
                handoff,
                store,
                session_id_sha256=session_hash,
                audit_header_sha256=begun["audit_header_sha256"],
                successful_control_plane_poll_observed=False,
            )
        self.assertEqual("activating", store.read()["status"])
        self.assertIsNone(self.load(handoff / "state.json")["mcp_session"])

        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        self.assertEqual("faulted", store.read()["status"])
        receipt = self.load(handoff / "receipt.json")
        failed_state = self.load(handoff / "state.json")
        self.assertEqual("approved", failed_state["phase"])
        self.assertEqual(
            "activation_failed", failed_state["mcp_protocol_trace"]["status"]
        )
        self.assertEqual(1, sum(event["type"] == "mcp_activation_failed" for event in receipt["events"]))
        self.run_cli("verify", "--handoff-dir", str(handoff))
        trace = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertEqual("activation_failed", trace["session_status"])
        self.assertTrue(trace["protocol_trace"]["header_binding_valid"])
        self.assertFalse(trace["protocol_trace"]["artifact_identity_bound"])
        self.assertFalse(trace["protocol_trace"]["lifecycle_binding_valid"])
        self.assertEqual(0, trace["disclosure_audit"]["tool_calls"])
        self.assertEqual(0, trace["disclosure_audit"]["disclosed_bytes"])

        stop = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=0,
            forced_exact_child=False,
        )
        repeated = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=0,
            forced_exact_child=False,
        )
        self.assertTrue(stop["activation_stop_receipt_recorded"])
        self.assertTrue(repeated["activation_stop_receipt_recorded"])
        runtime = store.read()
        self.assertTrue(runtime["activation_child_stopped"])
        self.assertEqual(0, runtime["activation_child_returncode"])
        self.assertFalse(runtime["activation_forced_exact_child"])
        self.assertTrue(runtime["activation_stop_receipt_recorded"])
        receipt = self.load(handoff / "receipt.json")
        activation_stops = [
            event for event in receipt["events"] if event["type"] == "mcp_activation_stopped"
        ]
        self.assertEqual(1, len(activation_stops))
        self.assertTrue(activation_stops[0]["data"]["exact_child_stop_observed"])
        self.assertNotIn("tunnel_runtime_stopped", failed_state["mcp_protocol_trace"])
        self.assertFalse(any(event["type"] == "mcp_stopped" for event in receipt["events"]))
        self.run_cli("verify", "--handoff-dir", str(handoff))
        final_trace = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )["protocol_trace"]
        self.assertTrue(final_trace["artifact_identity_bound"])
        self.assertTrue(final_trace["lifecycle_binding_valid"])
        self.assertFalse(final_trace["terminal_evidence"]["runtime_stop_observed"])
        self.assertTrue(
            final_trace["terminal_evidence"]["activation_failure_stop_observed"]
        )
        self.assertEqual(
            "activation_failed_child_stopped_protocol_eof_unobserved",
            final_trace["terminal_evidence"]["status"],
        )

    def test_content_verification_fails_closed_without_inverting_package_lock_order(self) -> None:
        handoff = self.prepare_and_approve()
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        session_hash = hashlib.sha256(b"pending-package-transaction").hexdigest()
        next_receipt = self.module.receipt_with_event(
            receipt,
            "mcp_activation_failed",
            {
                "phase_before": "approved",
                "phase_after": "approved",
                "session_id_sha256": session_hash,
                "error_code": "SIMULATED_CRASH",
            },
        )

        def crash_after_journal(checkpoint: str) -> None:
            if checkpoint == "journal":
                raise SystemExit("simulated package writer death")

        with self.assertRaises(SystemExit):
            self.module.commit_lifecycle_pair(
                handoff,
                operation="mcp-activation-failed",
                state=state,
                receipt=next_receipt,
                fault_injector=crash_after_journal,
            )

        with mock.patch.object(
            self.module,
            "recover_lifecycle_pair",
            side_effect=AssertionError("tool-side verification must not acquire package lock"),
        ) as recovery:
            with self.assertRaisesRegex(
                self.module.HandoffError, "PACKAGE_LIFECYCLE_PENDING"
            ):
                self.module.verify_package(handoff, recover_lifecycle=False)
            recovery.assert_not_called()

        recovered = self.module.verify_package(handoff)
        self.assertEqual("approved", recovered["state"]["phase"])
        self.assertEqual(
            1,
            sum(
                event["type"] == "mcp_activation_failed"
                for event in recovered["receipt"]["events"]
            ),
        )

    def test_failed_activation_stop_receipt_requires_strict_additive_contract(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"strict-activation-stop").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        failed = self.module.verify_package(handoff)
        malformed_receipt = self.module.receipt_with_event(
            failed["receipt"],
            "mcp_activation_stopped",
            {
                "phase_before": "approved",
                "phase_after": "approved",
                "session_id_sha256": session_hash,
                "reason": "controller_exit",
                "exact_child_stop_observed": True,
                "child_returncode": True,
                "forced_exact_child": False,
            },
        )
        with self.assertRaisesRegex(
            self.module.HandoffError, "exact-child stop evidence is invalid"
        ):
            self.module.verify_schema3_mcp_session(
                failed["state"],
                malformed_receipt,
                failed["manifest"],
                manifest_sha256=failed["manifest_sha256"],
            )

    def test_failed_activation_rejects_a_second_same_session_failure_receipt(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"duplicate-activation-failure").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=0,
            forced_exact_child=False,
        )
        failed = self.module.verify_package(handoff)
        duplicated = self.module.receipt_with_event(
            failed["receipt"],
            "mcp_activation_failed",
            {
                "phase_before": "approved",
                "phase_after": "approved",
                "session_id_sha256": session_hash,
                "error_code": "DUPLICATE_FAILURE",
            },
        )
        with self.assertRaisesRegex(
            self.module.HandoffError, "differs from its receipt"
        ):
            self.module.verify_schema3_mcp_session(
                failed["state"],
                duplicated,
                failed["manifest"],
                manifest_sha256=failed["manifest_sha256"],
            )

    def test_failed_activation_rejects_a_cross_session_failure_receipt(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"bound-activation-failure").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        failed = self.module.verify_package(handoff)
        duplicated = self.module.receipt_with_event(
            failed["receipt"],
            "mcp_activation_failed",
            {
                "phase_before": "approved",
                "phase_after": "approved",
                "session_id_sha256": hashlib.sha256(
                    b"unrelated-activation-failure"
                ).hexdigest(),
                "error_code": "CROSS_SESSION_FAILURE",
            },
        )

        with self.assertRaisesRegex(
            self.module.HandoffError, "differs from its receipt"
        ):
            self.module.verify_schema3_mcp_session(
                failed["state"],
                duplicated,
                failed["manifest"],
                manifest_sha256=failed["manifest_sha256"],
            )

    def test_failed_activation_stop_reconciles_a_late_commit_error(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"activation-stop-late-commit").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        original_commit = self.module.commit_lifecycle_pair

        def commit_then_report_failure(*args, **kwargs):
            original_commit(*args, **kwargs)
            raise self.module.RuntimeStateError(
                "RUNTIME_STATE_WRITE_FAILED", "simulated late directory sync failure"
            )

        with mock.patch.object(
            self.module,
            "commit_lifecycle_pair",
            side_effect=commit_then_report_failure,
        ):
            stopped = self.module.record_mcp_activation_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="controller_exit",
                child_returncode=0,
                forced_exact_child=False,
            )
        self.assertTrue(stopped["activation_stop_receipt_recorded"])
        self.assertTrue(store.read()["activation_stop_receipt_recorded"])
        receipt = self.module.verify_package(handoff)["receipt"]
        self.assertEqual(
            1,
            len(self.module.receipt_events(receipt, "mcp_activation_stopped")),
        )

    def test_failed_activation_with_unavailable_trace_still_records_global_child_stop(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"activation-stop-missing-trace").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        diagnostic = self.load(handoff / "state.json")["mcp_protocol_trace"]
        (handoff / diagnostic["protocol_trace_file"]).unlink()
        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )
        self.assertTrue(stopped["exact_child_stop_recorded"])
        self.assertFalse(stopped["package_evidence_available"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        runtime = store.read()
        self.assertTrue(runtime["activation_child_stopped"])
        self.assertFalse(runtime["activation_stop_receipt_recorded"])
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(
            0, len(self.module.receipt_events(receipt, "mcp_activation_stopped"))
        )

    def test_failed_activation_exact_child_stop_survives_attended_recovery_to_revoked(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"activation-stop-after-recovery").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        recovered = self.module.recover_interrupted_mcp_activation(
            handoff,
            store,
            reason="user_requested",
        )
        self.assertEqual("revoked", recovered["authorization"]["status"])
        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="remote_stop",
            child_returncode=-15,
            forced_exact_child=False,
        )
        self.assertTrue(stopped["package_evidence_available"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        self.assertEqual("revoked", store.read()["status"])
        self.assertTrue(store.read()["activation_child_stopped"])

    def test_failed_global_activation_publish_still_records_exact_child_stop(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"partial-activation-publication").hexdigest()
        begun = self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        original_transition = store.transition

        def fail_only_active_transition(session, current, target, **kwargs):
            if current == "activating" and target == "active":
                raise self.module.RuntimeStateError(
                    "RUNTIME_STATE_WRITE_FAILED", "simulated global activation failure"
                )
            return original_transition(session, current, target, **kwargs)

        with mock.patch.object(
            store, "transition", side_effect=fail_only_active_transition
        ):
            with self.assertRaisesRegex(
                self.module.HandoffError, "RUNTIME_STATE_WRITE_FAILED"
            ):
                self.module.complete_mcp_activation(
                    handoff,
                    store,
                    session_id_sha256=session_hash,
                    audit_header_sha256=begun["audit_header_sha256"],
                    successful_control_plane_poll_observed=True,
                )
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            "faulted", self.module.verify_package(handoff)["state"]["mcp_session"]["status"]
        )
        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )
        self.assertTrue(stopped["exact_child_stop_recorded"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        self.assertTrue(store.read()["activation_child_stopped"])
        receipt = self.module.verify_package(handoff)["receipt"]
        self.assertEqual(
            0, len(self.module.receipt_events(receipt, "mcp_activation_stopped"))
        )

    def test_mcp_stop_reports_machine_global_activation_child_stop(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"activation-stop-command").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )

        def stop_exact_activation_child(*args, **kwargs):
            del args, kwargs
            self.module.record_mcp_activation_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="remote_stop",
                child_returncode=-15,
                forced_exact_child=False,
            )
            return True

        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "request_cooperative_stop",
                side_effect=stop_exact_activation_child,
            ),
        ):
            payload = json.loads(
                self.run_cli(
                    "mcp-stop", "--handoff-dir", str(handoff), "--json"
                ).stdout
            )
        self.assertTrue(payload["tunnel_runtime_stopped"])
        self.assertEqual("machine_global_activation", payload["stop_evidence"])
        self.assertEqual("stopped", payload["exact_tunnel_process_status"])
        self.assertFalse(payload["manual_process_review_required"])
        self.assertTrue(store.read()["activation_child_stopped"])

    def test_probe_is_secretless_sanitized_and_reports_bounded_local_setup(self) -> None:
        result = self.run_cli(
            "mcp-probe",
            "--tunnel-client",
            str(self.root / "missing-tunnel-client"),
            "--json",
            expected=2,
        )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual("mcp-probe", payload["operation"])
        self.assertEqual("human_check_required", payload["developer_mode"])
        self.assertTrue(payload["runtime_state_safe"])
        self.assertIsNone(payload["authorization"])
        self.assertFalse(payload["side_effects"]["conversation_or_repository_disclosure"])
        self.assertEqual(
            "gptpro_wrapper_only", payload["side_effects"]["disclosure_claim_scope"]
        )
        self.assertFalse(payload["side_effects"]["credential_resolution"])
        self.assertEqual(
            "may_create_owner_only_runtime_directory_and_lock_file",
            payload["side_effects"]["local_runtime_setup"],
        )
        execution = payload["side_effects"]["tunnel_client_execution"]
        self.assertTrue(execution["may_execute"])
        self.assertEqual(
            "bounded_version_and_help_capability_subprocesses", execution["purpose"]
        )
        self.assertIn("trusted", execution["trust_requirement"])
        self.assertEqual(0o700, self.runtime_root.stat().st_mode & 0o777)
        self.assertEqual(0o600, (self.runtime_root / "lock").stat().st_mode & 0o777)
        self.assertNotIn(str(self.root), result.stdout)

    def test_unsupported_platform_fails_before_runtime_or_tunnel_probe(self) -> None:
        arguments = SimpleNamespace(tunnel_client="/must/not/run")
        output = io.StringIO()
        with (
            mock.patch.object(self.module.sys, "platform", "linux"),
            mock.patch.object(self.module, "runtime_store_for") as runtime_store,
            mock.patch.object(self.module, "tunnel_client_for") as tunnel_client,
            redirect_stdout(output),
        ):
            self.assertEqual(2, self.module.command_mcp_probe(arguments))
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["platform"]["supported"])
        self.assertEqual("RUNTIME_UNSUPPORTED_PLATFORM", payload["runtime_state_error"])
        self.assertEqual("RUNTIME_UNSUPPORTED_PLATFORM", payload["tunnel_client"]["code"])
        self.assertFalse(payload["side_effects"]["tunnel_client_execution"]["may_execute"])
        runtime_store.assert_not_called()
        tunnel_client.assert_not_called()

    def test_key_bearing_entrypoints_reject_platform_and_python_before_secrets(self) -> None:
        init_arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/must/not/run",
            confirm_tunnel_client_sha256="0" * 64,
            profile_dir=None,
        )
        activate_arguments = SimpleNamespace(
            handoff_dir="/must/not/read",
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/must/not/run",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
        )
        refresh_arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/must/not/run",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_current_profile_sha256="0" * 64,
            confirm_profile_replacement=True,
            profile_dir=None,
        )
        unsupported_cases = (
            ("linux", self.module.WEB_MCP_MINIMUM_PYTHON),
            ("darwin", (99, 0)),
        )
        for mocked_platform, minimum_python in unsupported_cases:
            with self.subTest(platform=mocked_platform, minimum_python=minimum_python):
                with (
                    mock.patch.object(self.module.sys, "platform", mocked_platform),
                    mock.patch.object(
                        self.module, "WEB_MCP_MINIMUM_PYTHON", minimum_python
                    ),
                    mock.patch.object(self.module, "TunnelClient") as tunnel_constructor,
                    mock.patch.object(
                        self.module, "checked_schema3_handoff"
                    ) as package_resolver,
                    mock.patch.object(
                        self.module, "runtime_key_environment"
                    ) as secret_resolver,
                ):
                    with self.assertRaisesRegex(
                        self.module.HandoffError, "RUNTIME_UNSUPPORTED_PLATFORM"
                    ):
                        self.module.command_mcp_profile_init(init_arguments)
                    with self.assertRaisesRegex(
                        self.module.HandoffError, "RUNTIME_UNSUPPORTED_PLATFORM"
                    ):
                        self.module.command_mcp_profile_refresh(refresh_arguments)
                    with self.assertRaisesRegex(
                        self.module.HandoffError, "RUNTIME_UNSUPPORTED_PLATFORM"
                    ):
                        self.module.command_mcp_activate(activate_arguments)
                tunnel_constructor.assert_not_called()
                package_resolver.assert_not_called()
                secret_resolver.assert_not_called()

    def test_profile_check_is_secretless_and_machine_readable(self) -> None:
        arguments = SimpleNamespace(tunnel_profile=TUNNEL_PROFILE, profile_dir=None)
        inspection = SimpleNamespace(
            ready=False,
            code="MCP_INTERPRETER_PATH_DRIFT",
            refresh_required=True,
            safe_to_refresh=True,
            reinit_required=False,
            profile_sha256="1" * 64,
            profile_dir_sha256="2" * 64,
            observed_mcp_command_sha256="3" * 64,
            expected_mcp_command_sha256="4" * 64,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                self.module, "inspect_tunnel_profile", return_value=inspection
            ) as inspect,
            mock.patch.object(self.module, "runtime_key_environment") as secret_resolver,
            mock.patch.object(self.module, "TunnelClient") as tunnel_client,
            redirect_stdout(output),
        ):
            self.assertEqual(2, self.module.command_mcp_profile_check(arguments))
        payload = json.loads(output.getvalue())
        self.assertEqual("MCP_INTERPRETER_PATH_DRIFT", payload["code"])
        self.assertTrue(payload["refresh_required"])
        self.assertTrue(payload["safe_to_refresh"])
        self.assertFalse(payload["reinit_required"])
        self.assertFalse(payload["credential_resolution"])
        self.assertFalse(payload["tunnel_client_execution"])
        inspect.assert_called_once()
        secret_resolver.assert_not_called()
        tunnel_client.assert_not_called()

    def test_profile_check_reports_missing_profile_without_secret_access(self) -> None:
        arguments = SimpleNamespace(tunnel_profile="missing-profile", profile_dir=None)
        output = io.StringIO()
        with (
            mock.patch.object(
                self.module,
                "inspect_tunnel_profile",
                side_effect=self.module.TunnelClientError(
                    "TUNNEL_PROFILE_NOT_FOUND",
                    "The requested Tunnel profile does not exist.",
                ),
            ),
            mock.patch.object(self.module, "runtime_key_environment") as secret_resolver,
            mock.patch.object(self.module, "TunnelClient") as tunnel_client,
            redirect_stdout(output),
        ):
            self.assertEqual(2, self.module.command_mcp_profile_check(arguments))
        payload = json.loads(output.getvalue())
        self.assertEqual("TUNNEL_PROFILE_NOT_FOUND", payload["code"])
        self.assertFalse(payload["refresh_required"])
        self.assertFalse(payload["safe_to_refresh"])
        self.assertTrue(payload["reinit_required"])
        self.assertFalse(payload["credential_resolution"])
        self.assertFalse(payload["tunnel_client_execution"])
        self.assertNotIn("/", output.getvalue())
        secret_resolver.assert_not_called()
        tunnel_client.assert_not_called()

    def test_profile_refresh_blocks_live_controller_before_profile_mutation(self) -> None:
        arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_current_profile_sha256="1" * 64,
            confirm_profile_replacement=True,
            profile_dir=None,
        )
        client = mock.Mock()
        capabilities = SimpleNamespace(supported=True, binary_sha256="0" * 64)
        transaction = mock.Mock()
        transaction.read.return_value = {
            "status": "active",
            "session_id_sha256": "2" * 64,
        }
        locked = mock.MagicMock()
        locked.__enter__.return_value = transaction
        store = mock.Mock()
        lease_root = self.root / "active-profile-refresh"
        lease_root.mkdir(mode=0o700)
        store.root = lease_root
        store.locked.return_value = locked
        with (
            mock.patch.object(
                self.module,
                "confirmed_key_bearing_tunnel_client",
                return_value=(client, capabilities),
            ),
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            self.assertRaisesRegex(self.module.HandoffError, "PROFILE_REFRESH_BLOCKED"),
        ):
            self.module.command_mcp_profile_refresh(arguments)
        client.refresh_profile_attended.assert_not_called()

    def test_profile_refresh_rejects_terminal_missing_or_unsafe_lease(self) -> None:
        arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_current_profile_sha256="1" * 64,
            confirm_profile_replacement=True,
            profile_dir=None,
        )
        client = mock.Mock()
        capabilities = SimpleNamespace(supported=True, binary_sha256="0" * 64)
        session_hash = "2" * 64
        for status, unsafe in (("revoked", False), ("expired", True)):
            with self.subTest(status=status, unsafe=unsafe):
                lease_root = self.root / f"lease-{status}"
                lease_root.mkdir(mode=0o700)
                if unsafe:
                    lease_path = lease_root / f"controller-{session_hash}.lock"
                    lease_path.write_bytes(b"")
                    lease_path.chmod(0o644)
                transaction = mock.Mock()
                transaction.read.return_value = {
                    "status": status,
                    "session_id_sha256": session_hash,
                }
                locked = mock.MagicMock()
                locked.__enter__.return_value = transaction
                store = mock.Mock()
                store.root = lease_root
                store.locked.return_value = locked
                with (
                    mock.patch.object(
                        self.module,
                        "confirmed_key_bearing_tunnel_client",
                        return_value=(client, capabilities),
                    ),
                    mock.patch.object(
                        self.module, "runtime_store_for", return_value=store
                    ),
                    self.assertRaisesRegex(
                        self.module.HandoffError,
                        "PROFILE_REFRESH_CONTROLLER_UNRESOLVED",
                    ),
                ):
                    self.module.command_mcp_profile_refresh(arguments)
                client.refresh_profile_attended.assert_not_called()

    def test_profile_refresh_holds_existing_terminal_lease_until_complete(self) -> None:
        arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_current_profile_sha256="1" * 64,
            confirm_profile_replacement=True,
            profile_dir=None,
        )
        session_hash = "2" * 64
        lease_root = self.root / "lease-held"
        lease_root.mkdir(mode=0o700)
        lease_path = lease_root / f"controller-{session_hash}.lock"
        lease_path.write_bytes(b"")
        lease_path.chmod(0o600)
        transaction = mock.Mock()
        transaction.read.return_value = {
            "status": "revoked",
            "session_id_sha256": session_hash,
        }
        locked = mock.MagicMock()
        locked.__enter__.return_value = transaction
        store = mock.Mock()
        store.root = lease_root
        store.locked.return_value = locked
        client = mock.Mock()
        capabilities = SimpleNamespace(supported=True, binary_sha256="0" * 64)

        def refresh_while_lease_is_held(*args: object, **kwargs: object) -> object:
            del args, kwargs
            self.assertTrue(locked.__exit__.called)
            with self.assertRaises(self.module.RuntimeStateError) as raised:
                self.module.ControllerLease(store, session_hash).acquire_existing()
            self.assertEqual("SESSION_CONFLICT", raised.exception.code)
            with self.assertRaises(self.module.RuntimeStateError) as global_lease:
                self.module.ProfileControllerLease(store.root).acquire()
            self.assertEqual("PROFILE_OPERATION_CONFLICT", global_lease.exception.code)
            return SimpleNamespace(
                ok=True,
                previous_profile_sha256="1" * 64,
                profile_sha256="3" * 64,
                profile_dir_sha256="4" * 64,
                mcp_command_sha256="5" * 64,
                staging_cleanup_complete=True,
            )

        client.refresh_profile_attended.side_effect = refresh_while_lease_is_held
        output = io.StringIO()
        with (
            mock.patch.object(
                self.module,
                "confirmed_key_bearing_tunnel_client",
                return_value=(client, capabilities),
            ),
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            redirect_stdout(output),
        ):
            self.assertEqual(0, self.module.command_mcp_profile_refresh(arguments))
        self.assertTrue(json.loads(output.getvalue())["staging_cleanup_complete"])
        released = self.module.ControllerLease(store, session_hash).acquire_existing()
        released.close()

    def test_profile_global_gate_blocks_refresh_before_client_or_state_probe(self) -> None:
        arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:MUST_NOT_BE_READ",
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/must/not/run",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_current_profile_sha256="1" * 64,
            confirm_profile_replacement=True,
            profile_dir=None,
        )
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        held = self.module.ProfileControllerLease(store.root).acquire()
        client_probe = mock.Mock()
        try:
            with (
                mock.patch.object(self.module, "runtime_store_for", return_value=store),
                mock.patch.object(
                    self.module,
                    "confirmed_key_bearing_tunnel_client",
                    client_probe,
                ),
                self.assertRaisesRegex(
                    self.module.HandoffError, "PROFILE_OPERATION_CONFLICT"
                ),
            ):
                self.module.command_mcp_profile_refresh(arguments)
        finally:
            held.close()
        client_probe.assert_not_called()

    def test_profile_global_gate_blocks_activation_before_profile_or_key_access(self) -> None:
        arguments = SimpleNamespace(
            handoff_dir="/approved/handoff",
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
        )
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        held = self.module.ProfileControllerLease(store.root).acquire()
        inspect = mock.Mock()
        secret_resolver = mock.Mock()
        client = mock.Mock()
        capabilities = SimpleNamespace(
            supported=True,
            health_require_control_plane_poll=True,
        )
        try:
            with (
                mock.patch.object(
                    self.module,
                    "checked_schema3_handoff",
                    return_value=(Path("/approved/handoff"), {"manifest": {}}),
                ),
                mock.patch.object(
                    self.module,
                    "confirmed_key_bearing_tunnel_client",
                    return_value=(client, capabilities),
                ),
                mock.patch.object(self.module, "runtime_store_for", return_value=store),
                mock.patch.object(self.module, "inspect_tunnel_profile", inspect),
                mock.patch.object(
                    self.module, "runtime_key_environment", secret_resolver
                ),
                self.assertRaisesRegex(
                    self.module.HandoffError, "PROFILE_OPERATION_CONFLICT"
                ),
            ):
                self.module.command_mcp_activate(arguments)
        finally:
            held.close()
        inspect.assert_not_called()
        secret_resolver.assert_not_called()
        client.doctor.assert_not_called()

    def test_mcp_activate_detects_profile_drift_before_runtime_key_resolution(self) -> None:
        arguments = SimpleNamespace(
            handoff_dir="/approved/handoff",
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
        )
        client = mock.Mock()
        capabilities = SimpleNamespace(
            supported=True,
            health_require_control_plane_poll=True,
        )
        inspection = SimpleNamespace(
            ready=False,
            code="MCP_INTERPRETER_PATH_DRIFT",
        )
        with (
            mock.patch.object(
                self.module,
                "checked_schema3_handoff",
                return_value=(Path("/approved/handoff"), {"manifest": {}}),
            ),
            mock.patch.object(
                self.module,
                "confirmed_key_bearing_tunnel_client",
                return_value=(client, capabilities),
            ),
            mock.patch.object(
                self.module, "inspect_tunnel_profile", return_value=inspection
            ),
            mock.patch.object(self.module, "runtime_key_environment") as secret_resolver,
            self.assertRaisesRegex(
                self.module.HandoffError,
                "MCP_INTERPRETER_PATH_DRIFT: Run mcp-profile-check and complete the reported attended profile action before activation",
            ),
        ):
            self.module.command_mcp_activate(arguments)
        secret_resolver.assert_not_called()
        client.doctor.assert_not_called()

    def test_request_correlation_rejects_unpinned_tunnel_before_key_resolution(self) -> None:
        arguments = SimpleNamespace(
            handoff_dir="/approved/handoff",
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:MUST_NOT_BE_READ",
            tunnel_client="/trusted/tunnel-client",
            confirm_tunnel_client_sha256="0" * 64,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
            diagnose_request_correlation=True,
        )
        client = mock.Mock()
        capabilities = SimpleNamespace(
            supported=True,
            health_require_control_plane_poll=True,
            request_correlation_contract_supported=False,
        )
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        with (
            mock.patch.object(
                self.module,
                "checked_schema3_handoff",
                return_value=(Path("/approved/handoff"), {"manifest": {}}),
            ),
            mock.patch.object(
                self.module,
                "confirmed_key_bearing_tunnel_client",
                return_value=(client, capabilities),
            ),
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(self.module, "inspect_tunnel_profile") as inspect,
            mock.patch.object(self.module, "runtime_key_environment") as secret_resolver,
            self.assertRaisesRegex(
                self.module.HandoffError,
                "REQUEST_CORRELATION_UNSUPPORTED_VERSION",
            ),
        ):
            self.module.command_mcp_activate(arguments)
        inspect.assert_not_called()
        secret_resolver.assert_not_called()
        client.doctor.assert_not_called()

    def test_lifecycle_cli_has_no_runtime_root_override(self) -> None:
        parser = self.module.build_parser()
        subcommands = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ).choices
        for command in (
            "mcp-probe",
            "mcp-profile-check",
            "mcp-profile-refresh",
            "mcp-activate",
            "mcp-status",
            "mcp-stop",
            "mcp-recover",
            "mark-submitted",
        ):
            with self.subTest(command=command):
                options = {
                    option
                    for action in subcommands[command]._actions
                    for option in action.option_strings
                }
                self.assertNotIn("--runtime-dir", options)

        attempted = self.root / "alternate-runtime"
        rejected = self.run_cli(
            "mcp-probe",
            "--runtime-dir",
            str(attempted),
            expected=2,
        )
        self.assertIn("unrecognized arguments", rejected.stderr)
        self.assertFalse(attempted.exists())

    def test_mcp_activate_default_ready_timeout_exceeds_one_long_poll(self) -> None:
        parser = self.module.build_parser()
        arguments = parser.parse_args(
            [
                "mcp-activate",
                "--handoff-dir",
                "/tmp/handoff",
                "--tunnel-profile",
                TUNNEL_PROFILE,
                "--runtime-api-key-ref",
                "env:CONTROL_PLANE_API_KEY",
                "--tunnel-client",
                "/tmp/tunnel-client",
                "--confirm-tunnel-client-sha256",
                "0" * 64,
            ]
        )
        self.assertEqual(60, arguments.ready_timeout)
        self.assertFalse(arguments.diagnose_request_correlation)
        diagnostic_arguments = parser.parse_args(
            [
                "mcp-activate",
                "--handoff-dir",
                "/tmp/handoff",
                "--tunnel-profile",
                TUNNEL_PROFILE,
                "--runtime-api-key-ref",
                "env:CONTROL_PLANE_API_KEY",
                "--tunnel-client",
                "/tmp/tunnel-client",
                "--confirm-tunnel-client-sha256",
                "0" * 64,
                "--diagnose-request-correlation",
            ]
        )
        self.assertTrue(diagnostic_arguments.diagnose_request_correlation)

    def test_path_discovered_probe_never_receives_runtime_key_or_unrelated_secrets(self) -> None:
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        environment_log = self.root / "probe-environment.jsonl"
        tunnel_client = fake_bin / "tunnel-client"
        tunnel_client.write_text(
            "\n".join(
                (
                    f"#!{sys.executable}",
                    "import json, os",
                    "from pathlib import Path",
                    f"path = Path({str(environment_log)!r})",
                    "with path.open('a', encoding='utf-8') as handle:",
                    "    handle.write(json.dumps(dict(os.environ), sort_keys=True) + '\\n')",
                    "print('fake tunnel-client probe')",
                    "",
                )
            ),
            encoding="utf-8",
        )
        tunnel_client.chmod(0o700)
        previous_environment = self.env
        self.env = {
            **self.env,
            "PATH": str(fake_bin),
            "CONTROL_PLANE_API_KEY": "sk-" + "P" * 24,
            "UNRELATED_SECRET": "do-not-forward",
            "UNRELATED_SECRET_SHAPED": "github_pat_" + "Q" * 24,
        }
        try:
            result = self.run_cli("mcp-probe", "--json", expected=2)
        finally:
            self.env = previous_environment
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(
            "deferred_to_explicitly_confirmed_key_bearing_command", payload["profile_check"]
        )
        environments = [
            json.loads(line)
            for line in environment_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(environments)
        for environment in environments:
            self.assertNotIn("CONTROL_PLANE_API_KEY", environment)
            self.assertNotIn("UNRELATED_SECRET", environment)
            self.assertNotIn("UNRELATED_SECRET_SHAPED", environment)

    def test_activation_binds_package_receipt_audit_and_single_use(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, completed = self.activate(handoff)
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")

        self.assertEqual("approved", state["phase"])
        self.assertEqual("active", state["mcp_session"]["status"])
        self.assertEqual(session_hash, state["mcp_session"]["session_id_sha256"])
        self.assertEqual("active", store.read()["status"])
        self.assertEqual(session_hash, completed["authorization"]["session_id_sha256"])
        activation = [event for event in receipt["events"] if event["type"] == "mcp_activated"]
        self.assertEqual(1, len(activation))
        self.assertEqual("approved", activation[0]["data"]["phase_before"])
        self.assertEqual("approved", activation[0]["data"]["phase_after"])
        expected_runtime_identity = {
            "tunnel_profile_sha256": TUNNEL_PROFILE_HASH,
            "tunnel_client_binary_sha256": TUNNEL_BINARY_HASH,
            "mcp_runtime_tree_sha256": self.module.mcp_runtime_tree_sha256(),
        }
        for key, expected in expected_runtime_identity.items():
            self.assertEqual(expected, store.read()[key])
            self.assertEqual(expected, state["mcp_session"][key])
            self.assertEqual(expected, activation[0]["data"][key])
        trace_header = state["mcp_session"]["protocol_trace_header_sha256"]
        self.assertEqual(trace_header, store.read()["protocol_trace_header_sha256"])
        self.assertEqual(trace_header, activation[0]["data"]["protocol_trace_header_sha256"])
        self.assertEqual("mcp-protocol-trace.jsonl", activation[0]["data"]["protocol_trace_file"])
        for source in (store.read(), state["mcp_session"], activation[0]["data"]):
            self.assertEqual(2, source["audit_schema_version"])
            self.assertEqual(
                "complete_model_visible_result_v1",
                source["disclosure_accounting"],
            )
        trace_path = handoff / "mcp-protocol-trace.jsonl"
        self.assertEqual(0o600, trace_path.stat().st_mode & 0o777)
        trace_status = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertEqual(trace_header, trace_status["protocol_trace"]["header_sha256"])
        self.assertFalse(trace_status["protocol_trace"]["closed"])
        self.assertFalse(completed["audit"]["footer"])
        self.assertEqual(2, completed["audit"]["audit_schema_version"])
        self.assertEqual(
            "complete_model_visible_result_v1",
            completed["audit"]["disclosure_accounting"],
        )
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_actual_legacy_schema3_session_remains_closable_and_verifiable(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)

        audit_path = handoff / "mcp-audit.jsonl"
        records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(1, len(records))
        header = records[0]
        header["audit_schema_version"] = 1
        header.pop("accounting_mode")
        header.pop("event_sha256")
        header["event_sha256"] = self.module.sha256_bytes(
            self.module.canonical_json_bytes(header)
        )
        legacy_header = header["event_sha256"]
        audit_path.write_text(
            json.dumps(
                header,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        audit_path.chmod(0o600)

        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        state["mcp_session"].pop("audit_schema_version")
        state["mcp_session"].pop("disclosure_accounting")
        state["mcp_session"]["audit_header_sha256"] = legacy_header
        for event in receipt["events"]:
            if event["type"] == "mcp_activated":
                event["data"].pop("audit_schema_version")
                event["data"].pop("disclosure_accounting")
                event["data"]["audit_header_sha256"] = legacy_header

        previous = None
        for sequence, event in enumerate(receipt["events"], start=1):
            event["sequence"] = sequence
            event["previous_event_hash"] = previous
            event["event_hash"] = self.module.event_hash(event)
            previous = event["event_hash"]
        (handoff / "state.json").write_text(
            json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (handoff / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        with store.locked() as transaction:
            runtime = transaction.read()
            runtime.pop("audit_schema_version")
            runtime.pop("disclosure_accounting")
            runtime["audit_header_sha256"] = legacy_header
            runtime["revision"] += 1
            runtime["updated_at"] = self.module.utc_now()
            transaction.write(runtime)

        verified = self.module.verify_package(handoff)
        self.assertEqual("active", verified["state"]["mcp_session"]["status"])
        status_output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "controller_lease_is_live",
                return_value=True,
            ),
            redirect_stdout(status_output),
        ):
            self.module.command_mcp_status(SimpleNamespace(handoff_dir=str(handoff)))
        status_payload = json.loads(status_output.getvalue())
        self.assertFalse(status_payload["effective_authorized"])
        self.assertEqual(1, status_payload["audit"]["audit_schema_version"])
        stopped = self.module.stop_mcp_authorization(handoff, store)
        self.assertEqual("revoked", stopped["authorization"]["status"])
        self.assertEqual(1, stopped["audit"]["audit_schema_version"])
        self.assertEqual(
            "legacy_tool_body_estimate",
            stopped["audit"]["disclosure_accounting"],
        )

        verified = self.module.verify_package(handoff)
        self.assertEqual("revoked", verified["state"]["mcp_session"]["status"])
        self.assertNotIn(
            "disclosure_accounting", verified["state"]["mcp_session"]
        )
        self.assertEqual(legacy_header, verified["state"]["mcp_session"]["audit_header_sha256"])
        audit_status = self.module.mcp_audit_status(verified)
        self.assertEqual(1, audit_status["audit_schema_version"])
        self.assertEqual("legacy_tool_body_estimate", audit_status["disclosure_accounting"])
        self.assertTrue(audit_status["footer"])
        self.assertEqual(session_hash, store.read()["session_id_sha256"])

    def test_current_audit_cannot_be_downgraded_by_stripping_receipt_fields(self) -> None:
        handoff = self.prepare_and_approve()
        self.activate(handoff)
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        state["mcp_session"].pop("audit_schema_version")
        state["mcp_session"].pop("disclosure_accounting")
        for event in receipt["events"]:
            if event["type"] == "mcp_activated":
                event["data"].pop("audit_schema_version")
                event["data"].pop("disclosure_accounting")
        previous = None
        for sequence, event in enumerate(receipt["events"], start=1):
            event["sequence"] = sequence
            event["previous_event_hash"] = previous
            event["event_hash"] = self.module.event_hash(event)
            previous = event["event_hash"]
        (handoff / "state.json").write_text(
            json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (handoff / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            self.module.HandoffError,
            "compatibility requires an actual legacy",
        ):
            self.module.verify_package(handoff)

    def test_concurrent_normal_stop_records_one_receipt_and_one_global_binding(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store)
        barrier = threading.Barrier(3)
        results: list[dict] = []
        errors: list[BaseException] = []

        def record() -> None:
            barrier.wait()
            try:
                results.append(
                    self.module.record_mcp_runtime_stopped_fail_closed(
                        handoff,
                        store,
                        session_id_sha256=session_hash,
                        reason="remote_stop",
                        child_returncode=-15,
                        forced_exact_child=False,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())

        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertTrue(all(item["runtime_stop_receipt_recorded"] for item in results))
        receipt = self.module.verify_package(handoff)["receipt"]
        self.assertEqual(1, len(self.module.receipt_events(receipt, "mcp_stopped")))
        self.assertTrue(store.read()["runtime_stop_receipt_recorded"])

    def test_concurrent_failed_activation_stop_records_one_receipt_and_binding(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"concurrent-activation-stop").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        barrier = threading.Barrier(3)
        results: list[dict] = []
        errors: list[BaseException] = []

        def record() -> None:
            barrier.wait()
            try:
                results.append(
                    self.module.record_mcp_activation_stopped_fail_closed(
                        handoff,
                        store,
                        session_id_sha256=session_hash,
                        reason="controller_exit",
                        child_returncode=-15,
                        forced_exact_child=False,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())

        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertTrue(
            all(item["activation_stop_receipt_recorded"] for item in results)
        )
        receipt = self.module.verify_package(handoff)["receipt"]
        self.assertEqual(
            1, len(self.module.receipt_events(receipt, "mcp_activation_stopped"))
        )
        self.assertTrue(store.read()["activation_stop_receipt_recorded"])

        verified = self.module.verify_package(handoff)
        with self.assertRaisesRegex(self.module.HandoffError, "only once"):
            self.module.mcp_activation_preflight(
                verified,
                tunnel_profile=TUNNEL_PROFILE,
                observed_tunnel_binding_sha256=verified["manifest"]["connector"][
                    "tunnel_id_binding_sha256"
                ],
                observed_tunnel_profile_sha256=TUNNEL_PROFILE_HASH,
                observed_tunnel_client_binary_sha256=TUNNEL_BINARY_HASH,
                observed_mcp_target_sha256=MCP_TARGET_HASH,
                observed_mcp_runtime_tree_sha256=self.module.mcp_runtime_tree_sha256(),
                profile_binding_verification="automatic-doctor-json",
                workspace_binding_confirmed=True,
            )

    def test_preflight_rejects_alias_binding_and_workspace_drift(self) -> None:
        handoff = self.prepare_and_approve()
        verified = self.module.verify_package(handoff)
        binding = verified["manifest"]["connector"]["tunnel_id_binding_sha256"]
        cases = (
            ({"tunnel_profile": "other"}, "profile alias"),
            ({"observed_tunnel_binding_sha256": "0" * 64}, "package binding"),
            ({"profile_binding_verification": "attended"}, "official doctor JSON"),
            ({"observed_tunnel_profile_sha256": "invalid"}, "profile hash"),
            ({"observed_tunnel_client_binary_sha256": "invalid"}, "client binary hash"),
            ({"observed_mcp_target_sha256": "invalid"}, "exact MCP target"),
            ({"observed_mcp_runtime_tree_sha256": "0" * 64}, "installed Skill runtime"),
            ({"workspace_binding_confirmed": False}, "explicit confirmation"),
        )
        baseline = {
            "tunnel_profile": TUNNEL_PROFILE,
            "observed_tunnel_binding_sha256": binding,
            "observed_tunnel_profile_sha256": TUNNEL_PROFILE_HASH,
            "observed_tunnel_client_binary_sha256": TUNNEL_BINARY_HASH,
            "observed_mcp_target_sha256": MCP_TARGET_HASH,
            "observed_mcp_runtime_tree_sha256": self.module.mcp_runtime_tree_sha256(),
            "profile_binding_verification": "automatic-doctor-json",
            "workspace_binding_confirmed": True,
        }
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                arguments = {**baseline, **overrides}
                with self.assertRaisesRegex(self.module.HandoffError, expected):
                    self.module.mcp_activation_preflight(verified, **arguments)

    def test_runtime_identity_wrapper_fails_before_child_spawn_on_any_drift(self) -> None:
        class Delegate:
            binary_sha256 = TUNNEL_BINARY_HASH

            def __init__(self) -> None:
                self.spawned = False

            def spawn_run(self, *args, **kwargs):
                del args, kwargs
                self.spawned = True
                return object()

            def health(self, *args, **kwargs):
                del args, kwargs
                return None

        delegate = Delegate()
        runtime_hash = self.module.mcp_runtime_tree_sha256()
        wrapped = self.module.RuntimeIdentityBoundTunnelClient(
            delegate,
            tunnel_client_binary_sha256=TUNNEL_BINARY_HASH,
            mcp_target_sha256=MCP_TARGET_HASH,
            mcp_runtime_tree_sha256_value=runtime_hash,
        )
        with mock.patch.object(
            self.module, "mcp_runtime_tree_sha256", return_value="0" * 64
        ):
            with self.assertRaises(self.module.TunnelClientError) as raised:
                wrapped.spawn_run("runtime-test")
        self.assertEqual("MCP_RUNTIME_IDENTITY_CHANGED", raised.exception.code)
        self.assertFalse(delegate.spawned)

        delegate.binary_sha256 = "1" * 64
        with self.assertRaises(self.module.TunnelClientError) as raised:
            wrapped.spawn_run("runtime-test")
        self.assertEqual("TUNNEL_CLIENT_IDENTITY_CHANGED", raised.exception.code)
        self.assertFalse(delegate.spawned)

        delegate.binary_sha256 = TUNNEL_BINARY_HASH
        with mock.patch.object(
            self.module, "bundled_mcp_target_sha256", return_value="3" * 64
        ):
            with self.assertRaises(self.module.TunnelClientError) as raised:
                wrapped.spawn_run("runtime-test")
        self.assertEqual("MCP_RUNTIME_IDENTITY_CHANGED", raised.exception.code)
        self.assertFalse(delegate.spawned)

        with mock.patch.object(
            self.module, "bundled_mcp_target_sha256", return_value=MCP_TARGET_HASH
        ):
            wrapped.spawn_run("runtime-test")
        self.assertTrue(delegate.spawned)

    def test_runtime_identity_hashes_are_immutable_and_cross_bound(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        with self.assertRaises(self.module.RuntimeStateError) as raised:
            store.transition(
                session_hash,
                "active",
                "revoking",
                updates={"tunnel_client_binary_sha256": "2" * 64},
            )
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)
        self.assertEqual("active", store.read()["status"])

        runtime_state = store.read()
        runtime_state["tunnel_profile_sha256"] = "3" * 64
        store.active_path.write_text(
            json.dumps(runtime_state, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        verified = self.module.verify_package(handoff)
        with self.assertRaisesRegex(self.module.HandoffError, "does not match"):
            self.module.assert_mcp_runtime_binding(
                verified,
                store.read(),
                session_id_sha256=session_hash,
                expected_statuses={"active"},
            )

        runtime_state = store.read()
        runtime_state["tunnel_profile_sha256"] = TUNNEL_PROFILE_HASH
        runtime_state["protocol_trace_header_sha256"] = "5" * 64
        store.active_path.write_text(
            json.dumps(runtime_state, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(self.module.HandoffError, "does not match"):
            self.module.assert_mcp_runtime_binding(
                verified,
                store.read(),
                session_id_sha256=session_hash,
                expected_statuses={"active"},
            )

        package_state = self.load(handoff / "state.json")
        package_state["mcp_session"]["mcp_runtime_tree_sha256"] = "4" * 64
        self.module.write_json(handoff / "state.json", package_state)
        with self.assertRaisesRegex(self.module.HandoffError, "activation receipt differs"):
            self.module.verify_package(handoff)

    def test_key_bearing_commands_require_explicit_probe_confirmed_binary_before_secrets(self) -> None:
        confirmation = "0" * 64
        init_arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:SHOULD_NOT_BE_READ",
            runtime_api_key_ref="env:SHOULD_NOT_BE_READ",
            tunnel_client=None,
            confirm_tunnel_client_sha256=confirmation,
            profile_dir=None,
        )
        with mock.patch.object(self.module, "TunnelClient") as constructor:
            with self.assertRaisesRegex(self.module.HandoffError, "explicit absolute"):
                self.module.command_mcp_profile_init(init_arguments)
        constructor.assert_not_called()

        init_arguments.tunnel_client = "/explicit/fake-tunnel-client"
        init_fake_client = mock.Mock()
        init_fake_client.probe.return_value = SimpleNamespace(
            binary_sha256="1" * 64,
            supported=True,
        )
        with mock.patch.object(self.module, "TunnelClient", return_value=init_fake_client):
            with self.assertRaisesRegex(self.module.HandoffError, "does not match"):
                self.module.command_mcp_profile_init(init_arguments)
        init_fake_client.init_profile_attended.assert_not_called()

        handoff = self.prepare_and_approve()
        fake_client = mock.Mock()
        fake_client.probe.return_value = SimpleNamespace(
            binary_sha256="1" * 64,
            supported=True,
            health_require_control_plane_poll=True,
        )
        activate_arguments = SimpleNamespace(
            handoff_dir=str(handoff),
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:SHOULD_NOT_BE_READ",
            tunnel_client="/explicit/fake-tunnel-client",
            confirm_tunnel_client_sha256=confirmation,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
        )
        with (
            mock.patch.object(self.module, "TunnelClient", return_value=fake_client),
            mock.patch.object(self.module, "runtime_key_environment") as secret_resolver,
        ):
            with self.assertRaisesRegex(self.module.HandoffError, "does not match"):
                self.module.command_mcp_activate(activate_arguments)
        secret_resolver.assert_not_called()
        fake_client.doctor.assert_not_called()

    def test_attended_profile_init_runs_only_after_exact_binary_confirmation(self) -> None:
        fake_client = mock.Mock()
        fake_client.probe.return_value = SimpleNamespace(
            binary_sha256=TUNNEL_BINARY_HASH,
            supported=True,
        )
        initialized = SimpleNamespace(
            ok=True,
            code=None,
            profile_sha256=TUNNEL_PROFILE_HASH,
            profile_dir_sha256=None,
            mcp_command_sha256=MCP_TARGET_HASH,
        )
        store = self.module.RuntimeStateStore(root=self.runtime_root)

        def init_while_profile_gate_is_held(*args: object, **kwargs: object) -> object:
            del args, kwargs
            with self.assertRaises(self.module.RuntimeStateError) as conflict:
                self.module.ProfileControllerLease(store.root).acquire()
            self.assertEqual("PROFILE_OPERATION_CONFLICT", conflict.exception.code)
            return initialized

        fake_client.init_profile_attended.side_effect = init_while_profile_gate_is_held
        arguments = SimpleNamespace(
            tunnel_profile=TUNNEL_PROFILE,
            tunnel_id_ref="env:ATTENDED_TUNNEL_ID",
            runtime_api_key_ref="env:ATTENDED_RUNTIME_KEY",
            tunnel_client="/explicit/fake-tunnel-client",
            confirm_tunnel_client_sha256=TUNNEL_BINARY_HASH,
            profile_dir=None,
        )
        output = io.StringIO()
        with (
            mock.patch.object(self.module, "TunnelClient", return_value=fake_client),
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            redirect_stdout(output),
        ):
            self.assertEqual(0, self.module.command_mcp_profile_init(arguments))
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(TUNNEL_BINARY_HASH, payload["tunnel_client_binary_sha256"])
        self.assertEqual(TUNNEL_PROFILE_HASH, payload["tunnel_profile_sha256"])
        fake_client.init_profile_attended.assert_called_once()
        call = fake_client.init_profile_attended.call_args
        self.assertEqual("env:ATTENDED_TUNNEL_ID", call.kwargs["tunnel_id_reference"])
        self.assertEqual("env:ATTENDED_RUNTIME_KEY", call.kwargs["control_plane_api_key_reference"])
        self.assertNotIn("ATTENDED_RUNTIME_KEY", output.getvalue())

    def test_mark_submitted_requires_exact_live_global_authorization(self) -> None:
        handoff = self.prepare_and_approve()
        manifest = self.load(handoff / "manifest.json")
        common = [
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "mcp-read",
            "--observed-delivery-channel",
            "browser",
            "--observed-app-name",
            APP_NAME,
            "--observed-workspace-label",
            WORKSPACE_LABEL,
            "--confirm-sent",
        ]
        rejected = self.run_cli(*common, expected=2)
        self.assertIn("active package-specific MCP authorization", rejected.stderr)
        self.assertEqual("approved", self.load(handoff / "state.json")["phase"])

        store, session_hash, _ = self.activate(handoff)
        orphaned = self.run_cli(*common, expected=2)
        self.assertIn("CONTROLLER_ORPHANED", orphaned.stderr)
        status = json.loads(
            self.run_cli(
                "mcp-status",
                "--handoff-dir",
                str(handoff),
            ).stdout
        )
        self.assertTrue(status["orphaned"])
        self.assertFalse(status["effective_authorized"])
        self.assertEqual("orphaned", status["controller"]["status"])
        self.assertIn("run_mcp_recover_for_exact_handoff", status["recovery_actions"])

        with self.module.ControllerLease(store, session_hash):
            self.run_cli(*common)
        self.assertEqual("submitted", self.load(handoff / "state.json")["phase"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_stop_is_revoke_first_and_stopped_receipt_is_idempotent(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        observed_statuses: list[str] = []
        original = self.module.AuditLog.append_footer

        def observing_footer(audit_log, reason):
            observed_statuses.append(store.read()["status"])
            return original(audit_log, reason)

        with mock.patch.object(self.module.AuditLog, "append_footer", observing_footer):
            stopped = self.module.stop_mcp_authorization(handoff, store)
        self.assertEqual(["revoking"], observed_statuses)
        self.assertEqual("revoked", store.read()["status"])
        self.assertTrue(stopped["audit"]["footer"])
        self.assertEqual("approved", self.load(handoff / "state.json")["phase"])

        trace = self.close_protocol_trace(handoff)
        self.assertTrue(trace.closed)
        runtime_stop = self.module.record_mcp_runtime_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="user_requested",
            child_returncode=0,
            forced_exact_child=False,
        )
        repeated_stop = self.module.record_mcp_runtime_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="user_requested",
            child_returncode=0,
            forced_exact_child=False,
        )
        self.assertTrue(runtime_stop["exact_child_stop_recorded"])
        self.assertTrue(runtime_stop["runtime_stop_receipt_recorded"])
        self.assertTrue(repeated_stop["runtime_stop_receipt_recorded"])
        runtime_state = store.read()
        self.assertTrue(runtime_state["runtime_child_stopped"])
        self.assertTrue(runtime_state["runtime_stop_receipt_recorded"])
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        self.assertTrue(state["mcp_session"]["tunnel_runtime_stopped"])
        self.assertTrue(state["mcp_session"]["protocol_trace_valid"])
        self.assertEqual(trace.head_sha256, state["mcp_session"]["protocol_trace_head_sha256"])
        self.assertTrue(state["mcp_session"]["protocol_trace_closed"])
        self.assertEqual(1, sum(event["type"] == "mcp_stopped" for event in receipt["events"]))
        self.run_cli("verify", "--handoff-dir", str(handoff))
        verified_audit = json.loads(
            self.run_cli("mcp-verify-audit", "--handoff-dir", str(handoff)).stdout
        )
        self.assertTrue(verified_audit["audit"]["valid"])
        self.assertEqual(2, verified_audit["audit"]["audit_schema_version"])
        self.assertEqual(
            "complete_model_visible_result_v1",
            verified_audit["audit"]["disclosure_accounting"],
        )
        diagnostic = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )["protocol_trace"]
        self.assertEqual(
            "runtime_stopped_stdio_eof_observed",
            diagnostic["terminal_evidence"]["status"],
        )
        self.assertTrue(diagnostic["terminal_evidence"]["runtime_stop_observed"])
        self.assertTrue(diagnostic["terminal_evidence"]["protocol_stream_closed"])
        self.assertTrue(diagnostic["terminal_evidence"]["protocol_eof_observed"])
        self.assertFalse(diagnostic["terminal_evidence"]["parent_shutdown_observed"])
        self.assertTrue(
            diagnostic["terminal_evidence"]["final_artifact_bound_to_stop_receipt"]
        )

        tampered_state = json.loads(json.dumps(state))
        tampered_state["mcp_session"]["protocol_trace_head_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            self.module.HandoffError, "tunnel-stop receipt differs from final protocol trace"
        ):
            self.module.verify_schema3_mcp_session(
                tampered_state,
                receipt,
                self.load(handoff / "manifest.json"),
                manifest_sha256=self.module.sha256_file(handoff / "manifest.json"),
            )

    def test_terminal_package_and_receipt_must_match_actual_audit_footer(self) -> None:
        for tamper in ("counter", "reason", "footer", "timestamp"):
            with self.subTest(tamper=tamper):
                self.use_runtime_home(f"terminal-audit-{tamper}")
                handoff = self.prepare_and_approve()
                store, _, _ = self.activate(handoff)
                self.module.stop_mcp_authorization(handoff, store)

                state = self.load(handoff / "state.json")
                receipt = self.load(handoff / "receipt.json")
                terminal = next(
                    event for event in receipt["events"] if event["type"] == "mcp_revoked"
                )
                if tamper == "counter":
                    state["mcp_session"]["disclosed_bytes"] += 1
                    terminal["data"]["disclosed_bytes"] += 1
                elif tamper == "reason":
                    state["mcp_session"]["reason"] = "remote_stop"
                    terminal["data"]["reason"] = "remote_stop"
                elif tamper == "footer":
                    state["mcp_session"]["footer"] = False
                else:
                    state["mcp_session"]["last_committed_at"] = (
                        "1970-01-01T00:00:00Z"
                    )
                previous = None
                for sequence, event in enumerate(receipt["events"], start=1):
                    event["sequence"] = sequence
                    event["previous_event_hash"] = previous
                    event["event_hash"] = self.module.event_hash(event)
                    previous = event["event_hash"]
                (handoff / "state.json").write_text(
                    json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                (handoff / "receipt.json").write_text(
                    json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    self.module.HandoffError,
                    "does not match its audit footer",
                ):
                    self.module.verify_package(handoff)
                with self.assertRaisesRegex(
                    self.module.HandoffError,
                    "does not match its audit footer",
                ):
                    self.module.stop_mcp_authorization(handoff, store)
                self.assertEqual("revoked", store.read()["status"])

    def test_parent_shutdown_footer_is_eof_observed_and_receipt_bound(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store)
        trace = self.close_protocol_trace(handoff, "parent_shutdown")
        self.assertTrue(trace.closed)
        self.assertEqual("parent_shutdown", trace.close_reason)
        self.module.record_mcp_runtime_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="user_requested",
            child_returncode=0,
            forced_exact_child=False,
        )

        diagnostic = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )["protocol_trace"]
        terminal = diagnostic["terminal_evidence"]
        self.assertEqual(
            "runtime_stopped_parent_shutdown_eof_observed", terminal["status"]
        )
        self.assertTrue(terminal["runtime_stop_observed"])
        self.assertTrue(terminal["protocol_stream_closed"])
        self.assertTrue(terminal["protocol_eof_observed"])
        self.assertTrue(terminal["parent_shutdown_observed"])
        self.assertTrue(terminal["final_artifact_bound_to_stop_receipt"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_runtime_stop_reconciles_a_late_commit_error_without_false_global_evidence(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store)
        self.close_protocol_trace(handoff)
        original_commit = self.module.commit_lifecycle_pair

        def commit_then_report_failure(*args, **kwargs):
            original_commit(*args, **kwargs)
            raise self.module.RuntimeStateError(
                "RUNTIME_STATE_WRITE_FAILED", "simulated late directory sync failure"
            )

        with mock.patch.object(
            self.module,
            "commit_lifecycle_pair",
            side_effect=commit_then_report_failure,
        ):
            stopped = self.module.record_mcp_runtime_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="user_requested",
                child_returncode=0,
                forced_exact_child=False,
            )
        self.assertTrue(stopped["runtime_stop_receipt_recorded"])
        runtime = store.read()
        self.assertTrue(runtime["runtime_stop_receipt_recorded"])
        receipt = self.module.verify_package(handoff)["receipt"]
        self.assertEqual(1, len(self.module.receipt_events(receipt, "mcp_stopped")))

    def test_runtime_stop_rejects_reason_drift_between_package_and_global_evidence(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store)
        self.close_protocol_trace(handoff)
        self.module.record_mcp_stopped(
            handoff,
            session_id_sha256=session_hash,
            reason="user_requested",
        )
        with self.assertRaisesRegex(self.module.HandoffError, "conflict"):
            self.module.record_mcp_runtime_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="child_exit",
                child_returncode=0,
                forced_exact_child=False,
            )
        self.assertNotIn("runtime_child_stopped", store.read())

    def test_forced_stop_records_valid_prefix_without_fabricating_a_footer(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        stopped = self.module.stop_mcp_authorization(handoff, store)
        self.assertTrue(stopped["audit"]["footer"])

        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
        state = self.load(handoff / "state.json")
        trace_state = state["mcp_session"]
        self.assertTrue(trace_state["tunnel_runtime_stopped"])
        self.assertTrue(trace_state["protocol_trace_valid"])
        self.assertFalse(trace_state["protocol_trace_closed"])
        self.assertIsNone(trace_state["protocol_trace_close_reason"])
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(1, sum(event["type"] == "mcp_stopped" for event in receipt["events"]))
        self.assertTrue(
            json.loads(
                self.run_cli(
                    "mcp-verify-audit", "--handoff-dir", str(handoff)
                ).stdout
            )["audit"]["valid"]
        )
        diagnostic = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertTrue(diagnostic["protocol_trace"]["artifact_valid"])
        self.assertFalse(diagnostic["protocol_trace"]["closed"])
        terminal = diagnostic["protocol_trace"]["terminal_evidence"]
        self.assertEqual("runtime_stopped_protocol_eof_unobserved", terminal["status"])
        self.assertTrue(terminal["runtime_stop_observed"])
        self.assertFalse(terminal["protocol_stream_closed"])
        self.assertFalse(terminal["protocol_eof_observed"])
        self.assertFalse(terminal["parent_shutdown_observed"])
        self.assertTrue(terminal["final_artifact_bound_to_stop_receipt"])
        status = json.loads(
            self.run_cli(
                "mcp-status", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertEqual(terminal, status["protocol_trace"]["terminal_evidence"])
        self.assertFalse(status["effective_authorized"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_request_correlation_aligns_outer_hmacs_with_trace_and_audit_order(self) -> None:
        session_hash = "a" * 64
        verified = {"state": {"mcp_session": {"session_id_sha256": session_hash}}}
        rpc_hash = hashlib.sha256(b"7").hexdigest()
        trace_events = tuple(
            {
                "sequence": index,
                "method": "tools_call",
                "stage": "response",
                "outcome": "response_flushed",
            }
            for index in range(1, 7)
        )
        trace_summary = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="parent_shutdown",
            events=trace_events,
        )
        audits = (
            *(
                {
                    "audit_sequence": index,
                    "tool": "gptpro_package_info",
                    "jsonrpc_request_id_sha256": rpc_hash,
                    "arguments_sha256": "1" * 64,
                    "disclosure_bytes": 7,
                    "result": "committed_for_return",
                }
                for index in range(1, 4)
            ),
            *(
                {
                    "audit_sequence": index,
                    "tool": "gptpro_repo_search",
                    "jsonrpc_request_id_sha256": rpc_hash,
                    "arguments_sha256": "2" * 64,
                    "disclosure_bytes": 50,
                    "result": "committed_for_return",
                }
                for index in range(4, 7)
            ),
        )
        outer = ["a" * 64, "a" * 64, "a" * 64, "b" * 64, "c" * 64, "d" * 64]
        captured = {
            "schema_version": 1,
            "status": "captured",
            "private_contract": (
                "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
            ),
            "capture_window_complete": True,
            "admin_events_observed": 10,
            "terminal_command_events": 6,
            "terminal_error_events": 0,
            "events": [
                {
                    "ordinal": index,
                    "outcome": "forwarded",
                    "outer_request_id_hmac_sha256": outer[index - 1],
                    "rpc_request_id_hmac_sha256": "e" * 64,
                    "jsonrpc_request_id_sha256": rpc_hash,
                }
                for index in range(1, 7)
            ],
            "privacy": {
                "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
                "raw_identifiers_persisted": False,
                "raw_payloads_persisted": False,
                "hmac_key_persisted": False,
                "stable_join_hashes_exposed_in_terminal": False,
                "raw_http_logging_enabled": False,
            },
        }
        fake_audit = SimpleNamespace(diagnostic_tool_records=lambda: audits)
        with (
            mock.patch.object(
                self.module,
                "verify_bound_protocol_trace",
                return_value=(None, trace_summary, None, True),
            ),
            mock.patch.object(self.module, "audit_log_for", return_value=fake_audit),
        ):
            report = self.module.mcp_request_correlation_payload(verified, captured)

        self.assertEqual("correlated", report["status"])
        self.assertEqual("mixed_outer_request_pattern", report["analysis"]["outer_request_attribution"])
        groups = {
            group["tool"]: group
            for group in report["analysis"]["duplicate_argument_groups"]
        }
        self.assertEqual(
            "same_outer_request_repeated",
            groups["gptpro_package_info"]["classification"],
        )
        self.assertEqual(
            "distinct_outer_requests",
            groups["gptpro_repo_search"]["classification"],
        )
        self.assertTrue(report["physical_calls_counted"])
        self.assertFalse(report["deduplication_applied"])
        self.assertEqual("blocked", report["write_tool_gate"])
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("jsonrpc_request_id_sha256", serialized)
        self.assertNotIn("arguments_sha256", serialized)
        self.assertNotIn(rpc_hash, serialized)
        self.assertFalse(
            report["privacy"]["stable_join_hashes_exposed_in_terminal"]
        )
        self.assertEqual(1, groups["gptpro_package_info"]["argument_group_ordinal"])
        self.assertEqual(2, groups["gptpro_repo_search"]["argument_group_ordinal"])

    def test_request_correlation_keeps_unadvertised_tool_identities_internal(self) -> None:
        session_hash = "a" * 64
        verified = {"state": {"mcp_session": {"session_id_sha256": session_hash}}}
        rpc_hash = hashlib.sha256(b"unadvertised-rpc").hexdigest()
        first_tool_hash = hashlib.sha256(b"unknown-tool-one").hexdigest()
        second_tool_hash = hashlib.sha256(b"unknown-tool-two").hexdigest()
        arguments_hash = hashlib.sha256(b"same-arguments").hexdigest()
        trace_summary = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="parent_shutdown",
            events=tuple(
                {
                    "sequence": index,
                    "method": "tools_call",
                    "stage": "response",
                    "outcome": "response_flushed",
                }
                for index in range(1, 4)
            ),
        )
        audits = tuple(
            {
                "audit_sequence": index,
                "tool": "<unadvertised>",
                "requested_tool_sha256": tool_hash,
                "jsonrpc_request_id_sha256": rpc_hash,
                "arguments_sha256": arguments_hash,
                "disclosure_bytes": 0,
                "result": "rejected",
            }
            for index, tool_hash in enumerate(
                (first_tool_hash, second_tool_hash, first_tool_hash), start=1
            )
        )
        captured = {
            "schema_version": 1,
            "status": "captured",
            "private_contract": (
                "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
            ),
            "capture_window_complete": True,
            "admin_events_observed": 3,
            "terminal_command_events": 3,
            "terminal_error_events": 0,
            "events": [
                {
                    "ordinal": index,
                    "outcome": "forwarded",
                    "outer_request_id_hmac_sha256": outer,
                    "rpc_request_id_hmac_sha256": "e" * 64,
                    "jsonrpc_request_id_sha256": rpc_hash,
                }
                for index, outer in enumerate(("b" * 64, "c" * 64, "d" * 64), start=1)
            ],
            "privacy": {
                "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
                "raw_identifiers_persisted": False,
                "raw_payloads_persisted": False,
                "hmac_key_persisted": False,
                "stable_join_hashes_exposed_in_terminal": False,
                "raw_http_logging_enabled": False,
            },
        }
        fake_audit = SimpleNamespace(diagnostic_tool_records=lambda: audits)
        with (
            mock.patch.object(
                self.module,
                "verify_bound_protocol_trace",
                return_value=(None, trace_summary, None, True),
            ),
            mock.patch.object(self.module, "audit_log_for", return_value=fake_audit),
        ):
            report = self.module.mcp_request_correlation_payload(verified, captured)

        self.assertEqual("correlated", report["status"])
        self.assertEqual(
            [1, 2, 1],
            [event["argument_group_ordinal"] for event in report["events"]],
        )
        groups = report["analysis"]["duplicate_argument_groups"]
        self.assertEqual(1, len(groups))
        self.assertEqual(2, groups[0]["physical_calls"])
        self.assertEqual("distinct_outer_requests", groups[0]["classification"])
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("requested_tool_sha256", serialized)
        self.assertNotIn(first_tool_hash, serialized)
        self.assertNotIn(second_tool_hash, serialized)

    def test_request_correlation_rejects_an_incomplete_admin_ring_window(self) -> None:
        report = self.module.mcp_request_correlation_payload(
            {"state": {}},
            {
                "schema_version": 1,
                "status": "captured",
                "private_contract": (
                    "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
                ),
                "capture_window_complete": False,
                "admin_events_observed": 2_000,
                "terminal_command_events": 0,
                "terminal_error_events": 0,
                "events": [],
                "privacy": {
                    "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
                    "raw_identifiers_persisted": False,
                    "raw_payloads_persisted": False,
                    "hmac_key_persisted": False,
                    "stable_join_hashes_exposed_in_terminal": False,
                    "raw_http_logging_enabled": False,
                },
            },
        )

        self.assertEqual("inconclusive", report["status"])
        self.assertEqual(
            "REQUEST_CORRELATION_CAPTURE_WINDOW_INCOMPLETE",
            report["code"],
        )
        self.assertEqual("blocked", report["write_tool_gate"])
        self.assertFalse(report["deduplication_applied"])

    def test_request_correlation_never_pairs_terminal_error_with_late_trace(self) -> None:
        captured = {
            "schema_version": 1,
            "status": "captured",
            "private_contract": (
                "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
            ),
            "capture_window_complete": True,
            "admin_events_observed": 2,
            "terminal_command_events": 2,
            "terminal_error_events": 1,
            "events": [
                {
                    "ordinal": 1,
                    "outcome": "upstream_error",
                    "outer_request_id_hmac_sha256": "a" * 64,
                    "rpc_request_id_hmac_sha256": "b" * 64,
                    "jsonrpc_request_id_sha256": "c" * 64,
                },
                {
                    "ordinal": 2,
                    "outcome": "forwarded",
                    "outer_request_id_hmac_sha256": "d" * 64,
                    "rpc_request_id_hmac_sha256": "e" * 64,
                    "jsonrpc_request_id_sha256": "f" * 64,
                },
            ],
            "privacy": {
                "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
                "raw_identifiers_persisted": False,
                "raw_payloads_persisted": False,
                "hmac_key_persisted": False,
                "stable_join_hashes_exposed_in_terminal": False,
                "raw_http_logging_enabled": False,
            },
        }
        trace_summary = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="stdio_eof",
            events=(
                {
                    "sequence": 1,
                    "method": "tools_call",
                    "stage": "response",
                    "outcome": "response_flushed",
                },
                {
                    "sequence": 2,
                    "method": "tools_call",
                    "stage": "response",
                    "outcome": "response_flushed",
                },
            ),
        )
        with mock.patch.object(
            self.module,
            "verify_bound_protocol_trace",
            return_value=(None, trace_summary, None, True),
        ):
            report = self.module.mcp_request_correlation_payload(
                {"state": {}}, captured
            )
        self.assertEqual("inconclusive", report["status"])
        self.assertEqual(
            "REQUEST_CORRELATION_TERMINAL_ERROR_PRESENT", report["code"]
        )

    def test_request_correlation_detects_late_response_count_and_zero_tools(self) -> None:
        captured = {
            "schema_version": 1,
            "status": "captured",
            "private_contract": (
                "tunnel-client-0.0.12-881c9a8fed7cccbe6607cd419863bbca506b8215"
            ),
            "capture_window_complete": True,
            "admin_events_observed": 1,
            "terminal_command_events": 1,
            "terminal_error_events": 0,
            "events": [
                {
                    "ordinal": 1,
                    "outcome": "forwarded",
                    "outer_request_id_hmac_sha256": "a" * 64,
                    "rpc_request_id_hmac_sha256": "b" * 64,
                    "jsonrpc_request_id_sha256": "c" * 64,
                }
            ],
            "privacy": {
                "scope": "terminal_identifiers_ephemeral_session_hmac_sha256",
                "raw_identifiers_persisted": False,
                "raw_payloads_persisted": False,
                "hmac_key_persisted": False,
                "stable_join_hashes_exposed_in_terminal": False,
                "raw_http_logging_enabled": False,
            },
        }
        open_trace = SimpleNamespace(
            truncated=False,
            closed=False,
            close_reason=None,
            events=(
                {
                    "sequence": 1,
                    "method": "initialize",
                    "stage": "response",
                    "outcome": "response_flushed",
                },
            ),
        )
        with mock.patch.object(
            self.module,
            "verify_bound_protocol_trace",
            return_value=(None, open_trace, None, True),
        ):
            open_result = self.module.mcp_request_correlation_payload(
                {"state": {}}, captured
            )
        self.assertEqual("REQUEST_CORRELATION_TRACE_OPEN", open_result["code"])

        broken_trace = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="protocol_broken",
            events=open_trace.events,
        )
        with mock.patch.object(
            self.module,
            "verify_bound_protocol_trace",
            return_value=(None, broken_trace, None, True),
        ):
            broken = self.module.mcp_request_correlation_payload(
                {"state": {}}, captured
            )
        self.assertEqual(
            "REQUEST_CORRELATION_PROTOCOL_BROKEN", broken["code"]
        )

        late_trace = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="stdio_eof",
            events=tuple(
                {
                    "sequence": index,
                    "method": "initialize",
                    "stage": "response",
                    "outcome": "response_flushed",
                }
                for index in (1, 2)
            ),
        )
        with mock.patch.object(
            self.module,
            "verify_bound_protocol_trace",
            return_value=(None, late_trace, None, True),
        ):
            late = self.module.mcp_request_correlation_payload(
                {"state": {}}, captured
            )
        self.assertEqual("REQUEST_CORRELATION_EVENT_COUNT_MISMATCH", late["code"])

        no_tool_trace = SimpleNamespace(
            truncated=False,
            closed=True,
            close_reason="stdio_eof",
            events=(
                {
                    "sequence": 1,
                    "method": "initialize",
                    "stage": "response",
                    "outcome": "response_flushed",
                },
            ),
        )
        fake_audit = SimpleNamespace(diagnostic_tool_records=lambda: ())
        with (
            mock.patch.object(
                self.module,
                "verify_bound_protocol_trace",
                return_value=(None, no_tool_trace, None, True),
            ),
            mock.patch.object(self.module, "audit_log_for", return_value=fake_audit),
        ):
            no_tools = self.module.mcp_request_correlation_payload(
                {"state": {"mcp_session": {"session_id_sha256": "a" * 64}}},
                captured,
            )
        self.assertEqual("REQUEST_CORRELATION_NO_TOOL_EVENTS", no_tools["code"])

    def test_corrupt_trace_does_not_erase_exact_stop_or_disclosure_audit(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        stopped = self.module.stop_mcp_authorization(handoff, store)
        self.assertTrue(stopped["audit"]["footer"])
        with (handoff / "mcp-protocol-trace.jsonl").open("ab") as handle:
            handle.write(b"{corrupt\n")

        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
        state = self.load(handoff / "state.json")["mcp_session"]
        self.assertTrue(state["tunnel_runtime_stopped"])
        self.assertFalse(state["protocol_trace_valid"])
        self.assertFalse(state["protocol_trace_closed"])
        self.assertEqual("PROTOCOL_TRACE_INVALID", state["protocol_trace_error_code"])
        self.assertTrue(state["protocol_trace_artifact_identity_bound"])
        corrupt_bytes = (handoff / "mcp-protocol-trace.jsonl").read_bytes()
        self.assertEqual(
            hashlib.sha256(corrupt_bytes).hexdigest(),
            state["protocol_trace_artifact_sha256"],
        )
        self.assertEqual(len(corrupt_bytes), state["protocol_trace_artifact_bytes"])
        diagnostic = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertFalse(diagnostic["protocol_trace"]["artifact_valid"])
        self.assertTrue(diagnostic["protocol_trace"]["lifecycle_binding_valid"])
        self.assertEqual(
            "PROTOCOL_TRACE_INVALID",
            diagnostic["protocol_trace"]["recorded_error_code"],
        )
        self.assertTrue(
            json.loads(
                self.run_cli(
                    "mcp-verify-audit", "--handoff-dir", str(handoff)
                ).stdout
            )["audit"]["valid"]
        )
        self.run_cli("verify", "--handoff-dir", str(handoff))

        (handoff / "mcp-protocol-trace.jsonl").write_bytes(b"{different-corrupt\n")
        (handoff / "mcp-protocol-trace.jsonl").chmod(0o600)
        rewritten = self.run_cli(
            "mcp-protocol-trace",
            "--handoff-dir",
            str(handoff),
            "--json",
            expected=2,
        )
        self.assertIn("bytes differ from tunnel-stop evidence", rewritten.stderr)

    def test_unsafe_trace_preserves_stop_but_marks_artifact_identity_unbound(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        stopped = self.module.stop_mcp_authorization(handoff, store)
        self.assertTrue(stopped["audit"]["footer"])
        (handoff / "mcp-protocol-trace.jsonl").chmod(0o644)

        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
        state = self.load(handoff / "state.json")["mcp_session"]
        self.assertTrue(state["tunnel_runtime_stopped"])
        self.assertFalse(state["protocol_trace_valid"])
        self.assertFalse(state["protocol_trace_artifact_identity_bound"])
        self.assertNotIn("protocol_trace_artifact_sha256", state)
        diagnostic = json.loads(
            self.run_cli(
                "mcp-protocol-trace", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertFalse(diagnostic["protocol_trace"]["artifact_identity_bound"])
        self.assertFalse(diagnostic["protocol_trace"]["lifecycle_binding_valid"])
        self.assertTrue(
            json.loads(
                self.run_cli(
                    "mcp-verify-audit", "--handoff-dir", str(handoff)
                ).stdout
            )["audit"]["valid"]
        )

    def test_self_consistent_post_stop_trace_rewrite_fails_lifecycle_binding(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store)
        self.close_protocol_trace(handoff, "stdio_eof")
        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)

        trace_path = handoff / "mcp-protocol-trace.jsonl"
        records = [
            json.loads(line)
            for line in trace_path.read_text(encoding="ascii").splitlines()
        ]
        footer = records[-1]
        footer["close_reason"] = "protocol_broken"
        unsigned = {key: value for key, value in footer.items() if key != "event_sha256"}
        footer["event_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest()
        trace_path.write_text(
            "".join(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + "\n"
                for record in records
            ),
            encoding="ascii",
        )
        trace_path.chmod(0o600)
        self.assertTrue(
            self.module.protocol_trace_for(
                self.module.verify_package(handoff)
            ).verify().closed
        )

        diagnostic = self.run_cli(
            "mcp-protocol-trace",
            "--handoff-dir",
            str(handoff),
            "--json",
            expected=2,
        )
        self.assertIn("differs from final tunnel-stop evidence", diagnostic.stderr)
        status = json.loads(
            self.run_cli(
                "mcp-status", "--handoff-dir", str(handoff), "--json"
            ).stdout
        )
        self.assertTrue(status["split_brain"])
        self.assertFalse(status["protocol_trace"]["lifecycle_binding_valid"])

    def test_stop_recovers_global_revoked_package_active_crash_window(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        store.transition(session_hash, "active", "revoking")
        summary = self.module.audit_log_for(verified, session_hash).append_footer("user_requested")
        store.transition(
            session_hash,
            "revoking",
            "revoked",
            updates={
                "audit_final_sequence": summary.final_sequence,
                "audit_final_head_sha256": summary.head_sha256,
                "tool_calls": summary.tool_calls,
                "disclosed_bytes": summary.disclosed_bytes,
                "revoked_reason": "user_requested",
            },
        )
        self.assertEqual("active", self.load(handoff / "state.json")["mcp_session"]["status"])

        recovered = self.module.stop_mcp_authorization(handoff, store)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        state = self.load(handoff / "state.json")
        self.assertEqual("revoked", state["mcp_session"]["status"])
        self.assertEqual(
            1,
            sum(
                event["type"] == "mcp_revoked"
                for event in self.load(handoff / "receipt.json")["events"]
            ),
        )
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_stop_reconciles_faulted_postappend_ambiguity_footer(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        summary = self.module.audit_log_for(verified, session_hash).append_footer(
            "commit_outcome_uncertain"
        )
        store.transition(session_hash, "active", "faulted")

        # Structural verification keeps this durable close-before-package
        # crash window recoverable, while the active authorization gate still
        # rejects the closed audit.
        self.assertTrue(summary.footer)
        self.assertEqual(
            "active",
            self.module.verify_package(handoff)["state"]["mcp_session"]["status"],
        )
        with self.assertRaisesRegex(
            self.module.HandoffError,
            "closed audit",
        ):
            self.module.mcp_audit_status(self.module.verify_package(handoff))

        recovered = self.module.stop_mcp_authorization(handoff, store)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        self.assertEqual(
            "commit_outcome_uncertain",
            recovered["authorization"]["revoked_reason"],
        )
        final = self.module.verify_package(handoff)
        self.assertEqual("revoked", final["state"]["mcp_session"]["status"])
        self.assertEqual(
            "commit_outcome_uncertain",
            final["state"]["mcp_session"]["reason"],
        )
        self.assertEqual(
            "commit_outcome_uncertain",
            next(
                event["data"]["reason"]
                for event in final["receipt"]["events"]
                if event["type"] == "mcp_revoked"
            ),
        )

    def test_late_activation_failure_does_not_rewrite_external_revoke(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        self.module.stop_mcp_authorization(handoff, store, reason="remote_stop")

        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="SESSION_CONFLICT",
        )

        latest = self.module.verify_package(handoff)
        self.assertEqual("revoked", store.read()["status"])
        self.assertEqual("revoked", latest["state"]["mcp_session"]["status"])
        self.assertEqual(
            0,
            len(
                self.module.receipt_events(
                    latest["receipt"], "mcp_recovery_recorded"
                )
            ),
        )

    def test_external_revoke_wins_between_global_failure_deny_and_package_record(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        failure_ready = threading.Event()
        allow_failure_package_record = threading.Event()
        failures: list[BaseException] = []
        real_record = self.module._record_mcp_activation_failure_package

        def delayed_record(*args, **kwargs) -> None:
            failure_ready.set()
            if not allow_failure_package_record.wait(timeout=5):
                raise AssertionError("failure package record barrier timed out")
            real_record(*args, **kwargs)

        def record_failure() -> None:
            try:
                self.module.fail_mcp_activation(
                    handoff,
                    store,
                    session_id_sha256=session_hash,
                    error_code="SESSION_CONFLICT",
                )
            except BaseException as exc:
                failures.append(exc)

        with mock.patch.object(
            self.module,
            "_record_mcp_activation_failure_package",
            side_effect=delayed_record,
        ):
            worker = threading.Thread(target=record_failure)
            worker.start()
            self.assertTrue(failure_ready.wait(timeout=5))
            stopped = self.module.stop_mcp_authorization(
                handoff,
                store,
                reason="remote_stop",
            )
            allow_failure_package_record.set()
            worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual([], failures)
        self.assertEqual("revoked", stopped["authorization"]["status"])
        latest = self.module.verify_package(handoff)
        self.assertEqual("revoked", store.read()["status"])
        self.assertEqual("revoked", latest["state"]["mcp_session"]["status"])
        self.assertEqual(
            0,
            len(
                self.module.receipt_events(
                    latest["receipt"], "mcp_recovery_recorded"
                )
            ),
        )

    def test_status_and_stop_cli_report_authorization_separately_from_process(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        with self.module.ControllerLease(store, session_hash):
            status = json.loads(
                self.run_cli(
                    "mcp-status",
                    "--handoff-dir",
                    str(handoff),
                    "--json",
                ).stdout
            )
        self.assertEqual("active", status["authorization"]["status"])
        self.assertFalse(status["split_brain"])
        self.assertTrue(status["effective_authorized"])
        self.assertEqual("live", status["controller"]["status"])
        self.assertFalse(status["expired_lazily"])
        self.assertTrue(status["protocol_trace"]["artifact_valid"])
        self.assertTrue(status["protocol_trace"]["header_binding_valid"])
        self.assertFalse(status["protocol_trace"]["artifact_identity_bound"])
        self.assertFalse(status["protocol_trace"]["lifecycle_binding_valid"])

        stopped = json.loads(
            self.run_cli(
                "mcp-stop",
                "--handoff-dir",
                str(handoff),
                "--json",
            ).stdout
        )
        self.assertEqual("revoked", stopped["authorization"]["status"])
        self.assertTrue(stopped["authorization_denied"])
        self.assertEqual("revoked", stopped["authorization_status"])
        self.assertTrue(stopped["revocation_receipt_recorded"])
        self.assertTrue(stopped["authorization_revoked"])
        self.assertFalse(stopped["tunnel_runtime_stopped"])
        self.assertTrue(stopped["controller_lease_released"])
        self.assertEqual("unconfirmed", stopped["exact_tunnel_process_status"])
        self.assertTrue(stopped["manual_process_review_required"])
        self.assertFalse(stopped["foreground_controller_stop_required"])
        revoked_status = json.loads(
            self.run_cli(
                "mcp-status",
                "--handoff-dir",
                str(handoff),
                "--json",
            ).stdout
        )
        self.assertTrue(revoked_status["protocol_trace"]["header_binding_valid"])
        self.assertFalse(revoked_status["protocol_trace"]["artifact_identity_bound"])
        self.assertFalse(revoked_status["protocol_trace"]["lifecycle_binding_valid"])
        self.close_protocol_trace(handoff)
        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
        final_trace = json.loads(
            self.run_cli(
                "mcp-protocol-trace",
                "--handoff-dir",
                str(handoff),
                "--json",
            ).stdout
        )["protocol_trace"]
        self.assertTrue(final_trace["header_binding_valid"])
        self.assertTrue(final_trace["artifact_identity_bound"])
        self.assertTrue(final_trace["lifecycle_binding_valid"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_status_denies_a_closed_audit_active_state_crash_window(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        closed = self.module.audit_log_for(verified, session_hash).append_footer(
            "commit_outcome_uncertain"
        )
        self.assertTrue(closed.footer)

        with self.module.ControllerLease(store, session_hash):
            status = json.loads(
                self.run_cli(
                    "mcp-status",
                    "--handoff-dir",
                    str(handoff),
                    "--json",
                ).stdout
            )
        self.assertEqual("active", status["authorization"]["status"])
        self.assertTrue(status["audit"]["valid"])
        self.assertTrue(status["audit"]["footer"])
        self.assertFalse(status["effective_authorized"])
        self.assertTrue(status["split_brain"])
        self.assertIn("run_mcp_stop_for_exact_package", status["recovery_actions"])

        recovered = self.module.stop_mcp_authorization(handoff, store)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        self.assertEqual(
            "commit_outcome_uncertain",
            recovered["authorization"]["revoked_reason"],
        )
        self.assertEqual(
            "revoked",
            self.module.verify_package(handoff)["state"]["mcp_session"]["status"],
        )

    def test_stop_emergency_denies_exact_session_without_rewriting_damaged_evidence(self) -> None:
        for index, artifact in enumerate(
            ("manifest", "state", "receipt", "archive", "audit")
        ):
            with self.subTest(artifact=artifact):
                self.use_runtime_home(f"emergency-stop-{index}")
                handoff = self.prepare_and_approve()
                store, session_hash, _ = self.activate(handoff)
                verified = self.module.verify_package(handoff)
                evidence_paths = {
                    "manifest": handoff / "manifest.json",
                    "state": handoff / "state.json",
                    "receipt": handoff / "receipt.json",
                    "archive": verified["archive_path"],
                    "audit": handoff / "mcp-audit.jsonl",
                }
                target = evidence_paths[artifact]
                damaged = b"{damaged-package-evidence\n"
                target.write_bytes(damaged)
                target.chmod(0o600)
                evidence_snapshot = {
                    name: path.read_bytes() for name, path in evidence_paths.items()
                }

                def stop_exact_child(*args, **kwargs):
                    del args, kwargs
                    self.module.record_mcp_runtime_stopped_fail_closed(
                        handoff,
                        store,
                        session_id_sha256=session_hash,
                        reason="remote_stop",
                        child_returncode=-15,
                        forced_exact_child=False,
                    )
                    return True

                with (
                    mock.patch.object(
                        self.module,
                        "request_cooperative_stop",
                        side_effect=stop_exact_child,
                    ) as cooperative_stop,
                    mock.patch.object(self.module.os, "kill") as broad_signal,
                ):
                    payload = json.loads(
                        self.run_cli(
                            "mcp-stop",
                            "--handoff-dir",
                            str(handoff),
                            "--json",
                        ).stdout
                    )

                self.assertEqual(damaged, target.read_bytes())
                for name, path in evidence_paths.items():
                    self.assertEqual(
                        evidence_snapshot[name],
                        path.read_bytes(),
                        f"{name} changed during evidence-unavailable stop",
                    )
                self.assertEqual("faulted", store.read()["status"])
                self.assertEqual(
                    "package_evidence_unavailable", store.read()["orphaned_reason"]
                )
                self.assertFalse(payload["package_evidence_available"])
                self.assertEqual("unavailable", payload["package_evidence_status"])
                self.assertEqual("authorization_denied", payload["status"])
                self.assertTrue(payload["authorization_denied"])
                self.assertEqual("faulted", payload["authorization_status"])
                self.assertFalse(payload["revocation_receipt_recorded"])
                self.assertFalse(payload["authorization_revoked"])
                self.assertEqual(
                    "PACKAGE_EVIDENCE_UNAVAILABLE", payload["audit"]["code"]
                )
                self.assertTrue(payload["cooperative_stop_requested"])
                self.assertTrue(payload["tunnel_runtime_stopped"])
                self.assertEqual("machine_global", payload["stop_evidence"])
                self.assertFalse(payload["controller_lease_released"])
                self.assertEqual("stopped", payload["exact_tunnel_process_status"])
                self.assertFalse(payload["manual_process_review_required"])
                self.assertFalse(payload["foreground_controller_stop_required"])
                runtime = store.read()
                self.assertTrue(runtime["runtime_child_stopped"])
                self.assertFalse(runtime["runtime_stop_receipt_recorded"])
                cooperative_stop.assert_called_once_with(
                    self.module.control_socket_path(store.root), session_hash
                )
                broad_signal.assert_not_called()

    def test_valid_but_replaced_audit_header_triggers_global_denial_only(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        audit_path = handoff / "mcp-audit.jsonl"
        records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
        ]
        records[0]["created_at"] = "2026-01-01T00:00:00Z"
        records[0].pop("event_sha256")
        records[0]["event_sha256"] = self.module.sha256_bytes(
            self.module.canonical_json_bytes(records[0])
        )
        audit_path.write_text(
            "".join(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        audit_path.chmod(0o600)
        before_state = (handoff / "state.json").read_bytes()
        before_receipt = (handoff / "receipt.json").read_bytes()
        replaced_audit = audit_path.read_bytes()

        result = self.module.revoke_mcp_authorization_fail_closed(handoff, store)

        self.assertFalse(result["package_evidence_available"])
        self.assertTrue(result["authorization_denied"])
        self.assertEqual("faulted", result["authorization_status"])
        self.assertFalse(result["revocation_receipt_recorded"])
        self.assertFalse(result["authorization_revoked"])
        self.assertEqual(session_hash, result["authorization"]["session_id_sha256"])
        self.assertEqual(before_state, (handoff / "state.json").read_bytes())
        self.assertEqual(before_receipt, (handoff / "receipt.json").read_bytes())
        self.assertEqual(replaced_audit, audit_path.read_bytes())
        self.assertEqual("faulted", store.read()["status"])

    def test_stop_ack_loss_still_reports_durable_exact_child_evidence(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)

        def stop_exact_child_without_ack(*args, **kwargs):
            del args, kwargs
            self.module.record_mcp_runtime_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="remote_stop",
                child_returncode=-15,
                forced_exact_child=False,
            )
            return False

        with mock.patch.object(
            self.module,
            "request_cooperative_stop",
            side_effect=stop_exact_child_without_ack,
        ):
            payload = json.loads(
                self.run_cli(
                    "mcp-stop",
                    "--handoff-dir",
                    str(handoff),
                    "--json",
                ).stdout
            )

        self.assertFalse(payload["cooperative_stop_requested"])
        self.assertTrue(payload["tunnel_runtime_stopped"])
        self.assertEqual("package_receipt", payload["stop_evidence"])
        self.assertEqual("stopped", payload["exact_tunnel_process_status"])
        self.assertFalse(payload["foreground_controller_stop_required"])

    def test_stop_reads_exact_archived_evidence_after_concurrent_new_activation(self) -> None:
        old_handoff = self.prepare_and_approve()
        new_handoff = self.prepare_and_approve()
        new_verified, new_preflight = self.preflight(new_handoff)
        store, old_session, _ = self.activate(old_handoff)
        new_session = hashlib.sha256(b"concurrent-new-activation").hexdigest()

        # Force the stop onto machine-global evidence only.  The cooperative
        # stop then commits the exact old child evidence and a concurrent new
        # activation archives it before command_mcp_stop begins polling.
        old_receipt = old_handoff / "receipt.json"
        old_receipt.write_bytes(b"{damaged-old-receipt\n")
        old_receipt.chmod(0o600)

        def stop_then_replace_active(*args, **kwargs):
            del args, kwargs
            stopped = self.module.record_mcp_runtime_stopped_fail_closed(
                old_handoff,
                store,
                session_id_sha256=old_session,
                reason="remote_stop",
                child_returncode=-15,
                forced_exact_child=False,
            )
            self.assertTrue(stopped["exact_child_stop_recorded"])
            self.module.begin_mcp_activation(
                new_verified,
                store,
                session_id_sha256=new_session,
                preflight=new_preflight,
            )
            return True

        with mock.patch.object(
            self.module,
            "request_cooperative_stop",
            side_effect=stop_then_replace_active,
        ):
            payload = json.loads(
                self.run_cli(
                    "mcp-stop",
                    "--handoff-dir",
                    str(old_handoff),
                    "--json",
                ).stdout
            )

        self.assertTrue(payload["tunnel_runtime_stopped"])
        self.assertEqual("machine_global_archive", payload["stop_evidence"])
        self.assertEqual("stopped", payload["exact_tunnel_process_status"])
        self.assertFalse(payload["manual_process_review_required"])
        self.assertEqual(new_session, store.read()["session_id_sha256"])
        archived = store.read_archived_session(old_session)
        self.assertIsNotNone(archived)
        self.assertTrue(archived["runtime_child_stopped"])

    def test_emergency_deny_rejects_wrong_handoff_or_session_binding(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        other = self.root / "other-handoff"
        other.mkdir()

        with self.assertRaisesRegex(self.module.HandoffError, "different handoff"):
            self.module.deny_mcp_authorization_without_package(other, store)
        with self.assertRaisesRegex(self.module.HandoffError, "different session"):
            self.module.deny_mcp_authorization_without_package(
                handoff,
                store,
                expected_session_id_sha256="0" * 64,
            )
        self.assertEqual("active", store.read()["status"])
        self.assertEqual(session_hash, store.read()["session_id_sha256"])

    def test_emergency_deny_preserves_canonical_handoff_after_package_damage(self) -> None:
        handoff = self.prepare_and_approve()
        alias = self.root / "approved-handoff-alias"
        alias.symlink_to(handoff, target_is_directory=True)
        # Activation resolves accepted directory aliases to the canonical
        # package binding; exercise the later stop with the same alias spelling.
        store, session_hash, _ = self.activate(handoff)
        receipt_path = handoff / "receipt.json"
        damaged = b"{damaged-symlinked-package-receipt\n"
        receipt_path.write_bytes(damaged)
        receipt_path.chmod(0o600)

        result = self.module.revoke_mcp_authorization_fail_closed(
            alias,
            store,
            expected_session_id_sha256=session_hash,
        )

        self.assertFalse(result["package_evidence_available"])
        self.assertTrue(result["authorization_denied"])
        self.assertEqual("faulted", result["authorization_status"])
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(str(handoff.resolve()), store.read()["handoff_dir"])
        self.assertEqual(damaged, receipt_path.read_bytes())

        def stop_exact_child(*args, **kwargs):
            del args, kwargs
            self.module.record_mcp_runtime_stopped_fail_closed(
                handoff,
                store,
                session_id_sha256=session_hash,
                reason="remote_stop",
                child_returncode=-15,
                forced_exact_child=False,
            )
            return True

        with mock.patch.object(
            self.module,
            "request_cooperative_stop",
            side_effect=stop_exact_child,
        ):
            payload = json.loads(
                self.run_cli(
                    "mcp-stop",
                    "--handoff-dir",
                    str(alias),
                    "--json",
                ).stdout
            )

        self.assertTrue(payload["tunnel_runtime_stopped"])
        self.assertEqual("machine_global", payload["stop_evidence"])
        self.assertEqual("stopped", payload["exact_tunnel_process_status"])
        self.assertFalse(payload["manual_process_review_required"])
        self.assertEqual(damaged, receipt_path.read_bytes())

    def test_failed_activation_stop_uses_only_global_state_when_package_is_damaged(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"damaged-failed-activation").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        receipt_path = handoff / "receipt.json"
        damaged = b"{damaged-failed-activation-receipt\n"
        receipt_path.write_bytes(damaged)
        receipt_path.chmod(0o600)

        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )

        self.assertFalse(stopped["package_evidence_available"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        self.assertEqual(damaged, receipt_path.read_bytes())
        runtime = store.read()
        self.assertEqual("faulted", runtime["status"])
        self.assertTrue(runtime["activation_child_stopped"])
        self.assertEqual(-15, runtime["activation_child_returncode"])
        self.assertFalse(runtime["activation_stop_receipt_recorded"])
        self.assertNotIn("activation_stop_receipt_event_sha256", runtime)
        self.assertNotIn("activation_protocol_trace_artifact_sha256", runtime)
        public = self.module.public_runtime_authorization(runtime)
        self.assertTrue(public["activation_child_stopped"])
        self.assertEqual(-15, public["activation_child_returncode"])
        self.assertFalse(public["activation_stop_receipt_recorded"])

    def test_missing_handoff_records_global_runtime_stop_then_reconciles_receipt(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        revoked = self.module.revoke_mcp_authorization_fail_closed(
            handoff,
            store,
            expected_session_id_sha256=session_hash,
            reason="remote_stop",
        )
        self.assertTrue(revoked["authorization_revoked"])
        saved = self.root / "saved-runtime-handoff"
        handoff.rename(saved)

        global_only = self.module.record_mcp_runtime_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="remote_stop",
            child_returncode=-15,
            forced_exact_child=False,
        )

        self.assertFalse(global_only["package_evidence_available"])
        self.assertFalse(global_only["runtime_stop_receipt_recorded"])
        self.assertTrue(store.read()["runtime_child_stopped"])
        self.assertFalse(store.read()["runtime_stop_receipt_recorded"])
        saved.rename(handoff)

        reconciled = self.module.record_mcp_runtime_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="remote_stop",
            child_returncode=-15,
            forced_exact_child=False,
        )

        self.assertTrue(reconciled["package_evidence_available"])
        self.assertTrue(reconciled["runtime_stop_receipt_recorded"])
        runtime = store.read()
        self.assertTrue(runtime["runtime_stop_receipt_recorded"])
        self.assertEqual(64, len(runtime["runtime_stop_receipt_event_sha256"]))
        verified = self.module.verify_package(handoff)
        self.assertEqual(
            1,
            len(self.module.receipt_events(verified["receipt"], "mcp_stopped")),
        )

    def test_missing_handoff_records_activation_stop_then_reconciles_receipt(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"missing-activation-handoff").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )
        saved = self.root / "saved-activation-handoff"
        handoff.rename(saved)

        global_only = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )

        self.assertFalse(global_only["package_evidence_available"])
        self.assertFalse(global_only["activation_stop_receipt_recorded"])
        self.assertTrue(store.read()["activation_child_stopped"])
        self.assertFalse(store.read()["activation_stop_receipt_recorded"])
        saved.rename(handoff)

        reconciled = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )

        self.assertTrue(reconciled["package_evidence_available"])
        self.assertTrue(reconciled["activation_stop_receipt_recorded"])
        runtime = store.read()
        self.assertTrue(runtime["activation_stop_receipt_recorded"])
        self.assertEqual(64, len(runtime["activation_stop_receipt_event_sha256"]))
        verified = self.module.verify_package(handoff)
        self.assertEqual(
            1,
            len(
                self.module.receipt_events(
                    verified["receipt"], "mcp_activation_stopped"
                )
            ),
        )

    def test_activation_failure_denies_globally_before_reading_damaged_package(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"damage-before-activation-failure").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        receipt_path = handoff / "receipt.json"
        damaged = b"{damage-before-global-denial\n"
        receipt_path.write_bytes(damaged)
        receipt_path.chmod(0o600)

        self.module.fail_mcp_activation(
            handoff,
            store,
            session_id_sha256=session_hash,
            error_code="TUNNEL_NOT_READY",
        )

        runtime = store.read()
        self.assertEqual("faulted", runtime["status"])
        self.assertEqual("TUNNEL_NOT_READY", runtime["activation_failure_code"])
        self.assertEqual(damaged, receipt_path.read_bytes())
        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )
        self.assertTrue(stopped["exact_child_stop_recorded"])
        self.assertFalse(stopped["package_evidence_available"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        self.assertEqual(damaged, receipt_path.read_bytes())
        self.assertTrue(store.read()["activation_child_stopped"])

    def test_missing_package_failure_receipt_does_not_block_global_child_stop(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"missing-package-failure-receipt").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        with mock.patch.object(
            self.module,
            "_record_mcp_activation_failure_package",
            side_effect=self.module.HandoffError("simulated package evidence failure"),
        ):
            self.module.fail_mcp_activation(
                handoff,
                store,
                session_id_sha256=session_hash,
                error_code="TUNNEL_NOT_READY",
            )

        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            0,
            len(
                self.module.receipt_events(
                    self.module.verify_package(handoff)["receipt"],
                    "mcp_activation_failed",
                )
            ),
        )
        stopped = self.module.record_mcp_activation_stopped_fail_closed(
            handoff,
            store,
            session_id_sha256=session_hash,
            reason="controller_exit",
            child_returncode=-15,
            forced_exact_child=False,
        )
        self.assertTrue(stopped["exact_child_stop_recorded"])
        self.assertFalse(stopped["package_evidence_available"])
        self.assertFalse(stopped["activation_stop_receipt_recorded"])
        self.assertTrue(store.read()["activation_child_stopped"])

    def test_activate_controller_revoke_callback_uses_emergency_deny(self) -> None:
        handoff = self.prepare_and_approve()
        manifest = self.load(handoff / "manifest.json")
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"controller-revoke-fallback").hexdigest()
        observed: dict[str, object] = {}

        fake_client = mock.Mock()
        capabilities = SimpleNamespace(
            binary_sha256=TUNNEL_BINARY_HASH,
            supported=True,
            health_require_control_plane_poll=True,
            request_correlation_contract_supported=True,
            parent_shutdown_contract_supported=True,
        )
        fake_client.doctor.return_value = SimpleNamespace(
            ok=True,
            code=None,
            tunnel_binding_matches=True,
            tunnel_binding_sha256=manifest["connector"]["tunnel_id_binding_sha256"],
            mcp_target_matches=True,
            mcp_target_sha256=MCP_TARGET_HASH,
            profile_sha256=TUNNEL_PROFILE_HASH,
            profile_binding_verification="automatic-doctor-json",
        )

        def fake_run_foreground(*, hooks, **kwargs):
            self.assertTrue(kwargs["parent_shutdown_contract_supported"])
            with self.assertRaises(self.module.RuntimeStateError) as profile_conflict:
                self.module.ProfileControllerLease(store.root).acquire()
            self.assertEqual(
                "PROFILE_OPERATION_CONFLICT", profile_conflict.exception.code
            )
            begun = hooks.begin_activation(session_hash)
            hooks.complete_activation(
                session_hash,
                begun["audit_header_sha256"],
                lambda: None,
            )
            receipt_path = handoff / "receipt.json"
            damaged = b"{controller-revoke-package-damage\n"
            receipt_path.write_bytes(damaged)
            receipt_path.chmod(0o600)
            revoked = hooks.revoke_authorization("child_exit")
            observed["revoked"] = revoked
            observed["runtime_stop"] = hooks.record_stopped(
                session_hash, "child_exit", 0, False
            )
            observed["damaged"] = damaged
            return SimpleNamespace(
                status="stopped",
                session_id_sha256=session_hash,
                stop_reason="child_exit",
                control_plane_poll_confirmed=True,
                authorization_denied=True,
                authorization_status="faulted",
                revocation_receipt_recorded=False,
                authorization_revoked=False,
                stopped_recorded=False,
                exact_child_stop_recorded=True,
                activation_stop_receipt_recorded=False,
                forced_exact_child=False,
                request_correlation={
                    "schema_version": 1,
                    "status": "captured",
                    "capture_window_complete": True,
                    "admin_events_observed": 1,
                    "events": [],
                },
            )

        arguments = SimpleNamespace(
            handoff_dir=str(handoff),
            tunnel_profile=TUNNEL_PROFILE,
            runtime_api_key_ref="env:ATTENDED_RUNTIME_KEY",
            tunnel_client="/explicit/fake-tunnel-client",
            confirm_tunnel_client_sha256=TUNNEL_BINARY_HASH,
            confirm_workspace_binding=True,
            profile_dir=None,
            ready_timeout=1,
            diagnose_request_correlation=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                self.module,
                "confirmed_key_bearing_tunnel_client",
                return_value=(fake_client, capabilities),
            ),
            mock.patch.object(
                self.module,
                "runtime_key_environment",
                return_value={"CONTROL_PLANE_API_KEY": "sk-" + "x" * 32},
            ),
            mock.patch.object(
                self.module,
                "inspect_tunnel_profile",
                return_value=SimpleNamespace(ready=True, code=None),
            ),
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module, "run_foreground", side_effect=fake_run_foreground
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(0, self.module.command_mcp_activate(arguments))

        revoked = observed["revoked"]
        self.assertIsInstance(revoked, dict)
        self.assertFalse(revoked["package_evidence_available"])
        self.assertEqual("faulted", revoked["authorization"]["status"])
        self.assertTrue(revoked["authorization_denied"])
        self.assertEqual("faulted", revoked["authorization_status"])
        self.assertFalse(revoked["revocation_receipt_recorded"])
        self.assertFalse(revoked["authorization_revoked"])
        runtime_stop = observed["runtime_stop"]
        self.assertIsInstance(runtime_stop, dict)
        self.assertTrue(runtime_stop["exact_child_stop_recorded"])
        self.assertFalse(runtime_stop["runtime_stop_receipt_recorded"])
        self.assertFalse(runtime_stop["package_evidence_available"])
        self.assertEqual("faulted", store.read()["status"])
        self.assertTrue(store.read()["runtime_child_stopped"])
        self.assertFalse(store.read()["runtime_stop_receipt_recorded"])
        public = self.module.public_runtime_authorization(store.read())
        self.assertTrue(public["runtime_child_stopped"])
        self.assertEqual(0, public["runtime_child_returncode"])
        self.assertFalse(public["runtime_stop_receipt_recorded"])
        self.assertEqual(
            observed["damaged"], (handoff / "receipt.json").read_bytes()
        )
        terminal = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual("mcp_exact_child_stopped", terminal["event"])
        self.assertTrue(terminal["exact_child_stop_recorded"])
        self.assertTrue(terminal["authorization_denied"])
        self.assertEqual("faulted", terminal["authorization_status"])
        self.assertFalse(terminal["revocation_receipt_recorded"])
        self.assertFalse(terminal["authorization_revoked"])
        self.assertEqual(
            "PACKAGE_EVIDENCE_UNAVAILABLE",
            terminal["request_correlation_diagnostic"]["code"],
        )
        self.assertEqual(
            "blocked",
            terminal["request_correlation_diagnostic"]["write_tool_gate"],
        )

    def test_lazy_expiry_is_terminal_without_advancing_lifecycle_phase(self) -> None:
        handoff = self.prepare_and_approve()
        store, _, _ = self.activate(handoff)
        expires_at = datetime.fromisoformat(store.read()["expires_at"].replace("Z", "+00:00"))
        result = self.module.expire_mcp_authorization(
            handoff,
            store,
            now=expires_at + timedelta(seconds=1),
        )
        self.assertTrue(result["expired"])
        self.assertTrue(result["authorization_denied"])
        self.assertEqual("expired", result["authorization_status"])
        self.assertFalse(result["revocation_receipt_recorded"])
        self.assertFalse(result["authorization_revoked"])
        self.assertEqual("expired", store.read()["status"])
        state = self.load(handoff / "state.json")
        self.assertEqual("approved", state["phase"])
        self.assertEqual("expired", state["mcp_session"]["status"])
        self.assertTrue(result["audit"]["footer"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_monotonic_deadlines_bind_preflight_and_wall_rollback_cannot_extend(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        wall_start = datetime.fromisoformat(preflight["activated_at"].replace("Z", "+00:00"))
        wall_end = datetime.fromisoformat(preflight["expires_at"].replace("Z", "+00:00"))
        self.assertAlmostEqual(
            (wall_end - wall_start).total_seconds(),
            preflight["expires_monotonic"] - preflight["activated_monotonic"],
            delta=1.0,
        )
        tampered = dict(preflight)
        tampered["expires_monotonic"] += 10
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        with self.assertRaisesRegex(self.module.HandoffError, "preflight TTL"):
            self.module.begin_mcp_activation(
                verified,
                store,
                session_id_sha256=hashlib.sha256(os.urandom(32)).hexdigest(),
                preflight=tampered,
            )
        self.assertIsNone(store.read())

        store, session_hash, _ = self.activate(handoff)
        runtime = store.read()
        with self.module.ControllerLease(store, session_hash):
            with mock.patch.object(
                self.module.time,
                "monotonic",
                return_value=runtime["activated_monotonic"] - 1,
            ):
                with self.assertRaisesRegex(self.module.HandoffError, "monotonic clock reset"):
                    self.module.require_active_mcp_authorization(
                        self.module.verify_package(handoff), store
                    )

        rolled_back_wall = datetime.fromisoformat(
            runtime["activated_at"].replace("Z", "+00:00")
        ) - timedelta(days=1)
        with mock.patch.object(
            self.module.time,
            "monotonic",
            return_value=runtime["activated_monotonic"] - 1,
        ):
            expired = self.module.expire_mcp_authorization(
                handoff,
                store,
                now=rolled_back_wall,
            )
        self.assertTrue(expired["expired"])
        self.assertEqual("expired", store.read()["status"])
        self.assertEqual("monotonic_clock_reset", store.read()["expired_reason"])
        self.assertEqual(
            "monotonic_clock_reset",
            self.load(handoff / "state.json")["mcp_session"]["reason"],
        )

    def test_recover_closes_valid_orphan_but_rejects_a_live_controller(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        command = [
            "mcp-recover",
            "--handoff-dir",
            str(handoff),
            "--confirm-controller-lost",
        ]
        with self.module.ControllerLease(store, session_hash):
            rejected = self.run_cli(*command, expected=2)
        self.assertIn("exact foreground controller is still live", rejected.stderr)
        self.assertEqual("active", store.read()["status"])

        recovered = json.loads(self.run_cli(*command).stdout)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        self.assertTrue(recovered["package_evidence_recovered"])
        self.assertEqual("audit_closed", recovered["recovery_mode"])
        self.assertTrue(recovered["audit"]["footer"])
        self.assertFalse(recovered["tunnel_runtime_stopped"])
        self.assertTrue(recovered["orphan_child_may_remain"])
        self.assertFalse(recovered["process_discovery_attempted"])
        self.assertFalse(recovered["process_signal_attempted"])
        self.assertEqual("revoked", self.load(handoff / "state.json")["mcp_session"]["status"])
        confirmed = json.loads(
            self.run_cli(
                *command,
                "--confirm-orphan-tunnel-stopped",
            ).stdout
        )
        self.assertTrue(confirmed["orphan_tunnel_termination_manually_confirmed"])
        self.assertFalse(confirmed["orphan_child_may_remain"])
        self.assertFalse(confirmed["tunnel_runtime_stopped"])
        self.assertNotIn("runtime_child_stopped", store.read())
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_recover_reconciles_terminal_package_commit_crash_on_rerun(self) -> None:
        handoff = self.prepare_and_approve()
        store, _, _ = self.activate(handoff)
        command = [
            "mcp-recover",
            "--handoff-dir",
            str(handoff),
            "--confirm-controller-lost",
        ]
        with mock.patch.object(
            self.module,
            "_record_terminal_package_session",
            side_effect=self.module.HandoffError("injected package commit failure"),
        ):
            failed = self.run_cli(*command, expected=2)
        self.assertIn("rerun mcp-recover", failed.stderr)
        self.assertEqual("revoked", store.read()["status"])
        self.assertEqual(
            "active", self.load(handoff / "state.json")["mcp_session"]["status"]
        )

        recovered = json.loads(self.run_cli(*command).stdout)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        self.assertEqual("terminal_package_reconciled", recovered["recovery_mode"])
        self.assertTrue(recovered["package_evidence_recovered"])
        self.assertTrue(recovered["audit"]["footer"])
        self.assertFalse(recovered["tunnel_runtime_stopped"])
        self.assertEqual(
            "revoked", self.load(handoff / "state.json")["mcp_session"]["status"]
        )
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(1, len(self.module.receipt_events(receipt, "mcp_revoked")))
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_recover_does_not_mislabel_an_operational_failure_as_invalid_evidence(
        self,
    ) -> None:
        handoff = self.prepare_and_approve()
        store, _, _ = self.activate(handoff)
        original_package = {
            path.name: path.read_bytes()
            for path in handoff.iterdir()
            if path.is_file()
        }
        with mock.patch.object(
            self.module,
            "recover_interrupted_mcp_activation",
            side_effect=self.module.HandoffError(
                "LOCK_TIMEOUT: The package lifecycle lock is busy."
            ),
        ):
            recovered = json.loads(
                self.run_cli(
                    "mcp-recover",
                    "--handoff-dir",
                    str(handoff),
                    "--confirm-controller-lost",
                ).stdout
            )

        self.assertEqual("global_only_faulted", recovered["recovery_mode"])
        self.assertFalse(recovered["package_evidence_recovered"])
        self.assertEqual("unavailable", recovered["audit"]["condition"])
        self.assertEqual("RECOVERY_FAILED", recovered["audit"]["code"])
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            "controller_lost_recovery_failed", store.read()["orphaned_reason"]
        )
        self.assertEqual("unavailable", store.read()["audit_recovery_status"])
        self.assertEqual(
            original_package,
            {
                path.name: path.read_bytes()
                for path in handoff.iterdir()
                if path.is_file()
            },
        )
        audit = self.module.audit_log_for(
            self.module.verify_package(handoff),
            recovered["authorization"]["session_id_sha256"],
        ).verify()
        self.assertFalse(audit.footer)

    def test_pre_audit_crash_recovery_faults_global_and_retires_only_stale_socket(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash = self.interrupt_before_audit_header(handoff)
        self.assertFalse((handoff / "mcp-audit.jsonl").exists())

        control_path = self.module.control_socket_path(store.root)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(control_path))
        os.chmod(control_path, 0o600, follow_symlinks=False)
        stale.close()
        self.assertTrue(control_path.exists())

        arguments = argparse.Namespace(
            handoff_dir=str(handoff),
            confirm_controller_lost=True,
        )
        output = io.StringIO()
        with (
            redirect_stdout(output),
            mock.patch.object(self.module, "RuntimeStateStore", return_value=store),
            mock.patch.object(self.module.os, "kill") as process_signal,
        ):
            self.assertEqual(0, self.module.command_mcp_recover(arguments))
        process_signal.assert_not_called()
        recovered = json.loads(output.getvalue())
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertEqual("pre_audit_faulted", recovered["recovery_mode"])
        self.assertEqual("missing", recovered["audit"]["condition"])
        self.assertEqual("retired", recovered["control_socket"]["status"])
        self.assertTrue(recovered["control_socket"]["retired"])
        self.assertTrue(recovered["orphan_child_may_remain"])
        self.assertFalse(control_path.exists())
        self.assertEqual("faulted", store.read()["status"])
        self.assertIsNone(self.load(handoff / "state.json")["mcp_session"])
        receipt = self.load(handoff / "receipt.json")
        failures = [
            event
            for event in receipt["events"]
            if event["type"] == "mcp_activation_failed"
            and event["data"].get("session_id_sha256") == session_hash
        ]
        self.assertEqual(1, len(failures))
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_prepublication_recovery_faults_global_on_actual_audit_contract_drift(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"prepublication-audit-drift").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        self.assertIsNone(self.load(handoff / "state.json")["mcp_session"])
        self.assertEqual(2, store.read()["audit_schema_version"])

        audit_path = handoff / "mcp-audit.jsonl"
        header = json.loads(audit_path.read_text(encoding="utf-8"))
        header["audit_schema_version"] = 1
        header.pop("accounting_mode")
        header.pop("event_sha256")
        header["event_sha256"] = self.module.sha256_bytes(
            self.module.canonical_json_bytes(header)
        )
        audit_path.write_text(
            json.dumps(
                header,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        audit_path.chmod(0o600)
        original_package = {
            path.name: path.read_bytes()
            for path in handoff.iterdir()
            if path.is_file()
        }

        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(handoff),
                "--confirm-controller-lost",
            ).stdout
        )
        self.assertEqual("global_only_faulted", recovered["recovery_mode"])
        self.assertFalse(recovered["package_evidence_recovered"])
        self.assertEqual("invalid", recovered["audit"]["condition"])
        self.assertEqual("AUDIT_OR_STATE_MISMATCH", recovered["audit"]["code"])
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertTrue(recovered["orphan_child_may_remain"])
        self.assertFalse(recovered["tunnel_runtime_stopped"])
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            "controller_lost_evidence_mismatch",
            store.read()["orphaned_reason"],
        )
        self.assertEqual("invalid", store.read()["audit_recovery_status"])
        self.assertEqual(2, store.read()["audit_schema_version"])
        self.assertIsNone(self.load(handoff / "state.json")["mcp_session"])
        self.assertEqual(
            original_package,
            {
                path.name: path.read_bytes()
                for path in handoff.iterdir()
                if path.is_file()
            },
        )
        self.assertEqual(1, len(audit_path.read_text(encoding="utf-8").splitlines()))

    def test_prepublication_current_audit_rejects_stripped_global_accounting(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"prepublication-stripped-current").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )
        with store.locked() as transaction:
            runtime = transaction.read()
            runtime.pop("audit_schema_version")
            runtime.pop("disclosure_accounting")
            runtime["revision"] += 1
            runtime["updated_at"] = self.module.utc_now()
            transaction.write(runtime)
        original_package = {
            path.name: path.read_bytes()
            for path in handoff.iterdir()
            if path.is_file()
        }

        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(handoff),
                "--confirm-controller-lost",
            ).stdout
        )
        self.assertEqual("global_only_faulted", recovered["recovery_mode"])
        self.assertFalse(recovered["package_evidence_recovered"])
        self.assertEqual("invalid", recovered["audit"]["condition"])
        self.assertEqual("AUDIT_OR_STATE_MISMATCH", recovered["audit"]["code"])
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            "controller_lost_evidence_mismatch", store.read()["orphaned_reason"]
        )
        self.assertEqual("invalid", store.read()["audit_recovery_status"])
        self.assertEqual(
            original_package,
            {
                path.name: path.read_bytes()
                for path in handoff.iterdir()
                if path.is_file()
            },
        )

    def test_prepublication_actual_legacy_audit_remains_closable(self) -> None:
        handoff = self.prepare_and_approve()
        verified, preflight = self.preflight(handoff)
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(b"prepublication-legacy-audit").hexdigest()
        self.module.begin_mcp_activation(
            verified,
            store,
            session_id_sha256=session_hash,
            preflight=preflight,
        )

        audit_path = handoff / "mcp-audit.jsonl"
        header = json.loads(audit_path.read_text(encoding="utf-8"))
        header["audit_schema_version"] = 1
        header.pop("accounting_mode")
        header.pop("event_sha256")
        header["event_sha256"] = self.module.sha256_bytes(
            self.module.canonical_json_bytes(header)
        )
        legacy_header = header["event_sha256"]
        audit_path.write_text(
            json.dumps(
                header,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        audit_path.chmod(0o600)

        # A genuine older pre-publication identity omitted the current pair
        # and bound the actual v1 header.  That exact historical shape remains
        # closure-compatible rather than being globally pinned to v2.
        with store.locked() as transaction:
            runtime = transaction.read()
            runtime.pop("audit_schema_version")
            runtime.pop("disclosure_accounting")
            runtime["audit_header_sha256"] = legacy_header
            runtime["revision"] += 1
            runtime["updated_at"] = self.module.utc_now()
            transaction.write(runtime)
        recovered = self.module.recover_interrupted_mcp_activation(handoff, store)
        self.assertEqual("revoked", recovered["authorization"]["status"])
        self.assertEqual(1, recovered["audit"]["audit_schema_version"])
        self.assertEqual(
            "legacy_tool_body_estimate",
            recovered["audit"]["disclosure_accounting"],
        )

    def test_recover_retires_nonwritable_post_bind_stale_socket_in_private_parent(self) -> None:
        handoff = self.prepare_and_approve()
        store, _ = self.interrupt_before_audit_header(handoff)
        control_path = self.module.control_socket_path(store.root)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(control_path))
        os.chmod(control_path, 0o755, follow_symlinks=False)
        stale.close()

        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(handoff),
                "--confirm-controller-lost",
            ).stdout
        )
        self.assertEqual("retired", recovered["control_socket"]["status"])
        self.assertTrue(recovered["control_socket"]["retired"])
        self.assertFalse(control_path.exists())

    def test_missing_handoff_can_record_global_only_attended_orphan_clearance(self) -> None:
        handoff = self.prepare_and_approve()
        store, session_hash, _ = self.activate(handoff)
        original_package = {
            path.name: path.read_bytes()
            for path in handoff.iterdir()
            if path.is_file()
        }
        saved = self.root / "saved-orphan-handoff"
        handoff.rename(saved)
        denied = self.module.deny_mcp_authorization_without_package(
            handoff,
            store,
            expected_session_id_sha256=session_hash,
        )
        self.assertEqual("faulted", denied["status"])
        self.assertNotIn("runtime_child_stopped", denied)
        self.assertNotIn("activation_child_stopped", denied)

        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(handoff),
                "--confirm-controller-lost",
                "--confirm-orphan-tunnel-stopped",
            ).stdout
        )

        self.assertFalse(recovered["package_evidence_recovered"])
        self.assertEqual("global_only_faulted", recovered["recovery_mode"])
        self.assertTrue(recovered["orphan_tunnel_termination_manually_confirmed"])
        self.assertFalse(recovered["orphan_child_may_remain"])
        self.assertFalse(recovered["tunnel_runtime_stopped"])
        runtime = store.read()
        self.assertTrue(runtime["orphan_tunnel_termination_manually_confirmed"])
        self.assertNotIn("runtime_child_stopped", runtime)
        self.assertNotIn("activation_child_stopped", runtime)
        self.assertFalse(handoff.exists())
        self.assertEqual(
            original_package,
            {
                path.name: path.read_bytes()
                for path in saved.iterdir()
                if path.is_file()
            },
        )

    def test_corrupt_audit_faults_authorization_without_rewriting_package_evidence(self) -> None:
        pre_handoff = self.prepare_and_approve()
        pre_runtime = self.use_runtime_home("pre-corrupt-home")
        pre_store, _ = self.interrupt_before_audit_header(
            pre_handoff, runtime_root=pre_runtime
        )
        (pre_handoff / "mcp-audit.jsonl").write_bytes(b"{not-json\n")
        (pre_handoff / "mcp-audit.jsonl").chmod(0o600)
        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(pre_handoff),
                "--confirm-controller-lost",
            ).stdout
        )
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertEqual("invalid", recovered["audit"]["condition"])
        self.assertEqual("faulted", pre_store.read()["status"])
        self.assertEqual(b"{not-json\n", (pre_handoff / "mcp-audit.jsonl").read_bytes())

        for condition in ("missing", "corrupt"):
            with self.subTest(active_audit=condition):
                runtime = self.use_runtime_home(f"active-{condition}-home")
                handoff = self.prepare_and_approve()
                store, _, _ = self.activate(handoff)
                audit_path = handoff / "mcp-audit.jsonl"
                if condition == "missing":
                    audit_path.unlink()
                else:
                    audit_path.write_bytes(b"{}\n")
                    audit_path.chmod(0o600)
                original_package = {
                    path.name: path.read_bytes()
                    for path in handoff.iterdir()
                    if path.is_file()
                }
                recovered = json.loads(
                    self.run_cli(
                    "mcp-recover",
                    "--handoff-dir",
                    str(handoff),
                    "--confirm-controller-lost",
                    ).stdout
                )
                self.assertEqual("global_only_faulted", recovered["recovery_mode"])
                self.assertFalse(recovered["package_evidence_recovered"])
                self.assertEqual("faulted", recovered["authorization"]["status"])
                self.assertTrue(recovered["orphan_child_may_remain"])
                self.assertFalse(recovered["process_discovery_attempted"])
                self.assertFalse(recovered["process_signal_attempted"])
                self.assertEqual("faulted", store.read()["status"])
                self.assertEqual("active", self.load(handoff / "state.json")["mcp_session"]["status"])
                self.assertEqual(
                    original_package,
                    {
                        path.name: path.read_bytes()
                        for path in handoff.iterdir()
                        if path.is_file()
                    },
                )

    def test_recover_rejects_wrong_handoff_and_faults_unavailable_package_without_process_kill(self) -> None:
        handoff = self.prepare_and_approve()
        store, _, _ = self.activate(handoff)
        other = self.root / "different-handoff"
        other.mkdir()
        rejected = self.run_cli(
            "mcp-recover",
            "--handoff-dir",
            str(other),
            "--confirm-controller-lost",
            expected=2,
        )
        self.assertIn("different handoff", rejected.stderr)
        self.assertEqual("active", store.read()["status"])

        (handoff / "state.json").unlink()
        recovered = json.loads(
            self.run_cli(
                "mcp-recover",
                "--handoff-dir",
                str(handoff),
                "--confirm-controller-lost",
            ).stdout
        )
        self.assertFalse(recovered["package_evidence_recovered"])
        self.assertEqual("faulted", recovered["authorization"]["status"])
        self.assertFalse(recovered["process_discovery_attempted"])
        self.assertFalse(recovered["process_signal_attempted"])
        self.assertTrue(recovered["orphan_child_may_remain"])
        self.assertFalse((handoff / "state.json").exists())
        self.assertEqual("faulted", store.read()["status"])

    def test_recover_does_not_retire_a_control_socket_with_a_live_listener(self) -> None:
        handoff = self.prepare_and_approve()
        store, _ = self.interrupt_before_audit_header(handoff)
        control_path = self.module.control_socket_path(store.root)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(control_path))
        os.chmod(control_path, 0o600, follow_symlinks=False)
        listener.listen(1)
        try:
            recovered = json.loads(
                self.run_cli(
                    "mcp-recover",
                    "--handoff-dir",
                    str(handoff),
                    "--confirm-controller-lost",
                ).stdout
            )
            self.assertEqual("listener_present", recovered["control_socket"]["status"])
            self.assertFalse(recovered["control_socket"]["retired"])
            self.assertTrue(recovered["orphan_child_may_remain"])
            self.assertTrue(control_path.exists())
        finally:
            listener.close()
            control_path.unlink(missing_ok=True)

    def test_audit_tamper_is_reported_and_schema2_mcp_commands_are_rejected(self) -> None:
        handoff = self.prepare_and_approve()
        self.activate(handoff)
        audit_path = handoff / "mcp-audit.jsonl"
        with audit_path.open("ab") as handle:
            handle.write(b"{}\n")
            handle.flush()
            os.fsync(handle.fileno())
        rejected = self.run_cli(
            "mcp-verify-audit",
            "--handoff-dir",
            str(handoff),
            expected=2,
        )
        self.assertIn("AUDIT_CHAIN_INVALID", rejected.stderr)

        legacy = self.prepare_and_approve(transport="paste")
        rejected_legacy = self.run_cli(
            "mcp-stop",
            "--handoff-dir",
            str(legacy),
            expected=2,
        )
        self.assertIn("schema-3", rejected_legacy.stderr)
        self.run_cli("verify", "--handoff-dir", str(legacy))


if __name__ == "__main__":
    unittest.main()
