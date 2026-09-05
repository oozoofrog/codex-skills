from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "sync_skill_mirrors.py"


def load_module():
    name = f"sync_skill_mirrors_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SyncSkillMirrorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="skill-mirror-test-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "gptpro"
        self.mirror = self.root / "plugins" / "gptpro" / "skills" / "gptpro"
        self.source.mkdir()
        (self.source / "SKILL.md").write_text("---\nname: gptpro\n---\n", encoding="utf-8")
        (self.source / "README.md").write_text("source\n", encoding="utf-8")
        self.module = load_module()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_check_then_atomic_write_and_recheck(self) -> None:
        before = self.module.sync_one(self.source, self.mirror, write=False)
        self.assertFalse(before["current"])
        self.assertFalse(before["write_performed"])
        written = self.module.sync_one(self.source, self.mirror, write=True)
        self.assertTrue(written["current"])
        self.assertTrue(written["write_performed"])
        self.assertEqual(
            self.module.package_files(self.source), self.module.package_files(self.mirror)
        )
        current = self.module.sync_one(self.source, self.mirror, write=False)
        self.assertTrue(current["current"])
        self.assertFalse(current["write_performed"])

    def test_source_symlink_is_rejected(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        (self.source / "linked.txt").symlink_to(outside)
        with self.assertRaises(self.module.SyncError):
            self.module.sync_one(self.source, self.mirror, write=True)


if __name__ == "__main__":
    unittest.main()
