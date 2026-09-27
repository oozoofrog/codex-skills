"""Blender process entry. Trusted scripts are acknowledged code, not sandboxed code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene_guard import preguard

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def validate_plan(plan):
    from workflow import check_plan
    return check_plan(plan)


def protected_changed(plan, before, after):
    fields = ("type", "vertex_groups", "mesh", "evaluated_mesh", "evaluated_instances", "shape_key_sha256", "transform", "material_sha256",
              "modifier_sha256", "data_name", "library", "data_library", "collections",
              "parent", "hide_render", "hide_viewport", "constraints_sha256", "data_sha256", "rig")
    changes = []
    for name in plan["protected_objects"]:
        old, new = before["objects"].get(name), after["objects"].get(name)
        if old is None or new is None:
            changes.append({"object": name, "fields": ["missing"]})
        else:
            changed = [f for f in fields if old.get(f) != new.get(f)]
            if changed:
                changes.append({"object": name, "fields": changed})
    return changes


def perform(job, output):
    import bpy
    from scene_state import inspect_scene
    command = job["command"]
    if command == "health":
        return {"status": "completed", "bpy": {"available": True, "version": bpy.app.version_string,
                 "background": bpy.app.background}, "mcp": {"availability": "unknown", "probed": False}}
    if job.get("source"):
        if digest(job["source"]) != job["source_sha256"]:
            raise ValueError("Source snapshot hash mismatch")
        origin = job.get("source_origin", job["source"])
        if digest(origin) != job["source_sha256"]:
            raise ValueError("Source changed before load")
        # Load at its original path so relative assets resolve correctly. The exact
        # source byte snapshot is retained; no save targets the source path.
        bpy.ops.wm.open_mainfile(filepath=origin, load_ui=False, use_scripts=False)
    if command == "inspect":
        state = inspect_scene(job.get("objects"), job.get("limit", 50))
        write(output / "inspection.json", state)
        return {"status": "completed", "inspection": "inspection.json"}
    if command == "render":
        scene = bpy.context.scene
        if scene.camera is None:
            return {"status": "needs_review", "reason": "active_camera_missing"}
        scene.frame_set(job["frame"])
        scene.render.resolution_x, scene.render.resolution_y = job["width"], job["height"]
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(output / "preview.png")
        if scene.render.engine == "CYCLES":
            scene.cycles.device = "CPU"
            scene.cycles.samples = job["samples"]
        bpy.ops.render.render(write_still=True)
        report = {"schema_version": 1, "source_sha256": job["source_sha256"],
                  "camera": scene.camera.name, "frame": scene.frame_current,
                  "engine": scene.render.engine, "settings": {"width": job["width"],
                  "height": job["height"], "samples_requested": job["samples"],
                  "cycles_samples": scene.cycles.samples if scene.render.engine == "CYCLES" else None},
                  "preview": "preview.png", "preview_sha256": digest(output / "preview.png"), "visual_review": "not_performed"}
        write(output / "render.json", report)
        return {"status": "completed", "render": report}
    if command != "run":
        raise ValueError("Unsupported worker command")
    plan = validate_plan(json.loads((output / "plan.json").read_text()))
    if digest(output / "plan.json") != job["plan_sha256"] or digest(output / "script.py") != job["script_sha256"]:
        raise ValueError("Staged plan/script hash mismatch")
    names = list(dict.fromkeys(plan["target_objects"] + plan["protected_objects"]))
    before = inspect_scene(names)
    write(output / "before.json", before)
    guard = preguard(plan, before)
    write(output / "guard.json", guard)
    if guard["status"] != "completed":
        return {"status": guard["status"], "guard": guard, "script_executed": False}
    from workflow import predecision_gate
    try:
        risk_checkpoint=predecision_gate(plan,before,json.loads((output/'pre-decision.json').read_text()) if (output/'pre-decision.json').exists() else None)
    except ValueError as error:
        return {'status':'needs_review','reason':str(error),'script_executed':False}
    checkpoint = None
    bpy.context.preferences.filepaths.save_version = 0
    if guard["requires_checkpoint"] or risk_checkpoint:
        path = output / "checkpoint.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
        checkpoint = {"path": "checkpoint.blend", "sha256": digest(path),
                      "state": "Exact staged memory before trusted script"}
        write(output / "checkpoint.json", checkpoint)
    write(output / "trace.json", {"schema_version": 1, "phase": "executing_trusted_script",
                                   "guard": guard, "checkpoint": checkpoint})
    namespace = {"__name__": "__main__", "__file__": str(output / "script.py"),
                 "bpy": bpy, "PLAN": plan, "OUTPUT_DIR": output}
    old_argv = sys.argv
    try:
        sys.argv = [str(output / "script.py")]
        exec(compile((output / "script.py").read_bytes(), str(output / "script.py"), "exec"), namespace)
    finally:
        sys.argv = old_argv
    after = inspect_scene(names)
    write(output / "after.json", after)
    changed = protected_changed(plan, before, after)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "candidate.blend"))
    return {"status": "needs_review" if changed else "staged", "script_executed": True,
            "protected_changes": changed, "checkpoint": checkpoint,
            "candidate": "candidate.blend", "candidate_sha256": digest(output / "candidate.blend"),
            "acceptance": "pending_deterministic_validation_and_visual_review",
            "guard_scope": guard["scope"],
            "predecision_origin": json.loads((output/"pre-decision.json").read_text()).get("origin") if (output/"pre-decision.json").exists() else "codex_plan_and_exact_guard"}


def main():
    job_path, output_path = sys.argv[sys.argv.index("--") + 1:]
    output = Path(output_path)
    job = json.loads(Path(job_path).read_text())
    result = {"schema_version": 1, "status": "failed", "command": job["command"], "run_id": job["run_id"]}
    try:
        result.update(perform(job, output))
    except Exception as error:
        result.update(reason=type(error).__name__, message=str(error))
        traceback.print_exc()
    write(output / "worker-result.json", result)
    return 0 if result["status"] in {"completed", "staged", "needs_review", "refused"} else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
