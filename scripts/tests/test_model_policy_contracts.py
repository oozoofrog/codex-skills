"""Static packaging/policy contracts, not live Codex behavior evaluation."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASTRA = ROOT / 'plugins/astra-team-building/skills/astra-team-building'
VERSIONS = {'gptplease': '0.3.0', 'astra-team-building': '0.1.0',
            'session-continuity': '0.1.1', 'unreal-agent': '0.1.3'}
PAIRS = {'gptplease': ('README.md', 'references/model-selection.md'),
         'session-continuity': ('SKILL.md', 'references/orchestration.md'),
         'unreal-agent': ('SKILL.md',)}


class ModelPolicyContracts(unittest.TestCase):
    def test_versions_and_skills_only_manifests(self):
        notes = (ROOT / 'docs/model-routing-changelog.md').read_text()
        for name, version in VERSIONS.items():
            with self.subTest(name=name):
                manifest = json.loads((ROOT / 'plugins' / name / '.codex-plugin/plugin.json').read_text())
                self.assertEqual(manifest['name'], name)
                self.assertEqual(manifest['version'], version)
                self.assertEqual(manifest['skills'], './skills/')
                self.assertIn(version, notes)
                for key in ('mcpServers', 'apps', 'hooks'):
                    self.assertNotIn(key, manifest)
                prompts = manifest['interface']['defaultPrompt']
                self.assertTrue(1 <= len(prompts) <= 3)
                for prompt in prompts:
                    self.assertIn('$' + name, prompt)
                    self.assertLessEqual(len(prompt), 128)

    def test_changed_mirror_files_are_byte_and_mode_identical(self):
        for name, relatives in PAIRS.items():
            for relative in relatives:
                with self.subTest(name=name, relative=relative):
                    source = ROOT / name / relative
                    mirror = ROOT / 'plugins' / name / 'skills' / name / relative
                    self.assertFalse(source.is_symlink())
                    self.assertFalse(mirror.is_symlink())
                    self.assertEqual(source.read_bytes(), mirror.read_bytes())
                    self.assertEqual(source.stat().st_mode & 0o777, mirror.stat().st_mode & 0o777)

    def test_astra_ui_metadata_matches_plugin_without_runtime_settings(self):
        lines = (ASTRA / 'agents/openai.yaml').read_text().splitlines()
        self.assertEqual(lines[0], 'interface:')
        ui = {}
        for line in lines[1:]:
            if line.strip():
                key, value = line.strip().split(': ', 1)
                ui[key] = json.loads(value)
        self.assertEqual(set(ui), {'display_name', 'short_description', 'default_prompt'})
        self.assertTrue(25 <= len(ui['short_description']) <= 64)
        interface = json.loads((ASTRA.parents[1] / '.codex-plugin/plugin.json').read_text())['interface']
        self.assertEqual(ui['display_name'], interface['displayName'])
        self.assertEqual(ui['short_description'], interface['shortDescription'])
        self.assertIn(ui['default_prompt'], interface['defaultPrompt'])

    def test_policy_references_resolve(self):
        from test_document_links import local_targets
        for document in ASTRA.rglob('*.md'):
            for target in local_targets(document.read_text()):
                self.assertTrue((document.parent / target).is_file(), (document, target))
        self.assertIn('(references/orchestration.md)', (ROOT / 'session-continuity/SKILL.md').read_text())

    def test_changed_skill_frontmatter_names_and_descriptions(self):
        for root in (ASTRA, ROOT / 'session-continuity', ROOT / 'unreal-agent'):
            text = (root / 'SKILL.md').read_text()
            front = re.match(r'^---\n(.*?)\n---', text, re.S)
            self.assertIsNotNone(front)
            self.assertEqual({'name', 'description'}, {line.split(':', 1)[0] for line in front[1].splitlines()})
            self.assertIn('name: ' + root.name, front[1])
            self.assertLess(len(text.splitlines()), 500)

    def test_operator_scenarios_are_inputs_not_live_results(self):
        scenario = json.loads((ROOT / 'tests/model-routing/scenarios.json').read_text())
        self.assertEqual(scenario['schema_version'], 1)
        self.assertEqual(scenario['kind'], 'operator_scenarios_not_live_results')
        required = {'team-default', 'mixed-bounded', 'read-only-contract', 'explicit-unavailable',
                    'custom-override', 'preserve-context', 'single-writer', 'fork-constraints',
                    'no-route-fallback', 'chat-work-only', 'work-current', 'partial-explicit',
                    'keep-and-recommend', 'pro-and-unknown-send', 'resume-unknown-worker',
                    'runner-low-explicit', 'budget-conflict', 'small-serial', 'shared-device',
                    'integration-backlog', 'environment-blocked', 'team-partial-explicit',
                    'reuse-idle-capacity', 'no-recursive-spawn'}
        self.assertEqual(required, {case['id'] for case in scenario['cases']})
        self.assertEqual(len(required), len(scenario['cases']))
        for case in scenario['cases']:
            self.assertEqual(set(case), {'id', 'scope', 'request', 'setup', 'expected_evidence', 'forbidden', 'policy_document'})
            self.assertTrue(case['request'] and case['setup'] and case['expected_evidence'] and case['forbidden'])
            self.assertTrue((ROOT / case['policy_document']).is_file())

    def test_fixture_explicitly_labels_synthetic_runs(self):
        fixture = json.loads((ROOT / 'tests/model-routing/evaluation.fixture.json').read_text())
        self.assertEqual(fixture['origin'], 'fixture')
        self.assertEqual({run['arm'] for run in fixture['runs']}, {'single-astra', 'astra-only', 'mixed-model'})
        self.assertIn('합성', (ROOT / 'docs/model-routing-review.md').read_text())

    def test_distribution_expectations_updated_without_changing_unrelated_versions(self):
        text = (ROOT / 'scripts/tests/test_plugin_distribution.py').read_text()
        self.assertIn('self.assertEqual("0.3.0", manifest["version"].split("+")[0])', text)
        self.assertIn('self.assertEqual("0.1.1", manifest["version"])', text)
        self.assertIn('self.assertEqual("0.1.3", manifest["version"])', text)
        self.assertIn('self.assertEqual("0.2.1", manifest["version"].split("+")[0])', text)
        self.assertIn('skill_files = {"SKILL.md", "agents/openai.yaml"}', text)


if __name__ == '__main__':
    unittest.main()
