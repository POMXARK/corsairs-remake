#!/usr/bin/env python3
"""Puts a GLB of comfy_model_batch.py into the game in place of the model it was made from (docs/ai-models.md, ours).

The new mesh takes the place of the old one in resource/models:
- glTF is right-handed with the front along +z, the engine left-handed with a character looking along -z:
  z is negated, the triangles face along their normals (storm_formats.Mesh.triangle);
- it is scaled to the height of the original and stood where it stood: the bottom on its bottom, the
  middle over its middle; of the four turns about the vertical the one nearest the original is taken
  (the mean distance of the points of one to the other, printed in cm);
- a character (a skinned .gm) keeps the skeleton and the animation of the original: every new vertex is
  carried by the bone of the nearest vertex of the original, in the pose pdm_model_views.py drew;
- the base colour becomes textures/<the folder of the original's>/ai_<name>.tga.tx, --tex pixels at most.
The original .gm is kept in data/ai_models/orig/ once and is what every run fits to, so a run repeats
whatever was written before; --restore puts it back. A model with locators (a ship part with its ropes
and sails, a location) is left alone: they belong to the old geometry.

usage: pdm_glb2gm.py <game dir> <name> [<name> ...] [--glb data/ai_models/glb] [--tex 1024] [--restore]
  <name>: the stem the views and the GLB have (hero1), the model is found under resource/models
"""
import argparse
import json
import math
import shutil
import struct
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "engine" / "demos" / "common"))
from pdm_model_views import find_model, read_gm, texture_index, texture_of  # noqa: E402
from storm_formats import Mesh, write_gm, write_tx  # noqa: E402

SAMPLE = 3000  # points of each model compared to find the turn
CHUNK = 2048
COMPONENTS = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path):
    """The triangles of a .glb in its scene: [(positions, normals or None, uvs or None, triangles, image)],
    the node transforms applied; image is the base colour (a texture, or its factor as one pixel)."""
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<3I", data)
    if magic != 0x46546C67:
        sys.exit(f"pdm_glb2gm: {path} is not a binary glTF (.glb)")
    off, doc, blob = 12, None, b""
    while off < len(data):
        size, kind = struct.unpack_from("<2I", data, off)
        chunk = data[off + 8:off + 8 + size]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            blob = chunk
        off += 8 + size

    def view(i):
        v = doc["bufferViews"][i]
        return blob[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]], v.get("byteStride")

    def accessor(i):
        a = doc["accessors"][i]
        raw, stride = view(a["bufferView"])
        dtype, width = np.dtype(COMPONENTS[a["componentType"]]), WIDTH[a["type"]]
        start, item = a.get("byteOffset", 0), dtype.itemsize * width
        stride = stride or item
        rows = np.frombuffer(raw, np.uint8, a["count"] * stride - (stride - item), start)
        rows = np.lib.stride_tricks.as_strided(rows, (a["count"], item), (stride, 1))
        out = np.frombuffer(rows.copy().tobytes(), dtype).reshape(a["count"], width).astype(np.float64)
        if a.get("normalized") and dtype.kind in "iu":
            out /= np.iinfo(dtype).max
        return out

    def image(material):
        pbr = doc.get("materials", [{}])[material].get("pbrMetallicRoughness", {}) if material is not None else {}
        tex = pbr.get("baseColorTexture")
        if tex is not None:
            src = doc["images"][doc["textures"][tex["index"]]["source"]]
            if "bufferView" in src:
                return Image.open(BytesIO(view(src["bufferView"])[0])).convert("RGBA")
            sys.exit(f"pdm_glb2gm: {path}: the texture is a file of its own ({src.get('uri')}), save as .glb")
        factor = pbr.get("baseColorFactor", (0.8, 0.8, 0.8, 1.0))
        return Image.new("RGBA", (4, 4), tuple(round(c * 255) for c in factor))

    def matrix(node):
        if "matrix" in node:
            return np.array(node["matrix"]).reshape(4, 4).T
        x, y, z, w = node.get("rotation", (0, 0, 0, 1))
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        m = np.eye(4)
        m[:3, :3] = r * np.array(node.get("scale", (1, 1, 1)))
        m[:3, 3] = node.get("translation", (0, 0, 0))
        return m

    parts = []

    def walk(n, parent):
        node = doc["nodes"][n]
        m = parent @ matrix(node)
        for prim in doc["meshes"][node["mesh"]]["primitives"] if "mesh" in node else ():
            if prim.get("mode", 4) != 4:
                continue
            at = prim["attributes"]
            pos = accessor(at["POSITION"]) @ m[:3, :3].T + m[:3, 3]
            normal = accessor(at["NORMAL"]) @ np.linalg.inv(m[:3, :3]) if "NORMAL" in at else None
            uv = accessor(at["TEXCOORD_0"]) if "TEXCOORD_0" in at else None
            tris = (accessor(prim["indices"]).astype(np.int64).reshape(-1, 3) if "indices" in prim
                    else np.arange(len(pos)).reshape(-1, 3))
            parts.append((pos, normal, uv, tris, image(prim.get("material"))))
        for c in node.get("children", ()):
            walk(c, m)

    scene = doc["scenes"][doc.get("scene", 0)] if doc.get("scenes") else {"nodes": range(len(doc["nodes"]))}
    for n in scene["nodes"]:
        walk(n, np.eye(4))
    if not parts:
        sys.exit(f"pdm_glb2gm: {path} has no triangles")
    return parts


def vertex_normals(pos, tris):
    n = np.zeros_like(pos)
    face = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    for k in range(3):
        np.add.at(n, tris[:, k], face)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def nearest(points, to):
    """For every point the index of the nearest of `to`, and the distance."""
    idx, dist = np.empty(len(points), np.int64), np.empty(len(points))
    for s in range(0, len(points), CHUNK):
        d = ((points[s:s + CHUNK, None, :] - to[None, :, :]) ** 2).sum(-1)
        idx[s:s + CHUNK] = d.argmin(1)
        dist[s:s + CHUNK] = np.sqrt(d[np.arange(len(d)), idx[s:s + CHUNK]])
    return idx, dist


def turn(yaw):
    a = math.radians(yaw)
    return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])


def fit(points, ref):
    """Scale and shift that stand points where ref stands: the same height, bottom and middle."""
    lo, hi, rlo, rhi = points.min(0), points.max(0), ref.min(0), ref.max(0)
    k = (rhi[1] - rlo[1]) / max(hi[1] - lo[1], 1e-9)
    shift = (rlo + rhi) / 2 - k * (lo + hi) / 2
    shift[1] = rlo[1] - k * lo[1]
    return k, shift


def sample(points, n):
    return points[np.linspace(0, len(points) - 1, min(n, len(points))).astype(np.int64)]


def convert(game: Path, name: str, glb: Path, tex_size: int):
    model = find_model(game, name)
    rel = model.relative_to(game / "resource" / "models")
    orig = game / "data" / "ai_models" / "orig" / rel
    ref = read_gm(orig if orig.exists() else model)
    if ref["labels"]:
        return f"{rel}: has locators (ropes, sails, places), left alone"
    if not orig.exists():
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model, orig)
    ref_pos = np.concatenate([o[2] for o in ref["objects"]])
    ref_bone = np.concatenate([o[5] for o in ref["objects"]])

    flip = np.array((1.0, 1.0, -1.0))
    # the normals before z is negated: a mirror turns the faces inside out
    parts = [(p * flip, (vertex_normals(p, t) if n is None else n) * flip, uv, t, im)
             for p, n, uv, t, im in read_glb(glb)]
    every = np.concatenate([p for p, *_ in parts])
    best = None
    for yaw in (0, 90, 180, 270):
        pts = every @ turn(yaw).T
        k, shift = fit(pts, ref_pos)
        a, b = sample(pts * k + shift, SAMPLE), sample(ref_pos, SAMPLE)
        err = (nearest(a, b)[1].mean() + nearest(b, a)[1].mean()) / 2
        if best is None or err < best[0]:
            best = (err, yaw, k, shift)
    err, yaw, k, shift = best

    textures = texture_index(game)
    first = next((texture_of(textures, o[1]) for o in ref["objects"] if texture_of(textures, o[1])), None)
    tex_dir = first.parent if first else game / "resource" / "textures" / "characters"
    prefix = next((o[1].replace("/", "\\").rsplit("\\", 1)[0] + "\\" for o in ref["objects"]
                   if o[1] and ("\\" in o[1] or "/" in o[1])), "")
    meshes, total = [], 0
    for i, (pos, normal, uv, tris, image) in enumerate(parts):
        pos = pos @ turn(yaw).T * k + shift
        normal = normal @ turn(yaw).T
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
        uv = np.zeros((len(pos), 2)) if uv is None else uv
        bones = ref_bone[nearest(pos, ref_pos)[0]] if ref["skinned"] else np.zeros(len(pos), np.int64)
        stem = f"ai_{name}" + (f"_{i}" if len(parts) > 1 else "")
        side = 1 << max(2, min(int(math.log2(max(image.size))), int(math.log2(tex_size))))
        write_tx(image.resize((side, side), Image.LANCZOS), tex_dir / f"{stem}.tga.tx")
        m = Mesh(stem, f"{prefix}{stem}.tga")
        for p, n, t, b in zip(pos, normal, uv, bones):
            m.vertex(tuple(map(float, p)), tuple(map(float, n)), tuple(map(float, t)), int(b))
        for a, b, c in tris:
            m.triangle(int(a), int(b), int(c))
        total += len(pos)
        if len(pos) > 65536:
            sys.exit(f"pdm_glb2gm: {glb}: {len(pos)} vertices, a .gm object holds 65536: lower --faces")
        meshes.append(m)
    if ref["skinned"] and total > 65536:
        sys.exit(f"pdm_glb2gm: {glb}: {total} vertices, a skinned .gm holds 65536: lower --faces")
    write_gm(meshes, model, skinned=ref["skinned"], bsp=ref["bsp"])
    faces = sum(len(m.triangles) for m in meshes)
    return (f"{rel}: {faces} faces (was {sum(len(o[6]) for o in ref['objects'])}), turned {yaw}, "
            f"scaled {k:.3f}, off the original by {err * 100:.1f} cm on average"
            + (f", {len(set(ref_bone.tolist()))} bones" if ref["skinned"] else ""))


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("names", nargs="+")
    ap.add_argument("--glb", type=Path)
    ap.add_argument("--tex", type=int, default=1024)
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    glbs = a.glb or a.game / "data" / "ai_models" / "glb"
    for name in a.names:
        if a.restore:
            model = find_model(a.game, name)
            rel = model.relative_to(a.game / "resource" / "models")
            orig = a.game / "data" / "ai_models" / "orig" / rel
            if orig.exists():
                shutil.copy2(orig, model)
                print(f"{rel}: the original is back")
            continue
        glb = glbs / f"{name}.glb"
        if not glb.exists():
            sys.exit(f"pdm_glb2gm: no {glb} (comfy_model_batch.py)")
        print(convert(a.game, name, glb, a.tex), flush=True)


if __name__ == "__main__":
    main()
