import bpy
obj=bpy.data.objects['Body']
obj.data.calc_loop_triangles()
# Decimate's ratio is based on triangles. Account for a quad source when the
# user constraint measures polygon faces, with a small margin for rounding.
ratio=min(1.0, .65*len(obj.data.polygons)/max(1,len(obj.data.loop_triangles)))
mod=obj.modifiers.new('PreviewDecimate','DECIMATE');mod.ratio=ratio
