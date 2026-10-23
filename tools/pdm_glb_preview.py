"""Draws GLB files into one picture, a column per file: front, three quarters, side (docs/ai-models.md, ours).
Runs inside Blender (the 5.x of the project, 3.3 does not open the big GLB of the networks):

  blender -b -P tools/pdm_glb_preview.py -- --out compare.png [--size 512] a.glb b.glb ...

The model is put on the floor and scaled to the height of 1.8, the light is the same for all of them, the
background is grey as in the views of pdm_model_views.py. The name of the file is written under the column
of it by the picture itself, not by this script: the order of the columns is the order of the arguments.
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
import mathutils
import numpy as np


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--shiny", action="store_true", help="keep the metallic and roughness of the file")
    ap.add_argument("files", nargs="+")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def engine():
    for name in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        try:
            bpy.context.scene.render.engine = name
            return
        except TypeError:
            pass


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def matte():
    """The network bakes metallic and roughness; the game takes the base colour only, so the preview shows that."""
    for mat in bpy.data.materials:
        for n in (mat.node_tree.nodes if mat.use_nodes else []):
            if n.type == "BSDF_PRINCIPLED":
                for name, value in (("Metallic", 0.0), ("Roughness", 1.0)):
                    for sock in n.inputs:
                        if sock.name == name:
                            for link in list(sock.links):
                                mat.node_tree.links.remove(link)
                            sock.default_value = value


def bounds(objs):
    lo, hi = mathutils.Vector((1e9,) * 3), mathutils.Vector((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector(map(min, lo, w))
            hi = mathutils.Vector(map(max, hi, w))
    return lo, hi


def fit(objs):
    """The model to the floor, the centre of it on the axis, 1.8 high."""
    lo, hi = bounds(objs)
    height = max(hi.z - lo.z, 1e-6)
    k = 1.8 / height
    root = bpy.data.objects.new("root", None)
    bpy.context.scene.collection.objects.link(root)
    for o in objs:
        if o.parent is None:
            o.parent = root
    root.scale = (k, k, k)
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    root.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.context.view_layer.update()
    return root


def scene_setup(size):
    sc = bpy.context.scene
    engine()
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.image_settings.file_format = "PNG"
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.2, 0.2, 0.2, 1)
    bg.inputs[1].default_value = 1.0
    for loc, energy in (((3, -4, 5), 3.0), ((-4, -2, 3), 1.5)):
        light = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        light.data.energy = energy
        light.rotation_euler = (math.radians(50), 0, math.atan2(loc[0], -loc[1]))
        sc.collection.objects.link(light)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.2
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def shot(cam, yaw, path):
    cam.location = (math.sin(yaw) * 6, -math.cos(yaw) * 6, 0.95)
    look = mathutils.Vector((0, 0, 0.95)) - cam.location
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    return px


def main():
    a = args()
    tmp = str(Path(a.out).with_suffix(".tmp.png"))
    columns = []
    for f in a.files:
        clear()
        cam = scene_setup(a.size)
        fit(load(f))
        if not a.shiny:
            matte()
        views = [shot(cam, math.radians(y), tmp) for y in (0, 40, 90)]
        columns.append(np.concatenate(views[::-1], axis=0))  # the image rows go from the bottom
        print("pdm_glb_preview:", f)
    sheet = np.concatenate(columns, axis=1)
    img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    img.pixels = sheet.reshape(-1).tolist()
    img.filepath_raw = a.out
    img.file_format = "PNG"
    img.save()
    Path(tmp).unlink(missing_ok=True)
    print("pdm_glb_preview:", a.out)


main()
