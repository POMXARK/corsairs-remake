"""Runs inside Blender: imports a character GLB of tools/pdm_chars_blender.py and tidies it for hand work (ours).

  blender -P tools/pdm_glb_open.py -- <file.glb> [action]

Imports without the helper bone shape (Icosphere in glTF_not_exported): the importer of Blender 5.4 alpha fails on it
in the window (bpy.context.object is None) and leaves nothing but the sphere. The import runs in a timer, when the
window exists (the importer needs bpy.context.window). The bones are drawn as octahedrons in front of the mesh, the
action is set (default idle_1) and the view is on the model with the textures, so the model can be posed (T-pose for
3D generation) and the clips of the game looked at in the Dope Sheet / Action Editor.
"""
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=args[0], disable_bone_shape=True)
    for coll in [c for c in bpy.data.collections if c.name == "glTF_not_exported"]:
        bpy.data.collections.remove(coll)
    for arm in (o for o in bpy.data.objects if o.type == "ARMATURE"):
        arm.data.display_type = "OCTAHEDRAL"
        arm.show_in_front = True
        arm.animation_data_create()
        arm.animation_data.action = bpy.data.actions.get(args[1] if len(args) > 1 else "idle_1")
        bpy.context.view_layer.objects.active = arm
    if bpy.app.background:
        return None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                region = next(r for r in area.regions if r.type == "WINDOW")
                area.spaces[0].shading.color_type = "TEXTURE"
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_axis(type="FRONT")
                    bpy.ops.view3d.view_all()
    return None


bpy.context.preferences.view.show_splash = False
if bpy.app.background:
    main()
else:
    bpy.app.timers.register(main, first_interval=1.0)
