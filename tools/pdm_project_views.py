#!/usr/bin/env python3
"""Paint the base colour texture of a generated .glb from the four views it was generated from.

The Pixal3D/TRELLIS.2 texture is generated per voxel and smears small details (eyes, eyebrows, lips). The views
(front, left, back, right, orthographic, cropped to the figure) are sharp and the mesh is built to match them, so every
texel is projected into the views and coloured from the view that faces it; where no view sees the texel the generated
colour stays. Usage: pdm_project_views.py in.glb out.glb front.png left.png back.png right.png
Needs numpy and Pillow only."""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

NAMES = ("front", "left", "back", "right")


def read_glb(path):
    d = open(path, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]
    return json.loads(d[20:20 + jl]), d[28 + jl:]


def write_glb(path, j, b):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    b += b"\0" * (-len(b) % 4)
    open(path, "wb").write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(b)) + struct.pack("<II", len(js), 0x4E4F534A)
                           + js + struct.pack("<II", len(b), 0x004E4942) + b)


def accessor(j, b, i):
    a = j["accessors"][i]
    v = j["bufferViews"][a["bufferView"]]
    n = {"VEC3": 3, "VEC2": 2, "SCALAR": 1, "VEC4": 4}[a["type"]]
    dt = {5126: "<f4", 5125: "<u4", 5123: "<u2"}[a["componentType"]]
    return np.frombuffer(b, dt, a["count"] * n, v.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, n)


def load_view(path):
    f = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    f[..., 1] = np.minimum(f[..., 1], np.maximum(f[..., 0], f[..., 2]))  # green background spill
    ys, xs = np.where(f.max(2) > 8)
    return f, (xs.min(), xs.max(), ys.min(), ys.max())


def project(positions, name, view, lo, hi):
    _, (x0, x1, y0, y1) = view
    y = y1 - (positions[:, 1] - lo[1]) / (hi[1] - lo[1]) * (y1 - y0)
    if name == "front":
        t = (positions[:, 0] - lo[0]) / (hi[0] - lo[0])
    elif name == "back":
        t = (hi[0] - positions[:, 0]) / (hi[0] - lo[0])
    elif name == "left":  # the face is on the left of the image
        t = (hi[2] - positions[:, 2]) / (hi[2] - lo[2])
    else:
        t = (positions[:, 2] - lo[2]) / (hi[2] - lo[2])
    return x0 + t * (x1 - x0), y


def paint(P, UV, tris, atlas, views, side, step=1):
    """Colours of the texels covered by the triangles, summed over the views: (sum of w*colour, sum of w)."""
    size = atlas.shape[0]
    lo, hi = P.min(0), P.max(0)
    dirs = {"front": (0, 0, 1.), "back": (0, 0, -1.), "left": (side, 0, 0.), "right": (-side, 0, 0.)}
    acc = np.zeros_like(atlas)
    wsum = np.zeros(atlas.shape[:2], np.float32)
    for f in tris[::step]:
        pp = P[f]
        nrm = np.cross(pp[1] - pp[0], pp[2] - pp[0])
        ln = np.linalg.norm(nrm)
        if ln < 1e-12:
            continue
        nrm /= ln
        uv = UV[f] * size
        a = np.floor(uv.min(0)).astype(int)
        e = np.ceil(uv.max(0)).astype(int)
        if (e - a).max() > 200:
            continue
        d = (uv[1, 1] - uv[2, 1]) * (uv[0, 0] - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (uv[0, 1] - uv[2, 1])
        if abs(d) < 1e-9:
            continue
        X, Y = np.meshgrid(np.arange(a[0], e[0] + 1), np.arange(a[1], e[1] + 1))
        l0 = ((uv[1, 1] - uv[2, 1]) * (X + .5 - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (Y + .5 - uv[2, 1])) / d
        l1 = ((uv[2, 1] - uv[0, 1]) * (X + .5 - uv[2, 0]) + (uv[0, 0] - uv[2, 0]) * (Y + .5 - uv[2, 1])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not ok.any():
            continue
        ax, ay = X[ok], Y[ok]
        for name, dv in dirs.items():
            lim = 0.1 if name in ("front", "back") else 0.35  # the side views smear the nose, give them less
            w = np.clip((nrm @ np.array(dv) - lim) / 0.5, 0, 1) ** 2
            if w <= 0:
                continue
            px, py = project(pp, name, views[name], lo, hi)
            sx = (l0 * px[0] + l1 * px[1] + l2 * px[2])[ok]
            sy = (l0 * py[0] + l1 * py[1] + l2 * py[2])[ok]
            img = views[name][0]
            c = img[np.clip(sy.astype(int), 0, img.shape[0] - 1), np.clip(sx.astype(int), 0, img.shape[1] - 1)]
            acc[ay, ax] += c * w
            wsum[ay, ax] += w
    return acc, wsum


def main():
    src, dst = sys.argv[1:3]
    views = {n: load_view(p) for n, p in zip(NAMES, sys.argv[3:7])}
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P = accessor(j, b, prim["attributes"]["POSITION"])
    UV = accessor(j, b, prim["attributes"]["TEXCOORD_0"])
    tris = accessor(j, b, prim["indices"]).reshape(-1, 3)
    mat = j["materials"][prim.get("material", 0)]
    tex = j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    bv = j["bufferViews"][j["images"][tex["source"]]["bufferView"]]
    atlas = np.asarray(Image.open(io.BytesIO(b[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB")).astype(np.float32)
    # which side of the mesh the "left" view looks at: the sign with the smaller difference to the generated colour
    best = None
    for side in (1., -1.):
        acc, w = paint(P, UV, tris, atlas, views, side, step=12)
        m = w > 0.3
        err = np.abs(acc[m] / w[m][:, None] - atlas[m]).mean() if m.any() else 1e9
        print(f"left view sees {'+' if side > 0 else '-'}x: difference {err:.2f}")
        if best is None or err < best[0]:
            best = (err, side)
    acc, w = paint(P, UV, tris, atlas, views, best[1])
    a = np.clip(w * 3, 0, 1)[..., None]  # follow the views: they win wherever one of them sees the texel
    out = atlas * (1 - a) + acc / np.maximum(w, 1e-6)[..., None] * a
    buf = io.BytesIO()
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(buf, format="PNG")
    b = b + b"\0" * (-len(b) % 4)
    bv["byteOffset"], bv["byteLength"] = len(b), len(buf.getvalue())
    b += buf.getvalue()
    j["buffers"][0]["byteLength"] = len(b) + (-len(b) % 4)
    write_glb(dst, j, b)
    print(f"{dst}: texture painted from the views, {int((w > 0).mean() * 100)} % of the texels")


if __name__ == "__main__":
    main()
