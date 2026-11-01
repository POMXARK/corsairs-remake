"""Runs inside Blender: imports a character GLB of tools/pdm_chars_blender.py and tidies it for hand work (ours).

  blender -P tools/pdm_glb_open.py -- <file.glb> [action]

Does not make the helper bone shape (Icosphere in glTF_not_exported) of the importer, which breaks the import in the window, draws the bones as octahedrons in
front of the mesh and sets the action (default idle_1), so the model can be posed (T-pose for 3D generation) and the
clips of the game looked at in the Dope Sheet / Action Editor.
"""
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
bpy.ops.wm.read_factory_settings(use_empty=True)
# disable_bone_shape: the importer of Blender 5.4 alpha fails in the window on the Icosphere it makes for the bones
# (bpy.context.object is None), and nothing but the sphere is imported
bpy.ops.import_scene.gltf(filepath=args[0], disable_bone_shape=True)
for coll in [c for c in bpy.data.collections if c.name == "glTF_not_exported"]:
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)
for arm in (o for o in bpy.data.objects if o.type == "ARMATURE"):
    arm.data.display_type = "OCTAHEDRAL"
    arm.show_in_front = True
    for bone in arm.pose.bones:
        bone.custom_shape = None
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.get(args[1] if len(args) > 1 else "idle_1")
    bpy.context.view_layer.objects.active = arm


def frame_all():
    """The whole model in the 3D view, with the textures (a timer: the window exists only after the script)."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                region = next(r for r in area.regions if r.type == "WINDOW")
                area.spaces[0].shading.color_type = "TEXTURE"
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_all()
                    bpy.ops.view3d.view_axis(type="FRONT")
                    bpy.ops.view3d.view_all()
    return None


bpy.context.preferences.view.show_splash = False
bpy.app.timers.register(frame_all, first_interval=1.0)
