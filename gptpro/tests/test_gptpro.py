from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"
STRUCTURE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_structure.py"


def load_gptpro_module():
    spec = importlib.util.spec_from_file_location("gptpro_cli_scanner_tests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GPTPRO = load_gptpro_module()


class GptProCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.git("add", "src/main.py", "README.md")
        self.git("commit", "-m", "fixture")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()

        self.secret_value = "sk-" + "a" * 32
        (self.repo / ".env").write_text("SAFE_NAME=still-excluded\n", encoding="utf-8")
        (self.repo / "secret.txt").write_text(f"OPENAI_API_KEY={self.secret_value}\n", encoding="utf-8")
        self.output_root = self.root / "handoffs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def run_cli(
        self, *args: str, expected: int = 0, umask: int = -1
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            umask=umask,
        )
        self.assertEqual(expected, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def configure_github_remote(self, *, pr_number: int | None = None) -> Path:
        remote = self.root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        github_url = "https://github.com/example/repository.git"
        self.git("config", "remote.origin.url", github_url)
        self.git("config", f"url.{remote.resolve().as_uri()}.insteadOf", github_url)
        self.git("push", "origin", "HEAD:refs/heads/main")
        if pr_number is not None:
            self.git("push", "origin", f"HEAD:refs/pull/{pr_number}/head")
        return remote

    def prepare(self, mode: str = "review", *extra: str) -> Path:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            mode,
            "--task",
            "Consult on this repository fixture.",
            "--output-root",
            str(self.output_root),
            *extra,
        )
        return Path(json.loads(result.stdout)["handoff_dir"])

    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def approve_and_submit(self, handoff: Path) -> dict:
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        github = manifest["transport"].get("github")
        github_args = (
            [
                "--observed-github-repository",
                github["repository"],
                "--observed-github-commit",
                github["commit_sha"],
            ]
            if github
            else []
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--confirm-sent",
            *github_args,
        )
        return manifest

    def test_prepare_records_git_and_excludes_detected_secrets_without_values(self) -> None:
        handoff = self.prepare()
        manifest_text = (handoff / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        self.assertEqual(self.head, manifest["git"]["head_sha"])
        self.assertFalse(manifest["git"]["clean"])
        self.assertIn("src/main.py", {item["path"] for item in manifest["files"]})
        finding_paths = {item["path"] for item in manifest["security_findings"]}
        self.assertIn(".env", finding_paths)
        self.assertIn("secret.txt", finding_paths)
        self.assertNotIn(self.secret_value, manifest_text)
        self.assertEqual(0, self.run_cli("verify", "--handoff-dir", str(handoff)).returncode)

    def test_json_boundaries_normalize_surrogates_and_excessive_depth(self) -> None:
        surrogate = json.loads(r'{"value":"\ud800"}')
        receipt_event = {
            "sequence": 1,
            "timestamp": "2026-08-22T00:00:00Z",
            "type": "prepared",
            "data": surrogate,
            "previous_event_hash": None,
            "event_hash": "0" * 64,
        }
        for label, action in (
            ("canonical", lambda: GPTPRO.canonical_json_bytes(surrogate)),
            ("pretty", lambda: GPTPRO.pretty_json_bytes(surrogate)),
            ("receipt-hash", lambda: GPTPRO.event_hash(receipt_event)),
        ):
            with self.subTest(boundary=label), self.assertRaises(GPTPRO.HandoffError):
                action()

        artifact = self.root / "surrogate.json"
        artifact.write_text(r'{"value":"\ud800"}', encoding="utf-8")
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.load_json(artifact)

        nested: object = 0
        for _ in range(GPTPRO.MAX_JSON_NESTING_DEPTH + 1):
            nested = [nested]
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.canonical_json_bytes({"nested": nested})

        receipt = GPTPRO.new_receipt(
            "package-one", {"manifest_sha256": "0" * 64}, schema_version=2
        )
        receipt["unexpected_nested_value"] = nested
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.receipt_with_event(receipt, "approved", {})

    def test_schema3_handoff_and_all_artifacts_are_owner_only_under_common_umasks(self) -> None:
        tunnel_id = self.root / "tunnel-id"
        tunnel_id.write_text("tunnel_" + "permissiontest" * 2, encoding="utf-8")
        tunnel_id.chmod(0o600)
        for process_umask in (0o022, 0o002):
            with self.subTest(umask=oct(process_umask)):
                output = self.root / f"handoffs-{process_umask:o}"
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "review",
                    "--task",
                    "Verify private package modes.",
                    "--transport",
                    "mcp-read",
                    "--output-root",
                    str(output),
                    "--tunnel-runtime-alias",
                    "permission-test",
                    "--tunnel-id-ref",
                    f"file:{tunnel_id}",
                    "--chatgpt-app-name",
                    "GPT Pro Repository Reader",
                    "--chatgpt-workspace-label",
                    "Permission Test Workspace",
                    umask=process_umask,
                )
                handoff = Path(json.loads(result.stdout)["handoff_dir"])
                self.assertEqual(0o700, handoff.stat().st_mode & 0o777)
                artifacts = [path for path in handoff.iterdir() if path.is_file()]
                self.assertTrue(artifacts)
                self.assertTrue(
                    all((path.stat().st_mode & 0o777) == 0o600 for path in artifacts),
                    {path.name: oct(path.stat().st_mode & 0o777) for path in artifacts},
                )
                self.run_cli("verify", "--handoff-dir", str(handoff))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "requires openat")
    def test_scan_rejects_final_component_symlink_swap_without_reading_outside_file(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text(f"OPENAI_API_KEY={self.secret_value}\n", encoding="utf-8")
        original = self.repo / "README.md"
        backup = self.repo / "README.original"
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is not None and path == "README.md" and not swapped:
                swapped = True
                original.rename(backup)
                original.symlink_to(outside)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(GPTPRO.os, "open", side_effect=swapping_open):
            scan = GPTPRO.scan_repository(
                self.repo,
                include_patterns=[],
                exclude_patterns=[],
                file_list_entries=[],
                max_files=100,
                max_bytes=1024 * 1024,
                max_file_bytes=1024 * 1024,
            )

        self.assertTrue(swapped)
        self.assertNotIn("README.md", {item.path for item in scan["included"]})
        self.assertIn(
            {"path": "README.md", "reason": "symlink"},
            scan["excluded"],
        )
        self.assertNotIn("README.md", {item["path"] for item in scan["security"]})

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "requires openat")
    def test_scan_rejects_intermediate_component_symlink_swap_without_reading_outside_file(self) -> None:
        outside = self.root / "outside-src"
        outside.mkdir()
        (outside / "main.py").write_text(
            f"OPENAI_API_KEY={self.secret_value}\n",
            encoding="utf-8",
        )
        original = self.repo / "src"
        backup = self.repo / "src.original"
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is not None and path == "src" and not swapped:
                swapped = True
                original.rename(backup)
                original.symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(GPTPRO.os, "open", side_effect=swapping_open):
            scan = GPTPRO.scan_repository(
                self.repo,
                include_patterns=[],
                exclude_patterns=[],
                file_list_entries=[],
                max_files=100,
                max_bytes=1024 * 1024,
                max_file_bytes=1024 * 1024,
            )

        self.assertTrue(swapped)
        self.assertNotIn("src/main.py", {item.path for item in scan["included"]})
        self.assertIn(
            {"path": "src/main.py", "reason": "unreadable"},
            scan["excluded"],
        )
        self.assertNotIn("src/main.py", {item["path"] for item in scan["security"]})

    def test_init_previews_then_applies_local_git_exclude_idempotently(self) -> None:
        preview = json.loads(
            self.run_cli("init", "--repo", str(self.repo)).stdout
        )
        self.assertFalse(preview["applied"])
        self.assertFalse(preview["ready"])
        self.assertEqual(
            {"create-directory", "append-ignore-entry"},
            {item["action"] for item in preview["actions"]},
        )
        self.assertFalse((self.repo / ".gptpro" / "handoffs").exists())

        applied = json.loads(
            self.run_cli("init", "--repo", str(self.repo), "--apply").stdout
        )
        self.assertTrue(applied["applied"])
        self.assertTrue(applied["ready"])
        self.assertTrue(applied["ignore_effective"])
        self.assertTrue((self.repo / ".gptpro" / "handoffs").is_dir())
        exclude_raw = self.git("rev-parse", "--git-path", "info/exclude").stdout.strip()
        exclude_path = Path(exclude_raw)
        if not exclude_path.is_absolute():
            exclude_path = self.repo / exclude_path
        exclude_text = exclude_path.read_text(encoding="utf-8")
        self.assertEqual(1, exclude_text.count(".gptpro/"))
        self.assertNotIn(".gptpro", self.git("status", "--porcelain=v1").stdout)

        repeated = json.loads(
            self.run_cli("init", "--repo", str(self.repo), "--apply").stdout
        )
        self.assertTrue(repeated["ready"])
        self.assertEqual([], repeated["changes"])
        self.assertEqual(1, exclude_path.read_text(encoding="utf-8").count(".gptpro/"))

    def test_init_can_write_repository_gitignore_when_explicitly_selected(self) -> None:
        result = json.loads(
            self.run_cli(
                "init",
                "--repo",
                str(self.repo),
                "--ignore-scope",
                "repository",
                "--apply",
            ).stdout
        )

        self.assertTrue(result["ready"])
        self.assertEqual((self.repo / ".gitignore").resolve(), Path(result["ignore_target"]))
        gitignore = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# gptpro local handoff artifacts\n.gptpro/\n", gitignore)
        self.assertIn("?? .gitignore", self.git("status", "--porcelain=v1").stdout)

    def test_init_external_output_needs_no_git_ignore_change(self) -> None:
        external = self.root / "external-handoffs"
        result = json.loads(
            self.run_cli(
                "init",
                "--repo",
                str(self.repo),
                "--output-root",
                str(external),
                "--apply",
            ).stdout
        )

        self.assertTrue(result["ready"])
        self.assertFalse(result["output_inside_repo"])
        self.assertIsNone(result["ignore_target"])
        self.assertEqual(["create-directory"], [item["action"] for item in result["changes"]])
        self.assertTrue(external.is_dir())

    def test_prepare_warns_until_default_output_is_git_ignored(self) -> None:
        first = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--task",
            "First-use warning check.",
        )
        first_manifest = self.load(Path(json.loads(first.stdout)["handoff_dir"]) / "manifest.json")
        self.assertTrue(any("not Git-ignored" in item for item in first_manifest["warnings"]))

        self.run_cli("init", "--repo", str(self.repo), "--apply")
        second = json.loads(
            self.run_cli(
                "prepare",
                "--repo",
                str(self.repo),
                "--mode",
                "ask",
                "--task",
                "Configured warning check.",
                "--dry-run",
            ).stdout
        )
        self.assertFalse(any("not Git-ignored" in item for item in second["warnings"]))

    def test_all_modes_support_dry_run(self) -> None:
        for mode in ("plan", "ask", "review", "debug", "architecture"):
            with self.subTest(mode=mode):
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    mode,
                    "--task",
                    "Bounded question.",
                    "--dry-run",
                )
                payload = json.loads(result.stdout)
                self.assertEqual(self.head, payload["git_head_sha"])
                self.assertGreater(payload["included_files"], 0)
                self.assertIn(payload["transport_resolved"], ("paste", "text-file"))

    def test_auto_transport_uses_paste_for_small_payload(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)

        self.assertEqual("auto", manifest["transport"]["requested"])
        self.assertEqual("paste", manifest["transport"]["resolved"])
        self.assertEqual(["paste_payload"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNotNone(status["paste_payload_path"])
        self.assertNotIn(
            status["local_audit_archive_path"],
            {item["path"] for item in status["outbound_paths"]},
        )
        self.assertFalse(status["human_takeover"]["available"])
        self.assertEqual([], status["human_takeover"]["reasons"])

    def test_human_handoff_is_read_only_and_phase_aware(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        before_state = (handoff / "state.json").read_bytes()
        before_receipt = (handoff / "receipt.json").read_bytes()

        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "manual-transport",
                "--details",
                "Chrome control is unavailable.",
            ).stdout
        )

        self.assertEqual("human_action_required", result["status"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["state_unchanged"])
        self.assertEqual("approved", result["phase"])
        self.assertEqual("paste", result["transport"])
        self.assertEqual("Chrome control is unavailable.", result["observed_blocker_details"])
        self.assertEqual(["sent", "not-sent", "unknown"], result["resume"]["allowed_outcomes"])
        self.assertFalse(result["resume"]["automatic_retry_allowed"])
        self.assertEqual(
            [manifest["transport"]["outbound_artifacts"][0]["sha256"]],
            [item["sha256"] for item in result["outbound_paths"]],
        )
        self.assertEqual(before_state, (handoff / "state.json").read_bytes())
        self.assertEqual(before_receipt, (handoff / "receipt.json").read_bytes())

        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertTrue(status["human_takeover"]["available"])
        self.assertIn("manual-transport", status["human_takeover"]["reasons"])
        self.assertNotIn("file-selection", status["human_takeover"]["reasons"])

    def test_text_file_human_handoff_lists_only_approved_attachment(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "file-selection",
            ).stdout
        )

        attachment_paths = [item["path"] for item in result["outbound_paths"] if item["role"] == "attachment"]
        self.assertEqual(1, len(attachment_paths))
        self.assertTrue(any(attachment_paths[0] in step for step in result["human_steps"]))
        self.assertIn("file-permission", json.loads(
            self.run_cli("status", "--handoff-dir", str(handoff)).stdout
        )["human_takeover"]["reasons"])

    def test_human_handoff_rejects_wrong_phase_or_transport(self) -> None:
        paste_handoff = self.prepare()
        self.run_cli(
            "human-handoff",
            "--handoff-dir",
            str(paste_handoff),
            "--reason",
            "manual-transport",
            expected=2,
        )
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(paste_handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "human-handoff",
            "--handoff-dir",
            str(paste_handoff),
            "--reason",
            "file-selection",
            expected=2,
        )

    def test_submitted_handoff_offers_human_response_export(self) -> None:
        handoff = self.prepare()
        manifest = self.approve_and_submit(handoff)
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual(["login", "captcha", "response-export"], status["human_takeover"]["reasons"])

        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "response-export",
            ).stdout
        )
        markers = manifest["response_markers"]
        instructions = "\n".join(result["human_steps"] + result["return_with"])
        self.assertIn(markers["begin"], instructions)
        self.assertIn(markers["end"], instructions)
        self.assertEqual(
            "run import-response with the saved response file",
            result["resume"]["on_completed"],
        )

    def test_auto_transport_uses_text_file_over_policy_threshold(self) -> None:
        handoff = self.prepare("review", "--max-paste-bytes", "1")
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)

        self.assertEqual("text-file", manifest["transport"]["resolved"])
        self.assertEqual(["prompt", "context"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNone(status["paste_payload_path"])

    def test_auto_transport_prefers_verified_github_snapshot(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("review", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")

        self.assertEqual("auto", manifest["transport"]["requested"])
        self.assertEqual("github", manifest["transport"]["resolved"])
        self.assertEqual(self.head, manifest["transport"]["github"]["commit_sha"])
        self.assertEqual(
            ["prompt"],
            [item["artifact"] for item in manifest["transport"]["outbound_artifacts"]],
        )

    def test_auto_transport_records_github_fallback_reason(self) -> None:
        handoff = self.prepare("ask")
        manifest = self.load(handoff / "manifest.json")

        self.assertEqual("paste", manifest["transport"]["resolved"])
        self.assertTrue(any("GitHub-first auto transport was unavailable" in item for item in manifest["warnings"]))

    def test_github_transport_pins_remote_commit_and_sends_only_prompt(self) -> None:
        self.configure_github_remote(pr_number=17)
        handoff = self.prepare(
            "review",
            "--transport",
            "github",
            "--github-pr-url",
            "https://github.com/example/repository/pull/17",
            "--include",
            "src/**",
        )
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        github = manifest["transport"]["github"]

        self.assertEqual("github", manifest["transport"]["resolved"])
        self.assertEqual("example/repository", github["repository"])
        self.assertEqual(self.head, github["commit_sha"])
        self.assertEqual("refs/pull/17/head", github["remote_ref"])
        self.assertEqual(["src/main.py"], github["allowed_paths"])
        self.assertTrue(github["remote_verified"])
        self.assertEqual(["prompt"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNone(status["paste_payload_path"])
        prompt = (handoff / "prompt.md").read_text(encoding="utf-8")
        self.assertIn(self.head, prompt)
        self.assertIn("example/repository", prompt)
        self.assertIn("GPTPRO_GITHUB_ATTESTATION", prompt)
        self.assertNotIn("def answer():", prompt)

    def test_github_transport_rejects_selected_dirty_or_unpushed_content(self) -> None:
        self.configure_github_remote()
        (self.repo / "src" / "main.py").write_text("def answer():\n    return 43\n", encoding="utf-8")
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Review selected code.",
            "--output-root",
            str(self.output_root),
            "--transport",
            "github",
            "--include",
            "src/**",
            expected=2,
        )
        self.assertIn("cannot represent selected local-only or dirty content", result.stderr)

        self.git("add", "src/main.py")
        self.git("commit", "-m", "not pushed")
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Review selected code.",
            "--output-root",
            str(self.output_root),
            "--transport",
            "github",
            "--include",
            "src/**",
            expected=2,
        )
        self.assertIn("not advertised by a GitHub branch or tag", result.stderr)

    def test_github_submission_and_response_require_pinned_identity(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("debug", "--transport", "github", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        github = manifest["transport"]["github"]
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
            "github",
            "--observed-github-repository",
            github["repository"],
            "--observed-github-commit",
            "0" * 40,
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "github",
            "--observed-github-repository",
            github["repository"],
            "--observed-github-commit",
            github["commit_sha"],
            "--confirm-sent",
        )
        markers = manifest["response_markers"]
        response_file = self.root / "github-response.md"
        response_file.write_text(
            f"{markers['begin']}\n"
            "GPTPRO_GITHUB_ATTESTATION: "
            + json.dumps(
                {
                    "status": "accessed",
                    "repository": github["repository"],
                    "commit_sha": github["commit_sha"],
                    "files_read": ["src/main.py"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + f"\nPinned analysis.\n{markers['end']}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        state = self.load(handoff / "state.json")
        self.assertEqual("accessed", state["response"]["github_attestation"]["status"])
        self.assertEqual(["src/main.py"], state["response"]["github_attestation"]["files_read"])

    def test_github_human_handoff_names_app_scope_and_prompt_only(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("review", "--transport", "github", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )

        authorization = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "app-authorization",
            ).stdout
        )
        manual = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "manual-transport",
            ).stdout
        )
        authorization_text = "\n".join(authorization["human_steps"])
        manual_text = "\n".join(manual["human_steps"])
        self.assertIn(manifest["transport"]["github"]["repository"], authorization_text)
        self.assertIn(manifest["transport"]["github"]["commit_sha"], authorization_text)
        self.assertIn("Activate the visible GitHub app/plugin", manual_text)
        self.assertIn("attach no local file", manual_text)
        self.assertEqual(["prompt"], [item["artifact"] for item in manual["outbound_paths"]])

    def test_text_context_contains_selected_files_without_local_absolute_paths(self) -> None:
        file_list = self.root / "selected-files.txt"
        file_list.write_text("src/main.py\n", encoding="utf-8")
        handoff = self.prepare(
            "architecture",
            "--transport",
            "text-file",
            "--file-list",
            str(file_list),
        )
        manifest = self.load(handoff / "manifest.json")
        context = (handoff / manifest["artifacts"]["context"]).read_text(encoding="utf-8")

        self.assertIn("src/main.py", context)
        self.assertIn("def answer():", context)
        self.assertIn(self.head, context)
        self.assertNotIn(str(self.repo), context)
        self.assertNotIn(str(file_list), context)
        with zipfile.ZipFile(handoff / manifest["artifacts"]["archive"], "r") as archive:
            internal = archive.read("_gptpro/file-manifest.json").decode("utf-8")
        self.assertNotIn(str(self.repo), internal)
        self.assertNotIn(str(file_list), internal)

    def test_non_utf8_text_is_excluded_from_text_transport(self) -> None:
        (self.repo / "invalid.txt").write_bytes(b"not utf-8: \xff\xfe")
        handoff = self.prepare("ask")
        manifest = self.load(handoff / "manifest.json")

        reasons = {(item["path"], item["reason"]) for item in manifest["excluded"]}
        self.assertIn(("invalid.txt", "non-utf8-text"), reasons)

    def test_directed_selection_records_omitted_files(self) -> None:
        handoff = self.prepare("architecture", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        self.assertEqual("directed", manifest["selection"]["mode"])
        self.assertEqual({"src/main.py"}, {item["path"] for item in manifest["files"]})
        self.assertIn("README.md", {item["path"] for item in manifest["omitted_by_selection"]})

    def test_approval_and_submission_gates_are_enforced(self) -> None:
        handoff = self.prepare()
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            "Pro",
            "--observed-transport",
            "paste",
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            expected=2,
        )
        self.approve_and_submit(handoff)
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual("submitted", status["phase"])
        receipt = self.load(handoff / "receipt.json")
        outbound = self.load(handoff / "manifest.json")["transport"]["outbound_artifacts"]
        self.assertEqual(
            outbound,
            receipt["events"][1]["data"]["outbound_artifacts"],
        )
        self.assertEqual(outbound, receipt["events"][2]["data"]["outbound_artifacts"])

    def test_submission_rejects_model_or_pro_setting_drift(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
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
            "A fallback model",
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--confirm-sent",
        )

    def test_submission_rejects_transport_fallback(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        manifest = self.load(handoff / "manifest.json")
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
            expected=2,
        )

    def test_response_import_and_evaluation_complete_receipt_chain(self) -> None:
        handoff = self.prepare("debug")
        manifest = self.approve_and_submit(handoff)
        markers = manifest["response_markers"]
        response_file = self.root / "response.md"
        response_file.write_text(
            f"{markers['begin']}\nA bounded advisory answer.\n{markers['end']}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        self.assertEqual("A bounded advisory answer.\n", (handoff / "response.md").read_text(encoding="utf-8"))
        self.run_cli(
            "record-evaluation",
            "--handoff-dir",
            str(handoff),
            "--verdict",
            "partially-accepted",
            "--summary",
            "One claim was confirmed.",
            "--evidence",
            "manual source inspection",
        )
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(
            ["prepared", "approved", "submitted", "response_imported", "evaluated"],
            [event["type"] for event in receipt["events"]],
        )
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_foreign_or_unmarked_response_is_rejected(self) -> None:
        handoff = self.prepare()
        self.approve_and_submit(handoff)
        response_file = self.root / "foreign.md"
        response_file.write_text("BEGIN_GPTPRO_RESPONSE:other\nNo.\nEND_GPTPRO_RESPONSE:other\n", encoding="utf-8")
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
            expected=2,
        )

    def test_archive_tampering_is_detected(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        archive = handoff / manifest["artifacts"]["archive"]
        with archive.open("ab") as handle:
            handle.write(b"tampered")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_paste_payload_tampering_is_detected(self) -> None:
        handoff = self.prepare("review", "--transport", "paste")
        manifest = self.load(handoff / "manifest.json")
        payload = handoff / manifest["artifacts"]["paste_payload"]
        with payload.open("a", encoding="utf-8") as handle:
            handle.write("tampered\n")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_text_context_tampering_is_detected(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        manifest = self.load(handoff / "manifest.json")
        context = handoff / manifest["artifacts"]["context"]
        with context.open("a", encoding="utf-8") as handle:
            handle.write("tampered\n")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_receipt_tampering_is_detected(self) -> None:
        handoff = self.prepare()
        receipt_path = handoff / "receipt.json"
        receipt = self.load(receipt_path)
        receipt["events"][0]["data"]["git_head_sha"] = "0" * 40
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_custom_output_root_inside_repo_is_never_repackaged(self) -> None:
        output_root = self.repo / "handoffs"
        first = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--task",
            "First package.",
            "--output-root",
            str(output_root),
        )
        self.assertTrue(Path(json.loads(first.stdout)["handoff_dir"]).is_dir())
        second = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Second package.",
            "--output-root",
            str(output_root),
        )
        manifest = self.load(Path(json.loads(second.stdout)["handoff_dir"]) / "manifest.json")
        self.assertFalse(any(item["path"].startswith("handoffs/") for item in manifest["files"]))


class GptProStructureTests(unittest.TestCase):
    def test_dependency_free_validator_checks_standalone_and_plugin_mirror(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        repository_root = skill_root.parent
        mirror = repository_root / "plugins" / "gptpro" / "skills" / "gptpro"
        result = subprocess.run(
            [
                "python3",
                str(STRUCTURE_SCRIPT),
                "--skill-dir",
                str(skill_root),
                "--mirror",
                str(mirror),
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertIn("standalone-plugin-mirror", payload["checks"])

    def test_dependency_free_validator_reports_missing_required_file(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            damaged = Path(temp) / "gptpro"
            shutil.copytree(skill_root, damaged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (damaged / "references" / "security.md").unlink()
            result = subprocess.run(
                ["python3", str(damaged / "scripts" / "validate_structure.py"), "--json"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertIn("Required file missing: references/security.md", payload["errors"])


if __name__ == "__main__":
    unittest.main()
