from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "jev-workbench"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kit = load_module("jev_review_regressions", CORE / "scripts/jev_cli.py")
installer = load_module("jev_installer_regressions", ROOT / "scripts/install_jev_skills.py")


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.packet = kit.read_json(CORE / "templates/plan-choice.json")
        self.packet["is_example"] = False
        self.response = kit.read_json(CORE / "fixtures/plan-choice.response.json")

    def prepare(self, name="run", packet=None):
        source = self.root / f"{name}.json"
        source.write_text(json.dumps(packet or self.packet))
        directory = self.root / name
        manifest = kit.prepare(source, directory, self.root, [])
        return directory, manifest

    def test_choice_order_reaches_transport_and_changes_approval(self):
        reversed_packet = copy.deepcopy(self.packet)
        for mapping in (reversed_packet["request"]["state"]["candidates"],
                        reversed_packet["request"]["questions"]["decision"]["criteria"]):
            items = list(mapping.items())[::-1]
            mapping.clear()
            mapping.update(items)
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = kit.canonical(self.response)
        manifests = []
        bodies = []
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-test-key"}), \
                mock.patch.object(kit.urllib.request, "build_opener", return_value=opener):
            for name, packet in (("original", self.packet), ("reversed", reversed_packet)):
                directory, manifest = self.prepare(name, packet)
                kit.run(directory, True, None, manifest["approval_sha256"], 30)
                body = opener.open.call_args.args[0].data
                preview = json.loads((directory / "payload.json").read_text())
                sent = json.loads(body)
                self.assertEqual(list(sent["questions"]["decision"]["criteria"]),
                                 list(preview["questions"]["decision"]["criteria"]))
                self.assertEqual(list(sent["state"]["candidates"]),
                                 list(packet["request"]["state"]["candidates"]))
                self.assertEqual(hashlib.sha256(body).hexdigest(), manifest["payload_sha256"])
                self.assertEqual(kit.status(directory)["receipt"]["payload_sha256"],
                                 manifest["payload_sha256"])
                manifests.append(manifest)
                bodies.append(body)
        self.assertNotEqual(bodies[0], bodies[1])
        self.assertNotEqual(manifests[0]["approval_sha256"], manifests[1]["approval_sha256"])
        self.assertEqual(opener.open.call_count, 2)

    def test_saved_order_change_is_rejected_before_dispatch(self):
        directory, manifest = self.prepare()
        for filename in ("packet.json", "payload.json"):
            data = json.loads((directory / filename).read_text())
            request = data["request"] if filename == "packet.json" else data
            criteria = request["questions"]["decision"]["criteria"]
            request["questions"]["decision"]["criteria"] = dict(reversed(list(criteria.items())))
            (directory / filename).write_text(json.dumps(data))
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-test-key"}), \
                mock.patch.object(kit, "live_request", return_value=self.response) as network:
            with self.assertRaises(kit.KitError):
                kit.run(directory, True, None, manifest["approval_sha256"], 30)
            network.assert_not_called()

    def test_preview_alias_records_returned_version(self):
        self.packet["request"]["model"] = "jev-preview"
        directory, manifest = self.prepare()
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-test-key"}), \
                mock.patch.object(kit, "live_request", return_value=self.response):
            result = kit.run(directory, True, None, manifest["approval_sha256"], 30)
        self.assertEqual(result["receipt"]["model"], "jev-1.13.0")
        self.assertTrue(kit.status(directory, True)["fresh"])

    def test_alias_rejects_non_jev_response(self):
        self.response["model"] = "unrelated-model"
        for alias in ("jev-latest", "jev-preview"):
            with self.subTest(alias=alias), self.assertRaises(kit.KitError):
                self.packet["request"]["model"] = alias
                kit.validate_response(self.packet["request"], self.response)

    def test_unknown_alias_is_rejected_before_prepare(self):
        self.packet["request"]["model"] = "jev-unknown-alias"
        with self.assertRaises(kit.KitError):
            self.prepare()
        self.assertFalse((self.root / "run").exists())

    def test_null_choice_description_round_trip(self):
        self.packet["request"]["questions"]["decision"]["criteria"]["local_handler"] = None
        directory, _ = self.prepare()
        kit.run(directory, False, CORE / "fixtures/plan-choice.response.json", None, 30)
        self.assertEqual(kit.status(directory)["receipt"]["selected"], "local_handler")

    @unittest.skipUnless(sys.platform == "darwin", "macOS system path aliases")
    def test_macos_system_tmp_alias_supports_install_and_execution(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as name:
            root = Path(name)
            installer.install(root / "skills", "core", False, True)
            source = root / "input.json"
            source.write_text(json.dumps(self.packet))
            kit.prepare(source, root / "run", root, [])
            kit.run(root / "run", False, CORE / "fixtures/plan-choice.response.json", None, 30)
            self.assertTrue(kit.status(root / "run")["fresh"])

    def test_user_created_parent_symlinks_remain_rejected(self):
        actual = self.root / "actual"
        actual.mkdir()
        link = self.root / "link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(link / "skills", "core", False, True)
        with self.assertRaises(kit.KitError):
            kit.prepare(CORE / "templates/plan-choice.json", link / "run", self.root, [])
        (actual / "source.txt").write_text("observation")
        with self.assertRaises(kit.KitError):
            kit.hash_watched(self.root, ["link/source.txt"])

    def legacy_run(self, completed):
        """Recreate the documented 0.1.0 disk format, independent of prepare()."""
        directory = self.root / "legacy"
        directory.mkdir()
        packet_hash = kit.digest(self.packet)
        manifest = {"kit_version": "0.1.0", "created_at": "2026-09-19T00:00:00Z",
                    "packet_sha256": packet_hash, "payload_sha256": kit.digest(self.packet["request"]),
                    "root": str(self.root), "watched": [], "watched_contents_uploaded": False,
                    "endpoint": kit.ENDPOINT}
        manifest["approval_sha256"] = kit.digest({"packet_sha256": packet_hash,
                                                  "root": str(self.root), "watched": []})
        files = {"packet.json": self.packet, "payload.json": self.packet["request"],
                 "manifest.json": manifest}
        if completed:
            files["response.json"] = self.response
            files["receipt.json"] = {
                "schema_version": 1, "kit_version": "0.1.0", "task_id": self.packet["task_id"],
                "workflow": "plan-choice", "authority": "delegated", "origin": "live",
                "decision_status": "SELECTED", "selected": "local_handler",
                "eligible_for_delegated_followup": True, "execution_authorized": False,
                "model": "jev-1.13.0", "packet_sha256": packet_hash,
                "response_sha256": kit.digest(self.response),
                "policy_revision": self.packet["policy"]["revision"],
                "note": "Selection is not factual proof or user execution permission. Cooperative record only."}
        for name, data in files.items():
            (directory / name).write_text(json.dumps(data))
        return directory, manifest

    def test_legacy_completed_run_remains_readable_without_replay(self):
        directory, manifest = self.legacy_run(True)
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        self.assertEqual(kit.status(directory)["receipt"]["kit_version"], "0.1.0")
        with mock.patch.object(kit, "live_request") as network:
            result = kit.run(directory, True, None, manifest["approval_sha256"], 30)
            self.assertEqual(result["status"], "CACHED")
            network.assert_not_called()
        with self.assertRaises(kit.KitError):
            kit.status(directory, True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_legacy_prepared_run_cannot_be_sent_with_new_serialization(self):
        directory, manifest = self.legacy_run(False)
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-test-key"}), \
                mock.patch.object(kit, "live_request", return_value=self.response) as network:
            with self.assertRaisesRegex(kit.KitError, "Legacy"):
                kit.run(directory, True, None, manifest["approval_sha256"], 30)
            network.assert_not_called()
        self.assertFalse((directory / "attempt.json").exists())


if __name__ == "__main__":
    unittest.main()
