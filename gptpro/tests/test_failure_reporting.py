from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "gptpro" / "scripts" / "gptpro.py"
SPEC = importlib.util.spec_from_file_location("gptpro_cli_v05", SCRIPT)
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class FailureReportingTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [os.sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_json_argument_error_is_stable_and_sanitized(self) -> None:
        result = self.run_cli("--error-format", "json", "verify")
        self.assertEqual(2, result.returncode)
        envelope = json.loads(result.stderr)
        self.assertEqual("GPTPRO_ARGUMENT_ERROR", envelope["error"]["code"])
        self.assertTrue(envelope["error"]["sanitized"])
        self.assertNotIn("Traceback", result.stderr)

    def test_text_error_contains_all_seven_user_fields(self) -> None:
        result = self.run_cli("verify")
        self.assertEqual(2, result.returncode)
        for label in (
            "실패 단계:",
            "기대한 결과/관찰:",
            "오류:",
            "승인·저장소 변경:",
            "package/Tunnel 상태:",
            "자동 재시도:",
            "다음 조치:",
        ):
            self.assertIn(label, result.stderr)

    def test_unexpected_exception_hides_original_and_traceback(self) -> None:
        stderr = io.StringIO()
        stdout = io.StringIO()
        with (
            mock.patch.object(CLI, "run", side_effect=RuntimeError("sk-secret-value-and-trace")),
            redirect_stderr(stderr),
            redirect_stdout(stdout),
        ):
            code = CLI.main(["--error-format", "json", "capabilities"])
        self.assertEqual(3, code)
        envelope = json.loads(stderr.getvalue())
        self.assertEqual("GPTPRO_INTERNAL_ERROR", envelope["error"]["code"])
        self.assertNotIn("sk-secret-value", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_secret_prepare_error_does_not_echo_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
            (repo / "README.md").write_text(secret + "\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
            result = self.run_cli(
                "--error-format",
                "json",
                "prepare",
                "--repo",
                str(repo),
                "--mode",
                "review",
                "--include",
                "README.md",
                "--task",
                "review",
            )
        self.assertEqual(2, result.returncode)
        self.assertNotIn(secret, result.stderr)
        self.assertEqual("SECRET_DETECTED", json.loads(result.stderr)["error"]["code"])

    def test_diagnostic_without_package_is_observation_only_and_tunnel_not_applicable(self) -> None:
        result = self.run_cli("--error-format", "json", "diagnostic-status", "--json")
        self.assertEqual(0, result.returncode, msg=result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["observation_only"])
        self.assertFalse(value["mutations_performed"])
        self.assertFalse(value["tunnel"]["applicable"])
        self.assertEqual("not_provided", value["package"]["availability"])

    def test_legacy_command_reports_removed_transport(self) -> None:
        result = self.run_cli("--error-format", "json", "mcp-status")
        self.assertEqual(2, result.returncode)
        envelope = json.loads(result.stderr)
        self.assertEqual("GPTPRO_LEGACY_TRANSPORT_REMOVED", envelope["error"]["code"])
        self.assertIn("Secure MCP Tunnel", envelope["error"]["message"])


if __name__ == "__main__":
    unittest.main()
