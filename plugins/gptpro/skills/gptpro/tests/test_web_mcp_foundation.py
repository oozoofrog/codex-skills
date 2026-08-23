from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"
VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate_structure.py"
SKILL_ROOT = Path(__file__).resolve().parents[1]
TUNNEL_ENV_NAME = "GPTPRO_TEST_TUNNEL_ID"
TUNNEL_REFERENCE = f"env:{TUNNEL_ENV_NAME}"
RAW_TUNNEL_ID = "tunnel_" + "foundationtest" * 2
APP_NAME = "GPT Pro Repository Reader"
WORKSPACE_LABEL = "Test Workspace"
EXPECTED_TOOLS = [
    "gptpro_package_info",
    "gptpro_repo_read",
    "gptpro_repo_search",
]


class WebMcpFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.output_root = self.root / "handoffs"
        self.git("init")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text(
            "def answer():\n    return 42\n",
            encoding="utf-8",
        )
        (self.repo / "src" / "repetitive.txt").write_text(
            "approved snapshot fixture\n" * 8_192,
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.git("add", "src/main.py", "src/repetitive.txt", "README.md")
        self.git("commit", "-m", "fixture")
        self.env = os.environ.copy()
        self.env[TUNNEL_ENV_NAME] = RAW_TUNNEL_ID
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(
            expected,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    @staticmethod
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def load_cli_module():
        module_name = "gptpro_foundation_test_module"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("Unable to load gptpro.py for pure boundary tests")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def prepare_mcp(self) -> tuple[Path, subprocess.CompletedProcess[str]]:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-read",
            "--task",
            "Review the immutable repository snapshot.",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            "foundation-test",
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--approval-ttl-seconds",
            "600",
            "--max-tool-calls",
            "7",
            "--session-ttl-seconds",
            "600",
            "--idle-ttl-seconds",
            "300",
        )
        return Path(json.loads(result.stdout)["handoff_dir"]), result

    def test_schema3_manifest_basis_rejects_deep_extra_without_traceback(self) -> None:
        handoff, _ = self.prepare_mcp()
        manifest_path = handoff / "manifest.json"
        manifest = self.load(manifest_path)
        module = self.load_cli_module()
        original_hashes = copy.deepcopy(manifest["hashes"])
        nested: object = 0
        for _ in range(module.MAX_JSON_NESTING_DEPTH + 1):
            nested = {"child": nested}
        manifest["unexpected_nested_value"] = nested

        with self.assertRaises(module.HandoffError):
            module.mcp_manifest_basis(manifest)
        self.assertEqual(original_hashes, manifest["hashes"])

        self.write_json(manifest_path, manifest)
        rejected = self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)
        self.assertIn("maximum JSON nesting depth", rejected.stderr)
        self.assertNotIn("Traceback", rejected.stderr)

    def approve_mcp(self, handoff: Path) -> None:
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
            "--confirm-mcp-disclosure",
        )

    def assert_tunnel_secret_absent(self, text: str | bytes) -> None:
        payload = text.encode("utf-8") if isinstance(text, str) else text
        for forbidden in (RAW_TUNNEL_ID, TUNNEL_REFERENCE, TUNNEL_ENV_NAME):
            self.assertNotIn(forbidden.encode("utf-8"), payload)

    def test_explicit_mcp_read_creates_verified_schema3_prompt_only_package(self) -> None:
        handoff, prepare_result = self.prepare_mcp()
        manifest = self.load(handoff / "manifest.json")
        summary = json.loads(prepare_result.stdout)

        self.assertEqual(3, manifest["schema_version"])
        self.assertEqual("mcp-read", manifest["transport"]["requested"])
        self.assertEqual("mcp-read", manifest["transport"]["resolved"])
        self.assertEqual(
            [{"role": "message", "artifact": "prompt", "bytes": (handoff / "prompt.md").stat().st_size,
              "sha256": manifest["hashes"]["prompt_sha256"]}],
            manifest["transport"]["outbound_artifacts"],
        )
        self.assertNotIn("context", manifest["artifacts"])
        self.assertNotIn("paste_payload", manifest["artifacts"])
        self.assertNotIn("context_sha256", manifest["hashes"])
        self.assertNotIn("paste_payload_sha256", manifest["hashes"])
        self.assertNotIn("context_markers", manifest)
        self.assertEqual(["prompt.md"], sorted(path.name for path in handoff.glob("*.md")))
        self.assertEqual(0o700, stat.S_IMODE(handoff.stat().st_mode))
        self.assertEqual(
            0o600,
            stat.S_IMODE((handoff / f"context-{manifest['package_id']}.zip").stat().st_mode),
        )

        self.assertEqual(
            {"channel": "browser", "approval_required": True},
            manifest["delivery"],
        )
        connector = manifest["connector"]
        self.assertEqual("secure-mcp-tunnel", connector["type"])
        self.assertEqual("foundation-test", connector["tunnel_profile_alias"])
        self.assertEqual(APP_NAME, connector["app_name"])
        self.assertEqual(WORKSPACE_LABEL, connector["workspace_label"])
        self.assertTrue(connector["workspace_binding_required"])

        self.assertRegex(connector["tunnel_id_binding_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(connector["tool_schema_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("openai-tunnel-legacy-tools-v1", connector["protocol_profile"])

        disclosure = manifest["mcp_disclosure"]
        prompt = (handoff / "prompt.md").read_text(encoding="utf-8")
        expected_files = [
            {key: item[key] for key in ("path", "size", "sha256")}
            for item in manifest["files"]
        ]
        expected_file_set_hash = hashlib.sha256(
            json.dumps(
                expected_files,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual("immutable-local-archive", disclosure["snapshot"])
        self.assertEqual(expected_files, disclosure["allowed_files"])
        self.assertEqual(expected_file_set_hash, disclosure["file_set_sha256"])
        self.assertEqual(expected_file_set_hash, manifest["hashes"]["file_set_sha256"])
        self.assertEqual(EXPECTED_TOOLS, disclosure["tools"])
        self.assertEqual(7, disclosure["limits"]["max_tool_calls"])
        self.assertEqual(600, disclosure["limits"]["session_ttl_seconds"])
        self.assertEqual(300, disclosure["limits"]["idle_ttl_seconds"])
        compact_limits = json.dumps(
            disclosure["limits"], sort_keys=True, separators=(",", ":")
        )
        self.assertIn(f"Approved hard limits (compact JSON): `{compact_limits}`.", prompt)
        self.assertIn("`include_paths=true` and `path_page_size=1`", prompt)
        self.assertIn("Invalid and rejected tool attempts consume", prompt)
        expiry = datetime.fromisoformat(
            disclosure["approval_valid_until"].removesuffix("Z") + "+00:00"
        )
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 600)
        self.assertRegex(manifest["hashes"]["approval_basis_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["hashes"]["manifest_basis_sha256"], r"^[0-9a-f]{64}$")

        verify_result = self.run_cli("verify", "--handoff-dir", str(handoff))
        verified = json.loads(verify_result.stdout)
        self.assertTrue(verified["verified"])
        self.assertEqual(3, verified["schema_version"])
        self.assertEqual("mcp-read", verified["transport"])
        self.assertEqual("secure-mcp-tunnel", verified["connector_type"])
        status_result = self.run_cli("status", "--handoff-dir", str(handoff))
        status = json.loads(status_result.stdout)
        self.assertIsNone(status["context_path"])
        self.assertIsNone(status["paste_payload_path"])
        self.assertEqual(["prompt"], [item["artifact"] for item in status["outbound_paths"]])

        for output in (prepare_result.stdout, prepare_result.stderr, verify_result.stdout, status_result.stdout):
            self.assert_tunnel_secret_absent(output)
        self.assert_tunnel_secret_absent(json.dumps(manifest, sort_keys=True))
        for artifact in handoff.iterdir():
            if artifact.is_file():
                self.assert_tunnel_secret_absent(artifact.read_bytes())
        with zipfile.ZipFile(handoff / manifest["artifacts"]["archive"], "r") as archive:
            self.assertTrue(
                all(member.compress_type == zipfile.ZIP_STORED for member in archive.infolist())
            )
            for member in archive.namelist():
                self.assert_tunnel_secret_absent(archive.read(member))
        self.assertNotIn(RAW_TUNNEL_ID, json.dumps(summary, sort_keys=True))

    def test_tunnel_id_environment_is_not_forwarded_to_git_hooks(self) -> None:
        capture = self.root / "git-hook-environment.txt"
        hook = self.root / "fsmonitor-hook.py"
        hook.write_text(
            "#!/usr/bin/env python3\n"
            "import os\n"
            "from pathlib import Path\n"
            f"Path({str(capture)!r}).write_text(os.environ.get({TUNNEL_ENV_NAME!r}, '<absent>'))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        hook.chmod(0o700)
        self.git("config", "core.fsmonitor", str(hook))

        self.prepare_mcp()

        self.assertTrue(capture.is_file(), "Git fsmonitor hook was not exercised")
        self.assertEqual("<absent>", capture.read_text(encoding="utf-8"))

    def test_structure_validator_never_executes_candidate_schema(self) -> None:
        candidate = self.root / "candidate-skill"
        marker = self.root / "validator-side-effect.txt"
        shutil.copytree(SKILL_ROOT, candidate)
        schema = candidate / "runtime" / "gptpro_mcp" / "schema.py"
        schema.write_text(
            schema.read_text(encoding="utf-8")
            + f"\nopen({str(marker)!r}, 'w', encoding='utf-8').write('executed')\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--skill-dir", str(candidate), "--json"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertFalse(marker.exists())
        self.assertIn("unsafe or unexpected top-level structure", result.stdout)

    def test_auto_remains_schema2_and_never_resolves_mcp_read(self) -> None:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--transport",
            "auto",
            "--task",
            "Explain the fixture.",
            "--output-root",
            str(self.output_root),
        )
        handoff = Path(json.loads(result.stdout)["handoff_dir"])
        manifest = self.load(handoff / "manifest.json")
        self.assertEqual(2, manifest["schema_version"])
        self.assertEqual("auto", manifest["transport"]["requested"])
        self.assertIn(manifest["transport"]["resolved"], {"github", "paste", "text-file"})
        self.assertNotEqual("mcp-read", manifest["transport"]["resolved"])
        self.assertNotIn("connector", manifest)
        self.assertNotIn("mcp_disclosure", manifest)
        verified = json.loads(
            self.run_cli("verify", "--handoff-dir", str(handoff)).stdout
        )
        self.assertEqual(2, verified["schema_version"])
        self.assertNotEqual("mcp-read", verified["transport"])

    def test_mcp_approval_requires_both_flags_and_binds_maximum_disclosure(self) -> None:
        handoff, _ = self.prepare_mcp()
        manifest = self.load(handoff / "manifest.json")

        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-mcp-disclosure",
            expected=2,
        )
        self.assertEqual("prepared", self.load(handoff / "state.json")["phase"])
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
            expected=2,
        )
        self.assertEqual("prepared", self.load(handoff / "state.json")["phase"])

        self.approve_mcp(handoff)
        state = self.load(handoff / "state.json")
        approval = state["approval"]
        self.assertEqual("approved", state["phase"])
        self.assertEqual("maximum-dynamic-disclosure", approval["approval_meaning"])
        self.assertEqual(manifest["hashes"]["approval_basis_sha256"], approval["approval_basis_sha256"])
        self.assertEqual(manifest["connector"]["tunnel_id_binding_sha256"], approval["tunnel_id_binding_sha256"])
        self.assertEqual(manifest["connector"]["tool_schema_sha256"], approval["tool_schema_sha256"])
        self.assertEqual(manifest["connector"]["protocol_profile"], approval["protocol_profile"])
        self.assertEqual(manifest["mcp_disclosure"]["file_set_sha256"], approval["file_set_sha256"])
        self.assertEqual(manifest["mcp_disclosure"]["potential_files"], approval["potential_files"])
        self.assertEqual(manifest["mcp_disclosure"]["potential_bytes"], approval["potential_bytes"])
        self.assertEqual(manifest["mcp_disclosure"]["limits"], approval["limits"])
        self.assertEqual(manifest["mcp_disclosure"]["approval_valid_until"], approval["approval_valid_until"])
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(approval, receipt["events"][-1]["data"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_connector_file_set_limits_and_approval_basis_tampering_is_rejected(self) -> None:
        handoff, _ = self.prepare_mcp()
        manifest_path = handoff / "manifest.json"
        original = self.load(manifest_path)

        cases = (
            (
                "connector",
                lambda value: value["connector"].__setitem__("protocol_profile", "unsupported-profile"),
                "connector contract",
            ),
            (
                "file-set",
                lambda value: value["mcp_disclosure"]["allowed_files"][0].__setitem__("sha256", "0" * 64),
                "maximum disclosure set",
            ),
            (
                "limits",
                lambda value: value["mcp_disclosure"]["limits"].__setitem__("max_tool_calls", 0),
                "limits are invalid",
            ),
            (
                "package-limits",
                lambda value: value["limits"].__setitem__("max_file_bytes", 3 * 1024 * 1024),
                "package limit max_file_bytes is invalid",
            ),
            (
                "approval-lifetime",
                lambda value: value["mcp_disclosure"].__setitem__(
                    "approval_valid_until", "2099-01-01T00:00:00Z"
                ),
                "approval lifetime is outside",
            ),
            (
                "approval-basis",
                lambda value: value["hashes"].__setitem__("approval_basis_sha256", "0" * 64),
                "approval-basis hash mismatch",
            ),
        )
        for label, mutate, expected_error in cases:
            with self.subTest(label=label):
                tampered = copy.deepcopy(original)
                mutate(tampered)
                self.write_json(manifest_path, tampered)
                result = self.run_cli(
                    "verify",
                    "--handoff-dir",
                    str(handoff),
                    expected=2,
                )
                self.assertIn(expected_error, result.stderr)
                self.write_json(manifest_path, original)
                self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_prepared_receipt_is_cross_bound_to_current_package(self) -> None:
        handoff, _ = self.prepare_mcp()
        receipt_path = handoff / "receipt.json"
        receipt = self.load(receipt_path)
        prepared = receipt["events"][0]
        prepared["data"]["manifest_sha256"] = "0" * 64
        payload = {key: value for key, value in prepared.items() if key != "event_hash"}
        prepared["event_hash"] = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.write_json(receipt_path, receipt)

        result = self.run_cli(
            "verify",
            "--handoff-dir",
            str(handoff),
            expected=2,
        )
        self.assertIn("Prepared receipt data does not match", result.stderr)

    def test_mcp_read_rejects_package_limits_above_archive_policy(self) -> None:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-read",
            "--task",
            "Review the immutable repository snapshot.",
            "--output-root",
            str(self.output_root),
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--max-file-bytes",
            str(5 * 1024 * 1024),
            expected=2,
        )
        self.assertIn("--max-file-bytes must not exceed the hard limit", result.stderr)
        self.assertFalse(self.output_root.exists())

    def test_schema3_rejects_late_nul_before_writing_but_schema2_remains_readable(self) -> None:
        late_nul = self.repo / "src" / "late-nul.txt"
        late_nul.write_bytes(b"a" * 9_000 + b"\0tail\n")
        self.git("add", "src/late-nul.txt")
        self.git("commit", "-m", "add legacy late-NUL fixture")

        rejected_root = self.root / "rejected-nul"
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-read",
            "--task",
            "Review the immutable repository snapshot.",
            "--output-root",
            str(rejected_root),
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("selected file contains NUL bytes", result.stderr)
        self.assertFalse(rejected_root.exists())

        legacy_result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "text-file",
            "--task",
            "Verify schema-2 compatibility.",
            "--output-root",
            str(self.root / "legacy-nul"),
        )
        legacy_handoff = Path(json.loads(legacy_result.stdout)["handoff_dir"])
        verified = json.loads(
            self.run_cli("verify", "--handoff-dir", str(legacy_handoff)).stdout
        )
        self.assertEqual(2, verified["schema_version"])

    def test_schema3_archive_plan_rejects_derived_path_and_directory_overflow(self) -> None:
        module = self.load_cli_module()
        too_long = module.SelectedFile(
            path="a/" + "b" * 1_018,
            content=b"x",
            sha256=hashlib.sha256(b"x").hexdigest(),
            size=1,
        )
        with self.assertRaisesRegex(module.HandoffError, "selected archive path.*too long"):
            module.validate_schema3_selection([too_long])

        files = []
        for index in range(2_000):
            path = f"p{index:04d}/" + "x" * 995
            files.append(
                module.SelectedFile(
                    path=path,
                    content=b"x",
                    sha256=hashlib.sha256(b"x").hexdigest(),
                    size=1,
                )
            )
        module.validate_schema3_selection(files)
        with self.assertRaisesRegex(module.HandoffError, "central directory would exceed"):
            module.validate_schema3_archive_plan(files, b"{}")

        with self.assertRaisesRegex(module.HandoffError, "internal manifest exceeds"):
            module.validate_schema3_archive_plan(
                [],
                b"x" * (module.SCHEMA3_INTERNAL_MANIFEST_MAX_BYTES + 1),
            )

    def test_tunnel_identifiers_are_excluded_from_files_and_rejected_in_metadata(self) -> None:
        secret_path = self.repo / "src" / "tunnel-note.txt"
        secret_path.write_text(f"temporary tunnel is {RAW_TUNNEL_ID}\n", encoding="utf-8")
        self.git("add", "src/tunnel-note.txt")
        self.git("commit", "-m", "add tunnel fixture")

        handoff, _ = self.prepare_mcp()
        manifest = self.load(handoff / "manifest.json")
        finding = next(
            item for item in manifest["security_findings"] if item["path"] == "src/tunnel-note.txt"
        )
        self.assertEqual("openai-tunnel-id", finding["detector"])
        self.assertNotIn("src/tunnel-note.txt", {item["path"] for item in manifest["files"]})
        for artifact in handoff.iterdir():
            if artifact.is_file():
                self.assert_tunnel_secret_absent(artifact.read_bytes())

        rejected = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--transport",
            "mcp-read",
            "--task",
            f"Inspect {RAW_TUNNEL_ID}.",
            "--output-root",
            str(self.root / "rejected-handoffs"),
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("Resolved Tunnel ID appears in schema-3 package data", rejected.stderr)
        self.assert_tunnel_secret_absent(rejected.stdout)

        injected_path = self.repo / "src" / f"{RAW_TUNNEL_ID}.txt"
        injected_path.write_text("safe body\n", encoding="utf-8")
        self.git("add", injected_path.relative_to(self.repo).as_posix())
        self.git("commit", "-m", "add tunnel-id path fixture")
        rejected_path_root = self.root / "rejected-path-handoffs"
        rejected_path = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--transport",
            "mcp-read",
            "--task",
            "Inspect the approved files.",
            "--output-root",
            str(rejected_path_root),
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("Resolved Tunnel ID appears in schema-3 package data", rejected_path.stderr)
        self.assertFalse(rejected_path_root.exists())

    def test_tunnel_id_file_reference_is_nofollow_owner_only_and_nonpersistent(self) -> None:
        reference_file = self.root / "tunnel-id.txt"
        reference_file.write_text(RAW_TUNNEL_ID + "\n", encoding="utf-8")
        reference_file.chmod(0o600)
        file_reference = f"file:{reference_file}"
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--transport",
            "mcp-read",
            "--task",
            "Plan against the immutable snapshot.",
            "--output-root",
            str(self.root / "file-reference-handoffs"),
            "--tunnel-id-ref",
            file_reference,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
        )
        handoff = Path(json.loads(result.stdout)["handoff_dir"])
        for output in (result.stdout, result.stderr):
            self.assertNotIn(RAW_TUNNEL_ID, output)
            self.assertNotIn(file_reference, output)
            self.assertNotIn(str(reference_file), output)
        for artifact in handoff.iterdir():
            if artifact.is_file():
                payload = artifact.read_bytes()
                self.assertNotIn(RAW_TUNNEL_ID.encode("utf-8"), payload)
                self.assertNotIn(str(reference_file).encode("utf-8"), payload)

        reference_file.chmod(0o644)
        rejected = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--transport",
            "mcp-read",
            "--task",
            "Plan against the immutable snapshot.",
            "--output-root",
            str(self.root / "bad-mode-handoffs"),
            "--tunnel-id-ref",
            file_reference,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("owned by the current user with mode 0600", rejected.stderr)

        reference_file.chmod(0o600)
        symlink = self.root / "tunnel-link.txt"
        symlink.symlink_to(reference_file)
        rejected_link = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--transport",
            "mcp-read",
            "--task",
            "Plan against the immutable snapshot.",
            "--output-root",
            str(self.root / "symlink-handoffs"),
            "--tunnel-id-ref",
            f"file:{symlink}",
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("Unable to open Tunnel ID reference file safely", rejected_link.stderr)
        self.assertNotIn(str(symlink), rejected_link.stderr)

    def test_schema2_normal_workflow_still_verifies(self) -> None:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--transport",
            "paste",
            "--task",
            "Plan a small change.",
            "--output-root",
            str(self.output_root),
        )
        handoff = Path(json.loads(result.stdout)["handoff_dir"])
        manifest = self.load(handoff / "manifest.json")
        self.assertEqual(2, manifest["schema_version"])
        self.run_cli("verify", "--handoff-dir", str(handoff))
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "paste",
            "--confirm-sent",
        )
        verified = json.loads(
            self.run_cli("verify", "--handoff-dir", str(handoff)).stdout
        )
        self.assertEqual(2, verified["schema_version"])
        self.assertEqual("submitted", verified["phase"])

    def test_legacy_shaped_schema2_can_complete_and_remain_verifiable(self) -> None:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--transport",
            "paste",
            "--task",
            "Explain the legacy fixture.",
            "--output-root",
            str(self.output_root),
        )
        handoff = Path(json.loads(result.stdout)["handoff_dir"])
        manifest_path = handoff / "manifest.json"
        manifest = self.load(manifest_path)
        manifest.pop("task_sha256")
        self.write_json(manifest_path, manifest)
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        state_path = handoff / "state.json"
        state = self.load(state_path)
        state["artifact_hashes"]["manifest_sha256"] = manifest_hash
        self.write_json(state_path, state)

        receipt_path = handoff / "receipt.json"
        receipt = self.load(receipt_path)
        prepared = receipt["events"][0]
        prepared["data"]["manifest_sha256"] = manifest_hash
        prepared_payload = {key: value for key, value in prepared.items() if key != "event_hash"}
        prepared["event_hash"] = hashlib.sha256(
            json.dumps(
                prepared_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.write_json(receipt_path, receipt)

        self.run_cli("verify", "--handoff-dir", str(handoff))
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "legacy-user",
            "--confirm-transmission",
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "paste",
            "--confirm-sent",
        )
        markers = manifest["response_markers"]
        response_file = self.root / "legacy-response.md"
        response_file.write_text(
            f"{markers['begin']}\nLegacy advisory body.\n{markers['end']}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        self.run_cli(
            "record-evaluation",
            "--handoff-dir",
            str(handoff),
            "--verdict",
            "accepted",
            "--summary",
            "Legacy schema remains readable.",
            "--evidence",
            "Current verifier completed the schema-2 lifecycle.",
        )
        verified = json.loads(
            self.run_cli("verify", "--handoff-dir", str(handoff)).stdout
        )
        self.assertEqual(2, verified["schema_version"])
        self.assertEqual("evaluated", verified["phase"])

    def test_mcp_submission_is_blocked_without_active_authorization(self) -> None:
        handoff, _ = self.prepare_mcp()
        manifest = self.load(handoff / "manifest.json")
        self.approve_mcp(handoff)
        state_before = (handoff / "state.json").read_bytes()
        receipt_before = (handoff / "receipt.json").read_bytes()

        result = self.run_cli(
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
            expected=2,
        )
        self.assertIn("requires an active package-specific MCP authorization", result.stderr)
        self.assertEqual(state_before, (handoff / "state.json").read_bytes())
        self.assertEqual(receipt_before, (handoff / "receipt.json").read_bytes())
        verified = json.loads(
            self.run_cli("verify", "--handoff-dir", str(handoff)).stdout
        )
        self.assertEqual("approved", verified["phase"])

    def test_mcp_manual_handoff_requires_exact_active_package_before_submission(self) -> None:
        handoff, _ = self.prepare_mcp()
        self.approve_mcp(handoff)
        state_before = (handoff / "state.json").read_bytes()
        receipt_before = (handoff / "receipt.json").read_bytes()

        result = self.run_cli(
            "human-handoff",
            "--handoff-dir",
            str(handoff),
            "--reason",
            "manual-transport",
        )
        payload = json.loads(result.stdout)
        instructions = "\n".join(payload["human_steps"])
        self.assertIn("this exact package as active", instructions)
        self.assertIn("foreground controller is still live", instructions)
        self.assertIn("Do not upload the ZIP", instructions)
        self.assertEqual(
            ["sent", "not-sent", "unknown"], payload["resume"]["allowed_outcomes"]
        )
        self.assertEqual(state_before, (handoff / "state.json").read_bytes())
        self.assertEqual(receipt_before, (handoff / "receipt.json").read_bytes())

    def test_mcp_account_and_app_handoffs_are_attended_and_preserve_approval(self) -> None:
        handoff, _ = self.prepare_mcp()
        self.approve_mcp(handoff)
        state_before = (handoff / "state.json").read_bytes()
        receipt_before = (handoff / "receipt.json").read_bytes()

        for reason in ("account-or-workspace", "app-authorization"):
            with self.subTest(reason=reason):
                payload = json.loads(
                    self.run_cli(
                        "human-handoff",
                        "--handoff-dir",
                        str(handoff),
                        "--reason",
                        reason,
                    ).stdout
                )
                instructions = "\n".join(payload["human_steps"])
                self.assertIn(APP_NAME, instructions)
                self.assertIn(WORKSPACE_LABEL, instructions)
                self.assertIn("MCP activation", instructions)
                self.assertIn("approval", instructions)
                self.assertNotIn("has no MCP runtime", payload["why_human_is_required"])
                self.assertEqual("mcp-read", payload["transport"])
                self.assertEqual("browser", payload["delivery_channel"])

        self.assertEqual(state_before, (handoff / "state.json").read_bytes())
        self.assertEqual(receipt_before, (handoff / "receipt.json").read_bytes())

    def test_foundation_rejects_handwritten_active_session_state(self) -> None:
        handoff, _ = self.prepare_mcp()
        self.approve_mcp(handoff)
        state_path = handoff / "state.json"
        state = self.load(state_path)
        state["mcp_session"] = {
            "status": "active",
            "session_id_sha256": "0" * 64,
        }
        self.write_json(state_path, state)

        result = self.run_cli(
            "verify",
            "--handoff-dir",
            str(handoff),
            expected=2,
        )
        self.assertIn("runtime sessions are not supported", result.stderr)

    def test_foundation_rejects_handwritten_post_approval_phase(self) -> None:
        handoff, _ = self.prepare_mcp()
        self.approve_mcp(handoff)
        state_path = handoff / "state.json"
        state = self.load(state_path)
        state["phase"] = "submitted"
        state["submission"] = {"transport": "mcp-read"}
        self.write_json(state_path, state)

        result = self.run_cli(
            "verify",
            "--handoff-dir",
            str(handoff),
            expected=2,
        )
        self.assertIn("submission and response phases are not supported", result.stderr)


if __name__ == "__main__":
    unittest.main()
