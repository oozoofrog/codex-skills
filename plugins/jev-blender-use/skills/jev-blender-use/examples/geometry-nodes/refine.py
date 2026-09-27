"""Scoped visual repair of the existing forest; keep all 20,000 instances."""
import bpy
from mathutils import Vector
forest=bpy.data.objects['Forest']
grid=next(n for n in forest.modifiers['ForestInstances'].node_group.nodes if n.bl_idname=='GeometryNodeMeshGrid')
grid.inputs['Size X'].default_value=60;grid.inputs['Size Y'].default_value=120
for v in bpy.data.objects['TreePrototype'].data.vertices:
    v.co.x*=1.5;v.co.y*=1.5;v.co.z=v.co.z*3+1.05
bpy.data.objects['Ground'].scale=(20,20,1)
camera=bpy.data.objects['Camera'];camera.location=(8,-67,8)
camera.rotation_euler=(Vector((0,-53,1))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=20
light=bpy.data.objects['Key'];light.location=(0,-54,12);light.data.energy=2400;light.data.size=10
