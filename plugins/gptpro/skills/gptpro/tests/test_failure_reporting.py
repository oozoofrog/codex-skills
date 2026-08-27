from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"


def load_cli_module():
    name = f"gptpro_failure_reporting_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FailureReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gptpro-reporting-")
        self.root = Path(self.temporary.name).resolve()
        self.runtime_root = self.root / "runtime"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.name", "Failure Reporting Test")
        self.git("config", "user.email", "failure@example.com")
        (self.repo / "README.md").write_text("# fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "fixture")
        self.module = load_cli_module()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def run_main(self, *args: str) -> subprocess.CompletedProcess[str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                self.module, "default_runtime_root", return_value=self.runtime_root
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            returncode = self.module.main(list(args))
        return subprocess.CompletedProcess(
            [sys.executable, str(SCRIPT), *args],
            returncode,
            stdout.getvalue(),
            stderr.getvalue(),
        )

    def prepare(self) -> Path:
        result = self.run_main(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Review this fixture.",
            "--transport",
            "paste",
            "--output-root",
            str(self.root / "handoffs"),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return Path(json.loads(result.stdout)["handoff_dir"])

    @staticmethod
    def tree_snapshot(root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def runtime_candidate(
        self, *, package_id: str = "other-private-package", expired: bool = False
    ) -> tuple[dict, str]:
        session_hash = hashlib.sha256(b"failure-reporting-session").hexdigest()
        now = datetime.now(timezone.utc)
        monotonic_now = time.monotonic()
        activated = now - timedelta(hours=2) if expired else now
        expires = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
        activated_mono = monotonic_now - 7200 if expired else monotonic_now
        expires_mono = monotonic_now - 3600 if expired else monotonic_now + 3600
        candidate = {
            "schema_version": 1,
            "revision": 1,
            "status": "activating",
            "package_id": package_id,
            "session_id_sha256": session_hash,
            "handoff_dir": str((self.root / "other-handoff").resolve()),
            "manifest_sha256": hashlib.sha256(b"other-manifest").hexdigest(),
            "approval_event_sha256": hashlib.sha256(b"approval").hexdigest(),
            "archive_sha256": hashlib.sha256(b"archive").hexdigest(),
            "file_set_sha256": hashlib.sha256(b"files").hexdigest(),
            "tool_schema_sha256": self.module.tool_schema_sha256(),
            "mcp_target_sha256": hashlib.sha256(b"target").hexdigest(),
            "tunnel_profile_sha256": hashlib.sha256(b"profile").hexdigest(),
            "tunnel_client_binary_sha256": hashlib.sha256(b"client").hexdigest(),
            "mcp_runtime_tree_sha256": hashlib.sha256(b"runtime").hexdigest(),
            "activated_at": activated.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "idle_ttl_seconds": 900,
            "activated_monotonic": activated_mono,
            "expires_monotonic": expires_mono,
            "last_activity_monotonic": activated_mono,
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        }
        return candidate, session_hash

    def test_text_error_output_and_exit_code_are_unchanged(self) -> None:
        missing = self.root / "missing"
        result = self.run_main("verify", "--handoff-dir", str(missing))
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertTrue(result.stderr.startswith("Error: "))

    def test_json_errors_cover_explicit_fallback_tool_parse_and_internal(self) -> None:
        with mock.patch.object(
            self.module,
            "command_verify",
            side_effect=self.module.HandoffError("EXPLICIT_FAILURE: refined explanation"),
        ):
            explicit = self.run_main(
                "--error-format", "json", "verify", "--handoff-dir", str(self.root)
            )
        explicit_payload = json.loads(explicit.stderr)
        self.assertEqual("EXPLICIT_FAILURE", explicit_payload["error"]["code"])
        self.assertEqual("refined explanation", explicit_payload["error"]["message"])

        fallback = self.run_main(
            "--error-format", "json", "verify", "--handoff-dir", str(self.root / "missing")
        )
        self.assertEqual(2, fallback.returncode)
        self.assertEqual("GPTPRO_VERIFY_FAILED", json.loads(fallback.stderr)["error"]["code"])

        tool_error = self.module.ToolError(
            "TOOL_STABLE",
            "Safe failure.",
            retryable=True,
            recovery="Retry the same read-only check.",
        )
        with mock.patch.object(self.module, "command_verify", side_effect=tool_error):
            tool = self.run_main(
                "--error-format", "json", "verify", "--handoff-dir", str(self.root)
            )
        tool_payload = json.loads(tool.stderr)
        self.assertEqual("TOOL_STABLE", tool_payload["error"]["code"])
        self.assertTrue(tool_payload["error"]["automatic_retry_allowed"])
        self.assertEqual("Retry the same read-only check.", tool_payload["error"]["recovery"])

        parsing = self.run_main("--error-format", "json", "verify")
        self.assertEqual(2, parsing.returncode)
        self.assertEqual("GPTPRO_ARGUMENT_ERROR", json.loads(parsing.stderr)["error"]["code"])

        secret = "sk-" + "z" * 32
        with mock.patch.object(
            self.module, "command_verify", side_effect=RuntimeError(f"boom {secret}")
        ):
            internal = self.run_main(
                "--error-format", "json", "verify", "--handoff-dir", str(self.root)
            )
        self.assertEqual(3, internal.returncode)
        self.assertEqual("GPTPRO_INTERNAL_ERROR", json.loads(internal.stderr)["error"]["code"])
        self.assertNotIn(secret, internal.stderr)
        self.assertNotIn("Traceback", internal.stderr)

    def test_json_error_redacts_referenced_environment_value(self) -> None:
        environment_secret = "opaque-runtime-value-not-matched-by-pattern"
        with (
            mock.patch.dict(os.environ, {"FAILURE_RUNTIME_KEY": environment_secret}),
            mock.patch.object(
                self.module,
                "command_mcp_profile_init",
                side_effect=self.module.HandoffError(
                    f"PROFILE_FAILED: runtime rejected {environment_secret}"
                ),
            ),
        ):
            result = self.run_main(
                "--error-format",
                "json",
                "mcp-profile-init",
                "--tunnel-profile",
                "test-profile",
                "--tunnel-id-ref",
                "env:FAILURE_TUNNEL_ID",
                "--runtime-api-key-ref",
                "env:FAILURE_RUNTIME_KEY",
                "--tunnel-client",
                "/tmp/tunnel-client",
                "--confirm-tunnel-client-sha256",
                "0" * 64,
            )
        self.assertEqual(2, result.returncode)
        self.assertEqual("PROFILE_FAILED", json.loads(result.stderr)["error"]["code"])
        self.assertNotIn(environment_secret, result.stderr)
        self.assertIn("[REDACTED]", result.stderr)

    def test_failure_reporting_contract_covers_required_fields_and_forward_cases(self) -> None:
        skill_root = SCRIPT.parent.parent
        reference = (skill_root / "references" / "failure-reporting.md").read_text(
            encoding="utf-8"
        )
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "실패한 단계와 작업",
            "기대한 결과와 실제 관찰",
            "정제된 오류 코드와 설명",
            "전송·승인·저장소 변경 여부",
            "현재 package/Tunnel 상태",
            "자동 재시도 가능 여부",
            "사용자가 해야 할 다음 조치",
            "secret prepare",
            "MCP_INTERPRETER_PATH_DRIFT",
            "controller lease",
            "browser submission",
            "상태 조회 자체 실패",
        ):
            self.assertIn(required, reference)
        self.assertIn("references/failure-reporting.md", skill)

    def test_diagnostic_status_uses_json_for_unexpected_errors_even_without_global_flag(self) -> None:
        with mock.patch.object(
            self.module,
            "command_diagnostic_status",
            side_effect=RuntimeError("unexpected private diagnostic"),
        ):
            result = self.run_main("diagnostic-status")
        self.assertEqual(3, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("GPTPRO_INTERNAL_ERROR", json.loads(result.stderr)["error"]["code"])
        self.assertNotIn("unexpected private diagnostic", result.stderr)

    def test_diagnostic_status_does_not_create_missing_runtime_root(self) -> None:
        result = self.run_main("--error-format", "json", "diagnostic-status")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["observation_only"])
        self.assertFalse(payload["mutations_performed"])
        self.assertEqual("not_provided", payload["package"]["availability"])
        self.assertEqual("absent", payload["tunnel"]["recorded_status"])
        self.assertFalse(self.runtime_root.exists())

    def test_diagnostic_status_does_not_create_lock_in_existing_runtime_root(self) -> None:
        self.runtime_root.mkdir(mode=0o700)
        before = self.tree_snapshot(self.runtime_root)
        result = self.run_main("--error-format", "json", "diagnostic-status")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.tree_snapshot(self.runtime_root))
        self.assertFalse((self.runtime_root / "lock").exists())

    def test_pending_lifecycle_is_reported_without_recovery_or_mutation(self) -> None:
        handoff = self.prepare()
        lock_root = handoff.parent / ".gptpro-lifecycle-locks"
        lock_root.mkdir(mode=0o700)
        identity = hashlib.sha256(str(handoff.resolve()).encode("utf-8")).hexdigest()
        journal = lock_root / f"{identity}.journal.json"
        journal.write_text("not parsed in observation mode\n", encoding="utf-8")
        os.chmod(journal, 0o600)
        before = self.tree_snapshot(handoff.parent)
        result = self.run_main(
            "--error-format", "json", "diagnostic-status", "--handoff-dir", str(handoff)
        )
        after = self.tree_snapshot(handoff.parent)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("partial", payload["package"]["availability"])
        self.assertEqual("PACKAGE_LIFECYCLE_PENDING", payload["package"]["code"])
        self.assertEqual(before, after)
        self.assertTrue(journal.exists())

    def test_damaged_package_is_partial_and_remains_byte_identical(self) -> None:
        handoff = self.prepare()
        (handoff / "prompt.md").write_text("tampered\n", encoding="utf-8")
        before = self.tree_snapshot(handoff)
        result = self.run_main("diagnostic-status", "--handoff-dir", str(handoff))
        after = self.tree_snapshot(handoff)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("partial", payload["package"]["availability"])
        self.assertEqual("GPTPRO_DIAGNOSTIC_STATUS_FAILED", payload["package"]["code"])
        self.assertEqual("unknown", payload["package"]["approval"])
        self.assertEqual("unknown", payload["package"]["submission"])
        self.assertEqual(before, after)

    def test_elapsed_runtime_and_lease_are_observed_without_writes(self) -> None:
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        candidate, session_hash = self.runtime_candidate(expired=True)
        store.begin_activation(candidate)
        lease = self.runtime_root / f"controller-{session_hash}.lock"
        descriptor = os.open(lease, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            before = self.tree_snapshot(self.runtime_root)
            result = self.run_main("--error-format", "json", "diagnostic-status")
            after = self.tree_snapshot(self.runtime_root)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        payload = json.loads(result.stdout)
        self.assertEqual("activating", payload["tunnel"]["recorded_status"])
        self.assertTrue(payload["tunnel"]["ttl_elapsed"])
        self.assertEqual("live", payload["tunnel"]["controller_lease"])
        self.assertEqual(before, after)

    def test_absent_controller_lease_is_observed_without_creating_it(self) -> None:
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        candidate, session_hash = self.runtime_candidate()
        store.begin_activation(candidate)
        lease = self.runtime_root / f"controller-{session_hash}.lock"
        before = self.tree_snapshot(self.runtime_root)
        result = self.run_main("diagnostic-status")
        self.assertEqual("absent", json.loads(result.stdout)["tunnel"]["controller_lease"])
        self.assertFalse(lease.exists())
        self.assertEqual(before, self.tree_snapshot(self.runtime_root))

    def test_different_package_binding_does_not_disclose_other_identity(self) -> None:
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        candidate, _ = self.runtime_candidate(package_id="private-other-package")
        store.begin_activation(candidate)
        package_summary = {
            "availability": "verified",
            "code": None,
            "package_id": "requested-package",
            "phase": "approved",
            "transport": "mcp-research",
            "approval": "recorded",
            "submission": "not_recorded",
        }
        verified = {
            "schema_version": 4,
            "manifest": {"package_id": "requested-package"},
            "manifest_sha256": hashlib.sha256(b"requested-manifest").hexdigest(),
            "state": {"mcp_session": None},
        }
        with mock.patch.object(
            self.module,
            "_diagnostic_package_summary",
            return_value=(package_summary, verified),
        ):
            result = self.run_main(
                "--error-format", "json", "diagnostic-status", "--handoff-dir", str(self.root)
            )
        payload = json.loads(result.stdout)
        self.assertEqual("different_package", payload["tunnel"]["package_binding"])
        self.assertNotIn("private-other-package", result.stdout)


if __name__ == "__main__":
    unittest.main()
