#!/usr/bin/env python3
"""Cuts the GLB of a neural network down to a game mesh before pdm_glb2gm.py (docs/ai-models.md, step 3.5, ours).

A generated mesh is dense (50-500 thousand triangles) and its UVs are scattered over many small charts. Per mesh:
- the vertices are welded by position and the degenerate triangles dropped;
- the quadric edge collapse (fast_simplification) cuts it to --faces triangles;
- the UVs are carried over from the original: every new triangle takes the UV chart of the original triangle under
  its centre, and its corners are put on that chart (the nearest points of the chart), so a seam does not
  smear the texture across the model;
- the vertices with the same position and UV are welded again, the base colour is cut to --tex pixels at most;
- the report: the faces and vertices before and after, the mean and the largest distance of the new surface from
  the old one (per cent of the diagonal), the mean colour change of the texture. More than 1-2 % of the
  diagonal or 10 colour levels is worth a look at the views (pdm_model_views.py) or a higher --faces.
A GLB with several meshes is cut mesh by mesh, every one with its own share of --faces and its own texture.

usage: pdm_glb_optimize.py <game dir> <name> [<name> ...] [--glb data/ai_models/glb] [--out data/ai_models/glb_opt]
                           [--faces 12000] [--tex 1024]
  then: pdm_glb2gm.py <game dir> <name> --glb <game dir>/data/ai_models/glb_opt
Needs numpy, Pillow, scipy, trimesh and fast-simplification (pip install --user trimesh fast-simplification).
"""
import argparse
import json
import struct
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

MAX_VERTICES = 65535
COMPONENTS = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path):
    """The triangles of a .glb in its scene: [(positions, normals or None, uvs or None, triangles, image)],
    the node transforms applied; image is the base colour (a texture, or its factor as one pixel)."""
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<3I", data)
    if magic != 0x46546C67:
        sys.exit(f"pdm_glb_optimize: {path} is not a binary glTF (.glb)")
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
            sys.exit(f"pdm_glb_optimize: {path}: the texture is a file of its own ({src.get('uri')}), save as .glb")
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
        sys.exit(f"pdm_glb_optimize: {path} has no triangles")
    return parts



def weld(pos, tris, digits=6):
    """Vertices with one position into one; the triangles that collapse go away."""
    scale = max(float(np.ptp(pos, axis=0).max()), 1e-9)
    key = np.round(pos / scale, digits)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    tris = inverse[tris]
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    return pos[first], tris[keep]


def charts(uv, tris):
    """The index of the UV chart of every triangle: triangles that share a vertex with one UV are one chart."""
    key = np.round(uv, 5)
    _, ids = np.unique(key, axis=0, return_inverse=True)
    ids = ids.reshape(-1)
    parent = np.arange(ids.max() + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in ids[tris]:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[rc] = ra
    return np.array([find(ids[t[0]]) for t in tris])


def uv_of(orig, tri_uv, points, tri_id):
    """UV at points lying (nearly) on the triangles tri_id of orig."""
    import trimesh
    bary = trimesh.triangles.points_to_barycentric(orig[tri_id], points)
    bary = np.clip(bary, 0, 1)
    bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-12)
    return np.einsum("ij,ijk->ik", bary, tri_uv[tri_id])


def optimize(pos, uv, tris, faces):
    import fast_simplification
    import trimesh

    tri_pos = pos[tris]                       # (F, 3, 3) original corners
    tri_uv = uv[tris] if uv is not None else None
    wpos, wtris = weld(pos, tris)
    target = min(faces, len(wtris))
    if len(wtris) > target:
        npos, ntris = fast_simplification.simplify(wpos.astype(np.float32), wtris.astype(np.int32),
                                                   target_reduction=1 - target / len(wtris))
        npos, ntris = npos.astype(np.float64), ntris.astype(np.int64)
    else:
        npos, ntris = wpos, wtris
    corners = npos[ntris]                     # (N, 3, 3)

    orig = trimesh.Trimesh(tri_pos.reshape(-1, 3), np.arange(len(tri_pos) * 3).reshape(-1, 3), process=False)
    centre = corners.mean(axis=1)
    _, _, centre_tri = trimesh.proximity.closest_point(orig, centre)

    out_uv = np.zeros((len(ntris), 3, 2))
    if tri_uv is not None:
        chart = charts(uv.astype(np.float64), tris)
        face_chart = chart[centre_tri]
        for c in np.unique(face_chart):
            sel = np.nonzero(face_chart == c)[0]
            members = np.nonzero(chart == c)[0]
            part = trimesh.Trimesh(tri_pos[members].reshape(-1, 3), np.arange(len(members) * 3).reshape(-1, 3),
                                   process=False)
            pts = corners[sel].reshape(-1, 3)
            close, _, tid = trimesh.proximity.closest_point(part, pts)
            got = uv_of(tri_pos[members], tri_uv[members], close, tid)
            out_uv[sel] = got.reshape(-1, 3, 2)

    # the way the new surface lies from the old one
    _, dist, _ = trimesh.proximity.closest_point(orig, npos)
    return corners, out_uv, tri_uv, centre_tri, dist, orig


def weld_corners(corners, uv):
    flat = np.concatenate([corners.reshape(-1, 3), uv.reshape(-1, 2)], axis=1)
    scale = max(float(np.ptp(corners.reshape(-1, 3), axis=0).max()), 1e-9)
    key = np.round(flat / np.array([scale] * 3 + [1.0] * 2), 6)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    return flat[first, :3], flat[first, 3:], inverse.reshape(-1, 3)


def color_change(image, corners, out_uv, orig, tri_uv, centre_tri):
    """Mean difference of the colour at the centres of the new triangles and at the point of the original under
    them, in levels of 0..255."""
    import trimesh
    if tri_uv is None:
        return 0.0
    tex = np.asarray(image.convert("RGB"), np.float64)
    h, w = tex.shape[:2]

    def at(u):
        x = np.clip((u[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
        y = np.clip((1 - (u[:, 1] % 1.0)) * (h - 1), 0, h - 1).astype(int)
        return tex[y, x]

    centre = corners.mean(axis=1)
    close, _, tid = trimesh.proximity.closest_point(orig, centre)
    old = uv_of(orig.triangles, tri_uv, close, tid)
    return float(np.abs(at(out_uv.mean(axis=1)) - at(old)).mean())


def write_glb(path: Path, parts):
    """parts: [(positions, uvs, triangles, PIL image)] as a glTF without normals; the engine side computes them."""
    blob = bytearray()
    views, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []

    def add(data: bytes, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    for i, (pos, uv, tris, image) in enumerate(parts):
        pos32 = pos.astype(np.float32)
        accessors.append({"bufferView": add(pos32.tobytes(), 34962), "componentType": 5126, "count": len(pos32),
                          "type": "VEC3", "min": pos32.min(axis=0).tolist(), "max": pos32.max(axis=0).tolist()})
        a_pos = len(accessors) - 1
        accessors.append({"bufferView": add(uv.astype(np.float32).tobytes(), 34962), "componentType": 5126,
                          "count": len(uv), "type": "VEC2"})
        a_uv = len(accessors) - 1
        accessors.append({"bufferView": add(tris.astype(np.uint16 if len(pos) <= MAX_VERTICES else np.uint32).tobytes(), 34963),
                          "componentType": 5123 if len(pos) <= MAX_VERTICES else 5125, "count": tris.size,
                          "type": "SCALAR"})
        a_idx = len(accessors) - 1
        png = BytesIO()
        image.save(png, "PNG")
        images.append({"bufferView": add(png.getvalue()), "mimeType": "image/png"})
        textures.append({"source": i})
        materials.append({"pbrMetallicRoughness": {"baseColorTexture": {"index": i}, "metallicFactor": 0.0}})
        meshes.append({"primitives": [{"attributes": {"POSITION": a_pos, "TEXCOORD_0": a_uv}, "indices": a_idx,
                                       "material": i}]})
        nodes.append({"mesh": i})
    doc = {"asset": {"version": "2.0", "generator": "pdm_glb_optimize.py"}, "scene": 0,
           "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": materials,
           "textures": textures, "images": images, "accessors": accessors, "bufferViews": views,
           "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<3I", 0x46546C67, 2, total) + struct.pack("<2I", len(js), 0x4E4F534A) + js +
                     struct.pack("<2I", len(blob), 0x004E4942) + bytes(blob))


def run(name, src: Path, dst: Path, faces, tex):
    parts = read_glb(src)
    total = sum(len(p[3]) for p in parts)
    out = []
    for n, (pos, _normal, uv, tris, image) in enumerate(parts):
        share = max(200, round(faces * len(tris) / total))
        corners, out_uv, tri_uv, centre_tri, dist, orig = optimize(pos, uv, tris, share)
        diag = float(np.linalg.norm(np.ptp(pos, axis=0)))
        vpos, vuv, vtris = weld_corners(corners, out_uv)
        if len(vpos) > MAX_VERTICES:
            sys.exit(f"pdm_glb_optimize: {name}: {len(vpos)} vertices, over {MAX_VERTICES}: lower --faces")
        if max(image.size) > tex:
            image = image.resize((max(1, round(image.width * tex / max(image.size))),
                                  max(1, round(image.height * tex / max(image.size)))), Image.LANCZOS)
        change = color_change(image, corners, out_uv, orig, tri_uv, centre_tri)
        print(f"{name}[{n}]: faces {len(tris)} -> {len(vtris)}, vertices {len(pos)} -> {len(vpos)}, "
              f"surface off by {100 * dist.mean() / diag:.2f} % (max {100 * dist.max() / diag:.2f} %) of the diagonal, "
              f"colour off by {change:.1f}/255, texture {image.width}x{image.height}")
        out.append((vpos, vuv, vtris, image))
    write_glb(dst, out)
    print(f"{name}: {dst}")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("names", nargs="+")
    ap.add_argument("--glb", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--faces", type=int, default=12000)
    ap.add_argument("--tex", type=int, default=1024)
    a = ap.parse_args()
    src_dir = a.glb or a.game / "data" / "ai_models" / "glb"
    dst_dir = a.out or a.game / "data" / "ai_models" / "glb_opt"
    for name in a.names:
        src = src_dir / f"{name}.glb"
        if not src.exists():
            sys.exit(f"pdm_glb_optimize: no {src}")
        run(name, src, dst_dir / f"{name}.glb", a.faces, a.tex)


if __name__ == "__main__":
    main()
