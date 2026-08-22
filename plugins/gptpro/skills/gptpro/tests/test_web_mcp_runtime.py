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
        self.assertFalse(payload["credential_resolution"])
        self.assertFalse(payload["tunnel_client_execution"])
        inspect.assert_called_once()
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
                self.module.HandoffError, "MCP_INTERPRETER_PATH_DRIFT"
            ),
        ):
            self.module.command_mcp_activate(arguments)
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
        self.run_cli("verify", "--handoff-dir", str(handoff))
        self.run_cli("mcp-verify-audit", "--handoff-dir", str(handoff))

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
        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
        self.module.record_mcp_stopped(handoff, session_id_sha256=session_hash)
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
        self.run_cli("verify", "--handoff-dir", str(handoff))

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
        self.assertFalse(stopped["tunnel_runtime_stopped"])
        self.assertTrue(stopped["foreground_controller_stop_required"])
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

                with (
                    mock.patch.object(
                        self.module, "request_cooperative_stop", return_value=True
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
                self.assertEqual(
                    "PACKAGE_EVIDENCE_UNAVAILABLE", payload["audit"]["code"]
                )
                self.assertTrue(payload["cooperative_stop_requested"])
                self.assertFalse(payload["tunnel_runtime_stopped"])
                self.assertIsNone(payload["stop_evidence"])
                self.assertTrue(payload["controller_lease_released"])
                self.assertEqual("unconfirmed", payload["exact_tunnel_process_status"])
                self.assertTrue(payload["manual_process_review_required"])
                self.assertFalse(payload["foreground_controller_stop_required"])
                cooperative_stop.assert_called_once_with(
                    self.module.control_socket_path(store.root), session_hash
                )
                broad_signal.assert_not_called()

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
            del kwargs
            with self.assertRaises(self.module.RuntimeStateError) as profile_conflict:
                self.module.ProfileControllerLease(store.root).acquire()
            self.assertEqual(
                "PROFILE_OPERATION_CONFLICT", profile_conflict.exception.code
            )
            begun = hooks.begin_activation(session_hash)
            hooks.complete_activation(session_hash, begun["audit_header_sha256"])
            receipt_path = handoff / "receipt.json"
            damaged = b"{controller-revoke-package-damage\n"
            receipt_path.write_bytes(damaged)
            receipt_path.chmod(0o600)
            revoked = hooks.revoke_authorization("child_exit")
            observed["revoked"] = revoked
            observed["damaged"] = damaged
            return SimpleNamespace(
                status="stopped",
                session_id_sha256=session_hash,
                stop_reason="child_exit",
                control_plane_poll_confirmed=True,
                authorization_revoked=True,
                stopped_recorded=False,
                forced_exact_child=False,
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
        self.assertEqual("faulted", store.read()["status"])
        self.assertEqual(
            observed["damaged"], (handoff / "receipt.json").read_bytes()
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
        self.run_cli("verify", "--handoff-dir", str(handoff))

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

    def test_corrupt_pre_audit_crash_is_faulted_but_active_audit_corruption_is_not_rewritten(self) -> None:
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
                rejected = self.run_cli(
                    "mcp-recover",
                    "--handoff-dir",
                    str(handoff),
                    "--confirm-controller-lost",
                    expected=2,
                )
                self.assertIn("after package activation", rejected.stderr)
                self.assertEqual("active", store.read()["status"])
                self.assertEqual("active", self.load(handoff / "state.json")["mcp_session"]["status"])

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
