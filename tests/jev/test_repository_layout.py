from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("jev_install_layout", ROOT/"scripts/install_jev_skills.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)

class RepositoryLayoutTests(unittest.TestCase):
    def test_frontmatter_has_only_name_and_description(self):
        for name in installer.JEV_SKILLS:
            text=(ROOT/name/"SKILL.md").read_text()
            header=text.split("---",2)[1]
            keys={line.split(":",1)[0] for line in header.splitlines() if line.strip()}
            self.assertEqual(keys,{"name","description"})
            self.assertTrue((ROOT/name/"LICENSE").is_file())

    def test_vendor_is_not_discovered_as_an_active_skill(self):
        self.assertEqual(list((ROOT/"docs/jev/vendor").rglob("SKILL.md")),[])
        self.assertEqual(len(list((ROOT/"docs/jev/vendor").rglob("SKILL.reference.md"))),2)

    def test_installer_never_enumerates_all_repository_directories(self):
        with tempfile.TemporaryDirectory() as t:
            r=installer.install(Path(t)/"destination","all",False,False)
            self.assertEqual(set(r["skills"]),set(installer.JEV_SKILLS))
            self.assertNotIn("scripts",r["skills"])
            self.assertNotIn("docs",r["skills"])

    def test_optional_official_snapshot_restores_entrypoint_on_install(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/"skills"
            installer.install(dest,"core",True,True)
            self.assertTrue((dest/"typesafe-ai/SKILL.md").is_file())
            self.assertFalse((dest/"typesafe-ai/SKILL.reference.md").exists())
            self.assertFalse((dest/"jev-review").exists())

if __name__ == "__main__":
    unittest.main()
