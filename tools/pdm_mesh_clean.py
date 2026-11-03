#!/usr/bin/env python3
"""Clean the generated mesh and unwrap it anew: <src.glb> <dst.glb> [--tex 4096] [--cost 8].

TRELLIS meshes come with shards (non-manifold edges, flaps, loose pieces) and an atlas of thousands of tiny charts. The projection
of the views (pdm_project_views.py) paints the clean mesh better: merge close vertices, drop duplicate faces, repair the
non-manifold edges and vertices, keep the biggest piece, orient the faces, unwrap with xatlas. The generated colour is carried to the
new atlas by the nearest surface point of the old mesh (the projection needs it to align the views).
pip: pymeshlab xatlas trimesh scipy Pillow."""
import io
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from pdm_project_views import accessor, read_glb  # noqa: E402

TEX = 4096
COST = 8.0  # xatlas chart cost: the higher, the bigger the charts (default 2)
SAMPLES = 4_000_000


def clean(P, T):
    import pymeshlab as ml
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(P.astype(np.float64), T.astype(np.int32)))
    ms.meshing_merge_close_vertices(threshold=ml.PercentageValue(0.0005))
    ms.meshing_remove_duplicate_faces()
    ms.meshing_repair_non_manifold_edges(method=0)
    ms.meshing_repair_non_manifold_vertices()
    ms.meshing_remove_connected_component_by_face_number(mincomponentsize=200)
    ms.meshing_re_orient_faces_coherently()
    m = ms.current_mesh()
    return m.vertex_matrix().astype(np.float32), m.face_matrix().astype(np.uint32)


def unwrap(P, T, tex, cost):
    import xatlas
    atlas = xatlas.Atlas()
    atlas.add_mesh(P, T)
    co = xatlas.ChartOptions()
    co.max_cost = cost
    po = xatlas.PackOptions()
    po.resolution = tex
    po.padding = 4
    po.bruteForce = False
    atlas.generate(co, po)
    vmap, idx, uv = atlas[0]
    return vmap, idx.reshape(-1, 3), uv.astype(np.float32), atlas.chart_count


def carry_colour(P0, UV0, T0, atlas0, P, UV, T, size):
    """New atlas (size²) painted with the colour of the nearest point of the old surface."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(0)
    a, b, c = P0[T0[:, 0]], P0[T0[:, 1]], P0[T0[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    f = rng.choice(len(T0), SAMPLES, p=area / area.sum())
    r1, r2 = np.sqrt(rng.random(SAMPLES)), rng.random(SAMPLES)
    w0, w1, w2 = (1 - r1)[:, None], (r1 * (1 - r2))[:, None], (r1 * r2)[:, None]
    pts = w0 * a[f] + w1 * b[f] + w2 * c[f]
    uv = w0 * UV0[T0[f, 0]] + w1 * UV0[T0[f, 1]] + w2 * UV0[T0[f, 2]]
    h = atlas0.shape[0]
    col = atlas0[np.clip((uv[:, 1] * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * h).astype(int), 0, h - 1)]
    tree = cKDTree(pts)
    out = np.zeros((size, size, 3), np.uint8)
    for f in T:
        uvf = UV[f] * size
        lo = np.floor(uvf.min(0)).astype(int)
        hi = np.ceil(uvf.max(0)).astype(int)
        X, Y = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        d = (uvf[1, 1] - uvf[2, 1]) * (uvf[0, 0] - uvf[2, 0]) + (uvf[2, 0] - uvf[1, 0]) * (uvf[0, 1] - uvf[2, 1])
        if abs(d) < 1e-9:
            continue
        l0 = ((uvf[1, 1] - uvf[2, 1]) * (X + .5 - uvf[2, 0]) + (uvf[2, 0] - uvf[1, 0]) * (Y + .5 - uvf[2, 1])) / d
        l1 = ((uvf[2, 1] - uvf[0, 1]) * (X + .5 - uvf[2, 0]) + (uvf[0, 0] - uvf[2, 0]) * (Y + .5 - uvf[2, 1])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not ok.any():
            continue
        pp = P[f]
        pos = l0[ok][:, None] * pp[0] + l1[ok][:, None] * pp[1] + l2[ok][:, None] * pp[2]
        _, k = tree.query(pos)
        out[np.clip(Y[ok], 0, size - 1), np.clip(X[ok], 0, size - 1)] = col[k]
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src, dst = args[:2]
    tex = int(sys.argv[sys.argv.index("--tex") + 1]) if "--tex" in sys.argv else TEX
    cost = float(sys.argv[sys.argv.index("--cost") + 1]) if "--cost" in sys.argv else COST
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P0 = accessor(j, b, prim["attributes"]["POSITION"]).astype(np.float64)
    UV0 = accessor(j, b, prim["attributes"]["TEXCOORD_0"])
    T0 = accessor(j, b, prim["indices"]).reshape(-1, 3)
    mat = j["materials"][prim.get("material", 0)]
    bv = j["bufferViews"][j["images"][j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]["bufferView"]]
    atlas0 = np.asarray(Image.open(io.BytesIO(b[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB"))
    P, T = clean(P0, T0)
    print(f"cleaned: {len(T0)} -> {len(T)} faces")
    vmap, idx, uv, charts = unwrap(P, T, tex, cost)
    print(f"unwrapped: {charts} charts (was 6444 pieces)")
    Pn = P[vmap]
    colour = carry_colour(P0, UV0, T0, atlas0, Pn, uv, idx, tex)
    import trimesh
    from trimesh.visual import TextureVisuals
    from trimesh.visual.material import PBRMaterial
    uvg = uv.copy()
    uvg[:, 1] = 1 - uvg[:, 1]  # trimesh keeps v upwards and flips it into the glTF convention on export
    mesh = trimesh.Trimesh(Pn, idx, process=False)
    mesh.visual = TextureVisuals(uv=uvg, material=PBRMaterial(baseColorTexture=Image.fromarray(colour)))
    mesh.export(dst)
    print(f"{dst} written")


if __name__ == "__main__":
    main()
