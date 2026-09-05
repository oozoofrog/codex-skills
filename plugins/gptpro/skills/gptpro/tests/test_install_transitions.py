from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGER_PATH = REPO_ROOT / "scripts" / "manage_skills.py"
GPTPRO = REPO_ROOT / "gptpro" / "scripts" / "gptpro.py"


def load_manager():
    spec = importlib.util.spec_from_file_location("gptpro_install_transition_contract", MANAGER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallTransitionContractTests(unittest.TestCase):
    def test_distribution_contains_only_gptpro(self) -> None:
        manager = load_manager()
        self.assertEqual(("gptpro",), manager.PACKAGE_NAMES)
        self.assertEqual(["gptpro"], sorted(manager.discover_skills(REPO_ROOT)))

    def test_capabilities_remove_tunnel_browser_and_computer_use(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GPTPRO), "capabilities", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(["desktop-electron"], value["delivery_channels"])
        self.assertEqual(["inline-immutable-snapshot"], value["context_transports"])
        self.assertEqual("gptpro-inline-context-v1", value["inline_format"])
        self.assertEqual(262144, value["max_outbound_bytes"])
        self.assertEqual(6, value["schema_version"])
        self.assertEqual("gpt-5-6-pro", value["default_model_id"])
        self.assertEqual("normal", value["chat_history_mode"])
        self.assertIn("signed-stream-handoff-v1", value["features"])
        self.assertIn("authenticated-exact-message-branch-proof", value["features"])
        self.assertIn("authenticated-exact-message-readback-recovery", value["features"])
        self.assertEqual(
            {
                "primary": "signed-stream-handoff-v1",
                "conditional_branch_proof": "authenticated-exact-message-readback-v1",
                "conditional_branch_proof_get_only": True,
                "conditional_branch_proof_timeout_seconds": 30,
                "conditional_branch_proof_when": [
                    "tool-route-candidate",
                    "pre-handoff-assistant-evidence",
                    "signed-delta-continuation",
                ],
                "direct_completion_fallback": False,
                "recovery": "conversation-readback-v1",
                "collect_response_get_only": True,
                "collect_response_role": "recovery-only",
            },
            value["response_collection"],
        )
        self.assertFalse(value["tools_enabled"])
        self.assertFalse(value["local_functions"])
        self.assertFalse(value["server_tool_fallback"])
        self.assertFalse(value["browser_delivery"])
        self.assertFalse(value["computer_use"])
        self.assertFalse(value["secure_mcp_tunnel"])
        self.assertTrue(value["electron_private_api"])

    def test_old_transport_command_fails_closed(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GPTPRO), "--error-format", "json", "mcp-status"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("GPTPRO_LEGACY_TRANSPORT_REMOVED", json.loads(result.stderr)["error"]["code"])
        help_result = subprocess.run(
            [sys.executable, str(GPTPRO), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, help_result.returncode, msg=help_result.stderr)
        self.assertNotIn("mcp-status", help_result.stdout)
        self.assertNotIn("browser-plan", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
