#!/usr/bin/env python3
"""Seams of a head by the usual rules of a character UV, for 3DCoat to unwrap (coat_autouv.py, job line 5).

head_seams.py mesh.obj variant out.txt [auto.obj]

The head looks along +z, y up (Pixal3D/TRELLIS). Variants:
  back   - one cut down the back of the head (crown to the neck, along the midline, through the hair) and the ring
           of the flat neck lid: the head opens as one mask, the lid is its own island;
  back+ears - the same, and a ring around the root of each ear (ears unwrap on their own, not stretched in the mask);
  auto-face+ears - auto-face and the ear rings;
  auto-face - the cuts of 3DCoat's Auto Seams (from auto.obj, the same mesh unwrapped by 3DCoat) except the ones on
           the face: front, between the ears, from the chin to the hairline; the face stays one piece;
  auto-face+back - auto-face and the back cut;
  parts-game - by the parts of head_parts.py (parts.npy of mesh.obj, 4th argument): the face (face, eyes, mouth, nose,
           brows) is one island, every ear is one, the rest (scalp, neck, ponytail) opens by the back cut, the lid
           is its own: the usual layout of a game head, the face gets the most texels in the pack;
  parts  - one island per part group: face, each ear, neck, scalp (opened by the back cut), ponytail, lid;
  auto-split - the cuts of Auto Seams (auto.obj) and one more through every island that lies over itself in the UV
           (a tube of the ponytail and the neck flattened: two places of the head share texels, the ponytail takes
           the skin of the neck): a plane between the two 3D clusters of the overlapping faces. Run again on the new
           result while islands still overlap;
  split  - only the extra cuts of auto-split (for coat_run.sh auto+seams: Auto Seams first, these cuts on top; the
           seams mode with all cuts given leaves faces without UV in the output).
The output lists seam edges, one 'a b' pair of 0-based vertex indices of mesh.obj per line.
"""
import heapq
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_from_obj import read_obj  # noqa: E402

OUT_CORE = 0.012  # share of the size: the ear rim stands this far out of the head skin (about 3 mm on a head)
OUT_EAR = 0.005  # share of the size: the ear root, the cut goes here
SMOOTH_STEPS = 6  # majority steps over the part borders of the parts variants (2 of head_parts.py left a zigzag seam)


def edges_of(F):
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    fi = np.tile(np.arange(len(F)), 3)
    return E, fi


def face_normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-30)


def region_border(F, inside):
    """Edges between faces in and out of the region."""
    E, fi = edges_of(F)
    key = E[:, 0] * (F.max() + 1) + E[:, 1]
    o = np.argsort(key, kind='stable')
    k, fi, E = key[o], fi[o], E[o]
    same = np.nonzero(k[1:] == k[:-1])[0]
    diff = inside[fi[same]] != inside[fi[same + 1]]
    return E[same[diff]]


def shortest(V, F, src, dst, cost):
    """Dijkstra over the mesh edges; cost(vertex) multiplies the edge length (taken at the edge middle)."""
    E, _ = edges_of(F)
    E = np.unique(E, axis=0)
    w = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) * 0.5 * (cost[E[:, 0]] + cost[E[:, 1]])
    nb = [[] for _ in range(len(V))]
    for (a, b), c in zip(E.tolist(), w.tolist()):
        nb[a].append((b, c))
        nb[b].append((a, c))
    dist = np.full(len(V), np.inf)
    prev = np.full(len(V), -1)
    dist[src] = 0
    h = [(0., src)]
    dst = set(int(d) for d in np.atleast_1d(dst))
    while h:
        d, a = heapq.heappop(h)
        if d > dist[a]:
            continue
        if a in dst:
            break
        for b, c in nb[a]:
            if d + c < dist[b]:
                dist[b], prev[b] = d + c, a
                heapq.heappush(h, (d + c, b))
    path = [a]
    while prev[path[-1]] >= 0:
        path.append(prev[path[-1]])
    return np.array([[path[i], path[i + 1]] for i in range(len(path) - 1)])


def lid(V, F):
    lo, hi = V.min(0), V.max(0)
    c = V[F].mean(1)
    n = face_normals(V, F)
    return ((c[:, 1] - lo[1]) / (hi[1] - lo[1]) < 0.08) & (n[:, 1] < -0.7)


def back_cut(V, F, ring):
    lo, hi = V.min(0), V.max(0)
    size = hi - lo
    xm = 0.5 * (lo[0] + hi[0])
    # crown: the top vertex near the midline; end: the back-most vertex of the lid ring near the midline
    near = np.abs(V[:, 0] - xm) < 0.03 * size[0]
    top = np.argmax(np.where(near, V[:, 1], -np.inf))
    rv = np.unique(ring)
    end = rv[np.argsort(np.abs(V[rv, 0] - xm) + 10 * np.maximum(V[rv, 2] - lo[2] - 0.3 * size[2], 0))[:3]]
    # stay on the back midline: off the plane x = xm and on the front half it costs a lot
    cost = 1 + 40 * (np.abs(V[:, 0] - xm) / size[0]) ** 2 * 25 + 200 * (V[:, 2] > lo[2] + 0.45 * size[2])
    return shortest(V, F, top, end, cost)


def ears(V, F):
    """Faces of both ears. An ear stands out of the head side: per cell (1.2 % of the size) of the side view the
    inner layer of the surface is the skin of the head, points more than OUT_CORE farther out are the ear rim; the
    ear is everything inside the outline of its rim (side view, grown by 10 %) more than OUT_EAR out of the skin."""
    from scipy.spatial import Delaunay
    lo, hi = V.min(0), V.max(0)
    size = hi - lo
    rel = (V - lo) / size
    xm = 0.5 * (lo[0] + hi[0])
    inside = np.zeros(len(F), bool)
    cell = 0.012 * size.max()
    key = np.floor(V[:, 1] / cell).astype(np.int64) * 1000003 + np.floor(V[:, 2] / cell).astype(np.int64)
    for sgn in (1, -1):
        ax = sgn * (V[:, 0] - xm)
        box = np.nonzero((ax > 0.25 * size[0]) & (rel[:, 1] > .36) & (rel[:, 1] < .68) & (rel[:, 2] > .25) & (rel[:, 2] < .7))[0]
        u, inv = np.unique(key[box], return_inverse=True)
        mn = np.full(len(u), np.inf)
        np.minimum.at(mn, inv, ax[box])
        out = np.zeros(len(V))
        out[box] = ax[box] - mn[inv]
        core = box[out[box] > OUT_CORE * size.max()]
        if len(core) < 50:
            continue
        yz = V[core][:, 1:]
        c = yz.mean(0)
        hull = Delaunay(c + (yz - c) * 1.1)
        vin = np.zeros(len(V), bool)
        vin[box] = (hull.find_simplex(V[box][:, 1:]) >= 0) & (out[box] > OUT_EAR * size.max())
        f = vin[F].all(1)
        # the largest connected piece: crumbs of hair inside the outline stay with the head
        idx = np.nonzero(f)[0]
        lab = face_components(F[idx])
        inside[idx[lab == np.bincount(lab).argmax()]] = True
    return inside


def face_components(F):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    fi = np.tile(np.arange(len(F)), 3)
    key = E[:, 0] * (F.max() + 1) + E[:, 1]
    o = np.argsort(key, kind='stable')
    k, fi = key[o], fi[o]
    s = np.nonzero(k[1:] == k[:-1])[0]
    g = coo_matrix((np.ones(len(s)), (fi[s], fi[s + 1])), shape=(len(F), len(F)))
    return connected_components(g, directed=False)[1]


def auto_seams(path_auto):
    V, T, F, FT = read_obj(path_auto)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    ET = np.concatenate([FT[:, [0, 1]], FT[:, [1, 2]], FT[:, [2, 0]]])
    flip = E[:, 0] > E[:, 1]
    E[flip], ET[flip] = E[flip][:, ::-1], ET[flip][:, ::-1]
    key = E[:, 0] * (F.max() + 1) + E[:, 1]
    o = np.argsort(key, kind='stable')
    k, E, ET = key[o], E[o], ET[o]
    same = np.nonzero(k[1:] == k[:-1])[0]
    cut = np.any(T[ET[same]] != T[ET[same + 1]], axis=(1, 2))  # same edge, other uv on the two sides
    return E[same[cut]]


def uv_overlap(T, FT, res=1024):
    """Faces of every UV island that share texels with another face of the same island (per face flag) and the
    island of every face."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    e = np.concatenate([FT[:, [0, 1]], FT[:, [1, 2]], FT[:, [2, 0]]])
    n = len(T)
    _, vc = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    isl = vc[FT[:, 0]]
    own = np.full((res, res), -1, np.int64)
    bad = np.zeros(len(FT), bool)
    for k, t in enumerate(T[FT] * res):
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
        o = own[yy, xx]
        hit = o >= 0
        hit[hit] = isl[o[hit]] == isl[k]
        if hit.any():
            bad[k] = True
            bad[o[hit]] = True
        own[yy, xx] = k
    return bad, isl


def split_folds(V, F, T, FT, min_faces=20):
    """A cut through every island with overlapping faces: the plane between the two 3D clusters of them (2-means)."""
    bad, isl = uv_overlap(T, FT)
    C = V[F].mean(1)
    cuts, n = [], 0
    for i in np.unique(isl[bad]):
        f = np.nonzero(bad & (isl == i))[0]
        if len(f) < min_faces:
            continue
        p = C[f]
        c0, c1 = p[np.argmin(p[:, 1])], p[np.argmax(p[:, 1])]
        for _ in range(20):
            near1 = np.linalg.norm(p - c1, axis=1) < np.linalg.norm(p - c0, axis=1)
            if near1.all() or not near1.any():
                break
            c0, c1 = p[~near1].mean(0), p[near1].mean(0)
        nrm, mid = c1 - c0, (c0 + c1) / 2
        side = (isl == i) & ((C - mid) @ nrm > 0)
        cuts.append(region_border(F, side))
        n += 1
    print(f'overlapping faces {int(bad.sum())} in {len(np.unique(isl[bad]))} islands, cut {n}')
    return cuts


def face_zone(V):
    lo, hi = V.min(0), V.max(0)
    rel = (V - lo) / (hi - lo)
    return (np.abs(rel[:, 0] - 0.5) < 0.33) & (rel[:, 1] > 0.18) & (rel[:, 1] < 0.8) & (rel[:, 2] > 0.55)


def main():
    src, variant, out = sys.argv[1:4]
    V, _, F, _ = read_obj(src)
    ring = region_border(F, lid(V, F))
    parts = []
    if variant.startswith('parts'):
        lab = np.load(sys.argv[4])
        if len(lab) != len(F):
            raise SystemExit(f'parts.npy has {len(lab)} faces, {src} has {len(F)}: head_parts.py {src} --views ...')
        from head_parts import face_graph
        G = face_graph(V, F)

        def even(m, steps=SMOOTH_STEPS):  # majority of the face and its neighbours: the zigzag of the part border goes
            for _ in range(steps):
                m = (G @ m.astype(np.float32) + 1.5 * m) / (np.asarray(G.sum(1)).ravel() + 1.5) > 0.5
            return m
        face = even(np.isin(lab, (1, 2, 3, 4, 5)))
        ear = even(lab == 6, 2) & ~face
        idx = np.nonzero(ear)[0]
        if len(idx):  # every ear on its own (the two ears are not joined anyway, a stray face of 'ears' is dropped)
            comp = face_components(F[idx])
            big = np.bincount(comp)
            for c in np.argsort(-big)[:2]:
                if big[c] > 20:
                    parts.append(region_border(F, np.isin(np.arange(len(F)), idx[comp == c])))
        parts += [region_border(F, face), ring, back_cut(V, F, ring)]
        if variant == 'parts':
            parts += [region_border(F, even(lab == 7) & ~face), region_border(F, even(lab == 9))]
    elif variant in ('auto-split', 'split'):
        Va, Ta, Fa, FTa = read_obj(sys.argv[4])
        parts += ([auto_seams(sys.argv[4])] if variant == 'auto-split' else []) + split_folds(Va, Fa, Ta, FTa)
    elif variant.startswith('auto-face'):
        S = auto_seams(sys.argv[4])
        fz = face_zone(V)
        parts.append(S[~(fz[S[:, 0]] | fz[S[:, 1]])])
        if '+back' in variant:
            parts.append(back_cut(V, F, ring))
        if variant.endswith('+ears'):
            parts.append(region_border(F, ears(V, F)))
    else:
        parts += [ring, back_cut(V, F, ring)]
        if variant.endswith('+ears'):
            parts.append(region_border(F, ears(V, F)))
    S = np.unique(np.sort(np.concatenate(parts), 1), axis=0)
    np.savetxt(out, S, fmt='%d')
    print(variant, 'seam edges', len(S), 'lid ring', len(ring))


if __name__ == '__main__':
    main()
