#!/usr/bin/env python3
"""Original procedural Blender scene: two steps, a box leap, a cloth cape.

Run with Blender, not system Python. No assets or network are required.
The output directory must not exist. The baked cloth cache is saved inside
robot.blend so the editable scene can be reopened without external assets.
"""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


FPS = 24
LAST_FRAME = 120
FOOT_HALF_HEIGHT = 0.13
FOOT_HALF_LENGTH = 0.23
BOX_CENTER = 2.40
BOX_HALF_LENGTH = 0.30
BOX_HEIGHT = 0.48


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not (64 <= args.width <= 4096 and 64 <= args.height <= 4096):
        parser.error("width and height must be between 64 and 4096")
    if not 1 <= args.samples <= 1024:
        parser.error("samples must be between 1 and 1024")
    args.output_dir = args.output_dir.expanduser().resolve()
    # mkdir without exist_ok is the output ownership boundary, including symlinks.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return args


def material(name, color, metallic=0.0, roughness=0.4, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return mat


def finish(obj, name, mat):
    obj.name = name
    obj.data.name = name + "_Mesh"
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def ellipsoid(name, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat)


def rounded_box(name, location, scale, mat, radius=0.08):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    finish(obj, name, mat)
    bevel = obj.modifiers.new("Rounded edges", "BEVEL")
    bevel.width = radius
    bevel.segments = 4
    obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    return obj


def collision(obj):
    obj.modifiers.new("Cape collision", "COLLISION")
    obj.collision.thickness_outer = 0.015
    obj.collision.cloth_friction = 5


def skin(obj, rig, bone):
    group = obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    modifier = obj.modifiers.new("Capsule deformation", "ARMATURE")
    modifier.object = rig
    obj.parent = rig
    return obj


def make_rig():
    data = bpy.data.armatures.new("Capsule_Rig_Data")
    rig = bpy.data.objects.new("Capsule_Armature", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    definitions = {
        "root": ((0, 0, 1.12), (0, 0, 1.42), None),
        "body": ((0, 0, 1.12), (0, 0, 1.72), "root"),
        "foot.L": ((0, -.29, .13), (0, -.29, .33), "root"),
        "foot.R": ((0, .29, .13), (0, .29, .33), "root"),
        "arm.L": ((0, -.48, 1.35), (0, -.48, .77), "root"),
        "arm.R": ((0, .48, 1.35), (0, .48, .77), "root"),
        "shin.L": ((0, -.29, .61), (0, -.29, .25), "root"),
        "shin.R": ((0, .29, .61), (0, .29, .25), "root"),
    }
    for name, (head, tail, parent) in definitions.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.show_in_front = True
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
    return rig


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def trajectory(frame):
    """World foot centers; constant stance x/z is an explicit planting invariant."""
    left, right = [0.0, -.29, .13], [0.0, .29, .13]
    squash, tilt, lift = 1.0, 0.0, 0.0
    if frame <= 48:
        root_x = lerp(0, 1.1, smooth((frame - 1) / 47))
        if frame >= 9:
            t = max(0, min(1, (frame - 9) / 19))
            left[0] = .68 * smooth(t)
            left[2] += .20 * math.sin(math.pi * t)
        if frame >= 29:
            t = max(0, min(1, (frame - 29) / 19))
            right[0] = 1.35 * smooth(t)
            right[2] += .20 * math.sin(math.pi * t)
        lift = .035 * math.sin(2 * math.pi * (frame - 1) / 24)
        phase = "step_left" if frame <= 28 else "step_right"
    elif frame <= 60:
        root_x, left[0], right[0] = 1.1, .68, 1.35
        t = smooth((frame - 48) / 12)
        lift, squash, tilt = -.19 * t, 1 - .07 * t, -.10 * t
        phase = "anticipation"
    elif frame < 90:
        t = (frame - 60) / 30
        root_x = lerp(1.1, 3.6, t)
        lift = 1.25 * math.sin(math.pi * t) - .19 * (1 - smooth(t * 5))
        left[0] = root_x + lerp(-.42, -.12, smooth(t))
        right[0] = root_x + lerp(.25, .12, smooth(t))
        left[2] += 1.14 * math.sin(math.pi * t)
        right[2] += 1.14 * math.sin(math.pi * t)
        squash = 1 + .07 * math.sin(math.pi * t)
        tilt = .10 * math.sin(2 * math.pi * t)
        phase = "leap"
    else:
        root_x, left[0], right[0] = 3.6, 3.48, 3.72
        compression = math.sin(math.pi * min(1, (frame - 90) / 18))
        lift, squash = -.17 * compression, 1 - .12 * compression
        phase = "landing" if frame < 108 else "settled"
    return {"frame": frame, "phase": phase, "root": [root_x, 0, 1.12 + lift],
            "left": left, "right": right, "squash": squash, "tilt": tilt}


def bone_matrix(rig, name, head, rotation=None, scale=None):
    rest = rig.data.bones[name].matrix_local
    orientation = rest.to_quaternion().to_matrix().to_4x4()
    if rotation is not None:
        orientation = rotation @ orientation
    if scale is not None:
        orientation = orientation @ Matrix.Diagonal((*scale, 1))
    rig.pose.bones[name].matrix = Matrix.Translation(Vector(head)) @ orientation


def animate(rig):
    evidence = []
    for frame in range(1, LAST_FRAME + 1):
        bpy.context.scene.frame_set(frame)
        state = trajectory(frame)
        root = state["root"]
        bone_matrix(rig, "root", root)
        # matrix setters on children convert through the evaluated parent pose.
        # Refresh the newly moved root before assigning world-space child targets.
        bpy.context.view_layer.update()
        body_scale = (1 / math.sqrt(state["squash"]), state["squash"],
                      1 / math.sqrt(state["squash"]))
        bone_matrix(rig, "body", root, Matrix.Rotation(state["tilt"], 4, "Y"), body_scale)
        for side, key, y in (("L", "left", -.29), ("R", "right", .29)):
            foot = state[key]
            bone_matrix(rig, "foot." + side, foot)
            # Short telescopic leg follows hip and ankle; rigid bone weighting
            # makes the editable articulation visible without an opaque IK solver.
            top = Vector((root[0], y, root[2] - .51))
            bottom = Vector((foot[0], y, foot[2] + .12))
            direction = bottom - top
            rest_length = rig.data.bones["shin." + side].length
            rotation = Vector((0, 1, 0)).rotation_difference(direction.normalized())
            rig.pose.bones["shin." + side].matrix = (
                Matrix.Translation(top) @ rotation.to_matrix().to_4x4()
                @ Matrix.Diagonal((1, direction.length / rest_length, 1, 1)))
            swing = .20 * math.sin((frame - 9) * math.pi / 20)
            if state["phase"] == "leap":
                swing = -.42 * math.sin(math.pi * (frame - 60) / 30)
            elif frame >= 90:
                swing = .12 * math.exp(-(frame - 90) / 9) * math.sin((frame - 90) / 3)
            bone_matrix(rig, "arm." + side, (root[0], y / .29 * .48, root[2] + .23),
                        Matrix.Rotation(swing * (1 if side == "L" else -1), 4, "Y"))
        for bone in rig.pose.bones:
            for channel in ("location", "rotation_quaternion", "scale"):
                bone.keyframe_insert(data_path=channel, frame=frame, group=bone.name)
        evidence.append(state)
    # Sampled control trajectories remain exact between integer simulation frames.
    action = rig.animation_data.action
    for slot in action.slots:
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    for curve in bag.fcurves:
                        for keyframe in curve.keyframe_points:
                            keyframe.interpolation = "LINEAR"
    bpy.context.scene.frame_set(1)
    return evidence


def make_cape(rig, mat):
    columns, rows = 17, 23
    vertices, faces = [], []
    for j in range(rows):
        t = j / (rows - 1)
        for i in range(columns):
            u = i / (columns - 1)
            width = lerp(.63, .95, t)
            vertices.append((-.39 - .36 * t - .025 * math.cos(u * math.pi * 6) * t,
                             (u - .5) * width, 1.75 - 1.11 * t))
    for j in range(rows - 1):
        for i in range(columns - 1):
            k = j * columns + i
            faces.append((k, k + 1, k + 1 + columns, k + columns))
    mesh = bpy.data.meshes.new("Cape_Grid_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    cape = bpy.data.objects.new("Cape_Cloth", mesh)
    bpy.context.collection.objects.link(cape)
    finish(cape, "Cape_Cloth", mat)
    skin(cape, rig, "root")
    pins = cape.vertex_groups.new(name="Shoulder_Pins")
    pins.add(list(range(columns)), 1, "REPLACE")
    cloth = cape.modifiers.new("Genuine cloth simulation", "CLOTH")
    settings = cloth.settings
    settings.quality = 8
    settings.mass = .18
    settings.vertex_group_mass = pins.name
    settings.pin_stiffness = 1
    settings.tension_stiffness = 24
    settings.compression_stiffness = 24
    settings.shear_stiffness = 16
    settings.bending_stiffness = .6
    settings.air_damping = 3
    cloth.collision_settings.use_collision = True
    cloth.collision_settings.use_self_collision = True
    cloth.collision_settings.collision_quality = 4
    cloth.collision_settings.distance_min = .015
    cloth.collision_settings.self_distance_min = .012
    cache = cloth.point_cache
    cache.frame_start, cache.frame_end = 1, LAST_FRAME
    cache.use_disk_cache = False
    cache.frame_step = 1
    subdivision = cape.modifiers.new("Fabric surface", "SUBSURF")
    subdivision.levels = subdivision.render_levels = 1
    thickness = cape.modifiers.new("Fabric thickness", "SOLIDIFY")
    thickness.thickness = .009
    return cape, cloth


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def light(name, location, energy, color, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.color, data.shape, data.size = energy, color, "DISK", size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    point_at(obj, (1.7, 0, 1.1))


def build(args):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, LAST_FRAME
    scene.render.fps = FPS
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 37
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get("Background").inputs[0].default_value = (.13, .19, .24, 1)
    scene.world.node_tree.nodes.get("Background").inputs[1].default_value = .35
    mats = {
        "cream": material("Porcelain cream", (.80, .76, .62), .18, .27),
        "teal": material("Sea glass teal", (.18, .51, .49), .22, .29),
        "visor": material("Ink glass visor", (.008, .027, .037), .48, .19),
        "eyes": material("Warm cyan eye lights", (.37, .95, 1), .1, .2, 3),
        "rubber": material("Soft graphite rubber", (.026, .038, .047), 0, .66),
        "metal": material("Joint titanium", (.18, .24, .26), .65, .32),
        "cape": material("Tangerine woven fabric", (.95, .20, .042), 0, .72),
        "stage": material("Warm studio platform", (.34, .45, .47), .05, .61),
        "floor": material("Studio background", (.09, .15, .18), 0, .73),
        "box": material("Peach obstacle", (.81, .39, .20), .04, .46),
    }
    rig = make_rig()
    body = skin(ellipsoid("Capsule_Shell", (0, 0, 1.24), (.37, .46, .65), mats["cream"]), rig, "body")
    collision(body)
    skin(ellipsoid("Belly_Teal", (.26, 0, .99), (.16, .34, .28), mats["teal"]), rig, "body")
    skin(ellipsoid("Face_Visor", (.326, 0, 1.49), (.09, .355, .23), mats["visor"]), rig, "body")
    for side, y in (("L", -.145), ("R", .145)):
        skin(ellipsoid("Eye_" + side, (.407, y, 1.51), (.025, .051, .077), mats["eyes"]), rig, "body")
        foot = skin(rounded_box("Rubber_Foot_" + side, (.055, y / .145 * .29, .13),
                                (.46, .27, .26), mats["rubber"], .10), rig, "foot." + side)
        collision(foot)
        skin(ellipsoid("Ankle_" + side, (0, y / .145 * .29, .28), (.085, .085, .085), mats["teal"]), rig, "foot." + side)
        skin(ellipsoid("Telescopic_Leg_" + side, (0, y / .145 * .29, .43), (.075, .075, .18), mats["metal"]), rig, "shin." + side)
        skin(ellipsoid("Arm_" + side, (0, y / .145 * .48, 1.065), (.095, .095, .27), mats["teal"]), rig, "arm." + side)
        skin(ellipsoid("Mitten_" + side, (0, y / .145 * .48, .80), (.105, .11, .13), mats["cream"]), rig, "arm." + side)
        skin(ellipsoid("Shoulder_Button_" + side, (-.17, y / .145 * .30, 1.73), (.055, .065, .055), mats["metal"]), rig, "root")
        # Visible straps bridge the shoulder fasteners and the pinned cape edge.
        skin(rounded_box("Cape_Strap_" + side, (-.28, y / .145 * .30, 1.74),
                         (.27, .065, .045), mats["cape"], .018), rig, "root")
    cape, cloth = make_cape(rig, mats["cape"])
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=4.35, depth=.18, location=(1.7, 0, -.09))
    stage = finish(bpy.context.object, "Round_Stage", mats["stage"])
    bevel = stage.modifiers.new("Stage rim", "BEVEL")
    bevel.width, bevel.segments = .08, 3
    collision(stage)
    floor = rounded_box("Studio_Floor", (1.7, 0, -.27), (200, 200, .1), mats["floor"], .01)
    collision(floor)
    obstacle = rounded_box("Jump_Box", (BOX_CENTER, 0, BOX_HEIGHT / 2),
                           (.60, 1.12, BOX_HEIGHT), mats["box"], .055)
    collision(obstacle)
    # A tiny raised stripe gives the obstacle a readable top face.
    rounded_box("Box_Top_Stripe", (BOX_CENTER, 0, BOX_HEIGHT + .002), (.42, .08, .005), mats["cream"], .002)
    light("Key_Softbox", (1.0, -4.8, 7), 1150, (1, .88, .73), 5)
    light("Cool_Fill", (6, 3, 4), 900, (.58, .83, 1), 4)
    light("Cape_Rim", (-3, 2, 5.5), 1350, (1, .62, .32), 3)
    camera_data = bpy.data.cameras.new("Demo_Camera_Data")
    camera = bpy.data.objects.new("Demo_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (8.0, -10.0, 5.7)
    point_at(camera, (1.75, 0, 1.25))
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 7.0
    scene.camera = camera
    # Save a useful initial editing view as well as the render camera.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.overlay.show_overlays = False
                space.shading.type = "SOLID"
                space.shading.color_type = "MATERIAL"
    evidence = animate(rig)
    for frame, name in ((1, "Ready"), (9, "Left lift"), (28, "Left plant"),
                        (29, "Right lift"), (48, "Right plant"), (60, "Launch"),
                        (75, "Apex"), (90, "Touchdown"), (99, "Landing squash"),
                        (108, "Recovered"), (120, "End")):
        scene.timeline_markers.new(name, frame=frame)
    blend_path = args.output_dir / "robot.blend"
    scene.render.filepath = str(args.output_dir / "frames" / "frame_")
    # Establish the delivery path before baking and embed the bake on final save.
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.context.view_layer.objects.active = cape
    bpy.ops.object.select_all(action="DESELECT")
    cape.select_set(True)
    print("CAPSULE_DEMO baking cloth frames 1..120", flush=True)
    with bpy.context.temp_override(scene=scene, object=cape, active_object=cape,
                                  point_cache=cloth.point_cache):
        result = bpy.ops.ptcache.bake(bake=True)
    if ("FINISHED" not in result or not cloth.point_cache.is_baked
            or cloth.point_cache.is_outdated or cloth.point_cache.is_frame_skip):
        raise RuntimeError("Cloth bake failed; output is incomplete")
    scene.frame_set(1)
    # No backup copy: this path belongs exclusively to this new recipe directory.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    crossings = []
    for state in evidence:
        for key in ("left", "right"):
            x, _, z = state[key]
            if abs(x + .055 - BOX_CENTER) <= BOX_HALF_LENGTH + FOOT_HALF_LENGTH:
                crossings.append({"frame": state["frame"], "foot": key,
                                  "clearance": z - FOOT_HALF_HEIGHT - BOX_HEIGHT})
    minimum_clearance = min(item["clearance"] for item in crossings)
    if minimum_clearance <= .10:
        raise RuntimeError(f"Insufficient planned foot/box clearance: {minimum_clearance}")
    manifest = {
        "schema_version": 1, "recipe": "original-capsule-two-steps-box-leap",
        "blender_version": bpy.app.version_string, "fps": FPS,
        "frame_start": 1, "frame_end": LAST_FRAME, "duration_seconds": 5,
        "coordinate_system": "Z up, +X forward, meters",
        "render": {"engine": scene.render.engine, "device": "CPU", "samples": args.samples,
                   "width": args.width, "height": args.height, "seed": 37,
                   "sequence_requested": args.render, "sequence_complete": False},
        "files": {"blend": "robot.blend", "frames": "frames/frame_####.png",
                  "cache_files": [str(p.relative_to(args.output_dir)) for p in sorted(args.output_dir.rglob("*.bphys"))]},
        "physics": {"cape": cape.name, "modifier": cloth.name, "baked": cloth.point_cache.is_baked,
                    "disk_cache": False, "pins": "Shoulder_Pins", "pinned_vertex_count": 17,
                    "cache_dependency": "Baked cloth cache embedded in robot.blend; verify persistence by reopening in a fresh Blender process.",
                    "collision_objects": [o.name for o in scene.objects if any(m.type == "COLLISION" for m in o.modifiers)]},
        "rig": {"object": rig.name, "bones": list(rig.data.bones.keys()),
                "weighted_parts": [o.name for o in scene.objects if any(m.type == "ARMATURE" for m in o.modifiers)],
                "control_note": "Keyframed pose bones; feet planted in world space, telescopic legs solve hip-to-ankle endpoints. No IK constraints."},
        "obstacle": {"object": obstacle.name, "center_x": BOX_CENTER,
                     "length_x": .60, "width_y": 1.12, "height": BOX_HEIGHT,
                     "bounds_world": {"min": [2.10, -.56, 0], "max": [2.70, .56, .48]}},
        "foot_geometry": {"left": "Rubber_Foot_L", "right": "Rubber_Foot_R",
                          "rest_center_offset_from_bone": [.055, 0, 0],
                          "dimensions": [.46, .27, .26], "bevel_radius": .10},
        "phases": [{"name": "two steps", "frames": [1, 48]},
                   {"name": "anticipation", "frames": [49, 60]},
                   {"name": "leap", "frames": [61, 89]},
                   {"name": "landing recovery", "frames": [90, 108]},
                   {"name": "settled", "frames": [109, 120]}],
        "events": [{"frame": m.frame, "name": m.name} for m in scene.timeline_markers],
        "trajectory": evidence, "foot_box_crossings": crossings,
        "minimum_planned_foot_box_clearance": minimum_clearance,
        "evidence_boundary": "Control-space planned foot clearance; visual rendered clearance and cloth quality require inspection. Cloth bake success is not a visual review.",
        "objects": sorted(o.name for o in scene.objects),
        "materials": list(m.name for m in mats.values()),
        "source_assets": [], "network_required": False,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.render:
        (args.output_dir / "frames").mkdir()
        print("CAPSULE_DEMO rendering frames 1..120", flush=True)
        bpy.ops.render.render(animation=True)
        frame_files = list((args.output_dir / "frames").glob("frame_*.png"))
        if len(frame_files) != LAST_FRAME:
            raise RuntimeError(f"Expected 120 PNG frames, found {len(frame_files)}")
        manifest["render"]["sequence_complete"] = True
        manifest["render"]["frame_count"] = len(frame_files)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"CAPSULE_DEMO complete {blend_path}", flush=True)


if __name__ == "__main__":
    build(arguments())
