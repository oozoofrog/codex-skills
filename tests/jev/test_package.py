from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install_jev_skills.py')
installer=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(installer)

class PackageTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)

    def test_seven_original_skills(self):
        skills=[ROOT/name/'SKILL.md' for name in installer.JEV_SKILLS]
        self.assertEqual(len(skills),7)
        for p in skills:
            text=p.read_text();front=text.split('---',2)[1]
            self.assertIn('name: '+p.parent.name,front)
            self.assertIn('description:',front)
            self.assertTrue((p.parent/'agents/openai.yaml').exists())
            self.assertIn('allow_implicit_invocation: false',(p.parent/'agents/openai.yaml').read_text())

    def test_twelve_catalog_paths_exist(self):
        data=json.loads((ROOT/'docs/jev/catalog.json').read_text())
        self.assertEqual(len(data['workflows']),12)
        for item in data['workflows']:
            self.assertTrue((ROOT/item['template']).is_file())
            self.assertTrue((ROOT/item['playbook']).is_file())

    def test_preview_does_not_create_destination(self):
        dest=self.root/'skills';r=installer.install(dest,'all',False,False)
        self.assertEqual(len(r['skills']),7)
        self.assertFalse(dest.exists())

    def test_all_install_and_existing_content_preserved(self):
        dest=self.root/'skills';dest.mkdir();(dest/'unrelated.txt').write_text('keep')
        r=installer.install(dest,'all',False,True)
        self.assertEqual(len(r['installed']),7)
        self.assertEqual((dest/'unrelated.txt').read_text(),'keep')
        self.assertTrue((dest/'jev-workbench/scripts/jev_cli.py').is_file())

    def test_core_preset_only_core(self):
        dest=self.root/'skills';r=installer.install(dest,'core',False,True)
        self.assertEqual(r['skills'],['jev-workbench'])

    def test_conflict_refuses_without_overwrite(self):
        dest=self.root/'skills';(dest/'jev-workbench').mkdir(parents=True)
        marker=dest/'jev-workbench/keep.txt';marker.write_text('keep')
        with self.assertRaises(ValueError):installer.install(dest,'all',False,True)
        self.assertEqual(marker.read_text(),'keep')
        self.assertFalse((dest/'jev-decision').exists())

    def test_optional_typesafe_has_license_not_mcp_review(self):
        dest=self.root/'skills';r=installer.install(dest,'core',True,True)
        self.assertTrue((dest/'typesafe-ai/LICENSE').is_file())
        self.assertFalse((dest/'jev-review').exists())

    def test_installer_rejects_symlink_dest(self):
        (self.root/'actual').mkdir();(self.root/'link').symlink_to(self.root/'actual',target_is_directory=True)
        with self.assertRaises(ValueError):installer.install(self.root/'link','core',False,True)

    def test_vendor_hashes_and_license_notices(self):
        items=json.loads((ROOT/'docs/jev/sources/UPSTREAM.json').read_text())
        for item in items:
            if 'local_skill_sha256' not in item:continue
            base=ROOT/'docs/jev/vendor'/item['name']
            self.assertEqual(hashlib.sha256((base/'SKILL.reference.md').read_bytes()).hexdigest(),item['local_skill_sha256'])
            self.assertIn('MIT License',(base/'LICENSE').read_text())
            self.assertIsNone(item['upstream_commit'])

    def test_no_unlicensed_skill_body(self):
        self.assertFalse((ROOT/'docs/jev/vendor/building-with-jev-skill').exists())

if __name__=='__main__':unittest.main()
