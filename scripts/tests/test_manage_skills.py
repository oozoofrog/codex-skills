from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "manage_skills.py"


def load_manager():
    spec = importlib.util.spec_from_file_location("manage_skills_v05_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANAGER = load_manager()


class ManageSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.destination = self.root / "skills"
        self.trash = self.root / "Trash"
        self.legacy_handoff = self.root / "legacy-handoff"
        self.legacy_handoff.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def test_list_contains_only_standalone_gptpro(self) -> None:
        listing = json.loads(self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout)
        self.assertEqual(["gptpro"], [item["name"] for item in listing])
        self.assertEqual("not-installed", listing[0]["status"])

    def test_dry_run_is_no_create_and_matches_install_hash(self) -> None:
        dry = json.loads(self.run_cli("install", "gptpro", "--dest", str(self.destination), "--dry-run").stdout)
        self.assertFalse(self.destination.exists())
        actual = json.loads(self.run_cli("install", "gptpro", "--dest", str(self.destination)).stdout)
        self.assertEqual(dry["source_sha256"], actual["installed_sha256_after"])
        self.assertEqual("current", json.loads(self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout)[0]["status"])
        self.assertFalse((self.destination / ".gptpro-components.json").exists())
        self.assertFalse((self.destination / "gptpro-mcp").exists())

    def test_differing_install_requires_update(self) -> None:
        self.run_cli("install", "gptpro", "--dest", str(self.destination))
        (self.destination / "gptpro" / "README.md").write_text("changed\n", encoding="utf-8")
        rejected = self.run_cli("install", "gptpro", "--dest", str(self.destination), expected=2)
        self.assertIn("--update", rejected.stderr)
        self.run_cli("install", "gptpro", "--dest", str(self.destination), "--update")
        self.assertEqual(MANAGER.tree_hash(REPO_ROOT / "gptpro"), MANAGER.tree_hash(self.destination / "gptpro"))

    def _legacy_component(
        self,
        *,
        status: str,
        lease: str,
        exact_stop: bool,
        package_phase: str = "evaluated",
    ) -> Path:
        component = self.destination / "gptpro-mcp"
        (component / "scripts").mkdir(parents=True)
        (component / "SKILL.md").write_text("---\nname: gptpro-mcp\n---\n", encoding="utf-8")
        script = component / "scripts" / "gptpro.py"
        value = {
            "ok": True,
            "package": {"availability": "verified", "phase": package_phase},
            "tunnel": {
                "recorded_status": status,
                "controller_lease": lease,
                "exact_child_stop_proven": exact_stop,
                "package_binding": "same_package",
            },
        }
        script.write_text("#!/usr/bin/env python3\nimport json\nprint(json.dumps(" + repr(value) + "))\n", encoding="utf-8")
        os.chmod(script, 0o755)
        (self.destination / ".gptpro-components.json").write_text("{}\n", encoding="utf-8")
        return component

    def test_active_legacy_mcp_blocks_dry_run_and_actual(self) -> None:
        self._legacy_component(status="active", lease="live", exact_stop=False)
        for arguments in (("--dry-run",), ()):
            result = self.run_cli(
                "install", "gptpro", "--dest", str(self.destination),
                "--legacy-handoff-dir", str(self.legacy_handoff), *arguments, expected=2,
            )
            self.assertIn("GPTPRO_LEGACY_MCP_ACTIVE", result.stderr)
            self.assertTrue((self.destination / "gptpro-mcp").exists())

    def test_legacy_component_requires_exact_package_evidence(self) -> None:
        self._legacy_component(status="revoked", lease="not_live", exact_stop=True)
        result = self.run_cli(
            "install", "gptpro", "--dest", str(self.destination), "--dry-run", expected=2
        )
        self.assertIn("GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED", result.stderr)

    def test_terminal_exact_stop_allows_dry_run_without_mutation(self) -> None:
        component = self._legacy_component(status="revoked", lease="not_live", exact_stop=True)
        before = {path.relative_to(self.destination).as_posix(): path.read_bytes() for path in self.destination.rglob("*") if path.is_file()}
        result = json.loads(
            self.run_cli(
                "install", "gptpro", "--dest", str(self.destination), "--dry-run",
                "--legacy-handoff-dir", str(self.legacy_handoff),
            ).stdout
        )
        after = {path.relative_to(self.destination).as_posix(): path.read_bytes() for path in self.destination.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(result["legacy_mcp"]["safe_to_remove"])
        self.assertTrue(component.exists())

    def test_global_terminal_state_cannot_replace_terminal_package_receipt(self) -> None:
        self._legacy_component(
            status="revoked",
            lease="not_live",
            exact_stop=True,
            package_phase="approved",
        )
        result = self.run_cli(
            "install",
            "gptpro",
            "--dest",
            str(self.destination),
            "--dry-run",
            "--legacy-handoff-dir",
            str(self.legacy_handoff),
            expected=2,
        )
        self.assertIn("GPTPRO_LEGACY_MCP_ACTIVE", result.stderr)
        self.assertTrue((self.destination / "gptpro-mcp").exists())

    def test_terminal_exact_stop_install_moves_legacy_assets_to_trash(self) -> None:
        self._legacy_component(status="expired", lease="absent", exact_stop=True)
        with mock.patch.object(MANAGER, "_trash_root", return_value=self.trash):
            result = MANAGER.install(
                "gptpro",
                destination=self.destination,
                update=False,
                dry_run=False,
                legacy_handoff_dir=self.legacy_handoff,
            )
        self.assertTrue(result["legacy_removed"])
        self.assertEqual(2, len(result["trash"]))
        self.assertFalse((self.destination / "gptpro-mcp").exists())
        self.assertFalse((self.destination / ".gptpro-components.json").exists())
        self.assertTrue((self.destination / "gptpro" / "SKILL.md").is_file())

    def test_duplicate_user_files_are_not_installed_or_hashed(self) -> None:
        source = self.root / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
        duplicate = source / "temporary 2.md"
        compound_duplicate = source / "temporary 2.test.js"
        duplicate.write_text("user duplicate\n", encoding="utf-8")
        compound_duplicate.write_text("user duplicate\n", encoding="utf-8")
        source_hash = MANAGER.tree_hash(source)
        duplicate.write_text("changed duplicate\n", encoding="utf-8")
        compound_duplicate.write_text("changed duplicate\n", encoding="utf-8")
        self.assertEqual(source_hash, MANAGER.tree_hash(source))
        target = self.root / "copied"
        MANAGER._copy_package(source, target)
        self.assertFalse((target / duplicate.name).exists())
        self.assertFalse((target / compound_duplicate.name).exists())


if __name__ == "__main__":
    unittest.main()
