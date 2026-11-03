#!/usr/bin/env python3
"""UV atlas made of the views themselves: <src.glb> <dst.glb> <front> <left> <back> <right> [--tex 4096].

Automatic unwrapping cuts a generated head into thousands of charts. Here every face goes to the view that sees it best
(smoothed normal facing the view, nothing in front of it in the z-buffer) and takes the picture coordinates of that view
as its texture coordinates: one chart per view, plus a few charts (planar, one per axis side) for faces no view sees (under the chin, top of
the head). Cells of the atlas: 3 x 2, the views are 1 cell each, the rest gets the last two. The colour of the source
atlas is carried to the new one (pdm_mesh_clean.carry_colour) so pdm_project_views.py can align the views to the mesh.
pip: trimesh scipy Pillow."""
import io
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from pdm_mesh_clean import carry_colour  # noqa: E402
from pdm_project_views import (NAMES, accessor, load_view, project, read_glb, smooth_normals,  # noqa: E402
                               smooth_positions)

TEX = 4096
MIN_FACING = 0.15  # n . direction to the viewer below which a face is edge-on to the view
REACH = 0.02  # share of the model size: a face deeper than this behind the z-buffer is hidden
RES = 2048


def face_depth_ids(P, tris, name, dv, view, lo, hi):
    px, py = project(P, name, view, lo, hi)
    px, py = px / view[0].shape[1] * RES, py / view[0].shape[0] * RES
    depth = P @ np.array(dv)
    buf = np.full((RES, RES), -1e9, np.float32)
    ids = np.full((RES, RES), -1, np.int32)
    for fi, f in enumerate(tris):
        x, y, z = px[f], py[f], depth[f]
        a = np.maximum(np.floor([x.min(), y.min()]).astype(int), 0)
        e = np.minimum(np.ceil([x.max(), y.max()]).astype(int), RES - 1)
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(d) < 1e-9 or (e - a).max() > 300:
            continue
        X, Y = np.meshgrid(np.arange(a[0], e[0] + 1), np.arange(a[1], e[1] + 1))
        l0 = ((y[1] - y[2]) * (X + .5 - x[2]) + (x[2] - x[1]) * (Y + .5 - y[2])) / d
        l1 = ((y[2] - y[0]) * (X + .5 - x[2]) + (x[0] - x[2]) * (Y + .5 - y[2])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if ok.any():
            xs, ys, zz = X[ok], Y[ok], (l0 * z[0] + l1 * z[1] + l2 * z[2])[ok]
            win = zz > buf[ys, xs]
            buf[ys[win], xs[win]] = zz[win]
            ids[ys[win], xs[win]] = fi
    return buf, ids


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src, dst = args[:2]
    tex = int(sys.argv[sys.argv.index("--tex") + 1]) if "--tex" in sys.argv else TEX
    views = {n: load_view(p) for n, p in zip(NAMES, args[2:6])}
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P0 = accessor(j, b, prim["attributes"]["POSITION"])
    UV0 = accessor(j, b, prim["attributes"]["TEXCOORD_0"])
    T0 = accessor(j, b, prim["indices"]).reshape(-1, 3)
    mat = j["materials"][prim.get("material", 0)]
    bv = j["bufferViews"][j["images"][j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]["bufferView"]]
    atlas0 = np.asarray(Image.open(io.BytesIO(b[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB"))
    P = smooth_positions(P0, T0)
    lo, hi = P.min(0), P.max(0)
    reach = REACH * float((hi - lo).max())
    sn = smooth_normals(P, T0)
    # which side the "left" view looks at is not known here: try both and keep the one that leaves fewer faces without a view
    best = None
    for side in (1., -1.):
        dirs = {"front": (0, 0, 1.), "back": (0, 0, -1.), "left": (side, 0, 0.), "right": (-side, 0, 0.)}
        score = np.full((len(T0), 4), -1.0, np.float32)
        for k, n in enumerate(NAMES):
            buf, ids = face_depth_ids(P, T0, n, dirs[n], views[n], lo, hi)
            vis = np.zeros(len(T0), bool)
            vis[np.unique(ids[ids >= 0])] = True
            facing = sn @ np.array(dirs[n])
            ok = vis & (facing > MIN_FACING)
            score[ok, k] = facing[ok]
        seen = (score > 0).any(1).sum()
        print(f"left view sees {'+' if side > 0 else '-'}x: {seen} of {len(T0)} faces seen")
        if best is None or seen > best[0]:
            best = (seen, side, score)
    _, side, score = best
    owner = np.where((score > 0).any(1), score.argmax(1), 4)
    print("faces per chart:", {(*NAMES, "rest")[k]: int((owner == k).sum()) for k in range(5)})
    cw, ch = tex // 3, tex // 2
    UV = np.zeros((len(T0), 3, 2), np.float32)
    for k, n in enumerate(NAMES):
        sel = owner == k
        if not sel.any():
            continue
        _, (x0, x1, y0, y1), _ = views[n]
        W, H = views[n][0].shape[1], views[n][0].shape[0]
        px, py = project(P, n, views[n], lo, hi)
        s = min((cw - 8) / (x1 - x0 + 1), (ch - 8) / (y1 - y0 + 1))  # texels per picture pixel, the picture keeps its shape
        cx, cy = (k % 3) * cw + 4, (k // 3) * ch + 4
        u = (cx + (px - x0) * s) / tex
        v = (cy + (py - y0) * s) / tex
        UV[sel] = np.stack([u, v], -1)[T0[sel]]
    rest = owner == 4
    if rest.any():
        # faces no view sees (inside the mesh, under the chin, top of the head): one planar chart per axis side; they may overlap,
        # what they show is hidden or painted from the nearest faces
        ax = np.abs(sn).argmax(1)
        side6 = ax * 2 + (np.take_along_axis(sn, ax[:, None], 1)[:, 0] < 0)
        ext = hi - lo
        w6, h6 = (tex - cw) // 3, ch // 2  # cells 1..2 of the lower row, three by two
        for q in range(6):
            sel = rest & (side6 == q)
            if not sel.any():
                continue
            a_ = q // 2
            u_ax, v_ax = [(2, 1), (0, 2), (0, 1)][a_]
            s_ = min((w6 - 8) / ext[u_ax], (h6 - 8) / ext[v_ax])
            cx, cy = cw + (q % 3) * w6 + 4, ch + (q // 3) * h6 + 4
            u = (cx + (P[:, u_ax] - lo[u_ax]) * s_) / tex
            v = (cy + (hi[v_ax] - P[:, v_ax]) * s_) / tex
            UV[sel] = np.stack([u, v], -1)[T0[sel]]
        owner = np.where(rest, 4 + side6, owner)
        print("rest charts:", len(set(side6[rest].tolist())))
    # weld: a vertex is shared by the faces of one chart
    key = T0 * 16 + owner[:, None]
    uk, inv = np.unique(key.reshape(-1), return_inverse=True)
    Pn = P[uk // 16]
    Tn = inv.reshape(-1, 3).astype(np.uint32)
    UVn = np.zeros((len(uk), 2), np.float32)
    UVn[inv] = UV.reshape(-1, 2)
    print(f"charts: {len(set(owner.tolist()))} (views and rest), vertices {len(P)} -> {len(uk)}")
    colour = carry_colour(P0, UV0, T0, atlas0, Pn, UVn, Tn, tex)
    import trimesh
    from trimesh.visual import TextureVisuals
    from trimesh.visual.material import PBRMaterial
    uvg = UVn.copy()
    uvg[:, 1] = 1 - uvg[:, 1]
    mesh = trimesh.Trimesh(Pn, Tn, process=False)
    mesh.visual = TextureVisuals(uv=uvg, material=PBRMaterial(baseColorTexture=Image.fromarray(colour)))
    mesh.export(dst)
    print(f"{dst} written, left view side {side}")


if __name__ == "__main__":
    main()
