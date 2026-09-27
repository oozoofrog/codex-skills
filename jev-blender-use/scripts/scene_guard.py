"""Pure deterministic guards for declared Blender operations; no bpy dependency."""
from __future__ import annotations

DESTRUCTIVE = {"delete", "join", "remesh", "apply_modifier", "apply_transform", "decimate",
               "subdivide", "extrude", "boolean", "edit_mesh", "edit_vertices", "modify_mesh",
               "remove_modifier", "rename", "bake", "delete_datablock", "overwrite"}
SHAPE_KEY_FORBIDDEN = {"join", "remesh", "apply_modifier", "apply_transform", "decimate",
                       "subdivide", "extrude", "boolean", "edit_mesh", "modify_mesh"}
KNOWN = DESTRUCTIVE | {"create", "create_mesh", "create_material", "create_light", "create_camera",
                       "add_primitive", "duplicate", "move", "rotate", "scale", "transform",
                       "set_transform", "set_material", "assign_material", "set_modifier",
                       "add_modifier", "geometry_nodes", "set_shape_key", "animate", "keyframe", "set_camera",
                       "render_settings", "cloth", "bake"}
CREATES = {"create", "create_mesh", "create_material", "create_light", "create_camera", "add_primitive"}
GLOBALS = {"render_settings", "set_camera", "bake"}


def preguard(plan, before):
    """Guard declared operations only. Arbitrary Python can exceed the declaration."""
    target = set(plan["target_objects"])
    protected = set(plan["protected_objects"])
    reasons, reviews = [], []
    if target & protected:
        reasons.append("target_protected_overlap")
    objects = before["objects"]
    for name in protected - objects.keys():
        reasons.append("missing_protected_object:" + name)
    requires_checkpoint = False
    for operation in plan["operations"]:
        kind = operation["type"].lower().replace("-", "_")
        name = operation.get("target")
        names = operation.get("targets", [])
        if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
            reasons.append("invalid_operation_targets")
            continue
        if name is not None:
            if not isinstance(name, str):
                reasons.append("invalid_operation_target")
                continue
            names = [name] + names
        if kind not in KNOWN:
            reviews.append("unknown_operation:" + kind)
        if kind in DESTRUCTIVE:
            requires_checkpoint = True
        if not names and kind not in CREATES | GLOBALS:
            reviews.append("operation_has_no_explicit_target:" + kind)
        for name in names:
            if name in protected:
                reasons.append("direct_operation_on_protected_object:" + name)
            if name not in target:
                reasons.append("operation_target_not_declared:" + name)
            obj = objects.get(name)
            if obj is None:
                if kind not in CREATES:
                    reviews.append("missing_operation_target:" + name)
                continue
            if obj.get("shape_keys") and kind in SHAPE_KEY_FORBIDDEN:
                reasons.append("shape_key_destructive_operation:" + name + ":" + kind)
            if obj.get("library") or obj.get("data_library"):
                reviews.append("linked_data:" + name)
            if obj.get("data_users", 0) > 1:
                reviews.append("shared_data:" + name)
            for protected_name in protected:
                other = objects.get(protected_name, {})
                if obj.get("data_name") and obj.get("data_name") == other.get("data_name"):
                    reviews.append("data_shared_with_protected:" + name + ":" + protected_name)
    return {"status": "refused" if reasons else "needs_review" if reviews else "completed",
            "reasons": sorted(set(reasons or reviews)), "requires_checkpoint": requires_checkpoint,
            "scope": "Declared-operation preguard. Trusted arbitrary Python is not constrained or sandboxed."}



def guard(plan, before):
    """Return refusal/review reasons. An empty list is not a sandbox guarantee."""
    return preguard(plan, before)["reasons"]
