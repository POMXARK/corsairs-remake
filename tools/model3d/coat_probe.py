#!/usr/bin/env python3
"""Black-box study of 3DCoat tools: what each one does, measured, and which open algorithm gives the same result.

coat_probe.py make dir [auto_uv.obj]   test meshes and the job list (dir/probe/*.obj, dir/probe.txt)
coat_probe.py make2 dir [solid.obj [atlas_uv.obj]]  probe 2: ABF / stripe on strips, volume tools, reduce, weld,
                                       Auto Seams on solids, pack
coat_probe.py run dir                  3DCoat on the Windows PC runs the list (coat_run.sh ... probe), results back
coat_probe.py seams auto_uv.obj [parts.npy]  where Auto Seams cut (seams against all edges, islands)
coat_probe.py analyze dir              compares every result with the open algorithms (table on stdout,
                                       dir/report.json)

The 3DCoat EULA (4.1) forbids disassembly, so nothing is decompiled: known meshes go in through the public Python API
(coat.uv.flattenSingleIsland with each of its methods, Mesh.relax with its degree / tangent / crease), the output is
compared with LSCM, ARAP, a plane projection (flatten) and with uniform / cotangent Laplacian smoothing (relax), and the
parameters of the open algorithm are fitted to the output.
Test meshes: a half cylinder (developable: every good flattening is exact), a spherical cap, a saddle with very uneven
triangles (LSCM depends on the triangle shapes, angle-based methods less), the largest islands of a real head UV
(auto_uv.obj, the Auto Seams output of coat_run.sh); a noisy sphere and a noisy box (relax, creases).
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from coat_algos import arap, cot_laplacian, plane, uniform_adj  # noqa: E402

WIN = os.environ.get('WIN', 'User@192.168.1.214')
KEY = os.environ.get('KEY', os.path.expanduser('~/.ssh/win_remake'))
RD = os.environ.get('RD', 'C:/Users/User/cof/coat')
METHODS = {0: 'plane', 1: 'LSCM', 2: 'ABF', 3: 'GU', 4: 'stripe'}
RELAX = [(d, t, 180.) for t in (0, 1) for d in (0.1, 0.3, 0.5, 1.0, 2.0, 5.0)]


# ---------------------------------------------------------------- meshes
def grid(nu, nv):
    F = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a, b, c, d = i * nv + j, (i + 1) * nv + j, (i + 1) * nv + j + 1, i * nv + j + 1
            F += [(a, b, c), (a, c, d)]
    return np.array(F)


def half_cylinder():
    u, v = np.meshgrid(np.linspace(0, np.pi, 25), np.linspace(-1, 1, 13), indexing='ij')
    return np.stack([np.cos(u), v, np.sin(u)], -1).reshape(-1, 3), grid(25, 13)


def cap():
    rings, seg = 10, 36
    V = [(0, 0, 1)]
    for r in range(1, rings + 1):
        th = np.radians(60) * r / rings
        for s in range(seg):
            ph = 2 * np.pi * s / seg
            V.append((np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)))
    F = [(0, 1 + s, 1 + (s + 1) % seg) for s in range(seg)]
    for r in range(rings - 1):
        o, p = 1 + r * seg, 1 + (r + 1) * seg
        for s in range(seg):
            a, b, c, d = o + s, p + s, p + (s + 1) % seg, o + (s + 1) % seg
            F += [(a, b, c), (a, c, d)]
    return np.array(V, float), np.array(F)


def saddle():
    x = np.linspace(0, 1, 21) ** 2.5 * 2 - 1  # dense on one side: triangles of very different shape
    y = np.linspace(-1, 1, 11)
    X, Y = np.meshgrid(x, y, indexing='ij')
    return np.stack([X, Y, 0.3 * (X ** 2 - Y ** 2)], -1).reshape(-1, 3), grid(21, 11)


def head_islands(path, n=3):
    from uv_from_obj import read_obj
    import head_seams as hs
    V, T, F, FT = read_obj(path)
    ok = (FT >= 0).all(1)
    comp = hs.face_components(FT[ok])
    fi = np.nonzero(ok)[0]
    out = []
    for c in np.argsort(-np.bincount(comp))[:n]:
        f = F[fi[comp == c]]
        vid, loc = np.unique(f, return_inverse=True)
        out.append((V[vid], loc.reshape(-1, 3)))
    return out


def noisy_sphere():
    import trimesh
    m = trimesh.creation.icosphere(3)
    r = np.random.default_rng(0)
    return m.vertices * (1 + 0.04 * r.standard_normal((len(m.vertices), 1))), m.faces


def noisy_box():
    import trimesh
    m = trimesh.creation.box((2, 2, 2))
    for _ in range(3):
        m = m.subdivide()
    m.merge_vertices()
    r = np.random.default_rng(1)
    return m.vertices + 0.02 * r.standard_normal(m.vertices.shape), m.faces


def write_obj(path, V, F):
    with open(path, 'w') as o:
        o.write(''.join(f'v {x:.6f} {y:.6f} {z:.6f}\n' for x, y, z in V))
        o.write(''.join(f'f {a + 1} {b + 1} {c + 1}\n' for a, b, c in F))


def read_vf(path):
    V, F = [], []
    for ln in open(path):
        w = ln.split()
        if not w:
            continue
        if w[0] == 'v':
            V.append([float(x) for x in w[1:4]])
        elif w[0] == 'f':
            idx = [int(x.split('/')[0]) - 1 for x in w[1:]]
            F += [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]
    return np.array(V), np.array(F)


def make(d, auto_uv=None):
    p = os.path.join(d, 'probe')
    os.makedirs(p, exist_ok=True)
    meshes = {'cyl': half_cylinder(), 'cap': cap(), 'saddle': saddle()}
    if auto_uv:
        for k, m in enumerate(head_islands(auto_uv)):
            meshes[f'head{k}'] = m
    lines = []
    for name, (V, F) in meshes.items():
        write_obj(os.path.join(p, name + '.obj'), V, F)
        lines += [f'probe/{name}.obj flatten {m} probe/{name}_f{m}.obj' for m in METHODS]
    for name, (V, F) in {'sphere': noisy_sphere(), 'box': noisy_box()}.items():
        write_obj(os.path.join(p, name + '.obj'), V, F)
        for dg, t, c in RELAX + ([(1.0, 0, 30.)] if name == 'box' else []):
            lines.append(f'probe/{name}.obj relax {dg} {t} {c:g} probe/{name}_r{dg}_{t}_{c:g}.obj')
    open(os.path.join(d, 'probe.txt'), 'w').write('\n'.join(lines) + '\n')
    print(f'{d}: {len(meshes) + 2} meshes, {len(lines)} jobs')


def strips():
    """Strips for ABF / stripe: straight, bent along an arc (developable), twisted half a turn (not developable)."""
    n, w = 41, 4
    t, s = np.meshgrid(np.linspace(0, 1, n), np.linspace(-0.5, 0.5, w), indexing='ij')
    out = {'strip': np.stack([4 * t, 0.4 * s, 0 * t], -1)}
    a = t * np.pi * 1.2
    out['arc'] = np.stack([2 * np.cos(a), 0.4 * s, 2 * np.sin(a)], -1)
    b = t * np.pi
    out['twist'] = np.stack([4 * t, 0.4 * s * np.cos(b), 0.4 * s * np.sin(b)], -1)
    return {k: (v.reshape(-1, 3), grid(n, w)) for k, v in out.items()}


def solids():
    """Closed bodies for Auto Seams: prisms with side faces meeting at 120 / 150 / 165 degrees (dihedral turn 60, 30,
    15), a smooth cylinder, a sphere, a torus, a box."""
    import trimesh
    out = {}
    for k in (3, 6, 12, 24):
        m = trimesh.creation.cylinder(radius=1, height=2, sections=k)
        m = m.subdivide().subdivide()
        out[f'prism{k}'] = m
    out['sphere3'] = trimesh.creation.icosphere(3)
    out['torus'] = trimesh.creation.torus(1, 0.35, major_sections=48, minor_sections=16) \
        if hasattr(trimesh.creation, 'torus') else trimesh.creation.capsule(2, 0.5)
    b = trimesh.creation.box((2, 1, 0.5))
    for _ in range(3):
        b = b.subdivide()
    out['box'] = b
    for m in out.values():
        m.merge_vertices()
    return {k: (np.asarray(m.vertices), np.asarray(m.faces)) for k, m in out.items()}


def write_obj_uv(path, V, F, UVc):
    key, inv = np.unique(np.round(UVc.reshape(-1, 2), 7), axis=0, return_inverse=True)
    FT = inv.reshape(-1, 3)
    with open(path, 'w') as o:
        o.write(''.join(f'v {x:.6f} {y:.6f} {z:.6f}\n' for x, y, z in V))
        o.write(''.join(f'vt {u:.6f} {v:.6f}\n' for u, v in key))
        o.write(''.join(f'f {a + 1}/{d + 1} {b + 1}/{e + 1} {c + 1}/{g + 1}\n' for (a, b, c), (d, e, g) in zip(F, FT)))


def rects():
    """Islands to pack: 24 flat rectangles of known sizes, each its own island, laid in a row in UV."""
    r = np.random.default_rng(3)
    V, F, U = [], [], []
    x0 = 0.
    for i in range(24):
        w, h = r.uniform(0.1, 1.0), r.uniform(0.1, 1.0)
        o = len(V)
        q = [(0, 0), (w, 0), (w, h), (0, h)]
        V += [(x0 + a, b, 0.) for a, b in q]
        F += [(o, o + 1, o + 2), (o, o + 2, o + 3)]
        U += [[(x0 + q[0][0], q[0][1]), (x0 + q[1][0], q[1][1]), (x0 + q[2][0], q[2][1])],
              [(x0 + q[0][0], q[0][1]), (x0 + q[2][0], q[2][1]), (x0 + q[3][0], q[3][1])]]
        x0 += w + 0.2
    U = np.array(U) / x0
    return np.array(V), np.array(F), U


def holed():
    """Spheres with a round hole of 10 / 20 / 35 degrees (closeHoles), and a sphere split along its equator with the
    halves 0.001 / 0.01 apart (weld)."""
    import trimesh
    out = {}
    base = trimesh.creation.icosphere(3)
    V, F = np.asarray(base.vertices), np.asarray(base.faces)
    for deg in (10, 20, 35):
        c = V[F].mean(1)
        keep = c[:, 2] < np.cos(np.radians(deg))
        out[f'hole{deg}'] = (V, F[keep])
    for gap in (0.001, 0.01):
        c = V[F].mean(1)
        top = c[:, 2] > 0
        V2 = np.concatenate([V, V + [0, 0, gap]])
        F2 = np.concatenate([F[~top], F[top] + len(V)])
        out[f'split{gap:g}'] = (V2, F2)
    return out


def make2(d, solid=None, atlas=None):
    """Probe 2: ABF and stripe on strips, volume tools, reduce, weld, then the UV room jobs (Auto Seams on solids and
    the head, pack of rectangles and of an atlas)."""
    p = os.path.join(d, 'probe')
    os.makedirs(p, exist_ok=True)
    lines = []
    for name, (V, F) in strips().items():
        write_obj(os.path.join(p, name + '.obj'), V, F)
        lines += [f'probe/{name}.obj flatten {m} probe/{name}_f{m}.obj' for m in METHODS]
    V, F = noisy_sphere()
    write_obj(os.path.join(p, 'sphere.obj'), V, F)
    for spec in ('vrelax:0.5', 'vrelax:2', 'voxrelax:3', 'voxrelax:10', 'vfaces:2000', 'reduce:640', 'reduce:200'):
        lines.append(f'probe/sphere.obj ops {spec} 0 probe/sphere_o{spec.replace(":", "")}.obj')
    for name, (V, F) in holed().items():
        write_obj(os.path.join(p, name + '.obj'), V, F)
        if name.startswith('hole'):
            for sz in (5, 20, 60):
                lines.append(f'probe/{name}.obj ops closeholes:{sz} 0 probe/{name}_c{sz}.obj')
        else:
            for rel in (0.0001, 0.001, 0.01):
                lines.append(f'probe/{name}.obj ops weld:{rel} 0 probe/{name}_w{rel:g}.obj')
    for name, (V, F) in solids().items():
        write_obj(os.path.join(p, name + '.obj'), V, F)
        lines.append(f'probe/{name}.obj autoseams probe/{name}_auto.obj')
    if solid:
        import shutil
        shutil.copy(solid, os.path.join(p, 'head.obj'))
        lines.append('probe/head.obj autoseams probe/head_auto.obj')
    V, F, U = rects()
    write_obj_uv(os.path.join(p, 'rects.obj'), V, F, U)
    lines += ['probe/rects.obj pack 0 probe/rects_p0.obj', 'probe/rects.obj pack 1 probe/rects_p1.obj']
    if atlas:
        import shutil
        shutil.copy(atlas, os.path.join(p, 'atlas.obj'))
        lines.append('probe/atlas.obj pack 1 probe/atlas_p1.obj')
    open(os.path.join(d, 'probe.txt'), 'w').write('\n'.join(lines) + '\n')
    print(f'{d}: {len(lines)} jobs')


def run(d):
    ssh = ['ssh', '-i', KEY, WIN]
    rdw = RD.replace('/', '\\')
    subprocess.run(ssh + [f'rmdir /s /q {rdw}\\probe 2>nul & exit 0'], check=True)
    tar = subprocess.Popen(['tar', '-cf', '-', '-C', d, 'probe'], stdout=subprocess.PIPE)
    subprocess.run(ssh + [f'tar -xf - -C {rdw}'], stdin=tar.stdout, check=True)
    tar.wait()
    subprocess.run([os.path.join(HERE, 'coat_run.sh'), os.path.join(d, 'probe.txt'), os.path.join(d, 'coat_out.obj'),
                    'probe'], check=True)
    get = subprocess.Popen(ssh + [f'tar -cf - -C {rdw} probe'], stdout=subprocess.PIPE)
    subprocess.run(['tar', '-xf', '-', '-C', d], stdin=get.stdout, check=True)
    get.wait()


# ---------------------------------------------------------------- open algorithms
def distortion(V, F, U):
    """Mean |log(s1/s2)| (angles kept: 0), mean |log area ratio| (areas kept: 0), share of flipped faces."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    ex = (b - a) / (np.linalg.norm(b - a, axis=1, keepdims=True) + 1e-30)
    nz = np.cross(b - a, c - a)
    A3 = np.linalg.norm(nz, axis=1) / 2
    nz /= 2 * A3[:, None] + 1e-30
    ey = np.cross(nz, ex)
    P = np.stack([np.stack([((b - a) * ex).sum(1), ((b - a) * ey).sum(1)], 1),
                  np.stack([((c - a) * ex).sum(1), ((c - a) * ey).sum(1)], 1)], 2)  # (m,2,2) columns
    Q = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)
    J = Q @ np.linalg.inv(P + 1e-12 * np.eye(2))
    s = np.linalg.svd(J, compute_uv=False)
    det = np.linalg.det(J)
    A2 = np.abs(det) * A3
    k = A2.sum() / A3.sum()
    w = A3 / A3.sum()
    return {'angle': float((w * np.abs(np.log((s[:, 0] + 1e-12) / (s[:, 1] + 1e-12)))).sum()),
            'area': float((w * np.abs(np.log((A2 + 1e-30) / (k * A3 + 1e-30)))).sum()),
            'flip': float((det * np.sign(np.median(det)) < 0).mean())}


def procrustes(U, R):
    """RMS of U against R after the best similarity (with mirror), in units of R's size."""
    u, r = U - U.mean(0), R - R.mean(0)
    best = 1e9
    for m in (1, -1):
        uu = u * [1, m]
        H = uu.T @ r
        x, s, yt = np.linalg.svd(H)
        Rot = x @ yt
        if np.linalg.det(Rot) < 0:
            x[:, 1] *= -1
            Rot = x @ yt
        sc = s.sum() / (uu ** 2).sum()
        best = min(best, np.sqrt(((sc * uu @ Rot - r) ** 2).sum(1).mean()) / np.sqrt((r ** 2).sum(1).mean()))
    return float(best)


def edge_faces(F):
    E = {}
    for f, t in enumerate(F):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            E.setdefault((min(a, b), max(a, b)), []).append(f)
    return E


def match_faces(F, F2, tries=400):
    """Face correspondence of two copies of one mesh with other vertex and face numbering (3DCoat renumbers both and
    may split a vertex): propagation over shared edges from a seed pair, each seed of F2 with each corner rotation
    tried against face 0 of F. Returns corner map C (len(F), 3): C[i, k] is the vertex of F2 at corner k of face i,
    or None when no seed gives a consistent cover of 99 % of the faces."""
    from collections import deque
    E1, E2 = edge_faces(F), edge_faces(F2)
    val1 = np.bincount(F.ravel(), minlength=F.max() + 1)
    val2 = np.bincount(F2.ravel(), minlength=F2.max() + 1)
    want = sorted(val1[F[0]])
    seeds = [j for j in range(len(F2)) if sorted(val2[F2[j]]) == want][:tries]
    for j in seeds:
        for rot in range(3):
            for flip in (False, True):
                t2 = list(F2[j][[(rot + k) % 3 for k in range(3)]])
                if flip:
                    t2 = t2[::-1]
                C = np.full((len(F), 3), -1)
                used = np.zeros(len(F2), bool)
                C[0] = t2
                used[j] = True
                q, bad, n = deque([0]), 0, 1
                while q and bad < 5:
                    i = q.popleft()
                    L = dict(zip(F[i], C[i]))
                    fo = None
                    for k in range(3):
                        a, b = int(F[i, k]), int(F[i, (k + 1) % 3])
                        nb = [x for x in E1.get((min(a, b), max(a, b)), []) if x != i]
                        if len(nb) != 1:
                            continue
                        oa, ob = int(L[a]), int(L[b])
                        cand = [x for x in E2.get((min(oa, ob), max(oa, ob)), [])
                                if sorted(F2[x]) != sorted(C[i])]
                        if len(cand) != 1:
                            continue
                        f1, f2 = nb[0], cand[0]
                        c1 = [v for v in F[f1] if v not in (a, b)][0]
                        c2 = [v for v in F2[f2] if v not in (oa, ob)][0]
                        m = {a: oa, b: ob, c1: c2}
                        row = [m[v] for v in F[f1]]
                        if C[f1, 0] >= 0:
                            bad += list(C[f1]) != row
                            continue
                        if used[f2]:
                            bad += 1
                            continue
                        C[f1], used[f2] = row, True
                        n += 1
                        q.append(f1)
                if bad < 5 and n >= 0.99 * len(F):
                    return C
    return None


def analyze_flatten(d, rep):
    from uv_unfold import lscm
    names = sorted({f.split('_f')[0] for f in os.listdir(os.path.join(d, 'probe')) if '_f' in f})
    print('flatten: angle / area distortion (0 = kept), flipped share; similarity RMS to our LSCM | ARAP | plane')
    for nm in names:
        V, F = read_vf(os.path.join(d, 'probe', nm + '.obj'))
        ours = {'LSCM': lscm(V, F), 'ARAP': arap(V, F), 'plane': plane(V)}
        for k, U in ours.items():
            m = distortion(V, F, U)
            rep.setdefault('flatten', {}).setdefault(nm, {})['ours ' + k] = m
            print(f'  {nm:7s} ours {k:6s} angle {m["angle"]:.3f} area {m["area"]:.3f} flip {m["flip"]:.3f}')
        for meth, mn in METHODS.items():
            p = os.path.join(d, 'probe', f'{nm}_f{meth}.obj')
            if not os.path.exists(p):
                print(f'  {nm:7s} 3DCoat {mn:6s} no output')
                continue
            V2, F2 = read_vf(p)
            if not len(F2):
                print(f'  {nm:7s} 3DCoat {mn:6s} empty output')
                rep['flatten'][nm]['3DCoat ' + mn] = {'faces': 0}
                continue
            C = match_faces(F, F2)
            if C is None:
                print(f'  {nm:7s} 3DCoat {mn:6s} {len(V2)} v {len(F2)} f: faces not matched')
                rep['flatten'][nm]['3DCoat ' + mn] = {'verts': len(V2), 'faces': len(F2)}
                continue
            okf = (C >= 0).all(1)
            Vc = V[F[okf]].reshape(-1, 3)  # corners as separate vertices: per corner positions and UV
            Fc = np.arange(3 * okf.sum()).reshape(-1, 3)
            X = V2[C[okf]].reshape(-1, 3)
            U = X[:, :2] if np.ptp(X[:, 2]) < 1e-6 * np.ptp(X) else plane(X)
            m = distortion(Vc, Fc, U)
            m.update({f'rms_{k}': procrustes(U, R[F[okf]].reshape(-1, 2)) for k, R in ours.items()})
            m['z_range'] = float(np.ptp(X[:, 2]))
            m['split_vertices'] = int(len(V2) - len(V))
            rep['flatten'][nm]['3DCoat ' + mn] = m
            print(f'  {nm:7s} 3DCoat {mn:6s} angle {m["angle"]:.3f} area {m["area"]:.3f} flip {m["flip"]:.3f} | '
                  f'{m["rms_LSCM"]:.3f} {m["rms_ARAP"]:.3f} {m["rms_plane"]:.3f}')


def smooth_steps(V, F, lam, steps, kind, tangent):
    n = len(V)
    W = uniform_adj(F, n) if kind == 'uniform' else cot_laplacian(V, F)
    deg = np.asarray(W.sum(1)).ravel()
    X = V.copy()
    for _ in range(steps):
        dv = (W @ X) / deg[:, None] - X
        if tangent:
            import trimesh
            N = trimesh.Trimesh(X, F, process=False).vertex_normals
            dv -= (dv * N).sum(1, keepdims=True) * N
        X = X + lam * dv
    return X


def analyze_relax(d, rep):
    print('relax: displacement RMS (of the mesh size) and the best open match: kind, lambda, steps, RMS left')
    for nm in ('sphere', 'box'):
        V, F = read_vf(os.path.join(d, 'probe', nm + '.obj'))
        size = np.sqrt(((V - V.mean(0)) ** 2).sum(1).mean())
        for f in sorted(x for x in os.listdir(os.path.join(d, 'probe')) if x.startswith(nm + '_r') and x.endswith('.obj')):
            V2, F2 = read_vf(os.path.join(d, 'probe', f))
            if len(V2) == len(V) and len(F2) == len(F) and (F2 == F).all():
                X = V2
            else:
                print(f'  {f}: other topology {len(V2)} v')
                continue
            moved = np.sqrt(((X - V) ** 2).sum(1).mean()) / size
            import trimesh
            N = trimesh.Trimesh(V, F, process=False).vertex_normals
            dv = X - V
            normal_share = float(np.sqrt(((dv * N).sum(1) ** 2).sum() / ((dv ** 2).sum() + 1e-30)))
            best = (1e9,)
            tangent = '_1_' in f
            for kind in ('uniform', 'cot'):
                for lam in (0.1, 0.25, 0.5, 0.75, 1.0):
                    Y = V.copy()
                    for st in range(1, 61):
                        Y = smooth_steps(Y, F, lam, 1, kind, tangent)
                        r = np.sqrt(((Y - X) ** 2).sum(1).mean()) / size
                        if r < best[0]:
                            best = (r, kind, lam, st)
            vol0 = abs(trimesh.Trimesh(V, F, process=False).volume)
            vol1 = abs(trimesh.Trimesh(X, F, process=False).volume)
            rep.setdefault('relax', {})[f] = {'moved': float(moved), 'normal_share': normal_share,
                                              'volume_ratio': float(vol1 / vol0), 'best': best[1:],
                                              'rms_left': float(best[0])}
            print(f'  {f:26s} moved {moved:.4f} normal share {normal_share:.2f} volume {vol1 / vol0:.4f} | '
                  f'{best[1]} lam {best[2]} steps {best[3]} rms {best[0]:.4f}')


def seams(path, parts=None):
    """What 3DCoat Auto Seams cut on a mesh: the seam edges (where the UV corners of two faces differ) against all
    edges - dihedral angle, facing, height, part - and the islands with the distortion of their UV."""
    from uv_from_obj import read_obj
    import head_seams as hs
    V, T, F, FT = read_obj(path)
    ok = (FT >= 0).all(1)
    print(f'{path}: {len(F)} faces, {int((~ok).sum())} without UV')
    E = {}
    for f in np.nonzero(ok)[0]:
        for k in range(3):
            a, b = F[f, k], F[f, (k + 1) % 3]
            ta, tb = FT[f, k], FT[f, (k + 1) % 3]
            E.setdefault((min(a, b), max(a, b)), []).append((f, {a: ta, b: tb}))
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-30
    rows = []
    for (a, b), lst in E.items():
        if len(lst) != 2:
            continue
        (f1, m1), (f2, m2) = lst
        seam = m1[a] != m2[a] or m1[b] != m2[b]
        dih = np.degrees(np.arccos(np.clip((fn[f1] * fn[f2]).sum(), -1, 1)))
        n = fn[f1] + fn[f2]
        n /= np.linalg.norm(n) + 1e-30
        rows.append((seam, dih, n[2], (V[a, 1] + V[b, 1]) / 2, np.linalg.norm(V[a] - V[b]), f1, f2))
    R = np.array(rows, float)
    s_, al = R[R[:, 0] == 1], R
    y0, y1 = V[:, 1].min(), V[:, 1].max()
    out = {'edges': len(R), 'seam_edges': len(s_), 'seam_length_share': float(s_[:, 4].sum() / al[:, 4].sum())}
    for nm, col in (('dihedral_deg', 1), ('normal_z', 2)):
        out[nm] = {'seams': float(s_[:, col].mean()), 'all': float(al[:, col].mean())}
    out['height'] = {'seams': float(((s_[:, 3] - y0) / (y1 - y0)).mean()), 'all': float(((al[:, 3] - y0) / (y1 - y0)).mean())}
    out['facing_front_share'] = {'seams': float((s_[:, 2] > 0.5).mean()), 'all': float((al[:, 2] > 0.5).mean())}
    out['facing_back_share'] = {'seams': float((s_[:, 2] < -0.5).mean()), 'all': float((al[:, 2] < -0.5).mean())}
    if parts is not None and len(parts) == len(F):
        P = {}
        for r in s_:
            for f in (int(r[5]), int(r[6])):
                P[int(parts[f])] = P.get(int(parts[f]), 0) + 1
        tot = np.bincount(parts.astype(int), minlength=11)
        out['seam_sides_per_part'] = {k: round(v / max(tot[k], 1), 3) for k, v in sorted(P.items())}
    comp = hs.face_components(FT[ok])
    fi = np.nonzero(ok)[0]
    isl = []
    for c in range(comp.max() + 1):
        f = fi[comp == c]
        vid, loc = np.unique(F[f], return_inverse=True)
        tv, tl = np.unique(FT[f], return_inverse=True)
        Fl, Tl = loc.reshape(-1, 3), tl.reshape(-1, 3)
        # per face corner UV in the local vertex order (a seam inside the island is not possible: one corner each)
        U = np.zeros((len(vid), 2))
        U[Fl.ravel()] = T[tv[Tl.ravel()]]
        m = distortion(V[vid], Fl, U)
        isl.append((len(f), m['angle'], m['area']))
    isl = np.array(isl)
    out['islands'] = len(isl)
    out['island_faces'] = {'max': int(isl[:, 0].max()), 'median': float(np.median(isl[:, 0])),
                           'under_10': int((isl[:, 0] < 10).sum())}
    w = isl[:, 0] / isl[:, 0].sum()
    out['island_distortion_mean'] = {'angle': float((w * isl[:, 1]).sum()), 'area': float((w * isl[:, 2]).sum())}
    big = isl[np.argsort(-isl[:, 0])[:8]]
    out['largest'] = [{'faces': int(a), 'angle': round(b, 3), 'area': round(c, 3)} for a, b, c in big]
    print(json.dumps(out, indent=1))
    return out


def analyze(d):
    rep = {}
    analyze_flatten(d, rep)
    analyze_relax(d, rep)
    json.dump(rep, open(os.path.join(d, 'report.json'), 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    cmd, d = sys.argv[1], sys.argv[2]
    {'make': lambda: make(d, sys.argv[3] if len(sys.argv) > 3 else None), 'run': lambda: run(d),
     'make2': lambda: make2(d, *(sys.argv[3:5] + [None] * 2)[:2]),
     'analyze': lambda: analyze(d),
     'seams': lambda: seams(d, np.load(sys.argv[3]) if len(sys.argv) > 3 else None)}[cmd]()
