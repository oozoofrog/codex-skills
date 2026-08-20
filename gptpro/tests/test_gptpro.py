from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"


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

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

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
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--confirm-sent",
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
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--confirm-sent",
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


if __name__ == "__main__":
    unittest.main()
