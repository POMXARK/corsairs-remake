#!/usr/bin/env python3
"""Score the UV atlas of a head: how much texture the face gets and how clean the cuts are.

uv_score.py model.(obj|glb) [more models...] [--json out.json]

Numbers (all area-weighted over the 3D surface):
  islands, tiny  - charts and the share of the surface in charts under 50 faces (crumbs: bleed and seams);
  fill           - share of the UV square covered by triangles, each texel once (packing);
  overlap        - share of the surface on faces that share texels with another face (folds, stacked islands);
  stretch        - mean of s1/s2 of the 3D->UV Jacobian (each face capped at 10), 1 = no shear (conformal);
  scale          - std of log texel density over the surface, 0 = every mm gets the same texels;
  face_density   - texels per unit area on the face zone (|x| < 0.6 of half width, front 0.25..0.75 of height,
                   normal facing +z) relative to an ideal atlas where the whole UV square is spread evenly;
  seam_front     - length of cuts on the front half (normal z > 0.3) per unit of head height: seams in sight;
  seam_total     - all cut length per unit of head height.
score = 100 * fill * face_density_share / stretch * exp(-scale) * (1 - tiny) * (1 - overlap) / (1 + seam_front / 4)
(higher is better; it is a ranking for runs on one mesh, not an absolute grade).
The head looks along +z with y up, as Pixal3D/TRELLIS write it.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def load(path):
    """Positions per vertex, UV per corner: V (n,3), F (m,3) position indices, UV (m,3,2)."""
    if path.endswith('.obj'):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from uv_from_obj import read_obj
        V, T, F, FT = read_obj(path)
        return V, F, T[FT]
    from pdm_project_views import accessor, read_glb
    j, b = read_glb(path)
    prim = j['meshes'][0]['primitives'][0]
    P = accessor(j, b, prim['attributes']['POSITION']).astype(np.float64)
    UV = accessor(j, b, prim['attributes']['TEXCOORD_0']).astype(np.float64)
    tris = accessor(j, b, prim['indices']).reshape(-1, 3).astype(np.int64)
    # glb vertices are split along UV seams: weld by position for the topology
    _, pid = np.unique(np.round(P, 6), axis=0, return_inverse=True)
    Pw = np.zeros((pid.max() + 1, 3))
    Pw[pid.ravel()] = P
    uv = UV[tris].copy()
    uv[..., 1] = 1 - uv[..., 1]
    return Pw, pid.ravel()[tris], uv


def charts(F, UV):
    """Chart label per face (faces share a chart over an edge with the same UV on both ends); the order of the
    (edge, face) list sorted by edge, and the seam flag in that order."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    m = len(F)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    euv = np.concatenate([UV[:, [0, 1]], UV[:, [1, 2]], UV[:, [2, 0]]])
    fi = np.tile(np.arange(m), 3)
    flip = e[:, 0] > e[:, 1]
    e[flip] = e[flip][:, ::-1]
    euv[flip] = euv[flip][:, ::-1]
    key = e[:, 0] * (F.max() + 1) + e[:, 1]
    o = np.argsort(key, kind='stable')
    k, euv, fi = key[o], euv[o], fi[o]
    same = k[1:] == k[:-1]
    a, b = np.nonzero(same)[0], np.nonzero(same)[0] + 1
    glued = np.abs(euv[a] - euv[b]).max(axis=(1, 2)) < 1e-6
    g = coo_matrix((np.ones(glued.sum()), (fi[a][glued], fi[b][glued])), shape=(m, m))
    lab = connected_components(g, directed=False)[1]
    # seam flag per (edge, face) in the order o: the pair is not glued, or the edge is open
    seam = np.ones(len(k), bool)
    seam[a[glued]] = seam[b[glued]] = False
    return lab, o, seam


STRETCH_CAP = 10.


def coverage(UV, res=1024):
    """Texel coverage of the atlas: the share of the triangles' texels that no other face covers (union / sum) and
    a per face flag 'shares texels with another face' (any island: folds and islands packed over each other)."""
    own = np.full((res, res), -1, np.int64)
    bad = np.zeros(len(UV), bool)
    total = 0
    for k, t in enumerate(UV * res):
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1 + 1, res)) + .5, np.arange(max(y0, 0), min(y1 + 1, res)) + .5)
        a, b, c = t
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if xs.size == 0 or abs(d) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        m = (l1 > 1e-6) & (l2 > 1e-6) & (l1 + l2 < 1 - 1e-6)
        yy, xx = ys[m].astype(int), xs[m].astype(int)
        total += len(yy)
        o = own[yy, xx]
        if (o >= 0).any():
            bad[k] = True
            bad[o[o >= 0]] = True
        own[yy, xx] = k
    return ((own >= 0).sum() / max(total, 1)), bad


def score(path):
    V, F, UV = load(path)
    p0, p1, p2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(p1 - p0, p2 - p0)
    a3 = 0.5 * np.linalg.norm(n, axis=1)
    n = n / (2 * a3[:, None] + 1e-30)
    u0, u1, u2 = UV[:, 0], UV[:, 1], UV[:, 2]
    d1, d2 = u1 - u0, u2 - u0
    auv = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    ok = (a3 > 1e-14) & (auv > 1e-16)
    # Jacobian 3D->UV in the triangle's own frame
    ex = (p1 - p0) / (np.linalg.norm(p1 - p0, axis=1, keepdims=True) + 1e-30)
    ey = np.cross(n, ex)
    q1 = np.stack([((p1 - p0) * ex).sum(1), ((p1 - p0) * ey).sum(1)], 1)
    q2 = np.stack([((p2 - p0) * ex).sum(1), ((p2 - p0) * ey).sum(1)], 1)
    Q = np.stack([q1, q2], 2)  # columns: edges in 3D frame
    U = np.stack([d1, d2], 2)
    Qi = np.linalg.inv(np.where(ok[:, None, None], Q, np.eye(2)))
    J = U @ Qi
    s = np.linalg.svd(J, compute_uv=False)
    w = a3 * ok
    W = w.sum()
    # s1/s2 capped at 10: a near-degenerate UV face (0.1 % of the area) gave 1e20 and the mean followed the rounding of
    # the last digits (3DCoat atlas 1.29, the same atlas repacked 2.6); capped, both are 1.28
    stretch = float((w * np.minimum(s[:, 0] / np.maximum(s[:, 1], 1e-30), STRETCH_CAP)).sum() / W)
    dens = np.log(np.maximum(auv, 1e-30) / np.maximum(a3, 1e-30))
    mu = (w * dens).sum() / W
    scale = float(np.sqrt((w * (dens - mu) ** 2).sum() / W))
    # fill counts a texel once: an LSCM fold or islands packed over each other gave fill 1.36 and the best score
    uni, over = coverage(UV)
    fill = float(auv.sum() * uni)
    overlap = float(w[over].sum() / W)
    lab, o, is_seam = charts(F, UV)
    cnt = np.bincount(lab)
    tiny = float(w[cnt[lab] < 50].sum() / W)
    lo, hi = V.min(0), V.max(0)
    hgt = hi[1] - lo[1]
    c = (p0 + p1 + p2) / 3
    rel = (c - lo) / (hi - lo)
    face = ok & (np.abs(rel[:, 0] - 0.5) < 0.3) & (rel[:, 1] > 0.25) & (rel[:, 1] < 0.75) & (n[:, 2] > 0.3)
    # texels per area on the face against the even spread of the whole square over the surface
    face_density = float((auv[face].sum() / a3[face].sum()) / (1.0 / W)) if face.any() else 0.
    # seams: every (edge, face) on a cut, half its 3D length (an inner seam edge is seen from both faces)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])[o]
    sf = np.tile(np.arange(len(F)), 3)[o]
    L = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) * is_seam * 0.5
    seam_total = float(L.sum() / hgt)
    seam_front = float((L * (n[sf, 2] > 0.3)).sum() / hgt)
    sc = 100 * fill * min(face_density, 2.0) / 2.0 / stretch * np.exp(-scale) * (1 - tiny) * (1 - overlap) / (1 + seam_front / 4)
    return dict(model=os.path.basename(path), faces=int(len(F)), islands=int(len(cnt)), tiny=round(tiny, 4), overlap=round(overlap, 4),
                fill=round(fill, 3), stretch=round(stretch, 3), scale=round(scale, 3),
                face_density=round(face_density, 3), seam_front=round(seam_front, 2),
                seam_total=round(seam_total, 2), score=round(float(sc), 2))


def main():
    args = sys.argv[1:]
    out = None
    if '--json' in args:
        i = args.index('--json')
        out = args[i + 1]
        del args[i:i + 2]
    rows = [score(p) for p in args]
    keys = list(rows[0])
    print('\t'.join(keys))
    for r in rows:
        print('\t'.join(str(r[k]) for k in keys))
    if out:
        json.dump(rows, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
