"""Shared deterministic fixture. Execute inside Blender via the trusted runner."""
import bpy
from mathutils import Vector

def material(name,color):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
    m.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.48
    return m

def stage():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_plane_add(size=20);plane=bpy.context.object;plane.name='Ground'
    plane.data.materials.append(material('GroundMat',(.12,.17,.2)))
    bpy.ops.object.camera_add(location=(7,-10,7));camera=bpy.context.object;camera.name='Camera'
    camera.rotation_euler=(Vector((0,0,1))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=8;bpy.context.scene.camera=camera
    bpy.ops.object.light_add(type='AREA',location=(1,-3,7));light=bpy.context.object;light.name='Key';light.data.energy=1200;light.data.shape='DISK';light.data.size=5
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8
    scene.world.color=(.25,.25,.25);scene.render.resolution_x=512;scene.render.resolution_y=384;scene.render.resolution_percentage=100

def body():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,location=(0,0,1.2))
    obj=bpy.context.object;obj.name='Body';obj.data.materials.append(material('BodyMat',(.12,.58,.6)))
    for p in obj.data.polygons:p.use_smooth=True
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.35,location=(2,0,.35))
    head=bpy.context.object;head.name='Head';head.data.materials.append(material('HeadMat',(.9,.5,.2)))
    return obj

helpers={"stage":stage,"body":body,"material":material}
import bpy
helpers['stage']()
bpy.ops.mesh.primitive_cone_add(vertices=8,radius1=.12,depth=.7,location=(0,0,-5))
tree=bpy.context.object;tree.name='TreePrototype';tree.data.materials.append(helpers['material']('Needles',(.1,.45,.2)))
bpy.ops.mesh.primitive_plane_add(size=1);obj=bpy.context.object;obj.name='Forest'
ng=bpy.data.node_groups.new('ForestInstances','GeometryNodeTree')
ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
mod=obj.modifiers.new('ForestInstances','NODES');mod.node_group=ng
n=ng.nodes;l=ng.links
out=n.new('NodeGroupOutput');grid=n.new('GeometryNodeMeshGrid');grid.inputs['Size X'].default_value=6;grid.inputs['Size Y'].default_value=6
grid.inputs['Vertices X'].default_value=100;grid.inputs['Vertices Y'].default_value=200
info=n.new('GeometryNodeObjectInfo');info.inputs['Object'].default_value=tree;info.inputs['As Instance'].default_value=True
inst=n.new('GeometryNodeInstanceOnPoints');l.new(grid.outputs['Mesh'],inst.inputs['Points']);l.new(info.outputs['Geometry'],inst.inputs['Instance']);l.new(inst.outputs['Instances'],out.inputs['Geometry'])
