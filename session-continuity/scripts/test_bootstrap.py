#!/usr/bin/env python3
"""Behavior checks in disposable repositories; uses only the standard library."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("bootstrap.py")


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="continuity-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.git("init", "--quiet")

    def git(self, *args, repo=None):
        return subprocess.run(
            ["git", "-C", str(repo or self.repo), *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def run_tool(self, mode, *args, ok=True, repo=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), mode, "--repo", str(repo or self.repo), *args],
            capture_output=True, text=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_preserves_existing_bytes_and_repeat_initialization(self):
        agents = self.repo / "AGENTS.md"
        ignore = self.repo / ".gitignore"
        original = b"# Existing\r\nKeep my rules."
        agents.write_bytes(original)
        ignore.write_bytes(b"build/\n")
        self.run_tool("init")
        self.assertTrue(agents.read_bytes().startswith(original))
        self.assertEqual(ignore.read_bytes(), b"build/\n")
        template = self.repo / ".codex/work/_template.md"
        template.write_bytes(template.read_bytes() + b"\nCustom field\n")
        snapshot = (agents.read_bytes(), ignore.read_bytes(), template.read_bytes())
        self.run_tool("init")
        self.assertEqual(snapshot, (agents.read_bytes(), ignore.read_bytes(), template.read_bytes()))

    def test_existing_continuity_section_is_not_replaced(self):
        agents = self.repo / "AGENTS.md"
        existing = "# Rules\n\n## Codex Session Continuity\nKeep the existing procedure.\n"
        agents.write_text(existing)
        self.run_tool("init")
        self.assertEqual(agents.read_text(), existing)

    def test_ignore_is_optional_and_repeatable(self):
        self.run_tool("init")
        ignore = self.repo / ".gitignore"
        self.assertFalse(ignore.exists())
        ignore.write_bytes(b"build/\r\n!/.codex/work/\r\n")
        self.run_tool("init", "--ignore-work")
        self.assertTrue(ignore.read_bytes().startswith(b"build/\r\n!/.codex/work/\r\n"))
        self.git("check-ignore", ".codex/work/example.md")
        original = ignore.read_bytes()
        self.run_tool("init", "--ignore-work")
        self.assertEqual(ignore.read_bytes(), original)

    def test_parent_ignore_and_tracked_state_are_preserved(self):
        ignore = self.repo / ".gitignore"
        ignore.write_text(".codex/\n")
        self.run_tool("init", "--ignore-work")
        self.assertEqual(ignore.read_text(), ".codex/\n")
        tracked = self.repo / ".codex/work/already.md"
        tracked.write_text("existing tracked task\n")
        self.git("add", "-f", ".codex/work/already.md")
        self.run_tool("init", "--ignore-work")
        self.assertIn(".codex/work/already.md", self.git("ls-files"))
        self.assertEqual(tracked.read_text(), "existing tracked task\n")

    def test_start_captures_actual_state_and_rejects_overwrite(self):
        self.run_tool("init")
        user_file = self.repo / "user.txt"
        user_file.write_text("existing user work")
        self.git("add", "user.txt")
        index_before = self.git("ls-files", "--stage")
        self.run_tool("start", "--task-id", "467", "--goal", "복구 작업")
        target = self.repo / ".codex/work/467.md"
        state = target.read_text()
        self.assertIn(str(self.repo.resolve()), state)
        self.assertIn("(unborn: no commit yet)", state)
        self.assertIn("A  user.txt", state)
        self.assertIn("| NOT RUN |", state)
        self.assertNotIn("| PASS |", state)
        self.assertNotIn("{{", state)
        self.run_tool("start", "--task-id", "467", "--goal", "다른 목표", ok=False)
        self.assertEqual(target.read_text(), state)
        self.assertEqual(user_file.read_text(), "existing user work")
        self.assertEqual(self.git("ls-files", "--stage"), index_before)

    def test_invalid_ids_and_missing_initialization_do_not_write(self):
        self.run_tool("start", "--task-id", "467", "--goal", "goal", ok=False)
        self.assertFalse((self.repo / ".codex").exists())
        for task_id in ("../escape", "/tmp/escape", "a/b", "..", "_template", "A", "x" * 65):
            with self.subTest(task_id=task_id):
                self.run_tool("start", "--task-id", task_id, "--goal", "goal", ok=False)
                self.assertFalse((self.repo / ".codex").exists())

    def test_symlink_and_non_root_rejected_before_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.repo / ".codex").symlink_to(outside, target_is_directory=True)
        self.run_tool("init", ok=False)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertEqual(list(outside.iterdir()), [])
        child = self.repo / "subdirectory"
        child.mkdir()
        self.run_tool("init", repo=child, ok=False)
        self.assertFalse((child / "AGENTS.md").exists())

    def test_detached_linked_worktree_records_its_own_root(self):
        self.git("-c", "user.name=Continuity Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                 "commit", "--allow-empty", "--quiet", "-m", "test fixture")
        head = self.git("rev-parse", "HEAD")
        linked = self.root / "linked worktree"
        self.git("-c", "core.hooksPath=/dev/null", "worktree", "add", "--quiet", "--detach", str(linked), "HEAD")
        self.run_tool("init", repo=linked)
        self.run_tool("start", "--task-id", "linked", "--goal", "worktree test", repo=linked)
        state = (linked / ".codex/work/linked.md").read_text()
        self.assertIn(str(linked.resolve()), state)
        self.assertIn("(detached HEAD)", state)
        self.assertIn(head, state)
        self.assertFalse((self.repo / ".codex").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
