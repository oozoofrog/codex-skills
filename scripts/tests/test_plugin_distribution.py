from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDALONE_SKILL = REPO_ROOT / "gptpro"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "gptpro"
PLUGIN_SKILL = PLUGIN_ROOT / "skills" / "gptpro"
SWIFT_PLUGIN_ROOT = REPO_ROOT / "plugins" / "swift-intelligence"
SWIFT_PLUGIN_SKILL = SWIFT_PLUGIN_ROOT / "skills" / "swift-intelligence"
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def tree_files(root: Path) -> dict[str, tuple[int, bytes]]:
    files: dict[str, tuple[int, bytes]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES or " 2." in part for part in relative.parts):
            continue
        if path.is_file() and path.suffix not in IGNORED_SUFFIXES:
            files[relative.as_posix()] = (path.stat().st_mode & 0o777, path.read_bytes())
    return files


class PluginDistributionTests(unittest.TestCase):
    def test_marketplace_points_to_available_plugins(self) -> None:
        marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual("codex-skills", marketplace["name"])
        self.assertEqual("Codex Skills", marketplace["interface"]["displayName"])
        self.assertEqual(
            ["gptpro", "swift-intelligence", "astra-orchestrator"],
            [plugin["name"] for plugin in marketplace["plugins"]],
        )
        for entry in marketplace["plugins"]:
            with self.subTest(plugin=entry["name"]):
                self.assertEqual(
                    {"source": "local", "path": f"./plugins/{entry['name']}"},
                    entry["source"],
                )
                self.assertEqual("AVAILABLE", entry["policy"]["installation"])
                self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
                self.assertEqual("Productivity", entry["category"])
                plugin_root = REPO_ROOT / entry["source"]["path"]
                manifest = json.loads(
                    (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
                )
                self.assertEqual(entry["name"], manifest["name"])
                skill_root = plugin_root / manifest["skills"] / entry["name"]
                self.assertTrue((skill_root / "SKILL.md").is_file())

    def test_plugin_manifest_describes_the_electron_runtime(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("gptpro", manifest["name"])
        self.assertEqual("0.6.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("GPT Pro Collaborator", manifest["interface"]["displayName"])
        self.assertTrue((PLUGIN_SKILL / "SKILL.md").is_file())
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertGreaterEqual(len(prompts), 1)
        self.assertLessEqual(len(prompts), 3)
        for prompt in prompts:
            self.assertIsInstance(prompt, str)
            self.assertLessEqual(len(prompt), 128)
            self.assertIn("$gptpro", prompt)
        description = manifest["interface"]["longDescription"]
        for token in ("loopback", "isolated", "Schema-6", "inline", "independently validate"):
            self.assertIn(token, description)
        for removed in ("manual Send/Copy", "custom ChatGPT Apps", "Secure MCP Tunnel"):
            self.assertIn(removed, description)

    def test_plugin_skill_is_a_byte_and_mode_exact_mirror(self) -> None:
        self.assertEqual(tree_files(STANDALONE_SKILL), tree_files(PLUGIN_SKILL))

    def test_skill_ui_readme_and_manifest_align(self) -> None:
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
                self.assertIn("electron", text.lower())
        self.assertIn("allow_implicit_invocation: false", ui)
        self.assertIn("desktop-electron", skill)
        self.assertIn("inline-immutable-snapshot", skill)
        self.assertNotIn("local-immutable-tool-snapshot", skill)
        self.assertNotIn("$gptpro-mcp", skill)
        self.assertNotIn("$gptpro-mcp", ui)


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
