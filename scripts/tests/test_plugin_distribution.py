from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDALONE_SKILL = REPO_ROOT / "gptplease"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "gptplease"
PLUGIN_SKILL = PLUGIN_ROOT / "skills" / "gptplease"
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
            ["swift-intelligence", "astra-team-building", "figma-computer-use", "gptplease", "session-continuity", "ponytail-beck-tdd", "unreal-agent", "local-ai-studio"],
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

    def test_gptplease_distribution(self) -> None:
        self.assertTrue((STANDALONE_SKILL / "SKILL.md").is_file())
        self.assertEqual(tree_files(STANDALONE_SKILL), tree_files(PLUGIN_SKILL))
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual("gptplease", manifest["name"])
        self.assertEqual("0.3.0", manifest["version"].split("+")[0])
        for relative in ("runtime/consult.mjs", "runtime/cua-chatgpt.mjs", "tests/consult.test.mjs", "tests/adapter.test.mjs", "references/transport-contract.md", "references/transport-recovery.md"):
            self.assertTrue((STANDALONE_SKILL / relative).is_file())
        for extension in ("json", "md", "swift"):
            self.assertTrue((STANDALONE_SKILL / "tests" / "fixtures" / f"probe.{extension}").is_file())
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertFalse((PLUGIN_ROOT / ".mcp.json").exists())
        self.assertFalse((PLUGIN_ROOT / ".app.json").exists())
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIn("$gptplease", prompt)
            self.assertLessEqual(len(prompt), 128)
        for path in STANDALONE_SKILL.rglob("*.md"):
            import re
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
                if "://" not in target:
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), (path, target))

    def test_retired_packages_are_not_distributed(self) -> None:
        for name in ("gptpro", "gptwork", "astra-orchestrator"):
            self.assertFalse((REPO_ROOT / name / "SKILL.md").exists())
            self.assertFalse((REPO_ROOT / "plugins" / name / ".codex-plugin" / "plugin.json").exists())

    def test_astra_team_building_distribution(self) -> None:
        plugin = REPO_ROOT / "plugins" / "astra-team-building"
        skill = plugin / "skills" / plugin.name
        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
        self.assertEqual("0.1.0", manifest["version"].split("+")[0])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertFalse((REPO_ROOT / plugin.name / "SKILL.md").exists())
        self.assertEqual({".codex-plugin", "README.md", "skills"}, {p.name for p in plugin.iterdir()})
        for key in ("mcpServers", "apps", "hooks"):
            self.assertNotIn(key, manifest)
        for path in plugin.rglob("*"):
            self.assertFalse(path.is_symlink(), path)
        from test_document_links import local_targets
        for document in plugin.rglob("*.md"):
            for target in local_targets(document.read_text(encoding="utf-8")):
                self.assertTrue((document.parent / target).exists(), (document, target))
        self.assertTrue((skill / "SKILL.md").is_file())

    def test_figma_computer_use_distribution(self) -> None:
        source = REPO_ROOT / "figma-computer-use"
        plugin = REPO_ROOT / "plugins" / source.name
        self.assertTrue((source / "SKILL.md").is_file())
        self.assertEqual(tree_files(source), tree_files(plugin / "skills" / source.name))
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        baseline = json.loads((source / "references" / "compatibility.json").read_text())
        self.assertEqual(source.name, manifest["name"])
        self.assertEqual(baseline["skill_version"], manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertFalse((plugin / ".mcp.json").exists())
        self.assertFalse((plugin / ".app.json").exists())
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIn("$figma-computer-use", prompt)
            self.assertLessEqual(len(prompt), 128)
        for path in source.rglob("*.md"):
            import re
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
                if "://" not in target:
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), (path, target))

    def test_session_continuity_distribution(self) -> None:
        source = REPO_ROOT / "session-continuity"
        plugin = REPO_ROOT / "plugins" / source.name
        self.assertTrue((source / "SKILL.md").is_file())
        self.assertEqual(tree_files(source), tree_files(plugin / "skills" / source.name))
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(source.name, manifest["name"])
        self.assertEqual("0.1.1", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIn("$session-continuity", prompt)
            self.assertLessEqual(len(prompt), 128)
        for path in source.rglob("*.md"):
            import re
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
                if "://" not in target:
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), (path, target))

    def test_ponytail_beck_tdd_distribution(self) -> None:
        source = REPO_ROOT / "ponytail-beck-tdd"
        plugin = REPO_ROOT / "plugins" / source.name
        self.assertTrue((source / "SKILL.md").is_file())
        self.assertTrue((source / "agents" / "openai.yaml").is_file())
        self.assertTrue((source / "references" / "kent-beck.md").is_file())
        self.assertEqual(tree_files(source), tree_files(plugin / "skills" / source.name))
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(source.name, manifest["name"])
        self.assertEqual("0.1.0", manifest["version"].split("+")[0])
        self.assertEqual("./skills/", manifest["skills"])
        for key in ("mcpServers", "apps", "hooks"):
            self.assertNotIn(key, manifest)
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIn("$ponytail-beck-tdd", prompt)
            self.assertLessEqual(len(prompt), 128)
        from test_document_links import local_targets
        for document in source.rglob("*.md"):
            for target in local_targets(document.read_text(encoding="utf-8")):
                self.assertTrue((document.parent / target).exists(), (document, target))

    def test_unreal_agent_distribution(self) -> None:
        source = REPO_ROOT / "unreal-agent"
        plugin = REPO_ROOT / "plugins" / source.name
        mirror = plugin / "skills" / source.name
        skill_files = {"SKILL.md", "agents/openai.yaml"}
        self.assertEqual(skill_files, set(tree_files(source)))
        self.assertEqual(tree_files(source), tree_files(mirror))
        # A skills-only allowlist excludes runners, credentials, MCP, apps and hooks,
        # including hidden files that would otherwise escape extension checks.
        self.assertEqual(
            {".codex-plugin/plugin.json"}
            | {f"skills/{source.name}/{relative}" for relative in skill_files},
            set(tree_files(plugin)),
        )
        for root in (source, plugin):
            for path in root.rglob("*"):
                self.assertFalse(path.is_symlink(), path)
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(source.name, manifest["name"])
        self.assertEqual("0.1.3", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        for key in ("mcpServers", "apps", "hooks"):
            self.assertNotIn(key, manifest)
        for relative in (".mcp.json", ".app.json", "hooks", "scripts", "runtime", "bin"):
            self.assertFalse((plugin / relative).exists())
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIsInstance(prompt, str)
            self.assertIn("$unreal-agent", prompt)
            self.assertLessEqual(len(prompt), 128)
        from test_sync_skill_mirrors import load_module
        self.assertIn(source.name, load_module().PACKAGES)

    def test_unreal_agent_explicit_invocation_metadata(self) -> None:
        source = REPO_ROOT / "unreal-agent"
        metadata_text = (source / "agents" / "openai.yaml").read_text(encoding="utf-8")
        scalars = {}
        for line in metadata_text.splitlines():
            if line.startswith("  ") and ": " in line:
                key, value = line.strip().split(": ", 1)
                scalars[key] = value.strip('"')
        self.assertEqual(
            {"display_name", "short_description", "default_prompt", "allow_implicit_invocation"},
            set(scalars),
        )
        self.assertEqual("false", scalars["allow_implicit_invocation"])
        manifest = json.loads(
            (REPO_ROOT / "plugins" / source.name / ".codex-plugin" / "plugin.json").read_text()
        )
        self.assertEqual(manifest["interface"]["displayName"], scalars["display_name"])
        self.assertEqual(manifest["interface"]["shortDescription"], scalars["short_description"])
        self.assertTrue(25 <= len(scalars["short_description"]) <= 64)
        self.assertIn(scalars["default_prompt"], manifest["interface"]["defaultPrompt"])

    def test_local_ai_studio_distribution(self) -> None:
        source = REPO_ROOT / "local-ai-studio"
        plugin = REPO_ROOT / "plugins" / source.name
        mirror = plugin / "skills" / source.name
        skill_files = {"SKILL.md", "agents/openai.yaml", "references/cli-workflows.md", "references/setup.md"}
        self.assertEqual(skill_files, set(tree_files(source)))
        self.assertEqual(tree_files(source), tree_files(mirror))
        # Exact allowlist excludes weights, generated media, credentials and binaries.
        self.assertEqual(
            {".codex-plugin/plugin.json"}
            | {f"skills/{source.name}/{relative}" for relative in skill_files},
            set(tree_files(plugin)),
        )
        for root in (source, plugin):
            for path in root.rglob("*"):
                self.assertFalse(path.is_symlink(), path)
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(source.name, manifest["name"])
        self.assertEqual("0.2.1", manifest["version"].split("+")[0])
        self.assertEqual("./skills/", manifest["skills"])
        for key in ("mcpServers", "apps", "hooks"):
            self.assertNotIn(key, manifest)
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        self.assertTrue(1 <= len(prompts) <= 3)
        for prompt in prompts:
            self.assertIsInstance(prompt, str)
            self.assertIn("$local-ai-studio", prompt)
            self.assertLessEqual(len(prompt), 128)
        from test_sync_skill_mirrors import load_module
        self.assertIn(source.name, load_module().PACKAGES)
        from test_document_links import local_targets
        for root in (source, mirror):
            for document in root.rglob("*.md"):
                for target in local_targets(document.read_text(encoding="utf-8")):
                    self.assertTrue((document.parent / target).exists(), (document, target))

    def test_local_ai_studio_discovery_metadata(self) -> None:
        source = REPO_ROOT / "local-ai-studio"
        # This package uses only JSON-compatible quoted YAML scalars, no dependencies
        # or explicit-only policy: normal automatic skill discovery remains enabled.
        lines = (source / "agents" / "openai.yaml").read_text().splitlines()
        self.assertEqual(["interface:"], [line for line in lines if line and not line.startswith(" ")])
        scalars = {}
        for line in lines:
            if line.startswith("  "):
                key, value = line.strip().split(": ", 1)
                scalars[key] = json.loads(value)
        self.assertEqual({"display_name", "short_description", "default_prompt"}, set(scalars))
        manifest = json.loads(
            (REPO_ROOT / "plugins" / source.name / ".codex-plugin" / "plugin.json").read_text()
        )
        self.assertEqual(manifest["interface"]["displayName"], scalars["display_name"])
        self.assertEqual(manifest["interface"]["shortDescription"], scalars["short_description"])
        self.assertTrue(25 <= len(scalars["short_description"]) <= 64)
        self.assertIn(scalars["default_prompt"], manifest["interface"]["defaultPrompt"])

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
