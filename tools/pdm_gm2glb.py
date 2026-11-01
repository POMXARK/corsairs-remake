#!/usr/bin/env python3
"""A .gm of pdm-game/resource as a GLB: the low-poly original as the target of baking and the input of mesh refinement
(UltraShape and the like), docs/ai-models.md (ours).

One primitive per object of the .gm with its texture and UVs, in the frame of glTF (z negated, the faces turned: the front along +z), so pdm_glb2gm.py
puts it back where it was, the bone of every vertex in a second file <out>.bones.json (list per
object), so the new geometry can be bound to the same skeleton later.

A skinned character also gets its skeleton (the joints of animation/<name>.an, frame 0 as the rest pose), the
skin weights (every vertex follows the bone of the .gm) and one glTF animation per action of animation/<name>.ani,
so Blender shows the bones and plays walk, hi_1 and the rest; the model itself stays in the pose it is bound in
and pdm_glb2gm.py still fits a new mesh to it (the skeleton and the animations of the game are not read back).

usage: pdm_gm2glb.py <game dir> <model> [--out data/ai_models/glb/<name>_orig.glb] [--no-rig]
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdm_model_views import find_model, load_texture, read_gm, texture_index  # noqa: E402


FLIP = np.array((1.0, 1.0, -1.0))  # the engine looks along -z, glTF along +z: the mirror the other way is pdm_glb2gm.py


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_rig(game: Path, model: Path):
    """The skeleton and the actions of animation/<name>.an and .ani next to a skinned model, or None."""
    from pdm_anim_check import read_ani  # noqa: E402
    stem = model.stem
    for name in (stem, stem[:-4] if stem.endswith("_brd") else stem):
        an, ani = game / "resource" / "animation" / f"{name}.an", game / "resource" / "animation" / f"{name}.ani"
        if an.exists() and ani.exists():
            break
    else:
        return None
    data = an.read_bytes()
    frames, bones, fps = struct.unpack_from("<iif", data, 0)
    parents = np.frombuffer(data, "<i4", bones, 12).tolist()
    joints = np.frombuffer(data, "<f4", bones * 3, 12 + 4 * bones).reshape(bones, 3)
    at = 12 + 16 * bones
    roots = np.frombuffer(data, "<f4", frames * 3, at).reshape(frames, 3)
    rot = np.frombuffer(data, "<f4", bones * frames * 4, at + 12 * frames).reshape(bones, frames, 4)
    return {"fps": fps, "parents": parents, "joints": joints, "roots": roots, "rot": rot,
            "clips": read_ani(ani)[1]}


TURN = np.array((-1.0, 1.0, -1.0, 1.0))  # char space -> glTF space is a half turn about y: x and z flip, in a quaternion too


def add_rig(rig, nodes, scene_nodes, accessor, names=None):
    """The joints as nodes (frame 0 the rest pose), the skin and an animation per action; returns the doc parts."""
    parents, rot, roots, joints, fps = rig["parents"], rig["rot"], rig["roots"], rig["joints"], rig["fps"]
    bones, frames = rot.shape[:2]
    first = len(nodes)
    flip3 = TURN[:3]
    world = []
    for b in range(bones):
        m = np.eye(4)
        m[:3, :3] = quat_matrix(rot[b, 0])
        m[:3, 3] = roots[0] if parents[b] < 0 else joints[b]
        world.append(m if parents[b] < 0 else world[parents[b]] @ m)
    turn = np.diag((-1.0, 1.0, -1.0, 1.0))
    ibm = np.stack([np.linalg.inv(turn @ w @ turn).T for w in world]).astype("<f4")  # column-major
    for b in range(bones):
        node = {"name": (names or {}).get(b, f"bone_{b:02d}"), "rotation": (rot[b, 0] * TURN).tolist(),
                "translation": ((roots[0] if parents[b] < 0 else joints[b]) * flip3).tolist()}
        kids = [c for c in range(bones) if parents[c] == b]
        if kids:
            node["children"] = [first + c for c in kids]
        nodes.append(node)
    root = parents.index(-1)
    scene_nodes.append(first + root)
    skin = {"joints": [first + b for b in range(bones)], "skeleton": first + root,
            "inverseBindMatrices": accessor(ibm.reshape(-1, 16), 5126, "MAT4", None)}
    animations = []
    for name, clip in rig["clips"].items():
        s, e = clip["start_time"], min(clip["end_time"], frames - 1)
        if e <= s:
            continue
        span = slice(s, e + 1)
        times = ((np.arange(s, e + 1) - s) / fps).astype("<f4")
        time_acc = accessor(times, 5126, "SCALAR", None, True)
        t_out = accessor((roots[span] * flip3).astype("<f4"), 5126, "VEC3", None)
        samplers, channels = [], []

        def channel(node, path, out):
            samplers.append({"input": time_acc, "output": out, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path}})
        channel(first + root, "translation", t_out)
        for b in range(bones):
            channel(first + b, "rotation", accessor((rot[b, span] * TURN).astype("<f4"), 5126, "VEC4", None))
        animations.append({"name": name, "samplers": samplers, "channels": channels})
    return {"skins": [skin], "animations": animations}


def build(gm, index, rig=None):
    blob = bytearray()
    views, accessors, images, textures, materials, meshes_prims = [], [], [], [], [], []
    cache, mat_of = {}, {}

    def add(raw: bytes, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw),
                      **({"target": target} if target else {})})
        blob.extend(raw)
        return len(views) - 1

    def accessor(arr, ctype, kind, target, bounds=False):
        acc = {"bufferView": add(arr.tobytes(), target), "componentType": ctype, "count": len(arr), "type": kind}
        if bounds:
            acc["min"], acc["max"] = np.atleast_1d(arr.min(0)).tolist(), np.atleast_1d(arr.max(0)).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for name, tex, p, n, uv, bones, tris in gm["objects"]:
        if tex not in mat_of:
            img = load_texture(index, tex, cache)
            mat = {"name": tex or "none", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}
            if img is not None:
                buf = io.BytesIO()
                # the alpha stays (a blade, hair, a feather are cut out by it): RGBA PNG and the mask mode of glTF
                cut = img.shape[-1] == 4 and img[..., 3].min() < 0.99
                Image.fromarray((img[..., :4 if cut else 3] * 255).astype(np.uint8)).save(buf, "PNG")
                if cut:
                    mat["alphaMode"], mat["alphaCutoff"] = "MASK", 0.5
                images.append({"bufferView": add(buf.getvalue()), "mimeType": "image/png"})
                textures.append({"source": len(images) - 1})
                mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(textures) - 1}
            materials.append(mat)
            mat_of[tex] = len(materials) - 1
        meshes_prims.append({"attributes": {
            "POSITION": accessor((p * FLIP).astype("<f4"), 5126, "VEC3", 34962, True),
            "NORMAL": accessor((n * FLIP).astype("<f4"), 5126, "VEC3", 34962),
            "TEXCOORD_0": accessor(uv.astype("<f4"), 5126, "VEC2", 34962),
            **({"JOINTS_0": accessor(np.stack([bones, *[np.zeros_like(bones)] * 3], 1).astype("<u2"), 5123, "VEC4", 34962),
                "WEIGHTS_0": accessor(np.tile(np.array([1, 0, 0, 0], "<f4"), (len(bones), 1)), 5126, "VEC4", 34962)}
               if rig else {})},
            "indices": accessor(tris[:, ::-1].astype("<u4").reshape(-1), 5125, "SCALAR", 34963),
            "material": mat_of[tex]})
    nodes = [{"mesh": i, "name": o[0], **({"skin": 0} if rig else {})} for i, o in enumerate(gm["objects"])]
    scene_nodes = list(range(len(nodes)))
    extra = {}
    if rig:
        # a bone carrying the vertices of one object is named after it (its texture: hero_new_arm_top)
        names, taken_all = {}, []
        for o in gm["objects"]:
            used = set(np.unique(o[5]).tolist())
            label = Path(o[1]).stem if o[1] else o[0]
            if len(used) == 1 and label and used.copy().pop() not in names:
                n = 1 + sum(t == label for t in taken_all)
                taken_all.append(label)
                names[used.pop()] = label if n == 1 else f"{label}_{n}"
        extra = add_rig(rig, nodes, scene_nodes, accessor, names)
    doc = {"asset": {"version": "2.0", "generator": "pdm_gm2glb"}, "scene": 0,
           "scenes": [{"nodes": scene_nodes}], "nodes": nodes, **extra,
           "meshes": [{"primitives": [pr], "name": o[0]} for pr, o in zip(meshes_prims, gm["objects"])],
           "materials": materials, "accessors": accessors, "bufferViews": views,
           "buffers": [{"byteLength": len(blob)}]}
    if images:
        doc["images"], doc["textures"] = images, textures
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("model")
    ap.add_argument("--out")
    ap.add_argument("--no-rig", action="store_true", help="the mesh only, without the skeleton and the animations")
    a = ap.parse_args()
    game = Path(a.game)
    gm = read_gm(find_model(game, a.model))
    out = Path(a.out) if a.out else game / "data" / "ai_models" / "glb" / f"{Path(a.model).name}_orig.glb"
    out.parent.mkdir(parents=True, exist_ok=True)
    model = find_model(game, a.model)
    rig = read_rig(game, model) if gm["skinned"] and not a.no_rig else None
    data = build(gm, texture_index(game), rig)
    out.write_bytes(data)
    out.with_suffix(".bones.json").write_text(json.dumps({o[0]: o[5].tolist() for o in gm["objects"]}))
    tris = sum(len(o[6]) for o in gm["objects"])
    print(f"pdm_gm2glb: {out} ({len(gm['objects'])} objects, {tris} triangles, {len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
