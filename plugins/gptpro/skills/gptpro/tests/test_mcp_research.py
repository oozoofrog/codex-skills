from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import errno
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
from types import SimpleNamespace
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "gptpro.py"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.authorization import AuthorizationGrant, StaticAuthorizationProvider
from runtime.gptpro_mcp.errors import ToolError
from runtime.gptpro_mcp.protocol import LegacyMcpServer
from runtime.gptpro_mcp.schema import RESEARCH_TOOL_NAMES, canonical_json_bytes, contract_for_schema
from runtime.gptpro_mcp.tools import ToolRuntime

TUNNEL_ENV_NAME = "GPTPRO_RESEARCH_TEST_TUNNEL_ID"
TUNNEL_REFERENCE = f"env:{TUNNEL_ENV_NAME}"
RAW_TUNNEL_ID = "tunnel_" + "researchtest" * 2
TUNNEL_PROFILE = "research-test"
APP_NAME = "GPT Pro Repository Research"
WORKSPACE_LABEL = "Research Test Workspace"
TUNNEL_PROFILE_HASH = hashlib.sha256(b"research-profile").hexdigest()
TUNNEL_BINARY_HASH = hashlib.sha256(b"research-binary").hexdigest()
MCP_TARGET_HASH = hashlib.sha256(b"research-target").hexdigest()


class CapturingCommitter:
    def __init__(self) -> None:
        self.commits: list[dict] = []
        self.rejections: list[dict] = []

    def commit_before_return(self, **kwargs: object) -> None:
        self.commits.append(dict(kwargs))

    def record_rejection(self, **kwargs: object) -> None:
        self.rejections.append(dict(kwargs))


class LedgerProvider:
    def __init__(self, ledger: object) -> None:
        self.ledger = ledger

    def resolve_analysis_ledger(self, grant: AuthorizationGrant) -> object:
        del grant
        return self.ledger


class McpResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gpr.", dir="/tmp")
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
        self.git("config", "user.name", "Research Test")
        self.git("config", "user.email", "research@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "src" / "main.py").write_text(
            "alpha\nold beta\nthird\nfourth\n", encoding="utf-8"
        )
        (self.repo / "docs" / "guide.md").write_text(
            "# Guide\nneedle reference\n", encoding="utf-8"
        )
        self.git("add", "src/main.py", "docs/guide.md")
        self.git("commit", "-m", "fixture")
        (self.repo / "src" / "main.py").write_text(
            "alpha\nneedle beta\nthird needle\nfourth\n", encoding="utf-8"
        )
        self.evidence = self.root / "test-output.txt"
        self.evidence.write_text("PASS unit-suite\n2 tests\n", encoding="utf-8")
        self.evidence.chmod(0o600)
        self.supplement = self.root / "requirements.md"
        self.supplement.write_text(
            "# External requirements\nPreserve the attended approval boundary.\n",
            encoding="utf-8",
        )
        self.supplement.chmod(0o600)
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

    @staticmethod
    def load_cli_module():
        module_name = f"gptpro_research_test_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("Unable to import gptpro.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

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

    def prepare(
        self,
        *,
        approve: bool = True,
        evidence: Path | None = None,
        supplement: Path | None = None,
    ) -> Path:
        prepared = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "architecture",
            "--transport",
            "mcp-research",
            "--task",
            "Analyze the approved repository snapshot and record findings.",
            "--output-root",
            str(self.output_root),
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
            "64",
            "--evidence-file",
            f"test-log={evidence or self.evidence}",
            *(
                ["--supplement", f"requirements={supplement}"]
                if supplement is not None
                else []
            ),
        )
        handoff = Path(json.loads(prepared.stdout)["handoff_dir"])
        if approve:
            self.run_cli(
                "approve",
                "--handoff-dir",
                str(handoff),
                "--approved-by",
                "research-test-user",
                "--confirm-transmission",
                "--confirm-mcp-disclosure",
                "--confirm-analysis-ledger",
            )
        return handoff

    def activate(self, handoff: Path) -> tuple[object, str, dict]:
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
        store = self.module.RuntimeStateStore(root=self.runtime_root)
        session_hash = hashlib.sha256(os.urandom(32)).hexdigest()
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

    def mark_submitted(self, handoff: Path, store: object) -> None:
        verified = self.module.verify_package(handoff)
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "require_active_mcp_authorization",
                return_value=({}, mock.Mock()),
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.module.command_mark_submitted(
                SimpleNamespace(
                    handoff_dir=str(handoff),
                    confirm_sent=True,
                    observed_model=verified["manifest"]["requested_model"],
                    thread_url=None,
                    observed_transport="mcp-research",
                    observed_github_repository=None,
                    observed_github_commit=None,
                    observed_delivery_channel="browser",
                    observed_app_name=APP_NAME,
                    observed_workspace_label=WORKSPACE_LABEL,
                )
            )

    def fixture_runtime(self, handoff: Path) -> tuple[ToolRuntime, object, CapturingCommitter]:
        verified = self.module.verify_package(handoff)
        session_hash = hashlib.sha256(b"research-static-session").hexdigest()
        ledger = self.module.analysis_ledger_for(verified, session_hash)
        ledger.create_header()
        now = datetime.now(timezone.utc)
        grant = AuthorizationGrant(
            package_id=verified["manifest"]["package_id"],
            manifest=verified["manifest"],
            archive_path=Path(verified["archive_path"]),
            archive_sha256=verified["manifest"]["hashes"]["archive_sha256"],
            manifest_sha256=verified["manifest_sha256"],
            session_id_sha256=session_hash,
            session_nonce=b"n" * 32,
            expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(minutes=30),
        )
        committer = CapturingCommitter()
        runtime = ToolRuntime(
            StaticAuthorizationProvider(grant),
            committer=committer,
            analysis_provider=LedgerProvider(ledger),
        )
        return runtime, ledger, committer

    @staticmethod
    def result(response: dict) -> dict:
        return response["structuredContent"]["result"]

    def test_prepare_binds_schema4_snapshot_evidence_diff_and_tool_catalog(self) -> None:
        handoff = self.prepare()
        verified = self.module.verify_package(handoff)
        manifest = verified["manifest"]
        self.assertEqual(4, manifest["schema_version"])
        self.assertEqual("mcp-research", manifest["transport"]["requested"])
        self.assertEqual("mcp-research", manifest["transport"]["resolved"])
        self.assertEqual(["prompt"], [item["artifact"] for item in manifest["transport"]["outbound_artifacts"]])
        self.assertEqual(list(RESEARCH_TOOL_NAMES), manifest["mcp_disclosure"]["tools"])
        self.assertEqual(
            contract_for_schema(4)["tool_schema_sha256"],
            manifest["connector"]["tool_schema_sha256"],
        )
        self.assertEqual(["test-log"], [item["artifact_id"] for item in manifest["research"]["evidence"]])
        self.assertEqual("HEAD", manifest["research"]["diff"]["base"])
        self.assertEqual(manifest["git"]["head_sha"], manifest["research"]["diff"]["base_sha"])
        self.assertNotIn(str(self.evidence), json.dumps(manifest, sort_keys=True))
        self.assertEqual("read-only-context-notes-v1", manifest["analysis_collaboration"]["mode"])
        self.assertFalse(manifest["analysis_collaboration"]["mcp_write_tools"])
        self.assertEqual(
            "visible-chat-response",
            manifest["analysis_collaboration"]["pro_response_channel"],
        )
        self.assertEqual("approved", verified["state"]["phase"])
        prompt = (handoff / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("`gptpro_workspace_map`", prompt)
        self.assertIn("`include`", prompt)
        self.assertIn("`exclude`", prompt)
        self.assertNotIn("any `paths` list", prompt)

    def test_supplement_reuses_bounded_research_artifact_without_repository_expansion(self) -> None:
        handoff = self.prepare(supplement=self.supplement)
        verified = self.module.verify_package(handoff)
        manifest = verified["manifest"]
        self.assertEqual(
            ["requirements"], manifest["research"]["supplement_artifact_ids"]
        )
        self.assertEqual(
            ["requirements", "test-log"],
            [item["artifact_id"] for item in manifest["research"]["evidence"]],
        )
        self.assertNotIn(str(self.supplement), json.dumps(manifest, sort_keys=True))
        repository_file_set = manifest["mcp_disclosure"]["allowed_files"]
        self.assertNotIn("requirements", json.dumps(repository_file_set, sort_keys=True))
        status = json.loads(
            self.run_cli("status", "--handoff-dir", str(handoff), "--json").stdout
        )
        self.assertEqual(
            [
                {
                    "label": "requirements",
                    "size": self.supplement.stat().st_size,
                    "sha256": self.module.sha256_file(self.supplement),
                }
            ],
            status["supplemental_documents"],
        )

        runtime, _, _ = self.fixture_runtime(handoff)
        package_id = manifest["package_id"]
        package = self.result(
            runtime.call(
                "gptpro_package_info",
                {"package_id": package_id, "include_paths": True, "path_page_size": 20},
            )
        )
        self.assertEqual(
            ["requirements", "test-log"],
            [item["artifact_id"] for item in package["research"]["evidence"]],
        )
        artifact = self.result(
            runtime.call(
                "gptpro_artifact_read",
                {
                    "package_id": package_id,
                    "artifact_id": "requirements",
                    "start_line": 1,
                    "end_line": 2,
                },
            )
        )
        self.assertEqual(self.supplement.read_text(encoding="utf-8"), artifact["text"])
        with self.assertRaises(ToolError) as repository_read:
            runtime.call(
                "gptpro_repo_read",
                {
                    "package_id": package_id,
                    "path": "requirements",
                    "ranges": [{"start_line": 1, "end_line": 1}],
                },
            )
        self.assertEqual("PATH_NOT_APPROVED", repository_read.exception.code)

    def test_supplement_and_evidence_share_label_and_budget_validation(self) -> None:
        duplicate = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--task",
            "Reject duplicate external artifact labels.",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            TUNNEL_PROFILE,
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--evidence-file",
            f"same={self.evidence}",
            "--supplement",
            f"same={self.supplement}",
            expected=2,
        )
        self.assertIn("unique safe LABEL", duplicate.stderr)
        self.assertEqual(
            [], list(self.output_root.iterdir()) if self.output_root.exists() else []
        )

    def test_approval_requires_disclosure_and_analysis_confirmation(self) -> None:
        handoff = self.prepare(approve=False)
        missing_analysis = self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "research-test-user",
            "--confirm-transmission",
            "--confirm-mcp-disclosure",
            expected=2,
        )
        self.assertIn("--confirm-analysis-ledger", missing_analysis.stderr)
        self.assertEqual("prepared", self.module.verify_package(handoff)["state"]["phase"])

    def test_prepare_records_selected_tracked_deletion_in_head_diff(self) -> None:
        (self.repo / "docs" / "guide.md").unlink()
        handoff = self.prepare()
        runtime, _, _ = self.fixture_runtime(handoff)
        package_id = self.module.verify_package(handoff)["manifest"]["package_id"]
        result = self.result(
            runtime.call(
                "gptpro_repo_diff",
                {"package_id": package_id, "paths": ["docs/**"], "max_results": 10},
            )
        )
        deleted = [entry for entry in result["entries"] if entry["path"] == "docs/guide.md"]
        self.assertEqual(1, len(deleted))
        self.assertEqual("deleted", deleted[0]["status"])
        self.assertIsNone(deleted[0]["new_sha256"])
        self.assertEqual(0, deleted[0]["new_bytes"])

    def test_prepare_rejects_secret_like_deleted_path_before_publication(self) -> None:
        secret = "ghp_" + ("A" * 24)
        unsafe = self.repo / "docs" / secret
        unsafe.write_text("historical non-secret body\n", encoding="utf-8")
        self.git("add", f"docs/{secret}")
        self.git("commit", "-m", "secret-like path fixture")
        unsafe.unlink()

        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--task",
            "Review the approved repository snapshot.",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            TUNNEL_PROFILE,
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--evidence-file",
            f"test-log={self.evidence}",
            expected=2,
        )
        self.assertIn("secret-like material", result.stderr)
        self.assertIn("github-token", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(
            [],
            list(self.output_root.iterdir()) if self.output_root.exists() else [],
        )

    def test_prepare_rejects_excluded_secret_like_deleted_path_before_publication(self) -> None:
        secret = "ghp_" + ("C" * 24)
        unsafe = self.repo / "docs" / secret
        unsafe.write_text("historical non-secret body\n", encoding="utf-8")
        self.git("add", f"docs/{secret}")
        self.git("commit", "-m", "excluded secret-like path fixture")
        unsafe.unlink()

        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--task",
            "Review only the explicitly selected safe file.",
            "--include",
            "docs/guide.md",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            TUNNEL_PROFILE,
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--evidence-file",
            f"test-log={self.evidence}",
            expected=2,
        )
        self.assertIn("secret-like material", result.stderr)
        self.assertIn("github-token", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(
            [],
            list(self.output_root.iterdir()) if self.output_root.exists() else [],
        )

    def test_prepare_rejects_strict_invalid_secret_path_without_reflection(self) -> None:
        secret = "ghp_" + ("D" * 24)
        relative = f"docs/{secret}\\suffix"
        unsafe = self.repo / relative
        unsafe.write_text("historical non-secret body\n", encoding="utf-8")
        self.git("add", relative)
        self.git("commit", "-m", "strict-invalid secret-like path fixture")
        unsafe.unlink()

        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--task",
            "Reject a strict-invalid secret-like Git path without reflection.",
            "--include",
            "docs/guide.md",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            TUNNEL_PROFILE,
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--evidence-file",
            f"test-log={self.evidence}",
            expected=2,
        )
        self.assertIn("secret-like material", result.stderr)
        self.assertIn("github-token", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(
            [],
            list(self.output_root.iterdir()) if self.output_root.exists() else [],
        )

    def test_audit_rejects_secret_like_paths_with_shared_detector_set(self) -> None:
        audit_module = sys.modules[self.module.AuditLog.__module__]
        secret_path = "docs/ghp_" + ("B" * 24)
        with self.assertRaisesRegex(ValueError, "secret-like"):
            audit_module._safe_path(secret_path)

    def test_schema4_manifest_verification_rejects_secret_path_without_reflection(self) -> None:
        handoff = self.prepare()
        manifest = self.module.verify_package(handoff)["manifest"]
        secret_path = "docs/ghp_" + ("E" * 24)
        manifest["git"]["dirty_paths"].append(
            {"status": " D", "path": secret_path}
        )
        with self.assertRaises(self.module.HandoffError) as rejected:
            self.module.verify_mcp_manifest_contract(manifest)
        self.assertIn("secret-like material", str(rejected.exception))
        self.assertIn("github-token", str(rejected.exception))
        self.assertNotIn(secret_path, str(rejected.exception))

    def test_prepare_fails_if_git_snapshot_changes_during_capture(self) -> None:
        with mock.patch.object(
            self.module,
            "research_worktree_snapshot",
            side_effect=[b"before", b"after"],
        ):
            result = self.run_cli(
                "prepare",
                "--repo",
                str(self.repo),
                "--mode",
                "architecture",
                "--transport",
                "mcp-research",
                "--task",
                "Analyze one stable snapshot.",
                "--output-root",
                str(self.output_root),
                "--tunnel-runtime-alias",
                TUNNEL_PROFILE,
                "--tunnel-id-ref",
                TUNNEL_REFERENCE,
                "--chatgpt-app-name",
                APP_NAME,
                "--chatgpt-workspace-label",
                WORKSPACE_LABEL,
                "--evidence-file",
                f"test-log={self.evidence}",
                expected=2,
            )
        self.assertIn("changed during schema-4 snapshot capture", result.stderr)

    def test_prepare_rejects_path_captured_as_both_selected_and_deleted(self) -> None:
        with mock.patch.object(
            self.module,
            "research_selected_deletions",
            return_value=["src/main.py"],
        ):
            result = self.run_cli(
                "prepare",
                "--repo",
                str(self.repo),
                "--mode",
                "architecture",
                "--transport",
                "mcp-research",
                "--task",
                "Reject an internally inconsistent snapshot.",
                "--output-root",
                str(self.output_root),
                "--tunnel-runtime-alias",
                TUNNEL_PROFILE,
                "--tunnel-id-ref",
                TUNNEL_REFERENCE,
                "--chatgpt-app-name",
                APP_NAME,
                "--chatgpt-workspace-label",
                WORKSPACE_LABEL,
                "--evidence-file",
                f"test-log={self.evidence}",
                expected=2,
            )
        self.assertIn("both selected and deleted", result.stderr)

    def test_head_blob_size_is_checked_before_git_show(self) -> None:
        selected = self.module.SelectedFile(
            path="src/main.py",
            content=b"new\n",
            sha256=hashlib.sha256(b"new\n").hexdigest(),
            size=4,
        )

        def fake_git(_root: Path, *args: str, binary: bool = False) -> object:
            del binary
            if args[0] == "ls-tree":
                return b"src/main.py\0"
            if args[:2] == ("cat-file", "-s"):
                return str(self.module.DEFAULT_MAX_FILE_BYTES + 1)
            if args[0] == "show":
                self.fail("git show must not run for an oversized HEAD blob")
            raise AssertionError(args)

        with (
            mock.patch.object(self.module, "run_git", side_effect=fake_git),
            self.assertRaisesRegex(self.module.HandoffError, "hard member limit"),
        ):
            self.module.research_head_diff(
                self.repo,
                [selected],
                [],
                self.module.RESEARCH_DEFAULT_LIMITS["max_diff_bytes"],
                head_sha="a" * 40,
            )

    def test_workspace_index_is_bounded_before_package_publication(self) -> None:
        files = []
        for index in range(500):
            components = [f"d{index:04d}-{depth:02d}-" + ("x" * 32) for depth in range(20)]
            path = "/".join([*components, "file.py"])
            files.append(
                self.module.SelectedFile(
                    path=path,
                    content=b"x",
                    sha256=hashlib.sha256(b"x").hexdigest(),
                    size=1,
                )
            )
        with self.assertRaisesRegex(self.module.HandoffError, "workspace index exceeds"):
            self.module.research_workspace_index(files)

    def test_secret_like_evidence_is_rejected_without_persisting_the_secret(self) -> None:
        secret = "sk-abcdefghijklmnopqrstuvwx"
        unsafe = self.root / "unsafe.txt"
        unsafe.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
        unsafe.chmod(0o600)
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--task",
            "Review approved evidence.",
            "--output-root",
            str(self.output_root),
            "--tunnel-runtime-alias",
            TUNNEL_PROFILE,
            "--tunnel-id-ref",
            TUNNEL_REFERENCE,
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            "--evidence-file",
            f"unsafe={unsafe}",
            expected=2,
        )
        self.assertIn("secret", result.stderr.lower())
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_secret_like_evidence_id_is_rejected_before_publication(self) -> None:
        secret_id = "ghp_" + ("f" * 24)
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                arguments = [
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "review",
                    "--transport",
                    "mcp-research",
                    "--task",
                    "Reject a secret-like evidence identity before publication.",
                    "--output-root",
                    str(self.output_root),
                    "--tunnel-runtime-alias",
                    TUNNEL_PROFILE,
                    "--tunnel-id-ref",
                    TUNNEL_REFERENCE,
                    "--chatgpt-app-name",
                    APP_NAME,
                    "--chatgpt-workspace-label",
                    WORKSPACE_LABEL,
                    "--evidence-file",
                    f"{secret_id}={self.evidence}",
                ]
                if dry_run:
                    arguments.append("--dry-run")
                result = self.run_cli(*arguments, expected=2)
                self.assertIn("secret-like material", result.stderr)
                self.assertIn("github-token", result.stderr)
                self.assertNotIn(secret_id, result.stdout + result.stderr)
        self.assertEqual(
            [],
            list(self.output_root.iterdir()) if self.output_root.exists() else [],
        )

    def test_evidence_and_note_paths_reject_symlink_components(self) -> None:
        link = self.root / "evidence-link.txt"
        link.symlink_to(self.evidence)
        with self.assertRaisesRegex(self.module.HandoffError, "symlink"):
            self.module.read_research_evidence(
                [f"linked={link}"],
                dict(self.module.RESEARCH_DEFAULT_LIMITS),
            )
        with self.assertRaisesRegex(self.module.HandoffError, "symlink"):
            self.module._read_private_note(
                str(link),
                maximum=self.module.RESEARCH_DEFAULT_LIMITS["max_analysis_event_bytes"],
            )

    def test_owner_input_rejects_intermediate_symlink_swap(self) -> None:
        owner = self.root / "owner"
        inner = owner / "inner"
        inner.mkdir(parents=True)
        source = inner / "evidence.txt"
        source.write_text("approved evidence\n", encoding="utf-8")
        source.chmod(0o600)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "evidence.txt").write_text("outside bytes\n", encoding="utf-8")
        (outside / "evidence.txt").chmod(0o600)
        original_open = self.module.os.open
        swapped = False

        def racing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal swapped
            if path == "inner" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                inner.rename(owner / "inner-original")
                inner.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with (
            mock.patch.object(self.module.os, "open", side_effect=racing_open),
            self.assertRaisesRegex(self.module.HandoffError, "symlink traversal"),
        ):
            self.module.read_research_evidence(
                [f"raced={source}"],
                dict(self.module.RESEARCH_DEFAULT_LIMITS),
            )
        self.assertTrue(swapped)

    def test_research_tools_expose_only_preapproved_snapshot_and_artifacts(self) -> None:
        handoff = self.prepare()
        before = (self.repo / "src" / "main.py").read_bytes()
        runtime, ledger, _ = self.fixture_runtime(handoff)
        package_id = self.module.verify_package(handoff)["manifest"]["package_id"]

        package = self.result(runtime.call(
            "gptpro_package_info",
            {"package_id": package_id, "include_paths": True, "path_page_size": 20},
        ))
        self.assertEqual("repository-research-v1", package["research"]["profile"])
        self.assertEqual(1, len(package["research"]["evidence"]))

        workspace = self.result(runtime.call(
            "gptpro_workspace_map",
            {"package_id": package_id, "root": "src", "max_depth": 2, "page_size": 20},
        ))
        self.assertIn("src/main.py", [item["path"] for item in workspace["entries"]])

        read = self.result(runtime.call(
            "gptpro_repo_read",
            {
                "package_id": package_id,
                "path": "src/main.py",
                "ranges": [
                    {"start_line": 1, "end_line": 1},
                    {"start_line": 3, "end_line": 4},
                ],
            },
        ))
        self.assertEqual(["alpha\n", "third needle\nfourth\n"], [item["text"] for item in read["fragments"]])
        with self.assertRaises(ToolError) as beyond:
            runtime.call(
                "gptpro_repo_read",
                {
                    "package_id": package_id,
                    "path": "src/main.py",
                    "ranges": [{"start_line": 99, "end_line": 100}],
                },
            )
        self.assertEqual("RANGE_INVALID", beyond.exception.code)

        search = self.result(runtime.call(
            "gptpro_repo_search",
            {
                "package_id": package_id,
                "queries": ["needle", "beta"],
                "operator": "all",
                "include": ["src/**"],
                "exclude": ["src/generated/**"],
                "case_sensitive": True,
                "max_results": 10,
                "context_lines": 0,
            },
        ))
        self.assertEqual([0, 1], search["matches"][0]["matched_query_indexes"])

        diff = self.result(runtime.call(
            "gptpro_repo_diff",
            {"package_id": package_id, "paths": ["src/**"], "max_results": 10},
        ))
        self.assertEqual(["src/main.py"], [item["path"] for item in diff["entries"]])
        self.assertEqual("HEAD", diff["base"])
        self.assertEqual(
            self.module.verify_package(handoff)["manifest"]["git"]["head_sha"],
            diff["base_sha"],
        )
        self.assertEqual("modified", diff["entries"][0]["status"])

        artifact = self.result(runtime.call(
            "gptpro_artifact_read",
            {"package_id": package_id, "artifact_id": "test-log", "start_line": 1, "end_line": 2},
        ))
        self.assertEqual("PASS unit-suite\n2 tests\n", artifact["text"])
        self.assertEqual(before, (self.repo / "src" / "main.py").read_bytes())
        self.assertFalse(ledger.verify().closed)

    def test_research_catalog_is_read_only_and_rejects_write_tool(self) -> None:
        handoff = self.prepare()
        runtime, ledger, committer = self.fixture_runtime(handoff)
        verified = self.module.verify_package(handoff)
        package_id = verified["manifest"]["package_id"]
        self.assertNotIn("gptpro_analysis_post", RESEARCH_TOOL_NAMES)
        self.assertTrue(
            all(
                tool["annotations"]["readOnlyHint"]
                for tool in contract_for_schema(4)["tool_catalog"]
            )
        )
        with self.assertRaises(ToolError) as rejected:
            runtime.call(
                "gptpro_analysis_post",
                {"package_id": package_id},
            )
        self.assertEqual("MCP_INVALID_ARGUMENT", rejected.exception.code)
        self.assertEqual(1, len(committer.rejections))
        self.assertEqual("gptpro_analysis_post", committer.rejections[0]["tool"])
        self.assertEqual("MCP_INVALID_ARGUMENT", committer.rejections[0]["error_code"])
        self.assertEqual(1, committer.rejections[0]["calls_used"])
        status = self.result(runtime.call(
            "gptpro_analysis_status", {"package_id": package_id, "page_size": 10}
        ))
        self.assertEqual(2, committer.commits[-1]["calls_used"])
        self.assertEqual([], status["events"])
        self.assertEqual(0, ledger.verify().event_count)

    def test_complete_model_visible_response_consumes_disclosure_budget(self) -> None:
        handoff = self.prepare()
        runtime, _, committer = self.fixture_runtime(handoff)
        package_id = self.module.verify_package(handoff)["manifest"]["package_id"]

        package_response = runtime.call(
            "gptpro_package_info",
            {"package_id": package_id, "include_paths": False},
        )
        package_bytes = len(canonical_json_bytes(package_response))
        package_result = self.result(package_response)
        self.assertEqual(
            package_bytes,
            package_result["disclosure"]["session_disclosed_bytes"],
        )
        self.assertEqual(package_bytes, package_result["session"]["disclosed_bytes"])
        self.assertEqual(package_bytes, committer.commits[-1]["disclosed_bytes"])

        map_response = runtime.call(
            "gptpro_workspace_map",
            {"package_id": package_id, "root": "", "page_size": 1, "max_depth": 1},
        )
        map_bytes = len(canonical_json_bytes(map_response))
        self.assertEqual(
            package_bytes + map_bytes,
            self.result(map_response)["disclosure"]["session_disclosed_bytes"],
        )
        self.assertEqual(package_bytes + map_bytes, committer.commits[-1]["disclosed_bytes"])

    def test_glob_matching_is_bounded_and_duplicate_patterns_are_rejected(self) -> None:
        tools_module = sys.modules[ToolRuntime.__module__]
        path = "/".join(["segment"] * 800 + ["target.py"])
        pattern = "/".join(["**", "missing", "**", "target.py"])
        started = time.monotonic()
        self.assertFalse(tools_module._safe_glob_match(path, pattern))
        self.assertLess(time.monotonic() - started, 0.5)
        with self.assertRaises(ToolError) as duplicate:
            tools_module._glob_array(["src/**", "src/**"], 16, "include")
        self.assertEqual("MCP_INVALID_ARGUMENT", duplicate.exception.code)

    def test_audit_metadata_omits_raw_queries(self) -> None:
        handoff = self.prepare()
        runtime, _, committer = self.fixture_runtime(handoff)
        verified = self.module.verify_package(handoff)
        package_id = verified["manifest"]["package_id"]
        query = "needle"
        runtime.call(
            "gptpro_repo_search",
            {"package_id": package_id, "queries": [query], "max_results": 10, "context_lines": 0},
        )
        metadata = json.dumps(
            [item["audit_metadata"] for item in committer.commits],
            sort_keys=True,
        )
        self.assertNotIn(query, metadata)

    def test_analysis_tamper_and_close_fail_closed(self) -> None:
        handoff = self.prepare()
        _, ledger, _ = self.fixture_runtime(handoff)
        head = ledger.verify().head_sha256
        approval_hash = hashlib.sha256(b"approved-note").hexdigest()
        ledger.append_codex_note(
            event_id="codex-note-0000000000000001",
            expected_head_sha256=head,
            summary="Bounded owner note.",
            approval_event_sha256=approval_hash,
        )
        closed = ledger.close(reason="user_revoked")
        self.assertTrue(closed.closed)
        with self.assertRaises(ToolError) as after_close:
            ledger.append_codex_note(
                event_id="codex-note-0000000000000002",
                expected_head_sha256=closed.head_sha256,
                summary="Too late.",
                approval_event_sha256=hashlib.sha256(b"second-note").hexdigest(),
            )
        self.assertEqual("ANALYSIS_LEDGER_CLOSED", after_close.exception.code)
        raw = ledger.path.read_bytes()
        ledger.path.write_bytes(raw.replace(b"Bounded owner note.", b"Tampered owner note", 1))
        with self.assertRaises(ToolError) as tampered:
            ledger.verify()
        self.assertEqual("ANALYSIS_LEDGER_INVALID", tampered.exception.code)

    def test_analysis_ledger_retries_short_header_and_event_writes(self) -> None:
        analysis_module = sys.modules[self.module.AnalysisLedger.__module__]
        binding = analysis_module.AnalysisBinding(
            package_id="short-write-package",
            session_id_sha256=hashlib.sha256(b"short-session").hexdigest(),
            manifest_sha256=hashlib.sha256(b"short-manifest").hexdigest(),
            approval_event_sha256=hashlib.sha256(b"short-approval").hexdigest(),
            tool_schema_sha256=contract_for_schema(4)["tool_schema_sha256"],
            limits_sha256=hashlib.sha256(b"short-limits").hexdigest(),
            max_events=8,
            max_event_bytes=4096,
            max_ledger_bytes=65536,
        )
        ledger = analysis_module.AnalysisLedger(self.root / "short-analysis.jsonl", binding)
        original_write = os.write
        short_writes = 0

        def short_write(descriptor: int, payload: object) -> int:
            nonlocal short_writes
            data = bytes(payload)
            limit = max(1, len(data) // 3)
            if limit < len(data):
                short_writes += 1
            return original_write(descriptor, data[:limit])

        with mock.patch.object(analysis_module.os, "write", side_effect=short_write):
            header_sha256 = ledger.create_header()
            appended = ledger.append_codex_note(
                event_id="codex-note-1111111111111111",
                expected_head_sha256=header_sha256,
                summary="Bounded short-write note.",
                approval_event_sha256=hashlib.sha256(b"note-approval").hexdigest(),
            )
        self.assertGreater(short_writes, 1)
        self.assertEqual(1, appended.sequence)
        self.assertEqual(1, ledger.verify().event_count)

    def test_missing_analysis_ledger_is_normalized_to_handoff_error(self) -> None:
        handoff = self.prepare()
        self.activate(handoff)
        (handoff / "mcp-analysis.jsonl").unlink()
        with self.assertRaises(self.module.HandoffError) as missing:
            self.module.verify_package(handoff)
        self.assertIn("ANALYSIS_LEDGER_IO_FAILED", str(missing.exception))

    def test_analysis_footer_io_failure_faults_authorization_without_raw_exception(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        analysis_module = sys.modules[self.module.AnalysisLedger.__module__]
        with mock.patch.object(
            analysis_module,
            "_write_all",
            side_effect=OSError(errno.EIO, "injected analysis write failure"),
        ):
            result = self.module.revoke_mcp_authorization_fail_closed(
                handoff,
                store,
                expected_session_id_sha256=session_hash,
                reason="user_requested",
            )
        self.assertEqual("faulted", result["authorization_status"])
        self.assertTrue(result["authorization_denied"])
        self.assertFalse(result["authorization_revoked"])
        self.assertFalse(result["package_evidence_available"])
        self.assertEqual("faulted", store.read()["status"])
        verified = self.module.verify_package(handoff)
        self.assertEqual("active", verified["state"]["mcp_session"]["status"])
        self.assertTrue(
            self.module.audit_log_for(verified, session_hash).verify().footer
        )
        self.assertFalse(
            self.module.analysis_ledger_for(verified, session_hash).verify().closed
        )

    def test_codex_note_is_invisible_until_exact_byte_approval_and_bound_on_stop(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        ledger = self.module.analysis_ledger_for(verified, session_hash)
        message = "Yes. Preserve the schema-3 behavior and add schema 4 separately.\n"
        message_path = self.root / "note.txt"
        message_path.write_text(message, encoding="utf-8")
        message_path.chmod(0o600)
        output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(self.module, "require_active_mcp_authorization", return_value=({}, mock.Mock())),
            redirect_stdout(output),
        ):
            self.assertEqual(
                0,
                self.module.command_analysis_note_prepare(
                    SimpleNamespace(
                        handoff_dir=str(handoff),
                        message_file=str(message_path),
                    )
                ),
            )
        staged = json.loads(output.getvalue())
        self.assertFalse(staged["transmitted"])
        self.assertEqual(0, ledger.verify().event_count)
        self.assertEqual(hashlib.sha256(message.encode()).hexdigest(), staged["message_sha256"])
        with self.assertRaisesRegex(self.module.HandoffError, "--confirm-publication"):
            self.module.command_analysis_note_approve(
                SimpleNamespace(
                    handoff_dir=str(handoff),
                    note_id=staged["note_id"],
                    message_sha256=staged["message_sha256"],
                    message_bytes=staged["message_bytes"],
                    expected_head_sha256=staged["expected_head_sha256"],
                    approved_by="research-test-user",
                    confirm_publication=False,
                )
            )
        output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(self.module, "require_active_mcp_authorization", return_value=({}, mock.Mock())),
            redirect_stdout(output),
        ):
            self.assertEqual(
                0,
                self.module.command_analysis_note_approve(
                    SimpleNamespace(
                        handoff_dir=str(handoff),
                        note_id=staged["note_id"],
                        message_sha256=staged["message_sha256"],
                        message_bytes=staged["message_bytes"],
                        expected_head_sha256=staged["expected_head_sha256"],
                        approved_by="research-test-user",
                        confirm_publication=True,
                    )
                ),
            )
        approved = json.loads(output.getvalue())
        self.assertFalse(approved["transmitted"])
        self.assertTrue(approved["ledger_published"])
        self.assertTrue(approved["available_for_mcp_read"])
        self.assertFalse(approved["network_delivery_observed"])
        events, summary = ledger.read_events()
        self.assertEqual(1, summary.event_count)
        self.assertEqual(message, events[0]["summary"])
        self.assertEqual("codex", events[0]["actor"])
        self.assertEqual("context_note", events[0]["kind"])
        self.assertNotIn("reply_to", events[0])

        stopped = self.module.stop_mcp_authorization(
            handoff, store, reason="user_requested"
        )
        self.assertEqual("revoked", stopped["authorization"]["status"])
        final = self.module.verify_package(handoff)
        final_session = final["state"]["mcp_session"]
        self.assertTrue(final_session["analysis_closed"])
        self.assertEqual(1, final_session["analysis_event_count"])
        self.assertEqual(ledger.verify().head_sha256, final_session["analysis_head_sha256"])
        receipts = [
            event for event in final["receipt"]["events"] if event["type"] == "mcp_revoked"
        ]
        self.assertEqual(final_session["analysis_head_sha256"], receipts[-1]["data"]["analysis_head_sha256"])

    def test_note_approval_rejects_stage_changed_after_review(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        ledger = self.module.analysis_ledger_for(verified, session_hash)
        message_path = self.root / "reviewed-note.txt"
        message_path.write_text("Reviewed exact note.\n", encoding="utf-8")
        message_path.chmod(0o600)
        output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(self.module, "require_active_mcp_authorization", return_value=({}, mock.Mock())),
            redirect_stdout(output),
        ):
            self.module.command_analysis_note_prepare(
                SimpleNamespace(handoff_dir=str(handoff), message_file=str(message_path))
            )
        staged = json.loads(output.getvalue())
        stage_path = Path(staged["stage_path"])
        changed = json.loads(stage_path.read_text(encoding="utf-8"))
        changed["message"] = "Different unreviewed note.\n"
        changed_bytes = changed["message"].encode("utf-8")
        changed["message_sha256"] = hashlib.sha256(changed_bytes).hexdigest()
        changed["message_bytes"] = len(changed_bytes)
        self.module.write_json(stage_path, changed)
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(self.module, "require_active_mcp_authorization", return_value=({}, mock.Mock())),
            self.assertRaisesRegex(self.module.HandoffError, "exact reviewed"),
        ):
            self.module.command_analysis_note_approve(
                SimpleNamespace(
                    handoff_dir=str(handoff),
                    note_id=staged["note_id"],
                    message_sha256=staged["message_sha256"],
                    message_bytes=staged["message_bytes"],
                    expected_head_sha256=staged["expected_head_sha256"],
                    approved_by="research-test-user",
                    confirm_publication=True,
                )
            )
        self.assertEqual(0, ledger.verify().event_count)

    def test_verify_rejects_note_without_exact_approval_receipt(self) -> None:
        handoff = self.prepare()
        _, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        ledger = self.module.analysis_ledger_for(verified, session_hash)
        ledger.append_codex_note(
            event_id="codex-note-2222222222222222",
            expected_head_sha256=ledger.verify().head_sha256,
            summary="Forged unapproved note.",
            approval_event_sha256=hashlib.sha256(b"missing-receipt").hexdigest(),
        )
        with self.assertRaisesRegex(self.module.HandoffError, "approval receipt"):
            self.module.verify_package(handoff)

    def test_note_approval_recovers_receipt_before_append_and_replays_idempotently(self) -> None:
        handoff = self.prepare()
        store, _, _ = self.activate(handoff)
        note_path = self.root / "crash-note.txt"
        note_path.write_text("Approved note after receipt crash.\n", encoding="utf-8")
        note_path.chmod(0o600)
        output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "require_active_mcp_authorization",
                return_value=({}, mock.Mock()),
            ),
            redirect_stdout(output),
        ):
            self.module.command_analysis_note_prepare(
                SimpleNamespace(handoff_dir=str(handoff), message_file=str(note_path))
            )
        staged = json.loads(output.getvalue())
        state = self.module.verify_package(handoff)["state"]
        approval = self.module.append_receipt_event(
            handoff,
            "analysis_note_approved",
            {
                "phase_before": state["phase"],
                "phase_after": state["phase"],
                "note_id": staged["note_id"],
                "message_sha256": staged["message_sha256"],
                "message_bytes": staged["message_bytes"],
                "expected_head_sha256": staged["expected_head_sha256"],
                "approved_by": "research-test-user",
                "approved_at": self.module.utc_now(),
            },
        )
        args = SimpleNamespace(
            handoff_dir=str(handoff),
            note_id=staged["note_id"],
            message_sha256=staged["message_sha256"],
            message_bytes=staged["message_bytes"],
            expected_head_sha256=staged["expected_head_sha256"],
            approved_by="research-test-user",
            confirm_publication=True,
        )
        first_output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "require_active_mcp_authorization",
                return_value=({}, mock.Mock()),
            ),
            redirect_stdout(first_output),
        ):
            self.module.command_analysis_note_approve(args)
        first = json.loads(first_output.getvalue())
        self.assertEqual(approval["event_hash"], first["approval_event_sha256"])
        self.assertFalse(first["idempotent_replay"])
        second_output = io.StringIO()
        with (
            mock.patch.object(self.module, "runtime_store_for", return_value=store),
            mock.patch.object(
                self.module,
                "require_active_mcp_authorization",
                return_value=({}, mock.Mock()),
            ),
            redirect_stdout(second_output),
        ):
            self.module.command_analysis_note_approve(args)
        second = json.loads(second_output.getvalue())
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["analysis_event_sha256"], second["analysis_event_sha256"])
        self.assertFalse(second["transmitted"])

    def test_stop_recovery_preserves_first_durable_close_reason(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        verified = self.module.verify_package(handoff)
        audit = self.module.audit_log_for(verified, session_hash)
        audit.append_footer("controller_lost")
        self.module.analysis_ledger_for(verified, session_hash).close(
            reason="controller_lost"
        )
        # A crash can leave package/global state active after both durable
        # footers. Package verification must allow recovery, while live tools
        # still reject the closed audit/ledger independently.
        self.assertEqual("active", self.module.verify_package(handoff)["state"]["mcp_session"]["status"])
        result = self.module.stop_mcp_authorization(
            handoff,
            store,
            reason="user_requested",
        )
        self.assertEqual("revoked", result["authorization"]["status"])
        self.assertEqual("controller_lost", result["authorization"]["revoked_reason"])
        final = self.module.verify_package(handoff)
        session = final["state"]["mcp_session"]
        self.assertEqual("controller_lost", session["reason"])
        self.assertEqual("controller_lost", session["analysis_close_reason"])
        revocations = [
            event for event in final["receipt"]["events"] if event["type"] == "mcp_revoked"
        ]
        self.assertEqual("controller_lost", revocations[-1]["data"]["reason"])

    def test_schema4_activation_cannot_strip_current_accounting_binding(self) -> None:
        handoff = self.prepare()
        self.activate(handoff)
        state = json.loads((handoff / "state.json").read_text(encoding="utf-8"))
        receipt = json.loads((handoff / "receipt.json").read_text(encoding="utf-8"))
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
            "runtime sessions are not supported|accounting binding",
        ):
            self.module.verify_package(handoff)

    def test_expiry_recovery_uses_persisted_reason_and_finishes_terminal_evidence(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        store.transition(
            session_hash,
            "active",
            "expired",
            updates={"expired_reason": "session_expired"},
        )
        result = self.module.expire_mcp_authorization(
            handoff,
            store,
            now=datetime.now(timezone.utc) + timedelta(days=2),
        )
        self.assertTrue(result["expired"])
        current = store.read()
        self.assertEqual("expired", current["status"])
        self.assertEqual("session_expired", current["expired_reason"])
        self.assertEqual("session_expired", current["analysis_close_reason"])
        self.assertIn("audit_final_head_sha256", current)
        final = self.module.verify_package(handoff)
        session = final["state"]["mcp_session"]
        self.assertEqual("expired", session["status"])
        self.assertEqual("session_expired", session["reason"])
        self.assertEqual("session_expired", session["analysis_close_reason"])

    def test_expired_response_binding_survives_later_stop_and_rejects_late_note(self) -> None:
        handoff = self.prepare()
        store, session_hash, _ = self.activate(handoff)
        self.mark_submitted(handoff, store)
        self.module.expire_mcp_authorization(
            handoff,
            store,
            now=datetime.now(timezone.utc) + timedelta(days=2),
        )
        self.module.record_mcp_stopped(
            handoff,
            session_id_sha256=session_hash,
            reason="session_expired",
        )
        verified = self.module.verify_package(handoff)
        markers = verified["manifest"]["response_markers"]
        response_path = self.root / "pro-response.md"
        response_path.write_text(
            f"{markers['begin']}\nBounded Pro findings.\n{markers['end']}\n",
            encoding="utf-8",
        )
        with redirect_stdout(io.StringIO()):
            self.module.command_import_response(
                SimpleNamespace(
                    handoff_dir=str(handoff),
                    response_file=str(response_path),
                )
            )
        imported = self.module.verify_package(handoff)
        bound = imported["state"]["response"]["mcp_terminal_evidence"]
        self.assertEqual("expired", bound["status"])
        stopped = self.module.stop_mcp_authorization(
            handoff,
            store,
            reason="user_requested",
        )
        self.assertEqual("expired", stopped["authorization"]["status"])
        after = self.module.verify_package(handoff)
        self.assertEqual("expired", after["state"]["mcp_session"]["status"])
        self.assertEqual(bound, after["state"]["response"]["mcp_terminal_evidence"])
        late_note = self.root / "late-note.txt"
        late_note.write_text("Too late.\n", encoding="utf-8")
        late_note.chmod(0o600)
        with self.assertRaisesRegex(self.module.HandoffError, "after response import"):
            self.module.command_analysis_note_prepare(
                SimpleNamespace(handoff_dir=str(handoff), message_file=str(late_note))
            )

    def test_research_handoff_lists_exact_catalog_and_uses_mcp_activation(self) -> None:
        connector = {"workspace_label": WORKSPACE_LABEL, "app_name": APP_NAME}
        summary, steps, _, _ = self.module.human_handoff_instructions(
            "app-authorization",
            transport="mcp-research",
            requested_model="ChatGPT Pro",
            outbound_paths=[{"path": "/approved/prompt.md"}],
            response_markers={"begin": "BEGIN", "end": "END"},
            github=None,
            connector=connector,
        )
        rendered = summary + "\n" + "\n".join(steps)
        for name in RESEARCH_TOOL_NAMES:
            self.assertIn(name, rendered)
        self.assertIn("mcp-activate", self.module.next_action("approved", "mcp-research"))

    def test_protocol_advertises_only_schema4_read_only_catalog(self) -> None:
        handoff = self.prepare()
        runtime, _, _ = self.fixture_runtime(handoff)
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in messages))
        output, stderr = io.StringIO(), io.StringIO()
        server = LegacyMcpServer(runtime, contract=contract_for_schema(4))
        self.assertEqual(0, server.serve(source, output, stderr))
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        tools = responses[1]["result"]["tools"]
        self.assertEqual(list(RESEARCH_TOOL_NAMES), sorted(tool["name"] for tool in tools))
        annotations = {tool["name"]: tool["annotations"] for tool in tools}
        for name, value in annotations.items():
            self.assertTrue(value["readOnlyHint"], name)
            self.assertFalse(value["destructiveHint"], name)
            self.assertFalse(value["openWorldHint"], name)
        self.assertEqual("", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
