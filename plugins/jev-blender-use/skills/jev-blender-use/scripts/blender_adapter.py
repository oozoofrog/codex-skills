"""Blender-side implementation. Invoke through blender_use.py, never in a live GUI."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


class NeedsCodex(Exception):
    pass


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def has_drivers(block) -> bool:
    animation = getattr(block, "animation_data", None)
    return bool(animation and animation.drivers)


def inventory() -> dict:
    scene = bpy.context.scene
    objects = []
    for obj in sorted(scene.objects, key=lambda item: item.name):
        objects.append({"id": obj.name, "type": obj.type,
                        "library": obj.library.filepath if obj.library else None,
                        "parent": obj.parent.name if obj.parent else None,
                        "hide_render": obj.hide_render,
                        "in_active_view_layer": obj.name in bpy.context.view_layer.objects,
                        "hide_viewport": obj.hide_viewport,
                        "dimensions": list(obj.dimensions),
                        "modifiers": [x.type for x in obj.modifiers],
                        "constraints": [x.type for x in obj.constraints],
                        "materials": [x.name for x in getattr(obj.data, "materials", []) if x],
                        "polygons": len(obj.data.polygons) if obj.type == "MESH" else None})
    missing = []
    for image in bpy.data.images:
        if image.source == "FILE" and not image.packed_file and image.filepath:
            if not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                missing.append(image.name)
    return {"schema_version": 1, "blender_version": bpy.app.version_string,
            "scene": scene.name, "view_layer": bpy.context.view_layer.name, "frame": scene.frame_current,
            "object_count": len(objects), "objects": objects,
            "missing_file_images": missing,
            "notes": ["Saved active scene only; no screenshot or visual quality judgment.",
                      "Embedded scripts are disabled; other scene dependencies are not exhaustively audited."]}


def ensure_supported(obj) -> None:
    if obj.type != "MESH" or obj.library or obj.data.library:
        raise NeedsCodex(f"{obj.name}: requires a local mesh")
    if obj.name not in bpy.context.view_layer.objects or obj.hide_viewport or obj.hide_get():
        raise NeedsCodex(f"{obj.name}: excluded or hidden from the active view layer")
    chain = []
    cursor = obj
    while cursor:
        chain.append(cursor)
        cursor = cursor.parent
    if any(x.constraints or has_drivers(x) or x.type == "ARMATURE" for x in chain):
        raise NeedsCodex(f"{obj.name}: constrained, driven or rig-parented object needs a dedicated recipe")
    if has_drivers(obj.data) or (obj.data.shape_keys and has_drivers(obj.data.shape_keys)):
        raise NeedsCodex(f"{obj.name}: driven mesh/shape keys need a dedicated recipe")
    if any(x.type in {"ARMATURE", "NODES", "CLOTH", "FLUID", "SOFT_BODY", "PARTICLE_SYSTEM"}
           for x in obj.modifiers):
        raise NeedsCodex(f"{obj.name}: rig, geometry nodes or simulation requires a dedicated recipe")


def prepare_scene(job: dict):
    source_scene = bpy.context.scene
    selected = []
    for name in job["objects"]:
        obj = source_scene.objects.get(name)
        if obj is None:
            raise NeedsCodex(f"Object is absent from saved active scene: {name}")
        ensure_supported(obj)
        selected.append(obj)
    source_scene.frame_set(job["frame"])
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene = bpy.data.scenes.new("AssetPreview")
    meshes = []
    corners = []
    for obj in selected:
        evaluated = obj.evaluated_get(depsgraph)
        data = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
        if not data.vertices or not data.polygons:
            raise NeedsCodex(f"{obj.name}: no evaluated surface geometry")
        copy = bpy.data.objects.new(obj.name + "_snapshot", data)
        copy.matrix_world = evaluated.matrix_world.copy()
        scene.collection.objects.link(copy)
        meshes.append(copy)
        corners.extend(copy.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not corners or any(not math.isfinite(v) for p in corners for v in p):
        raise NeedsCodex("Empty or non-finite world bounds")
    lower = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    upper = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    center = (lower + upper) / 2
    radius = (upper - lower).length / 2
    if radius < 1e-8:
        raise NeedsCodex("Degenerate world bounds")
    scene.unit_settings.system = source_scene.unit_settings.system
    scene.unit_settings.scale_length = source_scene.unit_settings.scale_length
    return scene, meshes, center, radius


def preview(scene, center, radius, options: dict, output: Path) -> None:
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1.0, -1.5, 1.0)).normalized() * radius * 4
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    aspect = options["width"] / options["height"]
    camera_data.ortho_scale = radius * 2.4 * max(aspect, 1 / aspect)
    camera_data.clip_start = max(radius / 1000, 1e-6)
    camera_data.clip_end = radius * 12
    scene.camera = camera
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.2, 0.2, 0.2, 1)
    for name, direction, energy in [("Key", (1, -2, 3), 900), ("Fill", (-2, -1, 1), 450)]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy * radius * radius
        data.shape = "DISK"
        data.size = radius * 3
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(direction).normalized() * radius * 4
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = options["samples"]
    scene.render.resolution_x = options["width"]
    scene.render.resolution_y = options["height"]
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(output / "preview.png")
    if bpy.ops.render.render(write_still=True, scene=scene.name) != {"FINISHED"}:
        raise RuntimeError("Render did not finish")


def save_scene(scene, output: Path) -> None:
    # A library write captures only this scene's dependencies. Reopen and save it
    # as a normal main file so users do not get a library-file warning on open.
    library = output / ".scene-library.blend"
    name = scene.name
    bpy.data.libraries.write(str(library), {scene}, path_remap="ABSOLUTE", fake_user=True, compress=True)
    if bpy.ops.wm.open_mainfile(filepath=str(library), load_ui=False, use_scripts=False) != {"FINISHED"}:
        raise RuntimeError("Snapshot library did not open")
    bpy.context.window.scene = bpy.data.scenes[name]
    saved = bpy.ops.wm.save_as_mainfile(filepath=str(output / "asset.blend"), copy=True, check_existing=False)
    if saved != {"FINISHED"}:
        raise RuntimeError("Snapshot did not save")
    library.unlink()


def main() -> None:
    if not bpy.app.background:
        raise RuntimeError("This adapter requires a separate background Blender process")
    args = sys.argv[sys.argv.index("--") + 1:]
    job = json.loads(Path(args[0]).read_text())
    output = Path(args[1])
    result = {"schema_version": 1, "status": "completed", "blender_version": bpy.app.version_string}
    try:
        if bpy.app.version < (4, 5, 0):
            raise NeedsCodex("Blender 4.5 or newer is required; target baselines are 4.5 and 5.2 LTS")
        if bpy.ops.wm.open_mainfile(filepath=job["source"], load_ui=False, use_scripts=False) != {"FINISHED"}:
            raise RuntimeError("Source did not open")
        if job["operation"] == "inspect":
            write_json(output / "inventory.json", inventory())
        else:
            scene, meshes, center, radius = prepare_scene(job)
            bpy.context.window.scene = scene
            bpy.context.view_layer.update()
            preview(scene, center, radius, job["preview"], output)
            snapshot_names = [x.name for x in meshes]
            if job["operation"] == "asset_bundle":
                for obj in scene.objects:
                    obj.select_set(obj in meshes)
                bpy.context.view_layer.objects.active = meshes[0]
                exported = bpy.ops.export_scene.gltf(filepath=str(output / "asset.glb"), export_format="GLB",
                                                      use_selection=True, use_active_scene=True, export_animations=False)
                if exported != {"FINISHED"}:
                    raise RuntimeError("GLB export did not finish")
                save_scene(scene, output)
            result.update(objects=job["objects"], frame=job["frame"],
                          snapshot_objects=snapshot_names,
                          notes=["Static evaluated mesh snapshot; no rig or animation exported.",
                                 "Preview lighting/camera are generated; visual review is still required.",
                                 "The .blend may reference external textures; it is not a portable archive."])
    except NeedsCodex as exc:
        result.update(status="needs_codex", reason=str(exc))
    write_json(output / "adapter-result.json", result)


if __name__ == "__main__":
    main()
