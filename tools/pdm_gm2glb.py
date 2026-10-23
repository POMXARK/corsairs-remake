#!/usr/bin/env python3
"""A .gm of pdm-game/resource as a GLB: the low-poly original as the target of baking and the input of mesh refinement
(UltraShape and the like), docs/ai-models.md (ours).

One primitive per object of the .gm with its texture and UVs, positions as pdm_model_views.py draws them (the frame the
views of the model and pdm_glb2gm.py use), the bone of every vertex in a second file <out>.bones.json (list per
object), so the new geometry can be bound to the same skeleton later.

usage: pdm_gm2glb.py <game dir> <model> [--out data/ai_models/glb/<name>_orig.glb]
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


def build(gm, index):
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
            acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for name, tex, p, n, uv, bones, tris in gm["objects"]:
        if tex not in mat_of:
            img = load_texture(index, tex, cache)
            mat = {"name": tex or "none", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}
            if img is not None:
                buf = io.BytesIO()
                Image.fromarray((img[..., :3] * 255).astype(np.uint8)).save(buf, "PNG")
                images.append({"bufferView": add(buf.getvalue()), "mimeType": "image/png"})
                textures.append({"source": len(images) - 1})
                mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(textures) - 1}
            materials.append(mat)
            mat_of[tex] = len(materials) - 1
        meshes_prims.append({"attributes": {
            "POSITION": accessor(p.astype("<f4"), 5126, "VEC3", 34962, True),
            "NORMAL": accessor(n.astype("<f4"), 5126, "VEC3", 34962),
            "TEXCOORD_0": accessor(uv.astype("<f4"), 5126, "VEC2", 34962)},
            "indices": accessor(tris.astype("<u4").reshape(-1), 5125, "SCALAR", 34963),
            "material": mat_of[tex]})
    nodes = [{"mesh": i, "name": o[0]} for i, o in enumerate(gm["objects"])]
    doc = {"asset": {"version": "2.0", "generator": "pdm_gm2glb"}, "scene": 0,
           "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes,
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
    a = ap.parse_args()
    game = Path(a.game)
    gm = read_gm(find_model(game, a.model))
    out = Path(a.out) if a.out else game / "data" / "ai_models" / "glb" / f"{Path(a.model).name}_orig.glb"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build(gm, texture_index(game))
    out.write_bytes(data)
    out.with_suffix(".bones.json").write_text(json.dumps({o[0]: o[5].tolist() for o in gm["objects"]}))
    tris = sum(len(o[6]) for o in gm["objects"])
    print(f"pdm_gm2glb: {out} ({len(gm['objects'])} objects, {tris} triangles, {len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
