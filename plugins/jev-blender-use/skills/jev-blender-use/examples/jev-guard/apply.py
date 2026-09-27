import bpy
obj=bpy.data.objects['Body'];bpy.context.view_layer.objects.active=obj
mod=obj.modifiers.new('DestructiveDecimate','DECIMATE');mod.ratio=.5
bpy.ops.object.modifier_apply(modifier=mod.name)
