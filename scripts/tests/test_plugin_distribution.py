from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STANDALONE_SKILL = REPO_ROOT / "gptpro"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "gptpro"
PLUGIN_SKILL = PLUGIN_ROOT / "skills" / "gptpro"
MCP_STANDALONE_SKILL = REPO_ROOT / "gptpro-mcp"
MCP_PLUGIN_ROOT = REPO_ROOT / "plugins" / "gptpro-mcp"
MCP_PLUGIN_SKILL = MCP_PLUGIN_ROOT / "skills" / "gptpro-mcp"
SWIFT_PLUGIN_ROOT = REPO_ROOT / "plugins" / "swift-intelligence"
SWIFT_PLUGIN_SKILL = SWIFT_PLUGIN_ROOT / "skills" / "swift-intelligence"
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def tree_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_file() and path.suffix not in IGNORED_SUFFIXES:
            files[relative.as_posix()] = path.read_bytes()
    return files


class PluginDistributionTests(unittest.TestCase):
    def test_marketplace_points_to_available_plugins(self) -> None:
        marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual("codex-skills", marketplace["name"])
        self.assertEqual("Codex Skills", marketplace["interface"]["displayName"])
        self.assertEqual(
            ["gptpro", "gptpro-mcp", "swift-intelligence"],
            [plugin["name"] for plugin in marketplace["plugins"]],
        )
        entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "gptpro")
        self.assertEqual({"source": "local", "path": "./plugins/gptpro"}, entry["source"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
        self.assertEqual("Productivity", entry["category"])
        mcp_entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "gptpro-mcp")
        self.assertEqual({"source": "local", "path": "./plugins/gptpro-mcp"}, mcp_entry["source"])
        self.assertEqual("AVAILABLE", mcp_entry["policy"]["installation"])

        swift_entry = next(
            plugin for plugin in marketplace["plugins"] if plugin["name"] == "swift-intelligence"
        )
        self.assertEqual(
            {"source": "local", "path": "./plugins/swift-intelligence"},
            swift_entry["source"],
        )
        self.assertEqual("AVAILABLE", swift_entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", swift_entry["policy"]["authentication"])
        self.assertEqual("Productivity", swift_entry["category"])

    def test_plugin_manifest_loads_mirrored_skill(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("gptpro", manifest["name"])
        self.assertEqual("0.3.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("GPT Pro Collaborator", manifest["interface"]["displayName"])
        self.assertTrue((PLUGIN_SKILL / "SKILL.md").is_file())
        ui_metadata = (STANDALONE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn(manifest["interface"]["shortDescription"], ui_metadata)
        default_prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(default_prompts, list)
        self.assertGreaterEqual(len(default_prompts), 1)
        self.assertLessEqual(len(default_prompts), 3)
        for prompt in default_prompts:
            self.assertIsInstance(prompt, str)
            self.assertTrue(prompt)
            self.assertLessEqual(len(prompt), 128)
            self.assertIn("$gptpro", prompt)
        combined_prompts = " ".join(default_prompts)
        self.assertIn("approved", combined_prompts.lower())
        self.assertIn("Desktop", combined_prompts)
        self.assertIn("validate", combined_prompts.lower())
        self.assertIn("$gptpro", ui_metadata)
        long_description = manifest["interface"]["longDescription"].lower()
        self.assertIn("visible chatgpt macos app", long_description)
        self.assertIn("bounded", long_description)
        self.assertIn("send at most once", long_description)
        self.assertIn("browser delivery", long_description)
        self.assertIn("not supported", long_description)

    def test_plugin_skill_mirrors_standalone_package(self) -> None:
        self.assertEqual(tree_files(STANDALONE_SKILL), tree_files(PLUGIN_SKILL))
        self.assertEqual(tree_files(MCP_STANDALONE_SKILL), tree_files(MCP_PLUGIN_SKILL))

    def test_optional_mcp_plugin_is_explicit_and_independent(self) -> None:
        manifest = json.loads(
            (MCP_PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("gptpro-mcp", manifest["name"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertTrue((MCP_PLUGIN_SKILL / "SKILL.md").is_file())
        skill = (MCP_STANDALONE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (MCP_STANDALONE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$gptpro-mcp", skill)
        self.assertIn("$gptpro-mcp", metadata)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("desktop-ui", skill.lower())
        self.assertIn("browser", skill.lower())

    def test_desktop_only_route_and_new_chat_contract_are_aligned(self) -> None:
        skill = (STANDALONE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        ui = (STANDALONE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        plugin_text = json.dumps(manifest, ensure_ascii=False)

        for label, text in (
            ("standalone Skill", skill),
            ("standalone UI metadata", ui),
            ("repository README", readme),
            ("Plugin manifest", plugin_text),
        ):
            with self.subTest(surface=label):
                self.assertIn("$gptpro", text)
                self.assertIn("desktop", text.lower())

        self.assertIn("visible macOS ChatGPT app", skill)
        self.assertIn("Desktop", ui)
        self.assertIn("Desktop", readme)
        self.assertIn(
            "visible ChatGPT macOS app",
            manifest["interface"]["longDescription"],
        )
        self.assertIn("empty new general Chat", skill)
        self.assertIn("new general Chat", ui)
        self.assertIn("빈 새 general Chat", readme)
        self.assertIn("new general Chat", plugin_text)
        self.assertIn("Browser delivery", plugin_text)

    def test_codex_and_chatgpt_app_names_are_not_conflated(self) -> None:
        skill = (STANDALONE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        readme = (STANDALONE_SKILL / "README.md").read_text(encoding="utf-8")
        manual = (STANDALONE_SKILL / "references" / "user-manual.md").read_text(
            encoding="utf-8"
        )
        workflow = (STANDALONE_SKILL / "references" / "desktop-workflow.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("# GPT Pro Collaborator", skill)
        self.assertIn("--chatgpt-app-name 'gptpro'", skill)
        self.assertNotIn("--chatgpt-app-name 'GPT Pro Collaborator'", skill)
        self.assertIn("Skill 이름은 `GPT Pro Collaborator`", readme)
        self.assertIn("App 이름은 `gptpro`", readme)
        self.assertIn("ChatGPT Plugins에 보이는 App 이름은 `gptpro`", manual)
        self.assertIn("`gpt-pro-collaborator`: owner-only", workflow)

    def test_swift_intelligence_plugin_loads_skill_and_mcp_server(self) -> None:
        manifest = json.loads(
            (SWIFT_PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("swift-intelligence", manifest["name"])
        self.assertEqual("0.1.0+codex.20260904035318", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        self.assertTrue((SWIFT_PLUGIN_SKILL / "SKILL.md").is_file())

        mcp_config = json.loads((SWIFT_PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["swift-intelligence"]
        self.assertEqual("python3", server["command"])
        self.assertEqual(["./scripts/swift_intelligence_mcp.py"], server["args"])
        self.assertEqual(".", server["cwd"])
        self.assertTrue(server["enabled"])
        self.assertTrue((SWIFT_PLUGIN_ROOT / "scripts" / "swift_intelligence_mcp.py").is_file())


if __name__ == "__main__":
    unittest.main()
