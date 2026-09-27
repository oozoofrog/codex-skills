#!/usr/bin/env python3
"""Bounded CLI transport for staged Blender work. Trusted Python is not a sandbox."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import uuid

from blender_use import digest, find_blender, write_json

MAX_LOG_BYTES = 2 * 1024 * 1024


def discover_blender(explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if path.suffix.lower() == ".app":
            explicit = str(path / "Contents/MacOS/Blender")
        return find_blender(explicit)
    try:
        return find_blender(None)
    except ValueError:
        candidates = []
        for directory in (Path("/Applications"), Path.home() / "Applications",
                          *Path("/Volumes").glob("*/Applications")):
            candidates.extend(directory.glob("Blender*.app/Contents/MacOS/Blender"))
        candidates = sorted(p for p in candidates if p.is_file() and os.access(p, os.X_OK))
        if len(candidates) != 1:
            raise ValueError("Blender discovery is absent or ambiguous; provide --blender")
        return find_blender(str(candidates[0]))


def run_process(command, log_path, timeout):
    """Drain output while capping stored bytes; terminate the process group on timeout."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    count = 0
    read_error = []

    def drain():
        nonlocal count
        try:
            with Path(log_path).open("wb") as log:
                while True:
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        break
                    available = max(0, MAX_LOG_BYTES - count)
                    if available:
                        log.write(chunk[:available])
                    count += len(chunk)
                if count > MAX_LOG_BYTES:
                    log.write(b"\n[Output truncated at 2 MiB; subprocess output was drained.]\n")
        except OSError as error:
            read_error.append(str(error))

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
    reader.join(timeout=3)
    if process.stdout:
        process.stdout.close()
    if reader.is_alive() or read_error:
        raise RuntimeError("Subprocess log capture did not complete")
    return {"exit_code": process.returncode, "timed_out": timed_out,
            "log_truncated": count > MAX_LOG_BYTES, "output_bytes": count}


def hash_argument(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("source_sha256 must be a lowercase SHA256 digest")
    return value


def source_path(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".blend":
        raise ValueError("Source must be an existing .blend file")
    return path


def artifact_hashes(output):
    # Only known artifacts are inventoried; do not expose arbitrary script-created files.
    names = ("plan.json", "script.py", "pre-decision.json", "source.blend", "before.json", "after.json",
             "inspection.json", "candidate.blend", "checkpoint.blend", "checkpoint.json",
             "preview.png", "render.json", "guard.json", "worker-result.json", "blender.log",
             "version.log", "job.json")
    return [{"path": name, "bytes": (output / name).stat().st_size, "sha256": digest(output / name)}
            for name in names if (output / name).is_file()]


def execute(args):
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 86400:
        raise ValueError("timeout must be finite in (0,86400]")
    if args.command == "run" and not args.trusted_script:
        raise ValueError("--trusted-script explicitly acknowledges arbitrary Python execution; this is not a sandbox")
    if args.command == "run" and args.source and not args.source_sha256:
        raise ValueError("--source-sha256 is required when run supplies --source")
    if args.command == "checkpoint" and not args.source_sha256:
        raise ValueError("--source-sha256 is required for checkpoint")
    output = Path(args.output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "run_id": str(uuid.uuid4()), "command": args.command,
              "status": "failed", "output_dir": str(output), "transport": "cli",
              "mcp": {"availability": "unknown", "probed": False},
              "jev": {"configured": bool(os.environ.get("TYPESAFE_API_KEY")), "service_probed": False},
              "source_sha256": None, "plan_sha256": None, "script_sha256": None,
              "candidate_sha256": None, "before_sha256": None, "after_sha256": None,
              "artifacts": [], "accepted": False}
    original = None
    source_hash = None
    job = {"schema_version": 1, "command": args.command, "run_id": result["run_id"]}
    try:
        if getattr(args, "source", None):
            original = source_path(args.source)
            source_hash = digest(original)
            result["source_sha256"] = source_hash
            if getattr(args, "source_sha256", None) and hash_argument(args.source_sha256) != source_hash:
                result.update(status="refused", reason="source_changed_since_inspection")
                return result
            shutil.copy2(original, output / "source.blend")
            if digest(output / "source.blend") != source_hash or digest(original) != source_hash:
                raise ValueError("Source changed during snapshot")
            job.update(source=str(output / "source.blend"), source_origin=str(original), source_sha256=source_hash)
        if args.command == "checkpoint":
            shutil.copy2(output / "source.blend", output / "checkpoint.blend")
            if digest(output / "checkpoint.blend") != source_hash:
                raise ValueError("Checkpoint verification failed")
            result.update(status="completed", checkpoint_sha256=source_hash,
                          checkpoint="checkpoint.blend", checkpoint_kind="verified_source_byte_copy")
            return result
        if args.command == "run":
            from scene_worker import validate_plan
            plan_path = Path(args.plan).expanduser().resolve(strict=True)
            script_path = Path(args.script).expanduser().resolve(strict=True)
            if not plan_path.is_file() or not script_path.is_file():
                raise ValueError("Plan and trusted script must be files")
            validate_plan(json.loads(plan_path.read_text()))
            shutil.copy2(plan_path, output / "plan.json")
            shutil.copy2(script_path, output / "script.py")
            result.update(plan_sha256=digest(output / "plan.json"), script_sha256=digest(output / "script.py"))
            if digest(plan_path) != result["plan_sha256"] or digest(script_path) != result["script_sha256"]:
                raise ValueError("Plan or script changed during snapshot")
            job.update(plan_sha256=result["plan_sha256"], script_sha256=result["script_sha256"])
            if getattr(args, 'pre_decision', None):
                shutil.copy2(args.pre_decision,output/'pre-decision.json')
        if args.command == "inspect":
            job.update(objects=args.objects, limit=args.limit)
        if args.command == "render":
            job.update(frame=args.frame, width=args.width, height=args.height, samples=args.samples)
        binary = discover_blender(args.blender)
        result["blender_executable"] = binary
        if args.command == "health":
            version = run_process([binary, "--version"], output / "version.log", min(args.timeout, 20))
            result["cli_probe"] = version
            if version["timed_out"] or version["exit_code"] != 0:
                result["reason"] = "cli_version_probe_failed"
                return result
            result["cli_version"] = (output / "version.log").read_text(errors="replace").splitlines()[0]
        write_json(output / "job.json", job)
        worker = Path(__file__).with_name("scene_worker.py")
        command = [binary, "--background", "--factory-startup", "--disable-autoexec", "--offline-mode",
                   "--python-exit-code", "1", "--python", str(worker), "--", str(output / "job.json"), str(output)]
        process = run_process(command, output / "blender.log", args.timeout)
        result["process"] = process
        if process["timed_out"]:
            result["reason"] = "timeout"
        elif process["exit_code"] != 0:
            result["reason"] = "blender_process_failed"
        elif not (output / "worker-result.json").is_file():
            result["reason"] = "worker_result_missing"
        else:
            worker_result = json.loads((output / "worker-result.json").read_text())
            if worker_result.get("run_id") != result["run_id"]:
                raise ValueError("Worker run identity mismatch")
            if worker_result.get("status") not in {"completed", "staged", "needs_review", "refused", "failed"}:
                raise ValueError("Unknown worker status")
            result.update(status=worker_result["status"], worker=worker_result,
                          candidate_sha256=worker_result.get("candidate_sha256"))
            if args.command == "run" and result["status"] == "staged":
                for name in ("before.json", "after.json", "candidate.blend"):
                    if not (output / name).is_file() or not (output / name).stat().st_size:
                        raise ValueError("Missing run artifact: " + name)
                if digest(output / "candidate.blend") != result["candidate_sha256"]:
                    raise ValueError("Candidate hash mismatch")
            if args.command == "render" and result["status"] == "completed":
                if not (output / "preview.png").is_file() or not (output / "preview.png").stat().st_size:
                    raise ValueError("Render artifact missing")
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        result.update(status="failed", reason=type(error).__name__, message=str(error))
    finally:
        for field in ("before", "after"):
            path = output / (field + ".json")
            if path.is_file():
                result[field + "_sha256"] = digest(path)
        if original is not None and source_hash is not None:
            try:
                result["source_unchanged"] = digest(original) == source_hash
            except OSError:
                result["source_unchanged"] = False
            if not result["source_unchanged"]:
                result.update(status="needs_review", reason="source_changed_during_run")
        result["artifacts"] = artifact_hashes(output)
        write_json(output / "trace.json", {"schema_version": 1, "run_id": result["run_id"],
                   "status": result["status"], "process": result.get("process"),
                   "source_unchanged": result.get("source_unchanged"),
                   "trust_boundary": "Separate process with disabled autoexec/offline mode; arbitrary trusted script is not sandboxed.",
                   "worker_trace": result.get("worker")})
        result["artifacts"].append({"path": "trace.json", "bytes": (output / "trace.json").stat().st_size,
                                    "sha256": digest(output / "trace.json")})
        write_json(output / "result.json", result)
    if args.command == 'health' and getattr(args,'mcp_config',None):
        probe_command=[sys.executable,str(Path(__file__).with_name('mcp_bridge.py')),'inspect','--config',args.mcp_config,
                       '--objects','--output-dir',str(output/'mcp-health'),'--timeout',str(min(args.timeout,30))]
        probe=run_process(probe_command,output/'mcp-health.log',min(args.timeout+5,40))
        path=output/'mcp-health'/'result.json'
        result['mcp']={'availability':'connected' if probe['exit_code']==0 else 'unavailable','probed':True,
                       'result':json.loads(path.read_text()) if path.is_file() else {'reason':'probe_failed'}}
        write_json(output/'result.json',result)
    return result


def bounded_integer(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Expected integer in [{low},{high}]")
        return number
    return parse


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    for command in ("health", "inspect", "run", "render", "checkpoint"):
        item = sub.add_parser(command)
        item.add_argument("--output-dir", required=True, help="Fresh directory only")
        item.add_argument("--blender")
        item.add_argument("--timeout", type=float, default=180)
        if command == "health":item.add_argument("--mcp-config",help="Probe installed stdio MCP with a bounded live inspection")
        if command != "health":
            item.add_argument("--source", required=command != "run")
            item.add_argument("--source-sha256")
        if command == "inspect":
            item.add_argument("--objects", nargs="+", default=None)
            item.add_argument("--limit", type=bounded_integer(1, 500), default=50)
        if command == "run":
            item.add_argument("--plan", required=True)
            item.add_argument("--script", required=True)
            item.add_argument("--trusted-script", action="store_true")
            item.add_argument("--pre-decision", help="Optional bound live Jev or explicit Codex risk decision")
        if command == "render":
            item.add_argument("--frame", type=bounded_integer(-1048574, 1048574), default=1)
            item.add_argument("--width", type=bounded_integer(64, 4096), default=512)
            item.add_argument("--height", type=bounded_integer(64, 4096), default=512)
            item.add_argument("--samples", type=bounded_integer(1, 128), default=8)
    return cli


def main():
    try:
        result = execute(parser().parse_args())
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0 if result["status"] in {"completed", "staged"} else 2
    except (OSError, ValueError) as error:
        print(json.dumps({"schema_version": 1, "status": "failed", "reason": type(error).__name__,
                          "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
