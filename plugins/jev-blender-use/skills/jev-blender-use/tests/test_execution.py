"""Host transport and deterministic guard tests; Blender runtime tested separately."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import blender_cli as cli
from scene_guard import guard, preguard
from scene_worker import validate_plan


def plan(kind="move", target="Cube", protected=None):
    return {"schema_version": 1, "task_id": "fixture", "goal": "Move a cube",
            "target_objects": [target], "protected_objects": protected or [],
            "operations": [{"type": kind, "target": target}], "validation": [{"kind": "exists", "object": "Body"}],
            "visual_requirements": []}


def object_fixture(**extra):
    return {"shape_keys": [], "data_users": 1, "data_name": "CubeMesh", **extra}


class GuardTests(unittest.TestCase):
    def test_shape_key_destructive_operation_refused(self):
        value = preguard(plan("remesh"), {"objects": {"Cube": object_fixture(shape_keys=["Basis", "Smile"])}})
        self.assertEqual(value["status"], "refused")
        self.assertIn("shape_key_destructive_operation:Cube:remesh", value["reasons"])

    def test_protected_overlap_and_direct_operation_refused(self):
        result = guard(plan(protected=["Cube"]), {"objects": {"Cube": object_fixture()}})
        self.assertIn("target_protected_overlap", result)
        self.assertIn("direct_operation_on_protected_object:Cube", result)

    def test_shared_and_linked_data_need_review(self):
        for extra in ({"data_users": 2}, {"data_library": "external.blend"}):
            result = preguard(plan(), {"objects": {"Cube": object_fixture(**extra)}})
            self.assertEqual(result["status"], "needs_review")

    def test_unknown_operation_does_not_execute(self):
        self.assertEqual(preguard(plan("magic"), {"objects": {"Cube": object_fixture()}})["status"], "needs_review")

    def test_checkpoint_required_for_declared_destructive_operation(self):
        result = preguard(plan("delete"), {"objects": {"Cube": object_fixture()}})
        self.assertTrue(result["requires_checkpoint"])
        self.assertEqual(result["status"], "completed")

    def test_new_mesh_target_missing_before_is_allowed(self):
        self.assertEqual(guard(plan("create_mesh", "NewMesh"), {"objects": {}}), [])

    def test_invalid_plan_rejected(self):
        value = plan()
        value["schema_version"] = True
        with self.assertRaises(ValueError):
            validate_plan(value)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "original.blend"
        self.source.write_bytes(b"source fixture")
        self.script = self.root / "trusted.py"
        self.script.write_text("# trusted fixture\n")
        self.plan = self.root / "input-plan.json"
        self.plan.write_text(json.dumps(plan()))

    def tearDown(self):
        self.temp.cleanup()

    def args(self, command, *extra):
        return cli.parser().parse_args([command, "--output-dir", str(self.root / "output"), *extra])

    def fake_worker(self, command, log_path, timeout):
        output = Path(log_path).parent
        Path(log_path).write_text("fixture subprocess output\n")
        job = json.loads((output / "job.json").read_text())
        if job["command"] == "health":
            result = {"status": "completed", "run_id": job["run_id"], "bpy": {"available": True}}
        else:
            (output / "before.json").write_text('{"schema_version":1}\n')
            (output / "after.json").write_text('{"schema_version":1,"after":true}\n')
            (output / "candidate.blend").write_bytes(b"candidate fixture")
            result = {"status": "staged", "run_id": job["run_id"],
                      "candidate_sha256": cli.digest(output / "candidate.blend")}
        (output / "worker-result.json").write_text(json.dumps(result))
        return {"exit_code": 0, "timed_out": False, "log_truncated": False}

    def test_trusted_script_acknowledgement_required_before_directory_creation(self):
        args = self.args("run", "--plan", str(self.plan), "--script", str(self.script))
        with self.assertRaises(ValueError):
            cli.execute(args)
        self.assertFalse((self.root / "output").exists())

    def test_source_hash_required_for_run(self):
        args = self.args("run", "--plan", str(self.plan), "--script", str(self.script),
                         "--trusted-script", "--source", str(self.source))
        with self.assertRaises(ValueError):
            cli.execute(args)

    def test_stale_source_refused_without_subprocess(self):
        args = self.args("checkpoint", "--source", str(self.source), "--source-sha256", "0" * 64)
        with patch.object(cli, "run_process") as process:
            result = cli.execute(args)
        self.assertEqual(result["status"], "refused")
        process.assert_not_called()
        self.assertFalse((self.root / "output" / "checkpoint.blend").exists())

    def test_checkpoint_exact_copy_and_no_source_mutation(self):
        args = self.args("checkpoint", "--source", str(self.source), "--source-sha256", cli.digest(self.source))
        result = cli.execute(args)
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.root / "output" / "checkpoint.blend").read_bytes(), self.source.read_bytes())
        self.assertTrue(result["source_unchanged"])

    def test_existing_output_refused(self):
        (self.root / "output").mkdir()
        with self.assertRaises(FileExistsError):
            cli.execute(self.args("health"))

    def test_staged_run_binds_all_hashes_and_flags(self):
        args = self.args("run", "--plan", str(self.plan), "--script", str(self.script), "--trusted-script",
                         "--source", str(self.source), "--source-sha256", cli.digest(self.source))
        calls = []
        def invoke(command, log_path, timeout):
            calls.append(command)
            return self.fake_worker(command, log_path, timeout)
        with patch.object(cli, "discover_blender", return_value="/mock/blender"), patch.object(cli, "run_process", side_effect=invoke):
            result = cli.execute(args)
        self.assertEqual(result["status"], "staged")
        self.assertFalse(result["accepted"])
        for field, name in (("before_sha256", "before.json"), ("after_sha256", "after.json"),
                            ("candidate_sha256", "candidate.blend"), ("plan_sha256", "plan.json"),
                            ("script_sha256", "script.py")):
            self.assertEqual(result[field], cli.digest(self.root / "output" / name))
        for flag in ("--factory-startup", "--disable-autoexec", "--offline-mode", "--background"):
            self.assertIn(flag, calls[0])
        self.assertTrue(result["source_unchanged"])

    def test_source_mutation_reported_even_if_worker_completed(self):
        args = self.args("run", "--plan", str(self.plan), "--script", str(self.script), "--trusted-script",
                         "--source", str(self.source), "--source-sha256", cli.digest(self.source))
        def mutate(*values):
            self.source.write_bytes(b"unexpected source mutation")
            return self.fake_worker(*values)
        with patch.object(cli, "discover_blender", return_value="/mock/blender"), patch.object(cli, "run_process", side_effect=mutate):
            result = cli.execute(args)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["reason"], "source_changed_during_run")

    def test_timeout_recorded(self):
        args = self.args("inspect", "--source", str(self.source))
        with patch.object(cli, "discover_blender", return_value="/mock/blender"), patch.object(cli, "run_process", return_value={"timed_out": True, "exit_code": -15}):
            result = cli.execute(args)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "timeout")
        self.assertTrue(result["source_unchanged"])

    def test_health_cli_and_bpy_probe_separate_from_mcp(self):
        def health(command, log_path, timeout):
            if "--version" in command:
                Path(log_path).write_text("Blender mock version\n")
                return {"exit_code": 0, "timed_out": False}
            return self.fake_worker(command, log_path, timeout)
        with patch.object(cli, "discover_blender", return_value="/mock/blender"), patch.object(cli, "run_process", side_effect=health):
            result = cli.execute(self.args("health"))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["worker"]["bpy"]["available"])
        self.assertEqual(result["mcp"], {"availability": "unknown", "probed": False})


if __name__ == "__main__":
    unittest.main()
