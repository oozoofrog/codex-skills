from __future__ import annotations

import json
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "manage_skills.py"


def load_manager_module():
    spec = importlib.util.spec_from_file_location("gptpro_manage_skills_tests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MANAGER = load_manager_module()


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
        self.assertEqual(["gptpro", "gptpro-mcp"], [item["name"] for item in listing])
        gptpro = next(item for item in listing if item["name"] == "gptpro")
        self.assertEqual("not-installed", gptpro["status"])
        self.assertEqual(
            "not-installed",
            next(item for item in listing if item["name"] == "gptpro-mcp")["status"],
        )

        self.run_cli("install", "gptpro", "--dest", str(self.destination))
        self.assertTrue((self.destination / "gptpro" / "SKILL.md").is_file())
        self.assertTrue((self.destination / "gptpro-mcp" / "SKILL.md").is_file())
        current = json.loads(
            self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout
        )
        self.assertEqual("current", next(item for item in current if item["name"] == "gptpro")["status"])

        descriptor_path = self.destination / ".gptpro-components.json"
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        self.assertEqual(0o600, stat.S_IMODE(descriptor_path.stat().st_mode))
        self.assertEqual(["gptpro", "gptpro-mcp"], sorted(descriptor["components"]))
        self.assertEqual(
            str((self.destination / "gptpro" / "scripts" / "gptpro.py").resolve()),
            descriptor["components"]["gptpro"]["entrypoint"],
        )

        self.run_cli("install", "gptpro-mcp", "--dest", str(self.destination))
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        self.assertEqual(["gptpro", "gptpro-mcp"], sorted(descriptor["components"]))
        handshake = subprocess.run(
            [
                "python3",
                str(self.destination / "gptpro-mcp" / "scripts" / "component_handshake.py"),
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, handshake.returncode, msg=handshake.stderr)
        self.assertEqual("installer-descriptor", json.loads(handshake.stdout)["selection_source"])

    def test_dry_run_does_not_create_destination(self) -> None:
        self.run_cli("install", "gptpro", "--dest", str(self.destination), "--dry-run")
        self.assertFalse(self.destination.exists())

    def test_selective_mcp_install_does_not_install_base(self) -> None:
        self.run_cli("install", "gptpro-mcp", "--dest", str(self.destination))
        self.assertTrue((self.destination / "gptpro-mcp" / "SKILL.md").is_file())
        self.assertFalse((self.destination / "gptpro").exists())
        descriptor = json.loads(
            (self.destination / ".gptpro-components.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["gptpro-mcp"], sorted(descriptor["components"]))

    def _write_legacy_base(
        self,
        recorded_status: str,
        *,
        exact_child_stop_proven: bool = False,
        include_session_binding: bool = True,
    ) -> str:
        target = self.destination / "gptpro"
        (target / "runtime" / "gptpro_mcp").mkdir(parents=True)
        (target / "scripts").mkdir()
        (target / "SKILL.md").write_text("---\nname: gptpro\n---\n", encoding="utf-8")
        script = target / "scripts" / "gptpro.py"
        tunnel = {
            "recorded_status": recorded_status,
            "exact_child_stop_proven": exact_child_stop_proven,
            "migration_session_binding_sha256": (
                "a" * 64 if include_session_binding else None
            ),
        }
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            f"print(json.dumps({{'tunnel': {tunnel!r}}}))\n",
            encoding="utf-8",
        )
        os.chmod(script, 0o755)
        listing = json.loads(
            self.run_cli("list", "--dest", str(self.destination), "--format", "json").stdout
        )
        return next(item for item in listing if item["name"] == "gptpro")["installed_sha256"]

    def test_unresolved_legacy_update_requires_exact_handoff_path(self) -> None:
        self._write_legacy_base("active")
        rejected = self.run_cli(
            "install",
            "gptpro",
            "--dest",
            str(self.destination),
            "--update",
            expected=2,
        )
        self.assertIn("GPTPRO_LEGACY_PACKAGE_EVIDENCE_REQUIRED", rejected.stderr)
        self.assertTrue((self.destination / "gptpro" / "runtime" / "gptpro_mcp").is_dir())

    def test_terminal_legacy_update_with_exact_stop_does_not_require_mcp(self) -> None:
        self._write_legacy_base("revoked", exact_child_stop_proven=True)
        target = self.destination / "gptpro"
        handoff = Path(self.temp_dir.name).resolve() / "handoff"
        with (
            mock.patch.object(
                MANAGER,
                "component_runtime_evidence",
                return_value={"status": "revoked", "exact_child_stop_proven": True},
            ),
            mock.patch.object(
                MANAGER,
                "_run_transition_command",
                return_value={
                    "decision": "safe_exact_terminal",
                    "exact_child_stop_proven": True,
                },
            ),
        ):
            evidence = MANAGER.require_mcp_transition_owner(
                REPO_ROOT / "gptpro",
                target,
                self.destination,
                legacy_handoff_dir=handoff,
                adopt_residual_mcp_state=False,
                confirm_legacy_package_unavailable=False,
                dry_run=True,
            )
        self.assertEqual("safe_exact_terminal", evidence["decision"])
        self.assertTrue(evidence["exact_child_stop_proven"])
        self.assertFalse(evidence["ownership_transferred"])

    def test_terminal_status_without_exact_stop_requires_mcp_owner(self) -> None:
        self._write_legacy_base("revoked")
        target = self.destination / "gptpro"
        handoff = Path(self.temp_dir.name).resolve() / "handoff"
        with (
            mock.patch.object(
                MANAGER,
                "component_runtime_evidence",
                return_value={"status": "revoked", "exact_child_stop_proven": False},
            ),
            mock.patch.object(
                MANAGER,
                "_run_transition_command",
                return_value={"decision": "adoption_required"},
            ),
            mock.patch.object(MANAGER, "component_capabilities", return_value=None),
            self.assertRaises(MANAGER.ManagerError) as raised,
        ):
            MANAGER.require_mcp_transition_owner(
                REPO_ROOT / "gptpro",
                target,
                self.destination,
                legacy_handoff_dir=handoff,
                adopt_residual_mcp_state=True,
                confirm_legacy_package_unavailable=False,
                dry_run=True,
            )
        self.assertIn("GPTPRO_MCP_COMPONENT_REQUIRED", str(raised.exception))

    def test_residual_adoption_dry_run_and_actual_use_same_decision_path(self) -> None:
        self._write_legacy_base("revoked")
        target = self.destination / "gptpro"
        handoff = Path(self.temp_dir.name).resolve() / "handoff"
        capabilities = {
            "contract": "gptpro-component-capabilities-v1",
            "component": "gptpro-mcp",
            "mcp_runtime": True,
            "version": "0.1.0",
        }
        adoption_required = {"decision": "adoption_required"}
        with (
            mock.patch.object(
                MANAGER,
                "component_runtime_evidence",
                return_value={"status": "revoked", "exact_child_stop_proven": False},
            ),
            mock.patch.object(MANAGER, "component_capabilities", return_value=capabilities),
            mock.patch.object(
                MANAGER, "installed_component_binding_verified", return_value=True
            ),
            mock.patch.object(
                MANAGER,
                "_run_transition_command",
                side_effect=[adoption_required, adoption_required],
            ) as transition,
        ):
            dry = MANAGER.require_mcp_transition_owner(
                REPO_ROOT / "gptpro",
                target,
                self.destination,
                legacy_handoff_dir=handoff,
                adopt_residual_mcp_state=True,
                confirm_legacy_package_unavailable=False,
                dry_run=True,
            )
        self.assertEqual("would_adopt_residual", dry["decision"])
        self.assertEqual(2, transition.call_count)

        adopted = {
            "operation": "residual-adopt",
            "decision": "safe_owned_residual",
            "ownership_transferred": True,
            "exact_child_stop_proven": False,
            "residual_receipt_sha256": "b" * 64,
        }
        with (
            mock.patch.object(
                MANAGER,
                "component_runtime_evidence",
                return_value={"status": "revoked", "exact_child_stop_proven": False},
            ),
            mock.patch.object(MANAGER, "component_capabilities", return_value=capabilities),
            mock.patch.object(
                MANAGER, "installed_component_binding_verified", return_value=True
            ),
            mock.patch.object(
                MANAGER,
                "_run_transition_command",
                side_effect=[adoption_required, adoption_required, adopted],
            ),
        ):
            actual = MANAGER.require_mcp_transition_owner(
                REPO_ROOT / "gptpro",
                target,
                self.destination,
                legacy_handoff_dir=handoff,
                adopt_residual_mcp_state=True,
                confirm_legacy_package_unavailable=False,
                dry_run=False,
            )
        self.assertEqual("safe_owned_residual", actual["decision"])
        self.assertTrue(actual["ownership_transferred"])
        self.assertFalse(actual["exact_child_stop_proven"])
        self.assertEqual("b" * 64, actual["residual_receipt_sha256"])

    def test_residual_dry_run_rejects_unbound_installed_owner(self) -> None:
        self._write_legacy_base("revoked")
        target = self.destination / "gptpro"
        handoff = Path(self.temp_dir.name).resolve() / "handoff"
        capabilities = {
            "contract": "gptpro-component-capabilities-v1",
            "component": "gptpro-mcp",
            "mcp_runtime": True,
            "version": "0.1.0",
        }
        with (
            mock.patch.object(
                MANAGER,
                "component_runtime_evidence",
                return_value={"status": "revoked", "exact_child_stop_proven": False},
            ),
            mock.patch.object(
                MANAGER,
                "_run_transition_command",
                return_value={"decision": "adoption_required"},
            ),
            mock.patch.object(MANAGER, "component_capabilities", return_value=capabilities),
            mock.patch.object(
                MANAGER, "installed_component_binding_verified", return_value=False
            ),
            self.assertRaises(MANAGER.ManagerError) as raised,
        ):
            MANAGER.require_mcp_transition_owner(
                REPO_ROOT / "gptpro",
                target,
                self.destination,
                legacy_handoff_dir=handoff,
                adopt_residual_mcp_state=True,
                confirm_legacy_package_unavailable=False,
                dry_run=True,
            )
        self.assertIn("GPTPRO_MCP_COMPONENT_REQUIRED", str(raised.exception))

    def test_update_rollback_preserves_old_tree_and_external_receipt(self) -> None:
        source = REPO_ROOT / "gptpro"
        target = self.destination / "gptpro"
        target.parent.mkdir(parents=True)
        shutil.copytree(source, target)
        old_readme = target / "README.md"
        old_readme.write_text("old installed tree\n", encoding="utf-8")
        receipt = Path(self.temp_dir.name) / "residual-receipt.json"
        receipt.write_text('{"ownership_transferred":true}\n', encoding="utf-8")
        original_replace = MANAGER.os.replace
        replacement_count = 0

        def fail_stage_replace(source_path, target_path):
            nonlocal replacement_count
            replacement_count += 1
            if replacement_count == 2:
                raise OSError("simulated base replacement failure")
            return original_replace(source_path, target_path)

        with (
            mock.patch.object(MANAGER.os, "replace", side_effect=fail_stage_replace),
            self.assertRaises(OSError),
        ):
            MANAGER.install_one(source, target, update=True, dry_run=False)
        self.assertEqual("old installed tree\n", old_readme.read_text(encoding="utf-8"))
        self.assertEqual(
            '{"ownership_transferred":true}\n', receipt.read_text(encoding="utf-8")
        )

    def test_descriptor_failure_before_base_replace_is_safe_and_repaired_on_retry(self) -> None:
        self._write_legacy_base("revoked")
        target = self.destination / "gptpro"
        receipt = Path(self.temp_dir.name) / "residual-receipt.json"
        receipt.write_text('{"ownership_transferred":true}\n', encoding="utf-8")
        args = MANAGER.build_parser().parse_args(
            [
                "install",
                "gptpro",
                "--dest",
                str(self.destination),
                "--update",
                "--legacy-handoff-dir",
                str((Path(self.temp_dir.name) / "handoff").resolve()),
                "--adopt-residual-mcp-state",
            ]
        )
        delegated = {
            "decision": "safe_owned_residual",
            "exact_child_stop_proven": False,
            "ownership_transferred": True,
            "residual_receipt_sha256": "c" * 64,
        }
        with (
            mock.patch.object(
                MANAGER, "require_mcp_transition_owner", return_value=delegated
            ),
            mock.patch.object(
                MANAGER,
                "write_descriptor",
                side_effect=OSError("simulated descriptor failure"),
            ),
            self.assertRaises(OSError),
        ):
            MANAGER.command_install(args)

        self.assertTrue((target / "runtime" / "gptpro_mcp").exists())
        self.assertEqual(
            '{"ownership_transferred":true}\n', receipt.read_text(encoding="utf-8")
        )
        with mock.patch.object(
            MANAGER, "require_mcp_transition_owner", return_value=delegated
        ):
            self.assertEqual(0, MANAGER.command_install(args))
        descriptor = json.loads(
            (self.destination / ".gptpro-components.json").read_text(encoding="utf-8")
        )
        self.assertEqual(MANAGER.tree_hash(target), descriptor["components"]["gptpro"]["tree_sha256"])

    def test_desktop_bind_is_private_hash_only_and_reusable(self) -> None:
        app_id = "app-private-desktop-fixture"
        app_id_file = Path(self.temp_dir.name) / "app-id.txt"
        app_id_file.write_text(app_id + "\n", encoding="utf-8")
        app_id_file.chmod(0o600)
        state_root = Path(self.temp_dir.name) / "desktop-state"

        dry_args = MANAGER.build_parser().parse_args(
            [
                "desktop-bind",
                "--app-id-file",
                str(app_id_file),
                "--state-root",
                str(state_root),
                "--dry-run",
            ]
        )
        with mock.patch("builtins.print") as printed:
            self.assertEqual(0, MANAGER.command_desktop_bind(dry_args))
        dry_payload = json.loads(printed.call_args.args[0])
        self.assertFalse(state_root.exists())
        self.assertNotIn(app_id, json.dumps(dry_payload))

        apply_args = MANAGER.build_parser().parse_args(
            [
                "desktop-bind",
                "--app-id-file",
                str(app_id_file),
                "--state-root",
                str(state_root),
                "--confirm-bind",
            ]
        )
        with mock.patch("builtins.print") as printed:
            self.assertEqual(0, MANAGER.command_desktop_bind(apply_args))
        payload = json.loads(printed.call_args.args[0])
        self.assertNotIn(app_id, json.dumps(payload))
        binding_path = Path(payload["binding_path"])
        plugin_root = Path(payload["plugin_root"])
        self.assertEqual(0o600, stat.S_IMODE(binding_path.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE((plugin_root / ".app.json").stat().st_mode))
        self.assertNotIn(app_id, binding_path.read_text(encoding="utf-8"))
        self.assertIn(app_id, (plugin_root / ".app.json").read_text(encoding="utf-8"))
        plugin = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("./.app.json", plugin["apps"])
        self.assertNotIn("skills", plugin)
        self.assertNotIn("mcpServers", plugin)

    def test_desktop_bind_rejects_non_private_app_id_file(self) -> None:
        app_id_file = Path(self.temp_dir.name) / "unsafe-app-id.txt"
        app_id_file.write_text("app-private\n", encoding="utf-8")
        app_id_file.chmod(0o644)
        args = MANAGER.build_parser().parse_args(
            [
                "desktop-bind",
                "--app-id-file",
                str(app_id_file),
                "--state-root",
                str(Path(self.temp_dir.name) / "state"),
                "--dry-run",
            ]
        )
        with self.assertRaises(MANAGER.ManagerError) as raised:
            MANAGER.command_desktop_bind(args)
        self.assertIn("DESKTOP_APP_ID_FILE_UNSAFE", str(raised.exception))

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
