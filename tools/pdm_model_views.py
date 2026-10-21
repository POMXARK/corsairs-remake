#!/usr/bin/env python3
"""Pictures of a converted model from four sides, the input of image-to-3D in ComfyUI (docs/ai-models.md, ours).

Reads a .gm of pdm-game/resource (what pdm_world.py and pdm_character.py made of the original) with its
textures and draws it without perspective, as the multi-view models take it: front, right, back, left,
the model turned around its vertical axis by --yaw first. Each view is a square PNG, the model
FILL of it, centred, on a flat grey the background removal of the workflow takes away. A character
is drawn in the pose it is bound in, the one pdm_glb2gm.py binds the new model to the bones in.

usage: pdm_model_views.py <game dir> <model> [<model> ...] [--out data/ai_models/views] [--size 1024] [--yaw 0]
  <model>: a path under resource/models without .gm (characters/hero1), or a name found there (hero1)
"""
import argparse
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent / "engine" / "demos" / "common"))
from storm_formats import read_tx  # noqa: E402

VIEWS = (("front", 180), ("right", 90), ("back", 0), ("left", 270))  # a character faces -z
FILL = 0.85
BACKGROUND = (128, 128, 128)
SUPER = 2  # drawn this many times bigger, then scaled down: smooth edges
LIGHT = np.array((0.4, 0.7, -0.6))  # from the front, above and to the right, as seen by the camera


def read_gm(path: Path):
    """A .gm as {texture, triangles, objects, skinned, labels}: objects are (name, texture name or None,
    positions, normals, uvs, bones, triangles) as numpy arrays, positions as authored (a skinned model is
    stored mirrored in x, storm_formats.write_gm), the triangles indexing the object's own vertices."""
    data = path.read_bytes()
    off = 0

    def rd(fmt):
        nonlocal off
        vals = struct.unpack_from("<" + fmt, data, off)
        off += struct.calcsize("<" + fmt)
        return vals

    (_, flags, name_size, names, ntextures, nmaterials, nlights, nlabels, nobjects, ntriangles,
     nvrtbuffs) = rd("11i")
    rd("7f")
    strings = data[off:off + name_size]
    off += name_size

    def text(o):
        return strings[o:strings.index(b"\0", o)].decode("latin-1")

    rd(f"{names}i")
    textures = [text(o) for o in rd(f"{ntextures}i")]
    materials = []
    for _ in range(nmaterials):
        m = rd("2i4f4i4i")
        materials.append(textures[m[10]] if m[6] and m[10] >= 0 else None)
    if nlights:
        raise ValueError(f"{path}: lights are not read")
    off += nlabels * struct.calcsize("<3i16f4i4f")
    objects = []
    for _ in range(nobjects):
        o = rd("3i3ff6i8i4ii")
        objects.append((text(o[1]), o[7], o[8], o[9], o[10], o[11], o[12]))  # name, vb, ntri, stri, nv, sv, mtl
    tris = np.frombuffer(data, "<u2", ntriangles * 3, off).reshape(-1, 3).astype(np.int64)
    off += ntriangles * 6
    buffers = []
    for _ in range(nvrtbuffs):
        fmt, size = rd("2i")
        buffers.append((fmt, data[off:off + size]))
        off += size
    skinned = any(fmt for fmt, _ in buffers)
    out = []
    for name, vb, ntri, stri, nv, sv, mtl in objects:
        fmt, raw = buffers[vb]
        if fmt:
            v = np.frombuffer(raw, np.dtype([("p", "<3f4"), ("w", "<f4"), ("b", "<u4"), ("n", "<3f4"),
                                             ("c", "<u4"), ("uv", "<2f4")]))[sv:sv + nv]
            p, n = v["p"] * (-1, 1, 1), v["n"] * (-1, 1, 1)
            bones = (v["b"] & 255).astype(np.int64)
        else:
            v = np.frombuffer(raw, np.dtype([("p", "<3f4"), ("n", "<3f4"), ("c", "<u4"), ("uv", "<2f4")]))[sv:sv + nv]
            p, n, bones = v["p"], v["n"], np.zeros(nv, np.int64)
        out.append((name, materials[mtl], p.astype(np.float64), n.astype(np.float64), v["uv"].astype(np.float64),
                    bones, tris[stri:stri + ntri]))
    return {"objects": out, "skinned": skinned, "labels": nlabels, "bsp": bool(flags & 2)}


def find_model(game: Path, model: str) -> Path:
    models = game / "resource" / "models"
    path = models / f"{model}.gm"
    if path.exists():
        return path
    found = sorted(models.rglob(f"{Path(model).name}.gm"))
    if not found:
        sys.exit(f"pdm_model_views: no {model}.gm under {models}")
    return found[0]


def texture_index(game: Path) -> dict:
    """<name>.tga -> the .tx of resource/textures with that name, any folder (lower case)."""
    return {p.name[:-3].lower(): p for p in (game / "resource" / "textures").rglob("*.tx")}


def texture_of(index: dict, name):
    """The .tx of a texture name of a .gm, which may carry the folder (ships\\brig\\shn_reya.tga)."""
    return index.get((name or "").replace("\\", "/").rsplit("/", 1)[-1].lower())


def load_texture(index: dict, name, cache: dict):
    if name not in cache:
        tx = texture_of(index, name)
        cache[name] = np.asarray(read_tx(tx), np.float64) / 255 if tx else None
    return cache[name]


def render(gm, textures: dict, yaw: float, size: int, cache: dict) -> Image.Image:
    """The model turned by yaw degrees, seen along +z (the camera behind it at -z), y up, no perspective."""
    big = size * SUPER
    a = math.radians(yaw)
    turn = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    every = np.concatenate([o[2] for o in gm["objects"]]) @ turn.T
    lo, hi = every.min(0), every.max(0)
    scale = FILL * big / max(hi[0] - lo[0], hi[1] - lo[1])
    centre = (lo + hi) / 2
    colour = np.empty((big, big, 3))
    colour[:] = np.array(BACKGROUND) / 255
    depth = np.full((big, big), np.inf)
    light = LIGHT / np.linalg.norm(LIGHT)
    for _, tex_name, pos, normal, uv, _, tris in gm["objects"]:
        tex = load_texture(textures, tex_name, cache)
        p = (pos @ turn.T - centre) * scale
        sx, sy, sz = p[:, 0] + big / 2, big / 2 - p[:, 1], p[:, 2]
        shade = 0.45 + 0.55 * np.clip(np.abs((normal @ turn.T) @ light), 0, 1)
        for t in tris:
            xs, ys = sx[t], sy[t]
            x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, big - 1)
            y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, big - 1)
            if x0 > x1 or y0 > y1:
                continue
            d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
            if abs(d) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (gy - ys[0])) / d
            w2 = ((xs[1] - xs[0]) * (gy - ys[0]) - (gx - xs[0]) * (ys[1] - ys[0])) / d
            w0 = 1 - w1 - w2
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            z = w0 * sz[t[0]] + w1 * sz[t[1]] + w2 * sz[t[2]]
            win = depth[y0:y1 + 1, x0:x1 + 1]
            near = inside & (z < win)
            if not near.any():
                continue
            win[near] = z[near]
            if tex is None:
                c = np.full((near.sum(), 3), 0.8)
            else:
                u = w0[near] * uv[t[0], 0] + w1[near] * uv[t[1], 0] + w2[near] * uv[t[2], 0]
                v = w0[near] * uv[t[0], 1] + w1[near] * uv[t[1], 1] + w2[near] * uv[t[2], 1]
                h, w = tex.shape[:2]
                c = tex[(np.mod(v, 1) * h).astype(int) % h, (np.mod(u, 1) * w).astype(int) % w, :3]
            s = w0[near] * shade[t[0]] + w1[near] * shade[t[1]] + w2[near] * shade[t[2]]
            colour[y0:y1 + 1, x0:x1 + 1][near] = c * s[:, None]
    image = Image.fromarray((np.clip(colour, 0, 1) * 255).astype(np.uint8))
    return image.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--yaw", type=float, default=0.0, help="degrees: turns the model so that its face is the front")
    a = ap.parse_args()
    out = a.out or a.game / "data" / "ai_models" / "views"
    out.mkdir(parents=True, exist_ok=True)
    textures, cache = texture_index(a.game), {}
    for model in a.models:
        path = find_model(a.game, model)
        gm = read_gm(path)
        missing = sorted({o[1] for o in gm["objects"] if o[1] and not texture_of(textures, o[1])})
        for view, angle in VIEWS:
            render(gm, textures, a.yaw + angle, a.size, cache).save(out / f"{path.stem}_{view}.png")
        note = f", no texture {' '.join(missing)}" if missing else ""
        print(f"{path.relative_to(a.game / 'resource' / 'models')}: {sum(len(o[6]) for o in gm['objects'])} "
              f"triangles, {'skinned' if gm['skinned'] else 'static'}{note} -> {out}/{path.stem}_*.png")


if __name__ == "__main__":
    main()
