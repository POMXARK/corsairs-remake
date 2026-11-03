#!/usr/bin/env python3
"""Open copies of the 3DCoat tools the head pipeline uses, found by the black-box probe (coat_probe.py): the same
result without 3DCoat, on Linux, for any mesh.

coat_algos.py relax in.obj out.obj degree [tangent 0/1] [crease_deg]   = Mesh.relax(degree, tangent, crease)
coat_algos.py flatten in.obj out.obj plane|lscm|abf|arap|pca            = uv.flattenSingleIsland(m, 0 | 1 | 2 | 3)
coat_algos.py vrelax in.obj out.obj degree                              ~ Volume.relaxSurface (topology kept)
coat_algos.py weld in.obj out.obj [rel]                                 = Mesh.weld(rel)
coat_algos.py reduce in.obj out.obj faces                               ~ reduceToPolycount (pymeshlab quadric)
coat_algos.py charts in.obj out.npy [sharp_deg]                          ~ Auto Seams islands (VSA, boxy shapes)
coat_algos.py pack in_uv.obj out_uv.obj [rotate 0/1]                    ~ uv.pack (xatlas brute force)
coat_algos.py verify probe_dir                                           how close each copy is to the 3DCoat output

What 3DCoat does (measured, docs/coat-tools.md):
- Mesh.relax: uniform (umbrella) Laplacian, every vertex moves to the mean of its edge neighbours by lambda. degree
  <= 1 is one step with lambda = degree; degree > 1 is n = floor(degree) + 1 steps with lambda = degree / n. tangent:
  the step without its part along the vertex normal (area weighted, of the current mesh, every step). crease: the
  vertices of an edge whose faces meet at more than crease degrees do not move. Residue against 3DCoat 0.0000.
- flattenSingleIsland method 0 = orthogonal projection on the coordinate plane nearest to the mean normal (exact,
  axis_plane; pca is the best-fit plane, close on flat islands), 1 = LSCM (Levy et al. 2002), 2 = ABF (Sheffer & de
  Sturler 2001; abf: the angles by Newton, the UV by LSCM from the angles), 3 = GU "globally uniform" = close to ARAP
  (Liu et al. 2008): nearly equal areas, angles a bit worse, 4 = stripe (all zeros on triangle meshes, even strips).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def cot_laplacian(V, F):
    from scipy.sparse import coo_matrix
    I, J, W = [], [], []
    for k in range(3):
        i, j, o = F[:, (k + 1) % 3], F[:, (k + 2) % 3], F[:, k]
        a, b = V[i] - V[o], V[j] - V[o]
        cot = (a * b).sum(1) / (np.linalg.norm(np.cross(a, b), axis=1) + 1e-30)
        I += [i, j]
        J += [j, i]
        W += [cot / 2, cot / 2]
    n = len(V)
    Wm = coo_matrix((np.concatenate(W), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsr()
    return Wm


def uniform_adj(F, n):
    from scipy.sparse import coo_matrix
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    A.data[:] = 1
    return A


def plane(V):
    c = V - V.mean(0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    return c @ vt[:2].T


def axis_plane(V, F):
    """flattenSingleIsland method 0 exactly: orthogonal projection on the coordinate plane (YZ, XZ or XY) whose axis is
    closest to the area weighted mean normal of the island."""
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]).sum(0)
    k = int(np.argmax(np.abs(n)))
    keep = [i for i in range(3) if i != k]
    return V[:, keep] - V[:, keep].mean(0)


def arap(V, F, it=20):
    """As rigid as possible flattening (Liu et al. 2008), started from LSCM."""
    from uv_unfold import lscm
    from scipy.sparse.linalg import factorized
    U = lscm(V, F)
    W = cot_laplacian(V, F)
    n = len(V)
    from scipy.sparse import diags
    L = (diags(np.asarray(W.sum(1)).ravel()) - W).tocsc()
    L = L.tolil()
    L[0, :] = 0
    L[0, 0] = 1
    solve = factorized(L.tocsc())
    # local frames of the triangles
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    ex = (b - a) / (np.linalg.norm(b - a, axis=1, keepdims=True) + 1e-30)
    nz = np.cross(b - a, c - a)
    nz /= np.linalg.norm(nz, axis=1, keepdims=True) + 1e-30
    ey = np.cross(nz, ex)
    X = np.stack([np.zeros((len(F), 2)), np.stack([((b - a) * ex).sum(1), np.zeros(len(F))], 1),
                  np.stack([((c - a) * ex).sum(1), ((c - a) * ey).sum(1)], 1)], 1)  # (m,3,2)
    cots = np.zeros((len(F), 3))  # cotangent of the angle at corner k (opposite the edge k+1, k+2) in its triangle
    for k in range(3):
        p, q = X[:, (k + 1) % 3] - X[:, k], X[:, (k + 2) % 3] - X[:, k]
        cots[:, k] = 0.5 * (p * q).sum(1) / (np.abs(p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]) + 1e-30)
    q1, q2 = U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]
    if np.median(q1[:, 0] * q2[:, 1] - q1[:, 1] * q2[:, 0]) < 0:  # LSCM gave the mirror: ARAP keeps orientation
        U = U * [1, -1]
    for _ in range(it):
        R = np.zeros((len(F), 2, 2))
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            du = U[F[:, i]] - U[F[:, j]]
            dx = X[:, i] - X[:, j]
            R += cots[:, k, None, None] * du[:, :, None] * dx[:, None, :]
        u_, _, vt_ = np.linalg.svd(R)
        Rot = u_ @ vt_
        neg = np.linalg.det(Rot) < 0
        u_[neg, :, 1] *= -1
        Rot = u_ @ vt_
        rhs = np.zeros((n, 2))
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            dx = X[:, i] - X[:, j]
            r = cots[:, k, None] * np.einsum('mab,mb->ma', Rot, dx)
            np.add.at(rhs, F[:, i], r)
            np.add.at(rhs, F[:, j], -r)
        rhs[0] = U[0]
        U = np.stack([solve(rhs[:, 0]), solve(rhs[:, 1])], 1)
    return U


def corner_angles(V, F):
    A = np.zeros((len(F), 3))
    for k in range(3):
        p, q = V[F[:, (k + 1) % 3]] - V[F[:, k]], V[F[:, (k + 2) % 3]] - V[F[:, k]]
        A[:, k] = np.arctan2(np.linalg.norm(np.cross(p, q), axis=1), (p * q).sum(1))
    return A


def boundary_vertices(F, n):
    from collections import Counter
    c = Counter()
    for t in F:
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            c[(min(a, b), max(a, b))] += 1
    on = np.zeros(n, bool)
    for (a, b), k in c.items():
        if k == 1:
            on[a] = on[b] = True
    return on


def lscm_angles(V, F, ang):
    """LSCM with the triangle shapes given by their angles (ABF++ reconstruction): each triangle is the plane
    triangle with these angles and the 3D length of its first edge."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import lsqr
    m, n = len(F), len(V)
    l01 = np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1)
    l02 = l01 * np.sin(ang[:, 1]) / np.maximum(np.sin(ang[:, 2]), 1e-12)  # sine law
    x = np.stack([np.zeros(m), l01, l02 * np.cos(ang[:, 0])], 1)
    y = np.stack([np.zeros(m), np.zeros(m), l02 * np.sin(ang[:, 0])], 1)
    area = 0.5 * l01 * l02 * np.sin(ang[:, 0])
    sc = 1 / np.sqrt(2 * area + 1e-30)
    wr = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], 1) * sc[:, None]
    wi = np.stack([y[:, 2] - y[:, 1], y[:, 0] - y[:, 2], y[:, 1] - y[:, 0]], 1) * sc[:, None]
    rows = np.repeat(np.arange(m), 3)
    cols = F.ravel()
    R = coo_matrix((np.concatenate([wr.ravel(), -wi.ravel(), wi.ravel(), wr.ravel()]),
                    (np.concatenate([rows, rows, rows + m, rows + m]),
                     np.concatenate([cols, cols + n, cols, cols + n]))), shape=(2 * m, 2 * n)).tocsc()
    i0 = int(np.argmin(V[:, 1]))
    i1 = int(np.argmax(np.linalg.norm(V - V[i0], axis=1)))
    pin = np.array([i0, i1, i0 + n, i1 + n])
    val = np.array([0., np.linalg.norm(V[i1] - V[i0]), 0., 0.])
    free = np.setdiff1d(np.arange(2 * n), pin)
    sol = lsqr(R[:, free], -R[:, pin] @ val, atol=1e-12, btol=1e-12, iter_lim=50000)[0]
    z = np.zeros(2 * n)
    z[pin], z[free] = val, sol
    return np.stack([z[:n], z[n:]], 1)


def abf(V, F, it=10):
    """Angle based flattening (Sheffer & de Sturler 2001): the plane angles closest to the 3D ones (relative squared
    error) under the triangle sum, the 2 pi sum around inner vertices and the sine (wheel) condition, solved by
    Newton with the exact Hessian of the energy; the UV is made from the angles by LSCM (lscm_angles)."""
    from scipy.sparse import coo_matrix, bmat, diags
    from scipy.sparse.linalg import spsolve
    m, n = len(F), len(V)
    beta = corner_angles(V, F)
    inner = ~boundary_vertices(F, n)
    # the wanted angles: around an inner vertex scaled to 2 pi (as in ABF)
    s = np.zeros(n)
    np.add.at(s, F.ravel(), beta.ravel())
    b = beta.copy()
    scale = np.where(inner, 2 * np.pi / np.maximum(s, 1e-12), 1.)
    b *= scale[F]
    b = np.clip(b, np.radians(1), np.pi - np.radians(1))
    w = 1 / b.ravel() ** 2
    a = b.ravel().copy()
    iv = np.nonzero(inner)[0]
    vrow = -np.ones(n, int)
    vrow[iv] = np.arange(len(iv))
    cv = F.ravel()  # vertex of each corner
    cid = np.arange(3 * m).reshape(m, 3)
    nxt, prv = cid[:, [1, 2, 0]].ravel(), cid[:, [2, 0, 1]].ravel()
    Jt = coo_matrix((np.ones(3 * m), (np.repeat(np.arange(m), 3), np.arange(3 * m))), shape=(m, 3 * m))
    ok = vrow[cv] >= 0
    Jv = coo_matrix((np.ones(ok.sum()), (vrow[cv[ok]], np.arange(3 * m)[ok])), shape=(len(iv), 3 * m))
    for _ in range(it):
        Ct = a.reshape(m, 3).sum(1) - np.pi
        Cv = np.zeros(len(iv))
        np.add.at(Cv, vrow[cv[ok]], a[ok])
        Cv -= 2 * np.pi
        ls = np.log(np.sin(a))
        Cl = np.zeros(len(iv))
        np.add.at(Cl, vrow[cv[ok]], ls[nxt[ok]] - ls[prv[ok]])
        ct = np.cos(a) / np.sin(a)
        Jl = coo_matrix((np.concatenate([ct[nxt[ok]], -ct[prv[ok]]]),
                         (np.concatenate([vrow[cv[ok]]] * 2), np.concatenate([nxt[ok], prv[ok]]))),
                        shape=(len(iv), 3 * m))
        J = bmat([[Jt], [Jv], [Jl]]).tocsr()
        C = np.concatenate([Ct, Cv, Cl])
        H = diags(2 * w + 1e-9)
        K = bmat([[H, J.T], [J, None]]).tocsc()
        g = 2 * w * (a - b.ravel())
        sol = spsolve(K, -np.concatenate([g, C]))
        da = sol[:3 * m]
        a = np.clip(a + da, 1e-4, np.pi - 1e-4)
        if np.abs(C).max() < 1e-9 and np.abs(da).max() < 1e-9:
            break
    return lscm_angles(V, F, a.reshape(m, 3))


def area_normals(X, F):
    n = np.zeros_like(X)
    fa = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fa)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-30)


def crease_vertices(V, F, crease):
    """Vertices on an edge whose two faces meet at more than crease degrees (Mesh.relax keeps them)."""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-30
    E = {}
    for f, t in enumerate(F):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            E.setdefault((min(a, b), max(a, b)), []).append(f)
    keep = np.zeros(len(V), bool)
    cos = np.cos(np.radians(crease))
    for (a, b), fs in E.items():
        if len(fs) == 2 and fn[fs[0]] @ fn[fs[1]] < cos:
            keep[a] = keep[b] = True
    return keep


def relax(V, F, degree, tangent=False, crease=180., free=None):
    """Mesh.relax of 3DCoat (see the module doc). free: optional mask of the vertices allowed to move."""
    A = uniform_adj(F, len(V))
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
    n = 1 if degree <= 1 else int(np.floor(degree)) + 1
    lam = degree / n
    move = np.ones(len(V), bool) if free is None else free.copy()
    if crease < 180:
        move &= ~crease_vertices(V, F, crease)
    X = V.astype(np.float64).copy()
    for _ in range(n):
        dv = (A @ X) / deg[:, None] - X
        if tangent:
            N = area_normals(X, F)
            dv -= (dv * N).sum(1, keepdims=True) * N
        X[move] += lam * dv[move]
    return X


def flatten(V, F, method):
    from uv_unfold import lscm
    return {'plane': lambda P: axis_plane(P, F), 'pca': plane, 'lscm': lambda P: lscm(P, F), 'arap': lambda P: arap(P, F),
            'abf': lambda P: abf(P, F)}[method](V)

def vrelax(V, F, degree):
    """Volume.relaxSurface(degree) of the surface volume, close copy: the topology stays and the shape moves as Mesh.relax
    with about 0.7 of the degree, no tangent (measured: 0.5 -> 0.35 residue 0.0027, 2 -> 1.3 residue 0.004)."""
    return relax(V, F, 0.7 * degree if degree <= 1 else 0.65 * degree)


def weld(V, F, rel=0.0001):
    """Mesh.weld(rel): vertices closer than rel x bounds diagonal become one, unused vertices go (3DCoat measured the
    same: gaps of 0.001 on a 3.46 diagonal weld at rel 0.001, not at 0.0001)."""
    from scipy.spatial import cKDTree
    tol = rel * np.linalg.norm(V.max(0) - V.min(0))
    rep = np.arange(len(V))
    for i, j in sorted(cKDTree(V).query_pairs(tol)):
        a, b = rep[i], rep[j]
        while rep[a] != a:
            a = rep[a]
        while rep[b] != b:
            b = rep[b]
        rep[max(a, b)] = min(a, b)
    for i in range(len(rep)):
        rep[i] = rep[rep[i]]
    F2 = rep[F]
    F2 = F2[(F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])]
    used, inv = np.unique(F2, return_inverse=True)
    return V[used], inv.reshape(-1, 3)


def reduce(V, F, faces):
    """reduceToPolycount(faces): half-edge collapse (the vertices left are input vertices). Open: quadric collapse of
    pymeshlab without optimal placement - also a subset of the input, error 0.0077 vs 3DCoat 0.0057 (640 faces of a
    1280 face noisy sphere, mean distance in units of the radius)."""
    import pymeshlab
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(V, F))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(faces), optimalplacement=False, preservetopology=True)
    m = ms.current_mesh()
    return m.vertex_matrix(), m.face_matrix()


def face_adjacency(F):
    """Pairs of faces sharing an edge (manifold edges only)."""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    f = np.tile(np.arange(len(F)), 3)
    key = e[:, 0].astype(np.int64) * (F.max() + 1) + e[:, 1]
    o = np.argsort(key, kind='stable')
    k, f = key[o], f[o]
    same = np.nonzero(k[1:] == k[:-1])[0]
    single = np.ones(len(same), bool)
    single[1:] &= k[same[1:]] != k[same[:-1]]  # three faces on an edge: keep the first pair
    return np.stack([f[same], f[same + 1]], 1)[single]


def charts(V, F, sharp=60., it=15):
    """Islands like Auto Seams (approximate): variational shape approximation (Cohen-Steiner et al. 2004) seeded by the six
    axis directions; a region grows over faces by the normal error, never over an edge sharper than `sharp`; the region
    normals are updated `it` times, each connected part is an island. Measured agreement with 3DCoat (share of faces in
    the matching island): prism3 1.0, box 1.0, prism6 0.91, prism12 0.75, prism24 0.79, sphere 0.73; not the rule on
    organic meshes (head: 607 islands vs 230) and the torus (6 vs 2)."""
    import heapq
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    fa = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    A = np.linalg.norm(fa, axis=1)
    N = fa / (A[:, None] + 1e-30)
    pr = face_adjacency(F)
    pr = pr[(N[pr[:, 0]] * N[pr[:, 1]]).sum(1) > np.cos(np.radians(sharp))]  # edges a region may cross
    adj = [[] for _ in F]
    for a, b in pr:
        adj[a].append(b)
        adj[b].append(a)
    P = np.vstack([np.eye(3), -np.eye(3)])
    lab = np.zeros(len(F), int)
    for _ in range(it):
        err = A[:, None] * ((N[:, None, :] - P[None]) ** 2).sum(2)
        best = np.argmax(N @ P.T, 1)
        lab = -np.ones(len(F), int)
        h = []
        for j in range(len(P)):
            e = np.where(best == j, err[:, j], np.inf)
            s = int(np.argmin(e))
            if np.isfinite(e[s]) and lab[s] < 0:
                lab[s] = j
                h += [(err[g, j], g, j) for g in adj[s]]
        heapq.heapify(h)
        while h:
            _, f, j = heapq.heappop(h)
            if lab[f] >= 0:
                continue
            lab[f] = j
            for g in adj[f]:
                if lab[g] < 0:
                    heapq.heappush(h, (err[g, j], g, j))
        while (lab < 0).any():  # faces behind sharp edges: a region of their own
            s = int(np.nonzero(lab < 0)[0][0])
            P = np.vstack([P, N[s]])
            j = len(P) - 1
            lab[s] = j
            st = [s]
            while st:
                f = st.pop()
                for g in adj[f]:
                    if lab[g] < 0 and N[g] @ P[j] > 0.5:
                        lab[g] = j
                        st.append(g)
        newP = np.array([fa[lab == j].sum(0) for j in range(len(P))])
        ok = np.linalg.norm(newP, axis=1) > 0
        P = newP[ok] / np.linalg.norm(newP[ok], axis=1, keepdims=True)
        m = -np.ones(len(ok), int)
        m[ok] = np.arange(ok.sum())
        lab = m[lab]
    same = pr[lab[pr[:, 0]] == lab[pr[:, 1]]]
    n = len(F)
    return connected_components(coo_matrix((np.ones(len(same)), (same[:, 0], same[:, 1])), shape=(n, n)),
                                directed=False)[1]


def pack(V, F, UVc, res=2048, rotate=True):
    """uv.pack(0, rotate): the islands of the per-corner UV packed into 0..1 at one texel density. Open copy: xatlas with
    the given islands, brute force, padding 2 of 2048 - fill 0.673 on the hero1 atlas (3DCoat 0.670), 0.843 on 24 rects
    (3DCoat 0.81 with rotation, 0.772 without; xatlas without rotation 0.778). Returns the new per-corner UV."""
    import xatlas
    key = np.concatenate([F.reshape(-1, 1).astype(np.float64), np.round(UVc.reshape(-1, 2), 7)], 1)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    uv = uk[:, 1:]
    uv = (uv - uv.min(0)) / (uv.max() - uv.min() + 1e-30)
    at = xatlas.Atlas()
    at.add_mesh(V[uk[:, 0].astype(int)].astype(np.float32), inv.ravel().reshape(-1, 3).astype(np.uint32), None,
                uv.astype(np.float32))
    co = xatlas.ChartOptions()
    co.use_input_mesh_uvs = True
    po = xatlas.PackOptions()
    po.resolution, po.padding, po.bilinear, po.rotate_charts, po.bruteForce = res, 2, True, rotate, True
    at.generate(co, po)
    _, idx, uvs = at[0]
    return uvs[idx]


def verify(d):
    import coat_probe as cp
    p = os.path.join(d, 'probe')
    for f in sorted(x for x in os.listdir(p) if '_r' in x and x.endswith('.obj')):
        nm, rest = f[:-4].split('_r')
        dg, t, c = rest.split('_')
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        X = cp.read_vf(os.path.join(p, f))[0]
        size = np.sqrt(((V - V.mean(0)) ** 2).sum(1).mean())
        Y = relax(V, F, float(dg), bool(int(t)), float(c))
        print(f'relax {f:26s} moved {np.sqrt(((X - V) ** 2).sum(1).mean()) / size:.4f} '
              f'residue {np.sqrt(((Y - X) ** 2).sum(1).mean()) / size:.6f}')
    for nm in sorted({x.split('_f')[0] for x in os.listdir(p) if '_f' in x}):
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        for meth, ours in ((0, 'plane'), (1, 'lscm'), (2, 'abf'), (3, 'arap')):
            q = os.path.join(p, f'{nm}_f{meth}.obj')
            if not os.path.exists(q):
                continue
            V2, F2 = cp.read_vf(q)
            C = cp.match_faces(F, F2) if len(F2) else None
            if C is None:
                continue
            ok = (C >= 0).all(1)
            U = flatten(V, F, ours)
            X = V2[C[ok]].reshape(-1, 3)[:, :2]
            print(f'flatten {nm:7s} {cp.METHODS[meth]:5s} ~ ours {ours:5s}: similarity residue '
                  f'{cp.procrustes(X, U[F[ok]].reshape(-1, 2)):.3f}')


def agreement(a, b):
    """Share of the faces lying in the island of b that most of their island of a falls into."""
    tot = 0
    for i in np.unique(a):
        tot += np.bincount(b[a == i]).max()
    return tot / len(a)


def verify_more(d):
    """The probe2/probe3 jobs (coat_probe.py make2): weld, reduce, Volume.relaxSurface, Auto Seams islands, uv.pack."""
    import coat_probe as cp
    import head_seams as hs
    from scipy.spatial import cKDTree
    from uv_from_obj import read_obj
    p = os.path.join(d, 'probe')
    ls = sorted(os.listdir(p))
    for f in [x for x in ls if '_w' in x and x.endswith('.obj')]:
        nm, rel = f[:-4].split('_w')
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        V2, F2 = cp.read_vf(os.path.join(p, f))
        W, G = weld(V, F, float(rel))
        print(f'weld {f:24s} vertices {len(V)} -> 3DCoat {len(V2)}, ours {len(W)}')
    for f in [x for x in ls if '_oreduce' in x and x.endswith('.obj')]:
        nm, n = f[:-4].split('_oreduce')
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        V2, F2 = cp.read_vf(os.path.join(p, f))
        W, G = reduce(V, F, int(n))
        r = np.linalg.norm(V - V.mean(0), axis=1).mean()
        tree = cKDTree(V)  # the distance of the dense input to the reduced surface, sampled at its vertices
        def err(X, Y):
            S = np.concatenate([X, X[Y].mean(1)])
            return tree.query(S)[0].mean() / r
        print(f'reduce {f:22s} faces 3DCoat {len(F2)} ours {len(G)}; vertices on the input 3DCoat '
              f'{(tree.query(V2)[0] < 1e-5).mean():.2f} ours {(tree.query(W)[0] < 1e-5).mean():.2f}; '
              f'face centre distance 3DCoat {err(V2, F2):.4f} ours {err(W, G):.4f}')
    for f in [x for x in ls if '_vrelax' in x and x.endswith('.obj')]:
        from scipy.optimize import linear_sum_assignment
        from scipy.spatial.distance import cdist
        nm, dg = f[:-4].split('_vrelax')
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        V2, F2 = cp.read_vf(os.path.join(p, f))
        if len(V2) != len(V):
            print(f'vrelax {f}: vertices {len(V)} -> {len(V2)}, not the surface volume')
            continue
        Y = vrelax(V, F, float(dg))
        r = np.linalg.norm(V - V.mean(0), axis=1).mean()
        i, j = linear_sum_assignment(cdist(Y, V2))
        print(f'vrelax {f:22s} moved {np.linalg.norm(V2[j] - V[i], axis=1).mean() / r:.4f} '
              f'residue {np.linalg.norm(V2[j] - Y[i], axis=1).mean() / r:.4f}')
    for f in [x for x in ls if x.endswith('_auto.obj')]:
        nm = f[:-9]
        V, F = cp.read_vf(os.path.join(p, nm + '.obj'))
        if len(F) > 5000:
            print(f'charts {nm}: {len(F)} faces, skipped (VSA in Python is slow, and not the rule on organic meshes)')
            continue
        V2, T2, F2, FT2 = read_obj(os.path.join(p, f))
        comp = hs.face_components(FT2)
        isl = comp[cKDTree(V2[F2].mean(1)).query(V[F].mean(1))[1]]
        o = charts(V, F)
        print(f'charts {nm:8s} islands 3DCoat {isl.max() + 1} ours {o.max() + 1} agreement '
              f'{agreement(isl, o):.2f}/{agreement(o, isl):.2f}')
    for f in [x for x in ls if '_p' in x and x.endswith('.obj')]:
        nm, rot = f[:-4].split('_p')
        V, T, F, FT = read_obj(os.path.join(p, nm + '.obj'))
        _, T2, F2, FT2 = read_obj(os.path.join(p, f))
        def fill(U):
            return np.abs(np.cross(U[:, 1] - U[:, 0], U[:, 2] - U[:, 0])).sum() / 2
        print(f'pack {f:14s} fill input {fill(T[FT]):.3f} 3DCoat {fill(T2[FT2]):.3f} '
              f'ours {fill(pack(V, F, T[FT], rotate=bool(int(rot)))):.3f}')


def main():
    import coat_probe as cp
    cmd = sys.argv[1]
    if cmd == 'verify':
        verify(sys.argv[2])
        return verify_more(sys.argv[2])
    V, F = cp.read_vf(sys.argv[2])
    if cmd == 'relax':
        a = sys.argv[4:]
        X = relax(V, F, float(a[0]), bool(int(a[1])) if len(a) > 1 else False, float(a[2]) if len(a) > 2 else 180.)
        cp.write_obj(sys.argv[3], X, F)
    elif cmd == 'flatten':
        U = flatten(V, F, sys.argv[4])
        cp.write_obj(sys.argv[3], np.c_[U, np.zeros(len(U))], F)
    elif cmd == 'vrelax':
        cp.write_obj(sys.argv[3], vrelax(V, F, float(sys.argv[4])), F)
    elif cmd == 'weld':
        cp.write_obj(sys.argv[3], *weld(V, F, float(sys.argv[4]) if len(sys.argv) > 4 else 0.0001))
    elif cmd == 'reduce':
        cp.write_obj(sys.argv[3], *reduce(V, F, int(sys.argv[4])))
    elif cmd == 'charts':
        isl = charts(V, F, float(sys.argv[4]) if len(sys.argv) > 4 else 60.)
        np.save(sys.argv[3], isl)
        print(f'{sys.argv[2]}: {isl.max() + 1} islands -> {sys.argv[3]}')
    elif cmd == 'pack':
        from uv_from_obj import read_obj
        from uv_unfold import write_obj
        V, T, F, FT = read_obj(sys.argv[2])
        write_obj(sys.argv[3], V, F, pack(V, F, T[FT], rotate=len(sys.argv) <= 4 or bool(int(sys.argv[4]))))


if __name__ == '__main__':
    main()
