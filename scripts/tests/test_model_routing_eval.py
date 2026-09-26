from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/model_routing_eval.py"
spec = importlib.util.spec_from_file_location("model_routing_eval", SCRIPT)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def fixture():
    runs = []
    for index, arm in enumerate(evaluator.ARMS):
        def model(role, name):
            return {"role": role, "requested": {"model": name, "effort": "high"},
                    "observed": {"model": name, "effort": "high"}, "evidence_ref": "fixture://settings"}
        models = [model("leader", "gpt-6-astra")]
        if arm != "single-astra":
            models.append(model("worker", "gpt-6-sol" if arm == "mixed-model" else "gpt-6-astra"))
        runs.append({
            "run_id": f"synthetic-{index}", "case_id": "bounded-change", "trial_id": "1", "arm": arm,
            "snapshot_sha": "a" * 40, "inputs_sha256": "b" * 64, "criteria_sha256": "c" * 64,
            "shared_context_sha256": "d" * 64, "environment_id": "synthetic-linux", "policy_sha256": str(index) * 64,
            "workspace_id": f"isolated-{index}", "session_id": f"session-{index}", "execution_path": "codex",
            "config_preserved": True, "writer_isolation": True, "explicit_mixed_authorization": arm == "mixed-model",
            "usage_scope": "entire-run", "models": models,
            "verification": {"status": "PASS", "evidence_ref": "fixture://test-result"},
            "metrics": {"wall_seconds": 10 + index, "input_tokens": 100, "output_tokens": 20,
                        "credits": None, "retries": 0, "leader_rework_minutes": None},
        })
    return {"schema_version": 1, "origin": "fixture", "runs": runs}


def repeat_trial(data):
    extra = copy.deepcopy(data["runs"])
    for run in extra:
        run["run_id"] += "-trial2"
        run["trial_id"] = "2"
        run["session_id"] += "-trial2"
        run["workspace_id"] += "-trial2"
    data["runs"].extend(extra)
    return extra


class RoutingEvaluationTests(unittest.TestCase):
    def test_fixture_is_never_live_validation(self):
        report = evaluator.summarize(fixture())
        self.assertEqual(report["matched_batches"], 1)
        self.assertEqual(report["status"], "fixture_only")
        self.assertEqual(report["schema_version"], 2)
        self.assertFalse(report["live_model_quality_verified"])

    def test_unknown_metrics_stay_null(self):
        report = evaluator.summarize(fixture())
        matched = report["arms"]["single-astra"]["matched_comparison"]
        self.assertIsNone(matched["metrics"]["credits"]["total"])
        self.assertIsNone(matched["metrics"]["leader_rework_minutes"]["mean"])

    def test_missing_arm_is_inconclusive(self):
        data = fixture(); data["origin"] = "reported-live"; data["runs"].pop()
        report = evaluator.summarize(data)
        self.assertEqual(report["status"], "inconclusive")
        self.assertIn("missing_arm", report["excluded_batches"][0]["reasons"])

    def test_changed_criteria_or_start_is_not_pooled(self):
        for field in evaluator.IDENTITY:
            with self.subTest(field=field):
                data = fixture()
                data["runs"][1][field] = "e" * (40 if field == "snapshot_sha" else 64)
                self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_distinct_arm_policy_hashes_are_allowed(self):
        self.assertEqual(evaluator.summarize(fixture())["matched_batches"], 1)

    def test_shared_session_or_workspace_is_excluded(self):
        for field in ("workspace_id", "session_id"):
            data = fixture(); data["runs"][1][field] = data["runs"][0][field]
            self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_session_reuse_across_trials_excludes_the_experiment(self):
        data = fixture()
        extra = repeat_trial(data)
        extra[0]["session_id"] = data["runs"][0]["session_id"]
        report = evaluator.summarize(data)
        self.assertEqual(report["matched_batches"], 0)
        reasons = {reason for group in report["excluded_batches"] for reason in group["reasons"]}
        self.assertIn("session_id_reused_across_experiment", reasons)

    def test_policy_change_within_an_arm_is_not_pooled_across_trials(self):
        data = fixture()
        extra = repeat_trial(data)
        extra[2]["policy_sha256"] = "f" * 64
        report = evaluator.summarize(data)
        self.assertEqual(report["matched_batches"], 0)
        self.assertTrue(all(len(group["reasons"]) for group in report["excluded_batches"]))
        self.assertTrue(all(
            "mixed-model:policy_version_changed_across_trials" in group["reasons"]
            for group in report["excluded_batches"]
        ))

    def test_leader_settings_must_match_across_arms(self):
        data = fixture()
        leader = data["runs"][2]["models"][0]
        leader["requested"]["effort"] = "low"
        leader["observed"]["effort"] = "low"
        report = evaluator.summarize(data)
        self.assertEqual(report["matched_batches"], 0)
        self.assertIn("different_leader_settings", report["excluded_batches"][0]["reasons"])

    def test_configuration_and_permissions_are_preserved(self):
        for field in ("config_preserved", "writer_isolation", "explicit_mixed_authorization"):
            data = fixture(); data["runs"][2][field] = False
            self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_unobserved_and_mismatched_settings_are_excluded(self):
        for observed in (None, {"model": "gpt-6-luna", "effort": "medium"}):
            data = fixture(); data["runs"][2]["models"][1]["observed"] = observed
            self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_empty_observation_evidence_is_invalid(self):
        data = fixture(); data["runs"][0]["models"][0]["evidence_ref"] = ""
        with self.assertRaises(evaluator.InvalidRecord): evaluator.summarize(data)

    def test_duplicate_run_and_cell_are_invalid(self):
        data = fixture(); data["runs"].append(copy.deepcopy(data["runs"][0]))
        with self.assertRaises(evaluator.InvalidRecord): evaluator.summarize(data)
        data["runs"][-1]["run_id"] = "new-id"
        with self.assertRaises(evaluator.InvalidRecord): evaluator.summarize(data)

    def test_numeric_validation_rejects_boolean_negative_nan_and_float_token_count(self):
        for field, value in (("credits", True), ("wall_seconds", -1), ("credits", float("nan")), ("input_tokens", 1.5)):
            data = fixture(); data["runs"][0]["metrics"][field] = value
            with self.assertRaises(evaluator.InvalidRecord): evaluator.summarize(data)

    def test_failed_and_incomplete_attempts_are_not_hidden(self):
        data = fixture(); data["runs"][1]["verification"]["status"] = "FAIL"
        data["runs"][2]["verification"]["status"] = "BLOCKED"
        report = evaluator.summarize(data)
        self.assertEqual(report["matched_batches"], 1)
        self.assertEqual(report["arms"]["astra-only"]["matched_comparison"]["pass_fraction_of_attempts"], 0)
        self.assertEqual(report["arms"]["mixed-model"]["matched_comparison"]["verification_counts"]["BLOCKED"], 1)

    def test_excluded_blocked_attempt_remains_in_arm_attempt_counts(self):
        data = fixture()
        extra = repeat_trial(data)
        blocked = extra[2]
        blocked["models"][1]["observed"] = None
        blocked["models"][1]["evidence_ref"] = None
        blocked["verification"] = {"status": "BLOCKED", "evidence_ref": "fixture://spawn-rejected"}
        blocked["usage_scope"] = "unknown"
        blocked["metrics"] = {name: None for name in evaluator.METRICS}
        report = evaluator.summarize(data)
        mixed = report["arms"]["mixed-model"]
        self.assertEqual(report["matched_batches"], 1)
        self.assertEqual(mixed["matched_comparison"]["attempts"], 1)
        self.assertEqual(mixed["all_attempts"]["attempts"], 2)
        self.assertEqual(mixed["all_attempts"]["verification_counts"]["BLOCKED"], 1)
        self.assertEqual(mixed["all_attempts"]["pass_fraction_of_attempts"], 0.5)
        self.assertIsNone(mixed["matched_comparison"]["metrics"]["credits"]["mean"])

    def test_no_workers_is_not_orchestration_evidence(self):
        data = fixture(); data["runs"][1]["models"].pop()
        self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_non_mixed_execution_is_not_mixed_evidence(self):
        data = fixture()
        for field in ("requested", "observed"):
            data["runs"][2]["models"][1][field]["model"] = "gpt-6-astra"
        self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_other_execution_path_or_partial_usage_is_excluded(self):
        for field, value in (("execution_path", "unreal-runner"), ("usage_scope", "partial")):
            data = fixture(); data["runs"][2][field] = value
            self.assertEqual(evaluator.summarize(data)["matched_batches"], 0)

    def test_schema_and_unknown_fields_are_checked(self):
        for field, value in (("schema_version", True), ("origin", "measured"), ("extra", 1)):
            data = fixture(); data[field] = value
            with self.assertRaises(evaluator.InvalidRecord): evaluator.summarize(data)

    def test_input_not_mutated(self):
        data = fixture(); before = copy.deepcopy(data); evaluator.summarize(data)
        self.assertEqual(data, before)

    def test_cli_success_and_no_evidence_file_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            path.write_text(json.dumps(fixture()))
            result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "fixture_only")

    def test_cli_rejects_duplicate_json_keys_nonfinite_and_bad_inputs(self):
        samples = ['{"schema_version":1,"schema_version":1}', '{"x":NaN}', '[1]', '{', '[' * 2000 + '0' + ']' * 2000]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            for sample in samples:
                path.write_text(sample)
                result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stderr)["status"], "invalid_input")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(set(json.loads(result.stderr)), {"error", "status"})

    def test_cli_rejects_large_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"; path.write_bytes(b" " * (evaluator.MAX_BYTES + 1))
            result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__": unittest.main()
