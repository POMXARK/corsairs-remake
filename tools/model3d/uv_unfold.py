#!/usr/bin/env python3
"""uv_unfold.py in_uv.obj out_uv.obj [res]: islands of a UV that lie over themselves are cut and unwrapped again, then
all islands are packed anew.

3DCoat Auto Seams leaves about 4 % of the texels used twice inside one island: the tube of the neck and the ponytail
flattened folds over itself, one texel serves the neck and the ponytail, and the ponytail gets the skin of the neck
(light spots). Here every such island is cut by the plane between the two 3D clusters of its overlapping faces
(head_seams.split_folds), each piece is unwrapped at the 3D scale of the island by LSCM (UNFOLD=lscm, default) or
ARAP (UNFOLD=arap: as rigid as possible, the open copy of 3DCoat's GU, even area inside a piece). On the hero1 head
(fix2/solid_auv.obj) LSCM gave 397 islands, 15 faces over themselves, uv_score 2.40; ARAP 426 islands, 26 faces,
2.06: ARAP pieces of the folded tube overlap more often and are cut again, so the atlas gets more small islands, a piece that still overlaps is cut again (up to MAX_DEPTH), and xatlas packs all
islands from the given UV (use_input_mesh_uvs: the other islands keep their shape). The positions keep their order
(uv_from_obj.py and head_parts.py work on the output as on the input).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_from_obj import read_obj  # noqa: E402
import head_seams as hs  # noqa: E402

MAX_DEPTH = 3
MIN_FACES = 20  # overlapping faces of an island below this are left


def components(FT):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    e = np.concatenate([FT[:, [0, 1]], FT[:, [1, 2]], FT[:, [2, 0]]])
    n = FT.max() + 1
    return connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)[1]


def lscm(P, tri):
    """UV of the vertices of a disk-like piece (P: positions of its own vertices, tri: local indices)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import lsqr
    a, b, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    ex = b - a
    ex /= np.linalg.norm(ex, axis=1, keepdims=True) + 1e-30
    nz = np.cross(b - a, c - a)
    area = np.linalg.norm(nz, axis=1) / 2
    nz /= np.linalg.norm(nz, axis=1, keepdims=True) + 1e-30
    ey = np.cross(nz, ex)
    x = np.stack([np.zeros(len(tri)), ((b - a) * ex).sum(1), ((c - a) * ex).sum(1)], 1)
    y = np.stack([np.zeros(len(tri)), ((b - a) * ey).sum(1), ((c - a) * ey).sum(1)], 1)
    s = 1 / np.sqrt(2 * area + 1e-30)
    wr = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], 1) * s[:, None]
    wi = np.stack([y[:, 2] - y[:, 1], y[:, 0] - y[:, 2], y[:, 1] - y[:, 0]], 1) * s[:, None]
    n, m = len(P), len(tri)
    rows = np.repeat(np.arange(m), 3)
    cols = tri.ravel()
    # (wr + i wi)(u + i v) = 0: real rows wr u - wi v, imaginary rows wi u + wr v
    R = coo_matrix((np.concatenate([wr.ravel(), -wi.ravel(), wi.ravel(), wr.ravel()]),
                    (np.concatenate([rows, rows, rows + m, rows + m]),
                     np.concatenate([cols, cols + n, cols, cols + n]))), shape=(2 * m, 2 * n)).tocsc()
    i0 = int(np.argmin(P[:, 1]))
    i1 = int(np.argmax(np.linalg.norm(P - P[i0], axis=1)))
    pin = np.array([i0, i1, i0 + n, i1 + n])
    val = np.array([0., np.linalg.norm(P[i1] - P[i0]), 0., 0.])
    free = np.setdiff1d(np.arange(2 * n), pin)
    rhs = -R[:, pin] @ val
    sol = lsqr(R[:, free], rhs, atol=1e-10, btol=1e-10, iter_lim=20000)[0]
    z = np.zeros(2 * n)
    z[pin], z[free] = val, sol
    return np.stack([z[:n], z[n:]], 1)


def split(V, F, faces):
    """Two halves of the faces by the plane between the 2-means of their centres (along the longest spread)."""
    C = V[F[faces]].mean(1)
    c0, c1 = C[np.argmin(C[:, 1])], C[np.argmax(C[:, 1])]
    for _ in range(20):
        near1 = np.linalg.norm(C - c1, axis=1) < np.linalg.norm(C - c0, axis=1)
        if near1.all() or not near1.any():
            break
        c0, c1 = C[~near1].mean(0), C[near1].mean(0)
    side = (C - (c0 + c1) / 2) @ (c1 - c0) > 0
    return faces[side], faces[~side]


METHOD = os.environ.get('UNFOLD', 'lscm')  # lscm or arap (= GU of 3DCoat), see the docstring for the measured scores


def flat(P, tri):
    if METHOD == 'lscm':
        return lscm(P, tri)
    from coat_algos import arap
    return arap(P, tri)


def unfold(V, F, faces, scale, depth=0):
    """Pieces (face lists) with their new per-face-corner UV: connected parts of the faces, each unwrapped by flat() (LSCM or ARAP);
    a piece that still overlaps itself is cut again."""
    out = []
    comp = hs.face_components(F[faces])
    for c in np.unique(comp):
        f = faces[comp == c]
        vid, loc = np.unique(F[f], return_inverse=True)
        uv = flat(V[vid], loc.reshape(-1, 3)) * scale
        T = uv - uv.min(0)
        T = T / max(T.max(), 1e-30)
        bad, _ = hs.uv_overlap(T, loc.reshape(-1, 3), res=512)
        if bad.sum() >= MIN_FACES and depth < MAX_DEPTH and len(f) > 2 * MIN_FACES:
            a, b = split(V, F, f)
            out += unfold(V, F, a, scale, depth + 1) + unfold(V, F, b, scale, depth + 1)
        else:
            out.append((f, uv[loc.reshape(-1, 3)]))
    return out


def write_obj(path, V, F, UVc):
    """Positions as given, one vt per face corner (shared ones merged)."""
    key, inv = np.unique(np.round(UVc.reshape(-1, 2), 7), axis=0, return_inverse=True)
    FT = inv.reshape(-1, 3)
    with open(path, 'w') as o:
        o.write(''.join(f'v {x:.6f} {y:.6f} {z:.6f}\n' for x, y, z in V))
        o.write(''.join(f'vt {u:.6f} {v:.6f}\n' for u, v in key))
        o.write(''.join(f'f {a + 1}/{d + 1} {b + 1}/{e + 1} {c + 1}/{g + 1}\n' for (a, b, c), (d, e, g) in zip(F, FT)))


def main():
    import xatlas
    src, dst = sys.argv[1:3]
    res = int(sys.argv[3]) if len(sys.argv) > 3 else 2048
    V, T, F, FT = read_obj(src)
    UVc = T[FT].copy()  # per face corner
    bad, isl = hs.uv_overlap(T, FT)
    a3 = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum()
    a2 = np.abs(np.cross(T[FT[:, 1]] - T[FT[:, 0]], T[FT[:, 2]] - T[FT[:, 0]])).sum()
    scale = np.sqrt(a2 / a3)  # UV units per 3D unit of the whole atlas: the new pieces keep the texel density
    n_new = 0
    for i in np.unique(isl[bad]):
        if (bad & (isl == i)).sum() < MIN_FACES:
            continue
        f0, f1 = split(V, F, np.nonzero(isl == i)[0])
        for f, uv in unfold(V, F, f0, scale, 1) + unfold(V, F, f1, scale, 1):
            UVc[f] = uv + 10. * (n_new + 1)  # apart from everything: xatlas sees a new chart
            n_new += 1
    print(f'{src}: overlapping faces {int(bad.sum())} in {len(np.unique(isl[bad]))} islands -> {n_new} new pieces')
    # xatlas wants per-vertex uv: one vertex per (position, uv corner)
    corners = np.round(UVc.reshape(-1, 2), 7)
    key = np.concatenate([F.reshape(-1, 1).astype(np.float64), corners], 1)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    pos = V[uk[:, 0].astype(int)].astype(np.float32)
    uv_in = uk[:, 1:].astype(np.float32)
    uv_in = (uv_in - uv_in.min(0)) / (uv_in.max() - uv_in.min() + 1e-30)
    atlas = xatlas.Atlas()
    atlas.add_mesh(pos, inv.reshape(-1, 3).astype(np.uint32), None, uv_in)
    co = xatlas.ChartOptions()
    co.use_input_mesh_uvs = True
    po = xatlas.PackOptions()
    po.resolution, po.padding, po.bilinear, po.rotate_charts, po.bruteForce = res, 4, True, True, False
    atlas.generate(co, po)
    vmap, idx, uvs = atlas[0]
    out = np.zeros_like(UVc)
    # the faces keep their order in xatlas; the corner uv is the uv of the output vertex
    out[:] = uvs[idx]
    write_obj(dst, V, F, out)
    _, T2, _, FT2 = read_obj(dst)
    bad2, isl2 = hs.uv_overlap(T2, FT2)
    print(f'-> {dst}: charts {atlas.chart_count}, islands {isl2.max() + 1}, faces over themselves {int(bad2.sum())}')


if __name__ == '__main__':
    main()
