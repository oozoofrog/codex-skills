from __future__ import annotations

import json
import importlib.util
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "gptpro.py"
RAW_TUNNEL_ID = "tunnel_" + "456789abcdef0123" * 2
SECOND_TUNNEL_ID = "tunnel_" + "56789abcdef01234" * 2
APP_NAME = "GPT Pro Repository Reader"
WORKSPACE_LABEL = "Profile Reuse Workspace"


class TunnelProfileReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gptpro-profile-", dir="/tmp")
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.profile_dir = self.root / "profiles"
        self.profile_dir.mkdir(mode=0o700)
        self.repo = self.root / "repo"
        self.repo.mkdir(mode=0o700)
        self.output = self.root / "handoffs"
        self.git("init")
        self.git("config", "user.name", "Profile Reuse Test")
        self.git("config", "user.email", "profile-reuse@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("VALUE = 42\n", encoding="utf-8")
        self.git("add", "src/main.py")
        self.git("commit", "-m", "fixture")
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env.pop("XDG_CONFIG_HOME", None)
        self.env.pop("GPTPRO_TUNNEL_ID", None)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def tearDown(self) -> None:
        self.temporary.cleanup()

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
        self.assertNotIn(RAW_TUNNEL_ID, result.stdout + result.stderr)
        self.assertNotIn(SECOND_TUNNEL_ID, result.stdout + result.stderr)
        return result

    @staticmethod
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def load_cli_module():
        name = f"gptpro_profile_reuse_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("Unable to load gptpro.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def write_profile(self, name: str, *, tunnel_id: str = RAW_TUNNEL_ID) -> Path:
        interpreter = str(Path(sys.executable).resolve(strict=True))
        command = shlex.join(
            [
                interpreter,
                "-I",
                "-S",
                "-B",
                f"-Xpycache_prefix={os.devnull}",
                str(SKILL_ROOT / "scripts" / "gptpro_mcp.py"),
                "serve",
            ]
        )
        path = self.profile_dir / f"{name}.yaml"
        path.write_text(
            "config_version: 1\n"
            "control_plane:\n"
            '  base_url: "https://api.openai.com"\n'
            '  url_path: "/"\n'
            f"  tunnel_id: {json.dumps(tunnel_id)}\n"
            '  api_key: "env:CONTROL_PLANE_API_KEY"\n'
            "health:\n"
            '  listen_addr: "127.0.0.1:0"\n'
            "admin_ui:\n"
            "  open_browser: false\n"
            "log:\n"
            "  level: info\n"
            "  format: json\n"
            "mcp:\n"
            "  commands:\n"
            "    - channel: main\n"
            f"      command: {json.dumps(command)}\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def profile_hash(self, name: str) -> str:
        result = self.run_cli(
            "mcp-profile-check",
            "--tunnel-profile",
            name,
            "--profile-dir",
            str(self.profile_dir),
            "--json",
        )
        return str(json.loads(result.stdout)["tunnel_profile_sha256"])

    def prepare_from_profile(self, name: str, profile_hash: str, *, expected: int = 0):
        return self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--include",
            "src/**",
            "--task",
            "Review the approved immutable repository snapshot.",
            "--output-root",
            str(self.output),
            "--tunnel-profile",
            name,
            "--confirm-tunnel-profile-sha256",
            profile_hash,
            "--profile-dir",
            str(self.profile_dir),
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
            expected=expected,
        )

    def test_new_process_prepares_and_approves_from_existing_profile_without_tunnel_id_ref(self) -> None:
        name = "persistent-profile"
        self.write_profile(name)
        profile_hash = self.profile_hash(name)

        preflight = self.run_cli(
            "preflight",
            "--repo",
            str(self.repo),
            "--transport",
            "mcp-research",
            "--profile-dir",
            str(self.profile_dir),
            "--json",
        )
        preflight_payload = json.loads(preflight.stdout)
        self.assertTrue(preflight_payload["ready_for_prepare"])
        self.assertEqual(name, preflight_payload["selected_profile"])
        self.assertEqual(profile_hash, preflight_payload["selected_profile_sha256"])
        self.assertFalse(preflight_payload["credential_resolution"])
        self.assertFalse(preflight_payload["tunnel_client_execution"])
        self.assertFalse(preflight_payload["package_created"])

        prepared = self.prepare_from_profile(name, profile_hash)
        handoff = Path(json.loads(prepared.stdout)["handoff_dir"])
        manifest = self.load(handoff / "manifest.json")
        connector = manifest["connector"]
        self.assertEqual(name, connector["tunnel_profile_alias"])
        self.assertEqual("verified-local-profile-v1", connector["tunnel_binding_source"])
        self.assertEqual(profile_hash, connector["tunnel_profile_sha256"])
        self.assertRegex(connector["tunnel_id_binding_sha256"], r"^[0-9a-f]{64}$")

        for artifact in handoff.iterdir():
            if artifact.is_file():
                self.assertNotIn(RAW_TUNNEL_ID.encode("utf-8"), artifact.read_bytes())

        self.run_cli("verify", "--handoff-dir", str(handoff))
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "profile-reuse-test",
            "--confirm-transmission",
            "--confirm-mcp-disclosure",
            "--confirm-analysis-ledger",
        )
        approval = self.load(handoff / "state.json")["approval"]
        self.assertEqual("verified-local-profile-v1", approval["tunnel_binding_source"])
        self.assertEqual(profile_hash, approval["tunnel_profile_sha256"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

        module = self.load_cli_module()
        verified = module.verify_package(handoff)
        binding = connector["tunnel_id_binding_sha256"]
        module.mcp_activation_preflight(
            verified,
            tunnel_profile=name,
            observed_tunnel_binding_sha256=binding,
            observed_tunnel_profile_sha256=profile_hash,
            observed_tunnel_client_binary_sha256="1" * 64,
            observed_mcp_target_sha256="2" * 64,
            observed_mcp_runtime_tree_sha256=module.mcp_runtime_tree_sha256(),
            profile_binding_verification="automatic-doctor-json",
            workspace_binding_confirmed=True,
        )
        with self.assertRaisesRegex(module.HandoffError, "changed after package preparation"):
            module.mcp_activation_preflight(
                verified,
                tunnel_profile=name,
                observed_tunnel_binding_sha256=binding,
                observed_tunnel_profile_sha256="3" * 64,
                observed_tunnel_client_binary_sha256="1" * 64,
                observed_mcp_target_sha256="2" * 64,
                observed_mcp_runtime_tree_sha256=module.mcp_runtime_tree_sha256(),
                profile_binding_verification="automatic-doctor-json",
                workspace_binding_confirmed=True,
            )

    def test_default_profile_resolves_ambiguity_and_stale_default_fails_closed(self) -> None:
        first = "profile-one"
        second = "profile-two"
        self.write_profile(first)
        self.write_profile(second, tunnel_id=SECOND_TUNNEL_ID)
        first_hash = self.profile_hash(first)

        ambiguous = self.run_cli(
            "preflight",
            "--repo",
            str(self.repo),
            "--transport",
            "mcp-research",
            "--profile-dir",
            str(self.profile_dir),
            expected=2,
        )
        self.assertEqual("TUNNEL_PROFILE_AMBIGUOUS", json.loads(ambiguous.stdout)["code"])

        selected = self.run_cli(
            "mcp-profile-default",
            "--tunnel-profile",
            first,
            "--confirm-tunnel-profile-sha256",
            first_hash,
            "--profile-dir",
            str(self.profile_dir),
        )
        self.assertEqual(first, json.loads(selected.stdout)["tunnel_profile"])
        preference = self.profile_dir / ".gptpro-default-profile.json"
        self.assertEqual(0o600, stat.S_IMODE(preference.stat().st_mode))
        self.assertNotIn(RAW_TUNNEL_ID.encode("utf-8"), preference.read_bytes())
        self.assertNotIn(SECOND_TUNNEL_ID.encode("utf-8"), preference.read_bytes())

        resolved = self.run_cli(
            "preflight",
            "--repo",
            str(self.repo),
            "--transport",
            "mcp-research",
            "--profile-dir",
            str(self.profile_dir),
        )
        self.assertEqual(first, json.loads(resolved.stdout)["selected_profile"])

        self.write_profile(first, tunnel_id=SECOND_TUNNEL_ID)
        stale = self.run_cli(
            "preflight",
            "--repo",
            str(self.repo),
            "--transport",
            "mcp-research",
            "--profile-dir",
            str(self.profile_dir),
            expected=2,
        )
        self.assertEqual("TUNNEL_DEFAULT_PROFILE_STALE", json.loads(stale.stdout)["code"])

    def test_wrong_profile_confirmation_and_mixed_binding_sources_fail_before_publication(self) -> None:
        name = "confirmed-profile"
        self.write_profile(name)
        profile_hash = self.profile_hash(name)
        rejected = self.prepare_from_profile(name, "0" * 64, expected=2)
        self.assertIn("TUNNEL_PROFILE_CONFIRMATION_MISMATCH", rejected.stderr)
        self.assertFalse(self.output.exists())

        mixed = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--include",
            "src/**",
            "--task",
            "Review the approved immutable repository snapshot.",
            "--output-root",
            str(self.output),
            "--tunnel-profile",
            name,
            "--confirm-tunnel-profile-sha256",
            profile_hash,
            "--tunnel-id-ref",
            "env:GPTPRO_TUNNEL_ID",
            "--profile-dir",
            str(self.profile_dir),
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("cannot be combined", mixed.stderr)
        self.assertFalse(self.output.exists())

        orphaned_confirmation = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--transport",
            "mcp-research",
            "--include",
            "src/**",
            "--task",
            "Review the approved immutable repository snapshot.",
            "--output-root",
            str(self.output),
            "--confirm-tunnel-profile-sha256",
            profile_hash,
            "--tunnel-id-ref",
            "env:GPTPRO_TUNNEL_ID",
            "--profile-dir",
            str(self.profile_dir),
            "--chatgpt-app-name",
            APP_NAME,
            "--chatgpt-workspace-label",
            WORKSPACE_LABEL,
            expected=2,
        )
        self.assertIn("requires --tunnel-profile", orphaned_confirmation.stderr)
        self.assertFalse(self.output.exists())

    def test_profile_list_is_secretless_and_marks_current_default(self) -> None:
        name = "listed-profile"
        self.write_profile(name)
        profile_hash = self.profile_hash(name)
        self.run_cli(
            "mcp-profile-default",
            "--tunnel-profile",
            name,
            "--confirm-tunnel-profile-sha256",
            profile_hash,
            "--profile-dir",
            str(self.profile_dir),
        )
        listed = self.run_cli(
            "mcp-profile-list",
            "--profile-dir",
            str(self.profile_dir),
            "--json",
        )
        payload = json.loads(listed.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["default_profile_current"])
        self.assertEqual(name, payload["default_profile"])
        self.assertEqual(
            [{
                "name": name,
                "ready": True,
                "code": None,
                "refresh_required": False,
                "safe_to_refresh": False,
                "reinit_required": False,
                "profile_sha256": profile_hash,
                "profile_dir_sha256": payload["profiles"][0]["profile_dir_sha256"],
                "entrypoint_matches": True,
                "default": True,
                "default_stale": False,
            }],
            payload["profiles"],
        )

    def test_symlinked_default_profile_preference_fails_closed(self) -> None:
        name = "symlink-profile"
        self.write_profile(name)
        target = self.root / "unsafe-default.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": name,
                    "profile_sha256": "0" * 64,
                }
            ),
            encoding="utf-8",
        )
        target.chmod(0o600)
        (self.profile_dir / ".gptpro-default-profile.json").symlink_to(target)

        rejected = self.run_cli(
            "preflight",
            "--repo",
            str(self.repo),
            "--transport",
            "mcp-research",
            "--profile-dir",
            str(self.profile_dir),
            expected=2,
        )
        payload = json.loads(rejected.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual("TUNNEL_DEFAULT_PROFILE_UNSAFE", payload["code"])


if __name__ == "__main__":
    unittest.main()
