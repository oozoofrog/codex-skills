#!/usr/bin/env python3
"""Run bounded Blender jobs in a separate process; Python 3.10+, stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys


OPERATIONS = ("inspect", "preview", "asset_bundle")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def integer(value, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def validate_job(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("job must be an object")
    fields = {"schema_version", "operation", "source", "source_sha256", "objects", "frame", "preview"}
    if set(value) - fields:
        raise ValueError(f"Unknown job fields: {sorted(set(value) - fields)}")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    operation = value.get("operation")
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {OPERATIONS}")
    source_value = value.get("source")
    if not isinstance(source_value, str) or not Path(source_value).is_absolute():
        raise ValueError("source must be an absolute .blend file path")
    source = Path(source_value).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".blend":
        raise ValueError("source must be an existing .blend file")
    objects = value.get("objects", [])
    if not isinstance(objects, list) or any(not isinstance(x, str) or not x for x in objects):
        raise ValueError("objects must be an array of exact nonempty object names")
    if len(set(objects)) != len(objects):
        raise ValueError("objects must not contain duplicate names")
    if operation != "inspect" and not objects:
        raise ValueError("preview and asset_bundle require explicit objects")
    if operation == "inspect" and (objects or "preview" in value or "frame" in value or "source_sha256" in value):
        raise ValueError("inspect accepts only schema_version, operation and source")
    preview = value.get("preview", {})
    if not isinstance(preview, dict) or set(preview) - {"width", "height", "samples"}:
        raise ValueError("preview accepts only width, height and samples")
    result = {"schema_version": 1, "operation": operation, "source": str(source)}
    if operation != "inspect":
        source_hash = value.get("source_sha256")
        if not isinstance(source_hash, str) or len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise ValueError("source_sha256 must be copied from the fresh inspection result")
        result["source_sha256"] = source_hash
        result.update(objects=objects, frame=integer(value.get("frame", 1), "frame", -1048574, 1048574))
        result["preview"] = {
            "width": integer(preview.get("width", 512), "width", 64, 2048),
            "height": integer(preview.get("height", 512), "height", 64, 2048),
            "samples": integer(preview.get("samples", 16), "samples", 1, 128),
        }
    return result


def find_blender(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not candidate:
        conventional = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        candidate = str(conventional) if conventional.is_file() else None
    if not candidate:
        raise ValueError("Blender not found; provide --blender or BLENDER_BIN")
    resolved = Path(candidate).expanduser().resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError("Blender executable is not executable")
    return str(resolved)


def run_job(args) -> dict:
    job = validate_job(json.loads(Path(args.job).read_text()))
    binary = find_blender(args.blender)
    output = Path(args.output_dir).expanduser().resolve()
    # A fresh directory prevents stale artifacts from satisfying a new run.
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "status": "failed", "operation": job["operation"],
              "output_dir": str(output), "artifacts": []}
    try:
        source = Path(job["source"])
        source_hash = digest(source)
        result["source_sha256"] = source_hash
        if job.get("source_sha256", source_hash) != source_hash:
            result.update(status="needs_codex", reason="source_changed_since_inspection")
            write_json(output / "result.json", result)
            return result
        write_json(output / "job.json", job)
        adapter = Path(__file__).with_name("blender_adapter.py")
        command = [binary, "--background", "--factory-startup", "--disable-autoexec", "--offline-mode",
                   "--python-exit-code", "1", "--python", str(adapter), "--",
                   str(output / "job.json"), str(output)]
        with (output / "blender.log").open("wb") as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                     timeout=args.timeout, check=False)
        result["process_exit_code"] = process.returncode
        if digest(source) != source_hash:
            result.update(status="needs_codex", reason="source_changed_during_run")
        elif process.returncode != 0:
            result["reason"] = "blender_process_failed"
        elif not (output / "adapter-result.json").is_file():
            result["reason"] = "missing_adapter_result"
        else:
            adapter_result = json.loads((output / "adapter-result.json").read_text())
            status = adapter_result.get("status")
            if status not in {"completed", "needs_codex"}:
                raise ValueError("Invalid adapter status")
            result.update(status=status, details=adapter_result)
            expected = ["inventory.json"] if job["operation"] == "inspect" else ["preview.png"]
            if job["operation"] == "asset_bundle":
                expected += ["asset.blend", "asset.glb"]
            if status == "completed":
                for name in expected:
                    artifact = output / name
                    if not artifact.is_file() or artifact.stat().st_size == 0:
                        raise ValueError(f"Missing or empty artifact: {name}")
                    result["artifacts"].append({"path": str(artifact),
                                               "bytes": artifact.stat().st_size,
                                               "sha256": digest(artifact)})
                result["verification"] = {
                    "source_unchanged": True, "artifacts_present": True,
                    "visual_review": "not_performed", "downstream_import": "not_performed"}
    except subprocess.TimeoutExpired:
        result.update(status="failed", reason="timeout", timeout_seconds=args.timeout)
    except (OSError, ValueError, KeyError) as exc:
        result.update(status="failed", reason=type(exc).__name__, message=str(exc))
    write_json(output / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    run = sub.add_parser("run")
    run.add_argument("--job", required=True)
    run.add_argument("--output-dir", required=True, help="Must not already exist")
    run.add_argument("--blender", help="Executable path, not an application bundle")
    run.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    try:
        if args.command == "capabilities":
            result = {"schema_version": 1, "operations": list(OPERATIONS),
                      "recipes": [{"name": "capsule_demo", "script": "capsule_demo.py",
                                   "scope": "new procedural rigged scene, 120-frame animation and baked cloth",
                                   "invocation": "Blender --python; see references/capsule-demo.md"}],
                      "source": "saved .blend; active GUI state is not read",
                      "asset_scope": "static evaluated local meshes; no rig/animation export",
                      "jev_required": False, "python": "3.10+", "blender_target": "4.5 and 5.2 LTS"}
        else:
            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("timeout must be positive and finite")
            result = run_job(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result.get("status", "completed") == "completed" else 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "reason": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
