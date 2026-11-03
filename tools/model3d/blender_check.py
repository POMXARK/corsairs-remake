"""Check a head .glb in Blender with the 3D Print Toolbox extension (extensions.blender.org, GPL).

blender -b --python blender_check.py -- model.glb

Prints the open (non-manifold) edges, the self-intersecting and the zero-size faces, vertices merged by position (without
the merge every UV seam counts as open: 220 000 edges on the TRELLIS mesh).
Install once: blender --online-mode -c extension install -s -e print3d_toolbox
"""
import sys

import bpy

path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='bl_ext.blender_org.print3d_toolbox')
from bl_ext.blender_org.print3d_toolbox import report  # noqa: E402

bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)  # UV seams are not open edges
obj = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
print(f'[check] {path}: {len(obj.data.polygons)} faces', flush=True)
for chk in ('print3d_check_solid', 'print3d_check_intersect', 'print3d_check_degenerate'):
    getattr(bpy.ops.mesh, chk)()
    for item in report.get():
        print(f'[check] {item.name}: {item.value}', flush=True)
