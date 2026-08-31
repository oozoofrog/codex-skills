from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_CLI = REPO_ROOT / "gptpro" / "scripts" / "gptpro.py"
MCP_CLI = REPO_ROOT / "gptpro-mcp" / "scripts" / "gptpro.py"
HANDSHAKE = REPO_ROOT / "gptpro-mcp" / "scripts" / "component_handshake.py"


def snapshot_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class InstallTransitionTests(unittest.TestCase):
    def run_cli(
        self, script: Path, *args: str, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(script), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(
            expected,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def test_component_capabilities_are_separate_and_compatible(self) -> None:
        base = json.loads(self.run_cli(BASE_CLI, "capabilities", "--json").stdout)
        mcp = json.loads(self.run_cli(MCP_CLI, "capabilities", "--json").stdout)
        self.assertEqual("gptpro", base["component"])
        self.assertFalse(base["mcp_runtime"])
        self.assertEqual("gptpro-mcp", mcp["component"])
        self.assertTrue(mcp["mcp_runtime"])
        self.assertEqual(
            base["context_export_contracts"],
            mcp["required_base_context_contracts"],
        )
        self.assertEqual(
            {"mcp-research": "aa5efa1f52d36a8e6d1300c638b97f6bd76a9ef229d7f74e37ab3e30ebddcf87"},
            mcp["tool_schema_sha256"],
        )
        self.assertIn("mcp-read", mcp["legacy_tool_schema_sha256"])

    def test_explicit_handshake_accepts_current_base(self) -> None:
        payload = json.loads(
            self.run_cli(
                HANDSHAKE,
                "--base-entrypoint",
                str(BASE_CLI.resolve()),
                "--json",
            ).stdout
        )
        self.assertTrue(payload["ok"])
        self.assertEqual("explicit", payload["selection_source"])

    def test_missing_descriptor_fails_closed_without_path_discovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gptpro-handshake-") as raw:
            missing = Path(raw) / "missing.json"
            result = self.run_cli(
                HANDSHAKE,
                "--descriptor",
                str(missing),
                "--json",
                expected=2,
            )
        error = json.loads(result.stderr)["error"]
        self.assertEqual("GPTPRO_BASE_COMPONENT_REQUIRED", error["code"])
        self.assertNotIn(str(Path.home()), error["message"])

    def test_operational_mcp_entrypoint_enforces_base_handshake(self) -> None:
        result = self.run_cli(
            MCP_CLI,
            "--error-format",
            "json",
            "preflight",
            "--repo",
            str(REPO_ROOT),
            "--transport",
            "mcp-research",
            "--json",
            expected=2,
        )
        error = json.loads(result.stderr)["error"]
        self.assertEqual("GPTPRO_BASE_COMPONENT_REQUIRED", error["code"])
        self.assertNotIn(str(Path.home()), error["message"])

    def test_base_mcp_operation_requires_optional_component(self) -> None:
        result = self.run_cli(
            BASE_CLI,
            "--error-format",
            "json",
            "mcp-status",
            "--handoff-dir",
            "/tmp/not-inspected-by-component-gate",
            expected=2,
        )
        error = json.loads(result.stderr)["error"]
        self.assertEqual("GPTPRO_MCP_COMPONENT_REQUIRED", error["code"])

    def test_base_delegates_package_verify_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gptpro-package-offline-") as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)

            tunnel_ref = root / "tunnel-id"
            tunnel_ref.write_text(
                "tunnel_0123456789abcdefghijklmnopqrstuv\n", encoding="utf-8"
            )
            os.chmod(tunnel_ref, 0o600)
            output_root = root / "handoffs"
            prepared = self.run_cli(
                MCP_CLI,
                "--base-entrypoint",
                str(BASE_CLI.resolve()),
                "prepare",
                "--repo",
                str(repo),
                "--mode",
                "review",
                "--task",
                "offline compatibility fixture",
                "--transport",
                "mcp-research",
                "--include",
                "README.md",
                "--output-root",
                str(output_root),
                "--tunnel-id-ref",
                f"file:{tunnel_ref}",
                "--tunnel-runtime-alias",
                "fixture-profile",
                "--chatgpt-app-name",
                "Fixture App",
                "--chatgpt-workspace-label",
                "Fixture Workspace",
            )
            package = Path(json.loads(prepared.stdout)["handoff_dir"])
            before = snapshot_tree(package)
            verified = json.loads(
                self.run_cli(
                    BASE_CLI,
                    "--mcp-entrypoint",
                    str(MCP_CLI.resolve()),
                    "verify",
                    "--handoff-dir",
                    str(package),
                ).stdout
            )
            self.assertTrue(verified["verified"])
            self.assertEqual(4, verified["schema_version"])
            optional_offline = json.loads(
                self.run_cli(MCP_CLI, "verify", "--handoff-dir", str(package)).stdout
            )
            self.assertTrue(optional_offline["verified"])
            self.assertEqual(before, snapshot_tree(package))


if __name__ == "__main__":
    unittest.main()
