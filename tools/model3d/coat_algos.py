#!/usr/bin/env python3
"""Open copies of the 3DCoat tools the head pipeline uses, found by the black-box probe (coat_probe.py): the same
result without 3DCoat, on Linux, for any mesh.

coat_algos.py relax in.obj out.obj degree [tangent 0/1] [crease_deg]   = Mesh.relax(degree, tangent, crease)
coat_algos.py flatten in.obj out.obj plane|lscm|arap                     = uv.flattenSingleIsland(m, 0 | 1 | 3)
coat_algos.py verify probe_dir                                           how close each copy is to the 3DCoat output

What 3DCoat does (measured, docs/coat-tools.md):
- Mesh.relax: uniform (umbrella) Laplacian, every vertex moves to the mean of its edge neighbours by lambda. degree
  <= 1 is one step with lambda = degree; degree > 1 is n = floor(degree) + 1 steps with lambda = degree / n. tangent:
  the step without its part along the vertex normal (area weighted, of the current mesh, every step). crease: the
  vertices of an edge whose faces meet at more than crease degrees do not move. Residue against 3DCoat 0.0000.
- flattenSingleIsland method 0 = projection on the best plane of the island (PCA), 1 = LSCM (Levy et al. 2002), 2 =
  ABF (angles as LSCM, less area stretch; no open copy here), 3 = GU "globally uniform" = close to ARAP (Liu et al.
  2008): nearly equal areas, angles a bit worse, 4 = stripe (nothing for islands that are not strips).
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
    return {'plane': plane, 'lscm': lambda P: lscm(P, F), 'arap': lambda P: arap(P, F)}[method](V)


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
        for meth, ours in ((0, 'plane'), (1, 'lscm'), (3, 'arap')):
            q = os.path.join(p, f'{nm}_f{meth}.obj')
            V2, F2 = cp.read_vf(q)
            C = cp.match_faces(F, F2) if len(F2) else None
            if C is None:
                continue
            ok = (C >= 0).all(1)
            U = flatten(V, F, ours)
            X = V2[C[ok]].reshape(-1, 3)[:, :2]
            print(f'flatten {nm:7s} {cp.METHODS[meth]:5s} ~ ours {ours:5s}: similarity residue '
                  f'{cp.procrustes(X, U[F[ok]].reshape(-1, 2)):.3f}')


def main():
    import coat_probe as cp
    cmd = sys.argv[1]
    if cmd == 'verify':
        return verify(sys.argv[2])
    V, F = cp.read_vf(sys.argv[2])
    if cmd == 'relax':
        a = sys.argv[4:]
        X = relax(V, F, float(a[0]), bool(int(a[1])) if len(a) > 1 else False, float(a[2]) if len(a) > 2 else 180.)
        cp.write_obj(sys.argv[3], X, F)
    elif cmd == 'flatten':
        U = flatten(V, F, sys.argv[4])
        cp.write_obj(sys.argv[3], np.c_[U, np.zeros(len(U))], F)


if __name__ == '__main__':
    main()
