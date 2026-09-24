"""Offline installer tests: no real Go download or Codex mutation."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'install_unreal_agent.sh'
COMMIT = '1b9f778453f411c029b39b85102aaefb95e7e48d'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        (self.tools / 'git').write_text('''#!/bin/sh
case " $* " in
  *" init "*) mkdir -p "$3" ;;
  *" remote get-url origin "*) echo "${MOCK_ORIGIN:-https://github.com/oozoofrog/codex-skills.git}" ;;
  *" rev-parse "*) echo "${MOCK_COMMIT}" ;;
  *) exit 0 ;;
esac
''')
        (self.tools / 'go').write_text('''#!/bin/sh
if [ "$1" = env ]; then echo "${MOCK_GO_VERSION:-go1.27.1}"; exit; fi
if [ "$1" = build ]; then
  if [ "${MOCK_BUILD_FAIL:-}" = 1 ]; then exit 9; fi
  printf '%s' 'mock runner' > "$3"
  exit
fi
exit 9
''')
        (self.tools / 'codex').write_text('''#!/bin/sh
if [ "$1 $2 $3" = "plugin marketplace list" ]; then cat "$MOCK_MARKETS"; exit; fi
if [ "$1 $2" = "plugin list" ]; then cat "$MOCK_PLUGINS"; exit; fi
printf '%s\n' "$*" >> "$MOCK_CALLS"
if [ "${MOCK_CODEX_FAIL:-0}" != 0 ]; then exit "$MOCK_CODEX_FAIL"; fi
if [ "$1 $2" = "plugin add" ]; then
  if [ "${MOCK_NO_ENABLE:-0}" = 1 ]; then
    printf '%s' '{"installed":[{"pluginId":"unreal-agent@codex-skills","installed":true,"enabled":false}]}' > "$MOCK_PLUGINS"
  else
    printf '%s' '{"installed":[{"pluginId":"unreal-agent@codex-skills","installed":true,"enabled":true}]}' > "$MOCK_PLUGINS"
  fi
fi
exit 0
''')
        self.markets = self.root / 'markets.json'
        self.plugins = self.root / 'plugins.json'
        self.calls = self.root / 'calls'
        self.set_market('absent')
        self.set_plugin('absent')
        for tool in self.tools.iterdir():
            tool.chmod(0o755)
        self.bin = self.root / 'bin'
        self.env = dict(os.environ, PATH=f'{self.tools}:{os.environ["PATH"]}',
                        UNREAL_AGENT_BIN_DIR=str(self.bin), MOCK_COMMIT=COMMIT,
                        CODEX_HOME=str(self.root / 'codex-home'),
                        MOCK_MARKETS=str(self.markets), MOCK_PLUGINS=str(self.plugins), MOCK_CALLS=str(self.calls))

    def set_market(self, kind):
        if kind == 'absent': entries = []
        else:
            source = ('https://github.com/oozoofrog/codex-skills.git' if kind == 'remote'
                      else str(self.root / 'checkout') if kind == 'local'
                      else 'https://github.com/other/repo')
            entries = [{'name': 'codex-skills', 'marketplaceSource':
                        {'sourceType': 'local' if kind == 'local' else 'git', 'source': source}}]
            if kind == 'local':
                manifest = self.root / 'checkout/.agents/plugins/marketplace.json'
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text('{"name":"codex-skills"}')
        self.markets.write_text(json.dumps({'marketplaces': entries}))

    def set_plugin(self, state):
        entries = [] if state == 'absent' else [{'pluginId': 'unreal-agent@codex-skills',
                                                  'installed': True, 'enabled': state == 'enabled'}]
        self.plugins.write_text(json.dumps({'installed': entries}))

    def commands(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def run_installer(self, *args, **extra):
        return subprocess.run(['bash', str(SCRIPT), *args], env={**self.env, **extra},
                              capture_output=True, text=True)

    def test_install_and_repeat_without_rebuilding(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.bin / 'unreal-agent-runner').read_text(), 'mock runner')
        self.assertEqual(self.commands(), ['plugin marketplace add oozoofrog/codex-skills --ref main', 'plugin add unreal-agent@codex-skills'])
        backups = list((self.root / 'codex-home/backups').glob('unreal-agent-install.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads((backups[0] / 'plugins-before.json').read_text()), {'installed': []})
        self.set_market('remote')
        self.set_plugin('enabled')
        second = self.run_installer(MOCK_BUILD_FAIL='1')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('already installed', second.stdout)
        self.assertEqual(len(self.commands()), 2)

    def test_unmanaged_and_tampered_are_preserved(self):
        self.bin.mkdir()
        binary = self.bin / 'unreal-agent-runner'
        binary.write_text('someone else')
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual(binary.read_text(), 'someone else')
        binary.unlink()
        self.assertEqual(self.run_installer().returncode, 0)
        binary.write_text('tampered')
        self.assertNotEqual(self.run_installer('--reinstall').returncode, 0)
        self.assertEqual(binary.read_text(), 'tampered')

    def test_build_and_tag_failure_leave_no_binary(self):
        for overrides in ({'MOCK_BUILD_FAIL': '1'}, {'MOCK_COMMIT': 'changed'},
                          {'MOCK_GO_VERSION': 'go1.26.9'}):
            with self.subTest(overrides=overrides):
                self.assertNotEqual(self.run_installer(**overrides).returncode, 0)
                self.assertFalse((self.bin / 'unreal-agent-runner').exists())

    def test_reinstall_build_failure_preserves_managed_binary(self):
        self.assertEqual(self.run_installer().returncode, 0)
        marker = (self.bin / '.unreal-agent-runner.install').read_bytes()
        self.assertNotEqual(self.run_installer('--reinstall', MOCK_BUILD_FAIL='1').returncode, 0)
        self.assertEqual((self.bin / 'unreal-agent-runner').read_text(), 'mock runner')
        self.assertEqual((self.bin / '.unreal-agent-runner.install').read_bytes(), marker)

    def test_reinstall_retains_previous_managed_binary(self):
        self.assertEqual(self.run_installer('--runner-only').returncode, 0)
        result = self.run_installer('--reinstall')
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(self.bin.glob('.unreal-agent-runner.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'runner').read_text(), 'mock runner')
        self.assertIn(str(backups[0]), result.stdout)

    def test_existing_install_lock_is_preserved(self):
        self.bin.mkdir()
        lock = self.bin / '.unreal-agent-runner.lock'
        lock.mkdir()
        result = self.run_installer('--runner-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.is_dir())
        self.assertFalse((self.bin / 'unreal-agent-runner').exists())

    def test_publish_failure_restores_managed_install(self):
        self.assertEqual(self.run_installer().returncode, 0)
        marker = (self.bin / '.unreal-agent-runner.install').read_bytes()
        # Fail only the staged marker publication, not rollback.
        (self.tools / 'mv').write_text('''#!/bin/sh
case "$1" in *.install) exit 8 ;; esac
exec /bin/mv "$@"
''')
        (self.tools / 'mv').chmod(0o755)
        result = self.run_installer('--reinstall')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.bin / 'unreal-agent-runner').read_text(), 'mock runner')
        self.assertEqual((self.bin / '.unreal-agent-runner.install').read_bytes(), marker)

    def test_remote_upgrade_then_add(self):
        self.set_market('remote')
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertEqual(self.commands(), ['plugin marketplace upgrade codex-skills',
                                           'plugin add unreal-agent@codex-skills'])

    def test_local_checkout_add_without_marketplace_mutation(self):
        self.set_market('local')
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertEqual(self.commands(), ['plugin add unreal-agent@codex-skills'])

    def test_local_checkout_with_different_origin_fails(self):
        self.set_market('local')
        result = self.run_installer(MOCK_ORIGIN='https://github.com/other/repo.git')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), [])
        self.assertFalse(self.bin.exists())

    def test_conflicting_source_fails_before_runner_or_codex_changes(self):
        self.set_market('conflict')
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('different source', result.stderr)
        self.assertEqual(self.commands(), [])
        self.assertFalse(self.bin.exists())

    def test_installed_and_disabled_preserved(self):
        for market in ('local', 'remote'):
            for state in ('enabled', 'disabled'):
                with self.subTest(market=market, state=state):
                    self.set_market(market)
                    self.set_plugin(state)
                    result = self.run_installer()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.commands(), [])
                    if state == 'disabled': self.assertIn('preserving disabled', result.stdout)

    def test_codex_failure_retains_backup(self):
        self.set_market('local')
        config = self.root / 'codex-home/config.toml'
        config.parent.mkdir()
        config.write_text('original-config')
        result = self.run_installer(MOCK_CODEX_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), ['plugin add unreal-agent@codex-skills'])
        self.assertFalse((self.bin / 'unreal-agent-runner').exists())
        backups = list((self.root / 'codex-home/backups').glob('unreal-agent-install.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'config.toml').read_text(), 'original-config')

    def test_plugin_not_enabled_fails_before_runner_publish(self):
        result = self.run_installer(MOCK_NO_ENABLE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not enabled after install', result.stderr)
        self.assertFalse((self.bin / 'unreal-agent-runner').exists())

    def test_symlink_refused(self):
        self.bin.mkdir()
        destination = self.root / 'outside'
        destination.write_text('safe')
        (self.bin / 'unreal-agent-runner').symlink_to(destination)
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual(destination.read_text(), 'safe')


if __name__ == '__main__':
    unittest.main()
