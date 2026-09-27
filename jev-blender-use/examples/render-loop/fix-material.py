import bpy
bpy.data.objects['Body'].data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.12,.58,.6,1)
