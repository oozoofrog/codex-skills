"""Compact bpy scene evidence, also importable from a Blender MCP exec session."""
from __future__ import annotations

import hashlib
import json
import math
import struct

import bpy


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def scalar(value, depth=0):
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, bpy.types.ID):
        return {"id": value.name_full, "type": type(value).__name__,
                "library": value.library.filepath if value.library else None}
    if isinstance(value, bpy.types.bpy_struct):
        # bpy repr contains process-specific memory addresses. Bound nested RNA
        # traversal and serialize type/properties instead for portable hashes.
        return {"rna_type": value.bl_rna.identifier,
                "properties": properties(value, depth + 1) if depth < 2 else {}}
    try:
        return [scalar(item, depth) for item in value]
    except TypeError:
        return str(value)


def properties(value, depth=0):
    """Scalar RNA properties only; never follow arbitrary ID pointers recursively."""
    result = {}
    for prop in value.bl_rna.properties:
        if prop.identifier in {"rna_type", "is_updated", "is_updated_data", "is_evaluated", "original", "session_uid", "users"} or prop.type == "COLLECTION":
            continue
        try:
            result[prop.identifier] = scalar(getattr(value, prop.identifier), depth)
        except (AttributeError, TypeError, RuntimeError):
            pass
    return result


def mesh_stats(mesh):
    mesh.calc_loop_triangles()
    digest = hashlib.sha256()
    # Stream coordinates/topology: no raw geometry in the JSON output.
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *vertex.co))
        for group in vertex.groups:
            digest.update(struct.pack("<Qd",group.group,group.weight))
    edge_use = {}
    winding = {}
    for edge in mesh.edges:
        pair = tuple(sorted(edge.vertices))
        digest.update(struct.pack("<2Q", *pair))
        edge_use[pair] = 0
    degenerate = 0
    for polygon in mesh.polygons:
        indices = tuple(polygon.vertices)
        digest.update(struct.pack("<Q", len(indices)))
        digest.update(struct.pack("<" + "Q" * len(indices), *indices))
        digest.update(struct.pack("<q?", polygon.material_index, polygon.use_smooth))
        if polygon.area <= 1e-12 or len(set(indices)) < 3:
            degenerate += 1
        for a, b in zip(indices, indices[1:] + indices[:1]):
            pair = tuple(sorted((a, b)))
            edge_use[pair] = edge_use.get(pair, 0) + 1
            winding[pair] = winding.get(pair, 0) + (1 if a < b else -1)
    # UVs, colors, weights and custom-normal attributes are part of protected geometry.
    for attribute in sorted(mesh.attributes, key=lambda a: a.name):
        digest.update(json.dumps([attribute.name,attribute.domain,attribute.data_type],sort_keys=True).encode())
        for item in attribute.data:
            digest.update(json.dumps(properties(item),sort_keys=True,allow_nan=False).encode())
    if mesh.has_custom_normals:
        for normal in mesh.corner_normals:
            digest.update(struct.pack('<3d', *normal.vector))
    return {"vertices": len(mesh.vertices), "edges": len(mesh.edges),
            "polygons": len(mesh.polygons), "triangles": len(mesh.loop_triangles),
            "nonmanifold_edges": sum(count != 2 for count in edge_use.values()),
            "degenerate_faces": degenerate, "winding_conflicts": sum(edge_use[k] == 2 and abs(v) == 2 for k,v in winding.items()), "sha256": digest.hexdigest()}


def node_tree_state(tree, seen=None):
    seen=set() if seen is None else seen
    if tree is None:return None
    if tree.name_full in seen:return {'recursive_reference':tree.name_full}
    seen=seen|{tree.name_full}
    nodes=[]
    for n in tree.nodes:
        nodes.append({'name':n.name,'type':n.bl_idname,'properties':properties(n),
                      'inputs':[{'name':sock.identifier,'value':scalar(sock.default_value)} for sock in n.inputs if hasattr(sock,'default_value')],
                      'nested':node_tree_state(getattr(n,'node_tree',None),seen)})
    return {'nodes':nodes,'links':sorted((l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in tree.links)}


def material_state(mat):
    if mat is None:return None
    return {'name':mat.name,'library':mat.library.filepath if mat.library else None,
            'properties':properties(mat),'node_tree':node_tree_state(mat.node_tree)}


def id_properties(value):
    try:return {k:scalar(v) for k,v in value.items()}
    except TypeError:return {}


def object_state(obj, depsgraph, instances=None):
    transform = [float(obj.matrix_world[row][col]) for row in range(4) for col in range(4)]
    evaluated = obj.evaluated_get(depsgraph)
    corners = [evaluated.matrix_world @ __import__("mathutils").Vector(v) for v in evaluated.bound_box]
    materials = [slot.material.name if slot.material else None for slot in obj.material_slots]
    mods = [{"name": m.name, "type": m.type, "properties": properties(m),
             "custom_properties":id_properties(m),
             "node_tree_sha256":fingerprint(node_tree_state(getattr(m,'node_group',None)))} for m in obj.modifiers]
    result = {"type": obj.type, "transform": transform,
              "dimensions": list(evaluated.dimensions),
              "bounds": {"min": [min(v[i] for v in corners) for i in range(3)],
                         "max": [max(v[i] for v in corners) for i in range(3)]},
              "materials": materials,
              "material_sha256": fingerprint([material_state(s.material) for s in obj.material_slots]),
              "modifiers": mods, "modifier_sha256": fingerprint(mods),
              "shape_keys": [], "shape_key_sha256": None,
              "vertex_groups": [{"name":g.name,"index":g.index,"lock_weight":g.lock_weight} for g in obj.vertex_groups],
              "data_name": obj.data.name if obj.data else None,
              "data_users": obj.data.users if obj.data else 0,
              "data_sha256": fingerprint(properties(obj.data)) if obj.data and obj.type != "MESH" else None,
              "library": obj.library.filepath if obj.library else None,
              "data_library": obj.data.library.filepath if obj.data and obj.data.library else None,
              "collections": sorted(c.name for c in obj.users_collection),
              "parent": obj.parent.name if obj.parent else None,
              "hide_render": obj.hide_render, "hide_viewport": obj.hide_viewport,
              "constraints_sha256": fingerprint([properties(c) for c in obj.constraints]),
              "mesh": None, "evaluated_mesh": None}
    if obj.type == 'ARMATURE':
        result['rig']={'bones':[{'name':b.name,'parent':b.parent.name if b.parent else None,
                                'head':list(b.head_local),'tail':list(b.tail_local),'deform':b.use_deform} for b in obj.data.bones],
                       'pose':[{'name':b.name,'matrix':[float(x) for row in b.matrix for x in row],
                                'constraints':[properties(c) for c in b.constraints]} for b in obj.pose.bones]}
    result["evaluated_instances"] = (instances or {}).get(obj.name, {"count": 0, "mesh_polygons": 0})
    if obj.type == "MESH":
        result["mesh"] = mesh_stats(obj.data)
        if obj.data.shape_keys:
            digest = hashlib.sha256()
            for block in obj.data.shape_keys.key_blocks:
                result["shape_keys"].append(block.name)
                digest.update(block.name.encode())
                digest.update(struct.pack("<d", block.value))
                for point in block.data:
                    digest.update(struct.pack("<3d", *point.co))
            result["shape_key_sha256"] = digest.hexdigest()
        temp = evaluated.to_mesh()
        try:
            if temp:
                result["evaluated_mesh"] = mesh_stats(temp)
        finally:
            evaluated.to_mesh_clear()
    return result


def inspect_scene(objects=None, limit=50):
    """Explicit exact-name filters are uncapped; default inventory is capped."""
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("limit must be an integer in [1,500]")
    scene = bpy.context.scene
    names = sorted(scene.objects.keys()) if objects is None else list(dict.fromkeys(objects))
    if len(names)>500 and objects is not None:raise ValueError("explicit scope exceeds 500 objects")
    if objects is not None and any(not isinstance(name, str) or not name for name in names):
        raise ValueError("objects must contain exact nonempty names")
    truncated = objects is None and len(names) > limit
    if objects is None:
        names = names[:limit]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    instances = {}
    for instance in depsgraph.object_instances:
        if not instance.is_instance or instance.parent is None:
            continue
        name = instance.parent.original.name
        entry = instances.setdefault(name, {"count": 0, "mesh_polygons": 0})
        entry["count"] += 1
        if instance.object.type == "MESH" and instance.object.data:
            entry["mesh_polygons"] += len(instance.object.data.polygons)
    return {"schema_version": 1,
            "scene": {"name": scene.name, "mode": bpy.context.mode,
                      "file": bpy.data.filepath, "is_dirty": bpy.data.is_dirty,
                      "is_saved": bpy.data.is_saved, "object_count": len(scene.objects),
                      "object_names": names,
                      "active_camera": scene.camera.name if scene.camera else None,
                      "render_engine": scene.render.engine,
                      "render_settings": {"width": scene.render.resolution_x,
                                          "height": scene.render.resolution_y,
                                          "percentage": scene.render.resolution_percentage,
                                          "fps": scene.render.fps, "fps_base": scene.render.fps_base},
                      "frame": scene.frame_current},
            "objects": {name: object_state(scene.objects[name], depsgraph, instances)
                        for name in names if name in scene.objects},
            "missing_objects": [name for name in names if name not in scene.objects],
            "selected_objects": sorted(obj.name for obj in bpy.context.selected_objects)[:limit],
            "selection_count": len(bpy.context.selected_objects),
            "collections": {c.name: {"objects": sorted(o.name for o in c.objects if o.name in names),
                                      "object_count": len(c.objects),
                                      "children": sorted(child.name for child in c.children)[:limit],
                                      "library": c.library.filepath if c.library else None}
                            for c in bpy.data.collections if any(o.name in names for o in c.objects)},
            "truncated": truncated}
