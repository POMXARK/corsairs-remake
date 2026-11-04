#!/usr/bin/env python3
"""uv_unfold.py in_uv.obj out_uv.obj [res]: islands of a UV that lie over themselves are cut and unwrapped again, then
all islands are packed anew.

3DCoat Auto Seams leaves about 4 % of the texels used twice inside one island: the tube of the neck and the ponytail
flattened folds over itself, one texel serves the neck and the ponytail, and the ponytail gets the skin of the neck
(light spots). Here every such island is cut by the plane between the two 3D clusters of its overlapping faces
(head_seams.split_folds), each piece is unwrapped at the 3D scale of the island by ARAP (UNFOLD=arap, default: as
rigid as possible, the open copy of 3DCoat's GU, even area inside a piece), LSCM (UNFOLD=lscm) or by xatlas charts of
the island (UNFOLD=xatlas). Sweep on the hero1 head (fix2/solid_auv.obj, uv_score with the overlap term; 3DCoat's own
atlas 3.52): arap MIN 50 DEPTH 5 4.81 (248 islands, 1.9 % of the surface over other faces), arap MIN 20 DEPTH 1 4.59
(7.8 %), lscm 1.7..3.3 (LSCM pieces fold: fill counted once drops), xatlas 2.73 (345 islands, many front seams). A
piece that still overlaps is cut again (up to MAX_DEPTH), and xatlas packs all
islands as they are (add_uv_mesh; add_mesh with use_input_mesh_uvs charts them again: 245 -> 396) on one square sheet
(pack_square: texels_per_unit bisected so that one res x res atlas holds them; pad, bilinear, res and blockAlign
change fill by 0.005 only). The positions keep their order
(uv_from_obj.py and head_parts.py work on the output as on the input).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_from_obj import read_obj  # noqa: E402
import head_seams as hs  # noqa: E402

MAX_DEPTH = int(os.environ.get('UNFOLD_DEPTH', 5))
MIN_FACES = int(os.environ.get('UNFOLD_MIN', 50))  # overlapping faces of an island below this are left
PAD = int(os.environ.get('UNFOLD_PAD', 2))  # xatlas padding in pixels of res
BRUTE = os.environ.get('UNFOLD_BRUTE', '1') == '1'  # xatlas brute force packing (denser)
BLOCK = os.environ.get('UNFOLD_BLOCK', '1') == '1'  # xatlas blockAlign: with brute force as dense and 10x faster
BILINEAR = os.environ.get('UNFOLD_BILINEAR', '1') == '1'  # a texel more around a chart for bilinear filtering


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


METHOD = os.environ.get('UNFOLD', 'arap')  # arap, lscm or xatlas (= GU of 3DCoat), see the docstring for the measured scores


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


def xatlas_charts(V, F, faces, scale):
    """Pieces (face lists) with per-corner UV: xatlas cuts and unwraps the faces by their 3D shape (its charts are disks
    with low stretch, unlike LSCM of an island with holes); each chart is scaled to `scale` UV units per 3D unit."""
    import xatlas
    vid, loc = np.unique(F[faces], return_inverse=True)
    loc = loc.reshape(-1, 3)
    at = xatlas.Atlas()
    at.add_mesh(V[vid].astype(np.float32), loc.astype(np.uint32))
    co = xatlas.ChartOptions()
    co.max_cost = float(os.environ.get('UNFOLD_COST', co.max_cost))  # higher: fewer, bigger charts, more stretch
    co.normal_deviation_weight = float(os.environ.get('UNFOLD_NORMAL', co.normal_deviation_weight))
    co.roundness_weight = float(os.environ.get('UNFOLD_ROUND', co.roundness_weight))
    co.straightness_weight = float(os.environ.get('UNFOLD_STRAIGHT', co.straightness_weight))
    co.max_iterations = int(os.environ.get('UNFOLD_ITER', co.max_iterations))
    po = xatlas.PackOptions()
    po.resolution = 1024
    at.generate(co, po)
    _, idx, uvs = at[0]  # faces keep their order
    uvc = uvs[idx].astype(np.float64) * [at.width, at.height]  # one scale for u and v
    out = []
    comp = hs.face_components(np.unique(np.round(uvc.reshape(-1, 2), 7), axis=0, return_inverse=True)[1].ravel().reshape(-1, 3))
    P = V[vid]
    for c in np.unique(comp):
        m = comp == c
        t = loc[m]
        a3 = np.linalg.norm(np.cross(P[t[:, 1]] - P[t[:, 0]], P[t[:, 2]] - P[t[:, 0]]), axis=1).sum()
        u = uvc[m]
        a2 = np.abs(np.cross(u[:, 1] - u[:, 0], u[:, 2] - u[:, 0])).sum()
        out.append((faces[m], (u - u.reshape(-1, 2).min(0)) * scale * np.sqrt(a3 / max(a2, 1e-30))))
    return out


def pack_square(UVc, res=2048, pad=None, rotate=True):
    """Per-corner UV packed into the unit square, every island as it is (rigid moves only, one texel density).

    xatlas add_uv_mesh: a chart per UV-connected piece, the UV scale kept (add_mesh with use_input_mesh_uvs re-charted
    the new pieces: 245 islands -> 396 charts). Its own texel density gives a sheet cut to the used part, not square
    (1800 x 2216 for 2048: fill 0.60 of the square), so the density is searched (bisection, 9 packs) for the largest
    one that still fits one res x res sheet. Returns the UV and the chart count."""
    import xatlas
    pad = PAD if pad is None else pad
    key, inv = np.unique(np.round(UVc.reshape(-1, 2), 7), axis=0, return_inverse=True)
    tri = inv.ravel().reshape(-1, 3).astype(np.uint32)

    def run(tpu):
        at = xatlas.Atlas()
        at.add_uv_mesh(key.astype(np.float32), tri)
        po = xatlas.PackOptions()
        po.resolution, po.padding, po.bilinear, po.rotate_charts, po.bruteForce = res, pad, BILINEAR, rotate, BRUTE
        po.blockAlign = BLOCK
        po.texels_per_unit = tpu
        at.generate(xatlas.ChartOptions(), po)
        _, idx, uvs = at[0]
        # the faces keep their order; uvs are normalized by the width and the height apart: back to pixels
        ok = at.atlas_count == 1 and at.width <= res and at.height <= res
        return ok, uvs[idx] * [at.width, at.height] / res, at.chart_count, at.texels_per_unit

    ok, best, n, t0 = run(0.)
    if not ok:  # the sheet of xatlas' own density is over res on one side: in res x res
        best = best * res / best.reshape(-1, 2).max()
    lo, hi = 0.6 * t0, 1.2 * t0
    for _ in range(9):
        m = (lo + hi) / 2
        ok, uv, n2, _ = run(m)
        if ok:
            lo, best, n = m, uv, n2
        else:
            hi = m
    return best, n


def main():
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
        if METHOD == 'xatlas':
            pieces = xatlas_charts(V, F, np.nonzero(isl == i)[0], scale)
        else:
            f0, f1 = split(V, F, np.nonzero(isl == i)[0])
            pieces = unfold(V, F, f0, scale, 1) + unfold(V, F, f1, scale, 1)
        for f, uv in pieces:
            UVc[f] = uv + 10. * (n_new + 1)  # apart from everything: xatlas sees a new chart
            n_new += 1
    print(f'{src}: overlapping faces {int(bad.sum())} in {len(np.unique(isl[bad]))} islands -> {n_new} new pieces')
    out, charts = pack_square(UVc, res)
    write_obj(dst, V, F, out)
    _, T2, _, FT2 = read_obj(dst)
    bad2, isl2 = hs.uv_overlap(T2, FT2)
    print(f'-> {dst}: charts {charts}, islands {isl2.max() + 1}, faces over themselves {int(bad2.sum())}')


if __name__ == '__main__':
    main()
