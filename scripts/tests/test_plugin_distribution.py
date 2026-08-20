from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STANDALONE_SKILL = REPO_ROOT / "gptpro"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "gptpro"
PLUGIN_SKILL = PLUGIN_ROOT / "skills" / "gptpro"
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
    def test_marketplace_points_to_gptpro_plugin(self) -> None:
        marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual("codex-skills", marketplace["name"])
        entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "gptpro")
        self.assertEqual({"source": "local", "path": "./plugins/gptpro"}, entry["source"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
        self.assertEqual("Productivity", entry["category"])

    def test_plugin_manifest_loads_mirrored_skill(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("gptpro", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("GPT Pro Collaborator", manifest["interface"]["displayName"])
        self.assertTrue((PLUGIN_SKILL / "SKILL.md").is_file())
        ui_metadata = (STANDALONE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn(manifest["interface"]["shortDescription"], ui_metadata)
        self.assertIn(manifest["interface"]["defaultPrompt"], ui_metadata)

    def test_plugin_skill_mirrors_standalone_package(self) -> None:
        self.assertEqual(tree_files(STANDALONE_SKILL), tree_files(PLUGIN_SKILL))


if __name__ == "__main__":
    unittest.main()
