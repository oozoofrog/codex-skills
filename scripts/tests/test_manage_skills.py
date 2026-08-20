from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "manage_skills.py"


class ManageSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.destination = Path(self.temp_dir.name) / "skills"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def test_list_and_selective_install(self) -> None:
        listing = json.loads(
            self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout
        )
        gptpro = next(item for item in listing if item["name"] == "gptpro")
        self.assertEqual("not-installed", gptpro["status"])

        self.run_cli("install", "gptpro", "--dest", str(self.destination))
        self.assertTrue((self.destination / "gptpro" / "SKILL.md").is_file())
        current = json.loads(
            self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout
        )
        self.assertEqual("current", next(item for item in current if item["name"] == "gptpro")["status"])

    def test_dry_run_does_not_create_destination(self) -> None:
        self.run_cli("install", "gptpro", "--dest", str(self.destination), "--dry-run")
        self.assertFalse(self.destination.exists())

    def test_different_install_requires_update_and_is_restored(self) -> None:
        self.run_cli("install", "gptpro", "--dest", str(self.destination))
        installed_readme = self.destination / "gptpro" / "README.md"
        installed_readme.write_text("locally changed\n", encoding="utf-8")
        self.run_cli("install", "gptpro", "--dest", str(self.destination), expected=2)
        self.run_cli("install", "gptpro", "--dest", str(self.destination), "--update")
        self.assertEqual(
            (REPO_ROOT / "gptpro" / "README.md").read_text(encoding="utf-8"),
            installed_readme.read_text(encoding="utf-8"),
        )

    def test_unknown_skill_is_rejected(self) -> None:
        self.run_cli("install", "does-not-exist", "--dest", str(self.destination), expected=2)


if __name__ == "__main__":
    unittest.main()
