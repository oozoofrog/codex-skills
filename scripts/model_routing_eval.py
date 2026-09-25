#!/usr/bin/env python3
"""Validate and compare reported Codex routing runs; never invoke an agent.

Records are operator attestations, not authenticated runtime telemetry. Evidence
references are retained but never opened or executed. No prices are inferred.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ARMS = ("single-astra", "astra-only", "mixed-model")
METRICS = ("wall_seconds", "input_tokens", "output_tokens", "credits", "retries", "leader_rework_minutes")
INTEGER_METRICS = {"input_tokens", "output_tokens", "retries"}
IDENTITY = ("snapshot_sha", "inputs_sha256", "criteria_sha256", "shared_context_sha256", "environment_id")
STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "INCOMPLETE"}
MAX_BYTES = 2 * 1024 * 1024


class InvalidRecord(ValueError):
    """A structural error, distinct from an inconclusive experiment."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidRecord(message)


def keys(value: Any, required: set[str], where: str) -> None:
    require(isinstance(value, dict), f"{where}: expected object")
    require(set(value) == required, f"{where}: missing or unknown fields")


def text(value: Any, where: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"{where}: expected nonempty string")


def pair(value: Any, where: str) -> None:
    keys(value, {"model", "effort"}, where)
    for field in value:
        text(value[field], f"{where}.{field}")


def validate(document: Any) -> list[dict[str, Any]]:
    keys(document, {"schema_version", "origin", "runs"}, "document")
    require(type(document["schema_version"]) is int and document["schema_version"] == 1, "unsupported schema_version")
    require(document["origin"] in ("fixture", "reported-live"), "unknown origin")
    runs = document["runs"]
    require(isinstance(runs, list) and 0 < len(runs) <= 10000, "runs must contain 1..10000 records")
    ids: set[str] = set()
    cells: set[tuple[str, str, str]] = set()
    fields = {
        "run_id", "case_id", "trial_id", "arm", "snapshot_sha", "inputs_sha256",
        "criteria_sha256", "shared_context_sha256", "environment_id", "policy_sha256",
        "workspace_id", "session_id", "execution_path", "config_preserved", "writer_isolation",
        "explicit_mixed_authorization", "usage_scope", "models", "verification", "metrics",
    }
    for index, run in enumerate(runs):
        where = f"runs[{index}]"
        keys(run, fields, where)
        for field in fields - {"models", "verification", "metrics", "config_preserved", "writer_isolation", "explicit_mixed_authorization"}:
            text(run[field], f"{where}.{field}")
        require(run["arm"] in ARMS, f"{where}: unknown arm")
        require(run["execution_path"] in ("codex", "unreal-runner", "chat", "work"), f"{where}: unknown execution_path")
        require(run["usage_scope"] in ("entire-run", "partial", "unknown"), f"{where}: unknown usage_scope")
        for field in ("config_preserved", "writer_isolation", "explicit_mixed_authorization"):
            require(type(run[field]) is bool, f"{where}.{field}: expected boolean")
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", run["snapshot_sha"]) is not None, f"{where}: invalid snapshot_sha")
        for field in ("inputs_sha256", "criteria_sha256", "shared_context_sha256", "policy_sha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", run[field]) is not None, f"{where}.{field}: expected SHA-256")
        require(run["run_id"] not in ids, "duplicate run_id")
        ids.add(run["run_id"])
        cell = (run["case_id"], run["trial_id"], run["arm"])
        require(cell not in cells, "duplicate case/trial/arm; use another trial_id")
        cells.add(cell)
        models = run["models"]
        require(isinstance(models, list) and bool(models), f"{where}: models required")
        leaders = 0
        for model in models:
            keys(model, {"role", "requested", "observed", "evidence_ref"}, f"{where}.model")
            text(model["role"], "model.role")
            leaders += model["role"] == "leader"
            pair(model["requested"], "model.requested")
            if model["observed"] is not None:
                pair(model["observed"], "model.observed")
                text(model["evidence_ref"], "model.evidence_ref")
            else:
                require(model["evidence_ref"] is None or isinstance(model["evidence_ref"], str), "invalid evidence_ref")
        require(leaders == 1, f"{where}: exactly one leader required")
        verification = run["verification"]
        keys(verification, {"status", "evidence_ref"}, f"{where}.verification")
        require(isinstance(verification["status"], str) and verification["status"] in STATUSES, "invalid verification status")
        if verification["status"] in ("PASS", "FAIL"):
            text(verification["evidence_ref"], "verification.evidence_ref")
        else:
            require(verification["evidence_ref"] is None or isinstance(verification["evidence_ref"], str), "invalid verification evidence_ref")
        keys(run["metrics"], set(METRICS), f"{where}.metrics")
        for name, value in run["metrics"].items():
            if value is None:
                continue
            require(type(value) in (int, float), f"{where}.{name}: expected number or null")
            require(math.isfinite(value) and value >= 0, f"{where}.{name}: expected finite nonnegative number")
            if name in INTEGER_METRICS:
                require(type(value) is int, f"{where}.{name}: expected integer or null")
    return runs


def setting_issues(run: dict[str, Any]) -> list[str]:
    issues = []
    models = run["models"]
    if any(m["observed"] is None for m in models):
        issues.append("settings_unobserved")
    if any(m["observed"] is not None and m["observed"] != m["requested"] for m in models):
        issues.append("settings_mismatch")
    observed = [m for m in models if m["observed"] is not None]
    leaders = [m for m in observed if m["role"] == "leader"]
    if not leaders or leaders[0]["observed"]["model"] != "gpt-6-astra":
        issues.append("astra_leader_not_observed")
    if run["arm"] in ("single-astra", "astra-only"):
        if any(m["observed"]["model"] != "gpt-6-astra" for m in observed):
            issues.append("non_astra_in_astra_arm")
    if run["arm"] == "single-astra" and len(models) != 1:
        issues.append("workers_in_single_arm")
    if run["arm"] == "astra-only" and len(models) < 2:
        issues.append("no_worker_in_orchestrated_arm")
    if run["arm"] == "mixed-model":
        if not run["explicit_mixed_authorization"]:
            issues.append("mixed_not_authorized")
        if not any(m["role"] != "leader" and m["observed"]["model"] in ("gpt-6-luna", "gpt-6-sol") for m in observed):
            issues.append("mixed_worker_not_observed")
    for field in ("config_preserved", "writer_isolation"):
        if not run[field]:
            issues.append(field + "_violated")
    if run["execution_path"] != "codex":
        issues.append("wrong_execution_path")
    if run["usage_scope"] != "entire-run":
        issues.append("usage_scope_incomplete")
    return issues


def summarize_attempts(selected: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["verification"]["status"] for r in selected)
    return {
        "attempts": len(selected),
        "verification_counts": {s: counts[s] for s in sorted(STATUSES)},
        "pass_fraction_of_attempts": counts["PASS"] / len(selected) if selected else None,
    }


def summarize_metrics(selected: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {}
    for name in METRICS:
        values = [r["metrics"][name] for r in selected]
        complete = bool(values) and all(v is not None for v in values)
        metrics[name] = {
            "observed_runs": sum(v is not None for v in values),
            "total": sum(values) if complete else None,
            "mean": sum(values) / len(values) if complete else None,
        }
    return metrics


def summarize(document: Any) -> dict[str, Any]:
    runs = validate(document)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    identifier_groups: dict[str, dict[str, set[tuple[str, str]]]] = {
        field: defaultdict(set) for field in ("workspace_id", "session_id")
    }
    policy_versions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for run in runs:
        group_key = (run["case_id"], run["trial_id"])
        groups[group_key].append(run)
        for field in identifier_groups:
            identifier_groups[field][run[field]].add(group_key)
        policy_versions[(run["case_id"], run["arm"])].add(run["policy_sha256"])
    matched = []
    exclusions = []
    for (case, trial), group in sorted(groups.items()):
        reasons = []
        if {r["arm"] for r in group} != set(ARMS):
            reasons.append("missing_arm")
        if len({tuple(r[f] for f in IDENTITY) for r in group}) != 1:
            reasons.append("different_start_or_criteria_or_environment")
        for field in ("workspace_id", "session_id"):
            if len({r[field] for r in group}) != len(group):
                reasons.append(field + "_reused")
            if any(len(identifier_groups[field][r[field]]) > 1 for r in group):
                reasons.append(field + "_reused_across_experiment")
        for run in group:
            reasons.extend(run["arm"] + ":" + issue for issue in setting_issues(run))
            if len(policy_versions[(case, run["arm"])]) > 1:
                reasons.append(run["arm"] + ":policy_version_changed_across_trials")
        leader_settings = [
            (model["observed"]["model"], model["observed"]["effort"])
            for run in group
            for model in run["models"]
            if model["role"] == "leader" and model["observed"] is not None
        ]
        if len(set(leader_settings)) > 1:
            reasons.append("different_leader_settings")
        if reasons:
            exclusions.append({"case_id": case, "trial_id": trial, "reasons": sorted(set(reasons))})
        else:
            matched.extend(group)
    summaries = {}
    for arm in ARMS:
        matched_runs = [r for r in matched if r["arm"] == arm]
        all_runs = [r for r in runs if r["arm"] == arm]
        summaries[arm] = {
            "matched_comparison": {
                **summarize_attempts(matched_runs),
                "metrics": summarize_metrics(matched_runs),
            },
            "all_attempts": summarize_attempts(all_runs),
        }
    return {
        "schema_version": 2,
        "origin": document["origin"],
        "evidence_level": "operator_records_not_independently_verified",
        "live_model_quality_verified": False,
        "input_runs": len(runs),
        "all_verification_counts": dict(sorted(Counter(r["verification"]["status"] for r in runs).items())),
        "matched_batches": len(matched) // len(ARMS),
        "excluded_batches": exclusions,
        "status": "fixture_only" if document["origin"] == "fixture" else ("reported_comparison" if matched else "inconclusive"),
        "arms": summaries,
    }


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        require(name not in result, "duplicate JSON key")
        result[name] = value
    return result


def invalid_constant(_: str) -> None:
    raise InvalidRecord("non-finite JSON constant")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="UTF-8 JSON operator records; never an executable task")
    args = parser.parse_args(argv)
    try:
        with args.records.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "input exceeds 2 MiB")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        result = summarize(document)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        # Do not echo input records or evidence contents in diagnostics.
        print(json.dumps({"error": type(exc).__name__, "status": "invalid_input"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
