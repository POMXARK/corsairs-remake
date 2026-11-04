#!/usr/bin/env python3
"""Tools that change one region of a head (a set of parts of head_parts.py, or any faces), and the score of a region.

head_tools.py in.glb out.glb --views f.png l.png b.png r.png --parts parts.npy --region eyes[,mouth] TOOL [k=v ...]
head_tools.py --list                      the tools and their parameters
  -> out.glb, and out_pass.png: the region before and after next to the view (magenta: the region)

The region is the parts named in --region (head_parts.EN) or 'faces:file.npy' (a bool mask or face ids). Geometry
tools move only the vertices inside the region (its border stays, the rest of the head does not move); texture tools
change only the texels of the region faces. Every tool returns a short note; region_score() tells how the region
looks against the views (colour difference, skin painted as hair, folds, how far it moved), head_agent.py picks the
tools by it. The 3DCoat tool (coat_relax) runs 3DCoat on the Windows PC (it opens on the screen there).
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import head_check as hc  # noqa: E402
import head_parts as hp  # noqa: E402
import pdm_project_views as pv  # noqa: E402
import solidify  # noqa: E402

RES = 512  # pixels per view for the region score and the pass pictures


class Head:
    """A head being fixed: positions, UV, faces, texture, parts of the faces, the views and their side."""

    def __init__(self, path, views, parts=None, side=None):
        self.path = path
        self.P, self.UV, self.tris, img = hc.load(path)
        self.img = img if img is not None else np.full((1024, 1024, 3), 128, np.float32)
        self.views = views
        self.parts = np.load(parts) if isinstance(parts, str) else parts
        if self.parts is not None and len(self.parts) != len(self.tris):
            raise SystemExit(f'parts: {len(self.parts)} faces, the model has {len(self.tris)}: run head_parts.py on this model')
        self.side = side if side is not None else hp.find_side(self.P, self.tris, self.UV, self.img, views)
        self.P0 = self.P.copy()
        self.img0 = self.img.copy()  # never written: the detail of the start for region_score
        self._weld = None

    def copy(self):
        h = Head.__new__(Head)
        h.__dict__.update(self.__dict__)
        h.P, h.img = self.P.copy(), self.img.copy()
        return h

    def weld(self):
        """Welded vertices: (vertex of every glb vertex, faces over welded vertices); the UV seams split the glb vertices."""
        if self._weld is None:
            _, pid = np.unique(np.round(self.P0, 6), axis=0, return_inverse=True)
            pid = pid.ravel()
            self._weld = pid, pid[self.tris]
        return self._weld

    def save(self, path):
        solidify.save(path, self.P.astype(np.float32), self.UV.astype(np.float32), self.tris.astype(np.uint32),
                      self.img.clip(0, 255).astype(np.uint8))
        self.path = path


def region(h, spec):
    """Bool mask of faces: 'eyes,mouth' (parts), 'faces:mask.npy', 'all', or a mask already; '~N' at the end grows the
    region by N rings of neighbour faces ('eyes~2': the lids and the corners around the eye part)."""
    if isinstance(spec, str) and '~' in spec:
        spec, k = spec.rsplit('~', 1)
        return grow(h, region(h, spec), int(k))
    if isinstance(spec, np.ndarray):
        return spec.astype(bool) if spec.dtype == bool or len(spec) == len(h.tris) else np.isin(np.arange(len(h.tris)), spec)
    if spec in (None, '', 'all'):
        return np.ones(len(h.tris), bool)
    if spec.startswith('faces:'):
        return region(h, np.load(spec[6:]))
    if h.parts is None:
        raise SystemExit('a region by parts needs --parts parts.npy (head_parts.py)')
    ids = [hp.P_ID[p] if p in hp.P_ID else hp.PARTS.index(p) for p in spec.split(',')]
    return np.isin(h.parts, ids)


def grow(h, mask, rings):
    G = hp.face_graph(h.P0, h.tris)
    m = mask.copy()
    for _ in range(rings):
        m |= (G @ m.astype(np.float32)) > 0
    return m


def texels(h, mask):
    size = h.img.shape[0]
    return pv._face_image((h.UV * size).astype(np.float64), h.tris.astype(np.int64),
                          mask.astype(np.float32)[:, None], size)[..., 0] > 0.5


def inner_vertices(h, mask):
    """Welded vertices all faces of which are in the region: they may move, the border ones are held."""
    pid, F = h.weld()
    n = pid.max() + 1
    out_v = np.zeros(n, bool)
    out_v[F[~mask].ravel()] = True
    in_v = np.zeros(n, bool)
    in_v[F[mask].ravel()] = True
    return in_v & ~out_v


def laplacian(F, n):
    from scipy.sparse import coo_matrix, diags
    a = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    b = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    A = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)).tocsr()
    A.data[:] = 1
    deg = np.asarray(A.sum(1)).ravel()
    return A, diags(1 / np.maximum(deg, 1))


def _welded(h):
    pid, F = h.weld()
    W = np.zeros((pid.max() + 1, 3))
    W[pid] = h.P
    return pid, F, W


# ---------- geometry tools ----------

def relax(h, mask, steps=10, lam=0.5):
    """Taubin smoothing (no shrinking) of the region: folds and shards flatten, the border stays."""
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = inner_vertices(h, mask)
    for _ in range(int(steps)):
        for f in (float(lam), -float(lam) - 0.03):
            L = Dinv @ (A @ W) - W
            W[move] += f * L[move]
    h.P = W[pid]
    return f'relax: {int(move.sum())} vertices, {int(steps)} steps'


def membrane(h, mask, blend=0.6):
    """The region is replaced by the smoothest surface over its border (harmonic: every vertex at the mean of its
    neighbours), blended with the old one: a dent, a hole or crumpled lids become a smooth patch."""
    from scipy.sparse.linalg import spsolve
    from scipy.sparse import identity
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = np.where(inner_vertices(h, mask))[0]
    if not len(move):
        return 'membrane: no inner vertices'
    fixed = np.setdiff1d(np.arange(len(W)), move)
    L = identity(len(W)) - Dinv @ A
    Lmm = L[move][:, move].tocsc()
    rhs = -(L[move][:, fixed] @ W[fixed])
    X = np.stack([spsolve(Lmm, rhs[:, k]) for k in range(3)], 1)
    W[move] = (1 - float(blend)) * W[move] + float(blend) * X
    h.P = W[pid]
    return f'membrane: {len(move)} vertices, blend {blend}'


def push(h, mask, amount=0.003):
    """The region moves along its normals by amount (share of the head height, minus: inward), the border held."""
    pid, F, W = _welded(h)
    N = pv.vertex_normals(W, F)
    move = inner_vertices(h, mask)
    # fades to the border: two rings of neighbours
    A, Dinv = laplacian(F, len(W))
    w = move.astype(float)
    for _ in range(2):
        w = np.minimum(w, Dinv @ (A @ w))
    W += N * (float(amount) * np.ptp(W[:, 1]) * w)[:, None]
    h.P = W[pid]
    return f'push: {int(move.sum())} vertices by {amount} of the height'


def coat_relax(h, mask, degree=0.5, tangent=0, mode='mesh'):
    """3DCoat on the Windows PC: Mesh.relax (mode mesh) or Volume.relaxSurface (mode volume) of the welded mesh; only
    the region takes the result. coat_run.sh ops mode: 3DCoat opens on the screen there."""
    pid, F, W = _welded(h)
    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, 'in.obj'), os.path.join(tmp, 'out.obj')
    with open(src, 'w') as f:
        f.write(''.join(f'v {x:.7f} {y:.7f} {z:.7f}\n' for x, y, z in W))
        f.write(''.join(f'f {a + 1} {b + 1} {c + 1}\n' for a, b, c in F))
    op = f"relax:{degree}:{int(tangent)}" if mode == 'mesh' else f"vrelax:{degree}"
    subprocess.run([os.path.join(HERE, 'coat_run.sh'), src, dst, 'ops'], check=True,
                   env={**os.environ, 'OPS': op})
    from uv_from_obj import read_obj
    V2 = read_obj(dst)[0]
    if len(V2) != len(W):
        return f'coat_relax: 3DCoat gave {len(V2)} vertices for {len(W)}, not taken'
    move = inner_vertices(h, mask)
    W[move] = V2[move]
    h.P = W[pid]
    return f'coat_relax: {op}, {int(move.sum())} vertices'


def open_relax(h, mask, degree=0.5, tangent=0, crease=180.):
    """The open copy of 3DCoat Mesh.relax (coat_algos.relax, same result to 1e-6, no Windows): umbrella Laplacian
    steps on the welded mesh, only the inner vertices of the region move."""
    from coat_algos import relax
    pid, F, W = _welded(h)
    move = inner_vertices(h, mask)
    W2 = relax(W.astype(np.float64), F, float(degree), bool(int(tangent)), float(crease), free=move)
    W[move] = W2[move]
    h.P = W[pid]
    return f'open_relax: degree {degree} tangent {int(tangent)} crease {crease}, {int(move.sum())} vertices'


# ---------- texture tools ----------

def repaint(h, mask, views='all', align=1):
    """The texels of the region painted again from the views (all, front, sides, back or one name), with the skin guard by
    the parts: eyes from the front only, the neck from the sides only."""
    sel = {'all': pv.NAMES, 'sides': ('left', 'right')}.get(views, tuple(views.split('+')))
    pv.ZCACHE.clear()
    P, UV, T = h.P.astype(np.float32), h.UV.astype(np.float32), h.tris.astype(np.uint32)
    V = dict(h.views)
    skin = pv.skin_texels(P, UV, T, h.img.shape[0], V, h.parts)
    acc, ws, cover, used = pv.paint(P, UV, T, h.img, V, h.side, do_align=bool(int(align)), skin=skin)
    acc = {n: acc[n] for n in sel}
    ws = {n: ws[n] for n in sel}
    col, w = pv.combine(h.img, acc, ws, P, UV, T)
    t = texels(h, mask) & (w > pv.SEEN_W)
    h.img[t] = col[t]
    pv.ZCACHE.clear()
    return f'repaint: {int(t.sum())} texels from {"+".join(sel)}'


def hair_to_skin(h, mask):
    """Hair coloured texels of the region (dark: pdm_project_views.pixel_classes) that are skin by the views (front and
    both sides: the beard under the jaw and faces hidden in the ponytail are not) take the colour of the nearest skin
    texel of the region, or the mean skin of the head when the region has none."""
    from scipy.ndimage import distance_transform_edt
    t = texels(h, mask)
    cls = pv.pixel_classes(h.img, np.ones(t.shape, bool))
    by_views = pv.skin_texels(h.P.astype(np.float32), h.UV.astype(np.float32), h.tris.astype(np.uint32), t.shape[0],
                              h.views) == 1
    bad, good = t & (cls == 2) & by_views, t & (cls == 1)
    if not bad.any():
        return 'hair_to_skin: no hair texels'
    if good.sum() < 50:
        skin = texels(h, np.isin(h.parts, pv.SKIN_PARTS)) & (cls == 1) if h.parts is not None else cls == 1
        h.img[bad] = np.median(h.img[skin], 0) if skin.any() else (190, 140, 110)
    else:
        _, (iy, ix) = distance_transform_edt(~good, return_indices=True)
        h.img[bad] = h.img[iy[bad], ix[bad]]
    return f'hair_to_skin: {int(bad.sum())} texels'


HAIR_PARTS = (8, 9)  # hair, ponytail


def hair_texels(h, mask):
    """Texels of the region faces that belong to hair parts (all region faces when parts are unknown)."""
    return texels(h, mask & np.isin(h.parts, HAIR_PARTS) if h.parts is not None else mask)


def skin_to_hair(h, mask):
    """Skin coloured texels on the hair parts of the region (light spots under the ponytail that no view sees: filled
    from the neck by the projection) take the colour of the nearest hair texel. Texels the views call skin (temples)
    are kept."""
    from scipy.ndimage import distance_transform_edt
    t = hair_texels(h, mask)
    cls = pv.pixel_classes(h.img, np.ones(t.shape, bool))
    by_views = pv.skin_texels(h.P.astype(np.float32), h.UV.astype(np.float32), h.tris.astype(np.uint32), t.shape[0],
                              h.views) == 1
    # the ponytail has no skin: under it skin_texels looks through to the neck of the views and says skin
    tail = texels(h, mask & (h.parts == 9)) if h.parts is not None else np.zeros(t.shape, bool)
    bad, good = t & (cls == 1) & (~by_views | tail), t & (cls == 2)
    if not bad.any() or not good.any():
        return 'skin_to_hair: nothing to do'
    _, (iy, ix) = distance_transform_edt(~good, return_indices=True)
    h.img[bad] = h.img[iy[bad], ix[bad]]
    return f'skin_to_hair: {int(bad.sum())} texels'


def blur(h, mask, sigma=2.0):
    """Gaussian blur of the region texels (only region texels are mixed): specks and noise go."""
    from scipy.ndimage import gaussian_filter
    t = texels(h, mask)
    w = gaussian_filter(t.astype(np.float32), float(sigma))
    b = np.stack([gaussian_filter(h.img[..., k] * t, float(sigma)) for k in range(3)], -1)
    h.img[t] = b[t] / np.maximum(w[t], 1e-6)[:, None]
    return f'blur: {int(t.sum())} texels, sigma {sigma}'


_LAMA = []


def lama(h, mask, grow=1, context=96):
    """LaMa (open source neural inpaint, $W/lama) over the region texels: the specks, seams and patches are filled from
    the texture around them (ours, as in head-wrap-ai/lama_patch.py). Only region texels change."""
    from scipy import ndimage as ndi
    from PIL import Image
    t = texels(h, mask)
    if not t.any():
        return 'lama: no texels'
    if not _LAMA:
        W = os.environ.get('W', '/media/roman/383be9ee-c114-4bf8-8956-66b985661cb4/home/remake-linux')
        os.environ.setdefault('LAMA_MODEL', W + '/lama/big-lama.pt')
        sys.path.insert(0, W + '/lama/pkg')
        from simple_lama_inpainting import SimpleLama
        _LAMA.append(SimpleLama())
    m = ndi.binary_dilation(t, iterations=int(grow)) if grow else t
    ys, xs = np.where(m)
    H, Wd = m.shape
    y0, y1, x0, x1 = max(ys.min() - context, 0), min(ys.max() + context + 1, H), max(xs.min() - context, 0), min(xs.max() + context + 1, Wd)
    crop = h.img[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
    res = np.array(_LAMA[0](Image.fromarray(crop), Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8))))
    res = res[:y1 - y0, :x1 - x0].astype(np.float32)
    sub = m[y0:y1, x0:x1]
    h.img[y0:y1, x0:x1][sub] = res[sub]
    return f'lama: {int(sub.sum())} texels, box {x0},{y0}-{x1},{y1}'


# ---------- tools against the reference shape (head_views.py: h.ref, h.fit; ours) ----------

def _need_ref(h, name):
    return None if getattr(h, 'ref', None) is not None and getattr(h, 'fit', None) is not None else \
        f'{name}: no reference (head_auto.py / head_views.Reference)'


def _smooth_field(D, A, Dinv, move, steps=4):
    """A displacement spread over the region: a vertex moves as its neighbours do, so the surface does not tear."""
    for _ in range(steps):
        D = np.where(move[:, None], 0.5 * D + 0.5 * (Dinv @ (A @ D)), D)
    return D


def hull(h, mask, blend=1.0, rounds=4):
    """The region is pulled back inside the twelve silhouettes of the original (the visual hull): every vertex outside
    a view by more than head_views.HULL_TOL steps to the silhouette in that view, the steps spread over the region."""
    import head_views as hv
    if _need_ref(h, 'hull'):
        return _need_ref(h, 'hull')
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = inner_vertices(h, mask)
    tol = hv.HULL_TOL * h.ref.height / h.fit[1]
    n0 = None
    for _ in range(int(rounds)):
        h.P = W[pid]
        out, step = hv.hull_steps(h, h.ref)
        D = np.zeros_like(W)
        D[pid] = step
        o = np.zeros(len(W))
        o[pid] = out
        far = move & (o > hv.HULL_TOL)
        n0 = int(far.sum()) if n0 is None else n0
        if not far.any():
            break
        L = np.linalg.norm(D, axis=1, keepdims=True) + 1e-30
        D = np.where(far[:, None], D * np.maximum(L - 0.5 * tol, 0) / L, 0.)  # to just inside the tolerance
        W += float(blend) * _smooth_field(D, A, Dinv, move)
    h.P = W[pid]
    return f'hull: {n0} vertices outside, {int(rounds)} rounds, blend {blend}'


def snap(h, mask, blend=0.3, far=0.0):
    """The region moves toward the surface of the original (the nearest point), by blend; only the vertices further
    than far (share of the height) from it: a blob the generator added melts into the reference shape."""
    import head_views as hv
    if _need_ref(h, 'snap'):
        return _need_ref(h, 'snap')
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = inner_vertices(h, mask)
    X = hv.to_ref(W, h.fit)
    d, k = h.ref.tree.query(X)
    D = np.where((move & (d / h.ref.height > float(far)))[:, None], h.ref.S[k] - X, 0.)
    W += float(blend) * hv.from_ref_vec(_smooth_field(D, A, Dinv, move), h.fit)
    h.P = W[pid]
    return f'snap: {int(move.sum())} vertices, blend {blend}'


def mirror(h, mask, blend=1.0):
    """The region takes the shape of its mirror (the symmetry plane of the original): every vertex goes to the mirror of
    the surface of the other side, from the vertices outside the region if there are enough (the good side), else from
    both sides (the region is symmetrised)."""
    import head_views as hv
    from scipy.spatial import cKDTree
    if _need_ref(h, 'mirror'):
        return _need_ref(h, 'mirror')
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = inner_vertices(h, mask)
    X = hv.to_ref(W, h.fit)
    Xm = X.copy()
    Xm[:, 0] = 2 * h.ref.sym_x - Xm[:, 0]
    src = ~move
    if src.sum() < 50:
        src = np.ones(len(W), bool)
    idx = np.where(src)[0]
    _, k = cKDTree(Xm[idx]).query(X[move])
    D = np.zeros_like(X)
    D[move] = Xm[idx[k]] - X[move]
    if src.all():
        D *= 0.5
    W += float(blend) * hv.from_ref_vec(_smooth_field(D, A, Dinv, move, 2), h.fit)
    h.P = W[pid]
    return f'mirror: {int(move.sum())} vertices, blend {blend}'


def despike(h, mask, k=1.2, rounds=3):
    """Vertices standing out of their neighbours by more than k mean edge lengths (spikes, shards of the generator) go
    to the mean of the neighbours."""
    pid, F, W = _welded(h)
    A, Dinv = laplacian(F, len(W))
    move = inner_vertices(h, mask)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    n = 0
    for _ in range(int(rounds)):
        L = np.linalg.norm(W[e[:, 0]] - W[e[:, 1]], axis=1)
        el = np.zeros(len(W))
        np.add.at(el, e[:, 0], L)
        cnt = np.bincount(e[:, 0], minlength=len(W))
        el /= np.maximum(cnt, 1)
        M = Dinv @ (A @ W)
        sp = move & (np.linalg.norm(W - M, axis=1) > float(k) * el)
        n += int(sp.sum())
        if not sp.any():
            break
        W[sp] = M[sp]
    h.P = W[pid]
    return f'despike: {n} moves'


def orient(h, mask):
    """Faces of the region wound against their neighbours (the normal looks inside) are turned over: the winding is made
    consistent over every piece, outward (trimesh.repair.fix_winding / fix_normals of the welded mesh)."""
    import trimesh
    pid, F, W = _welded(h)
    m = trimesh.Trimesh(W, F.copy(), process=False)
    trimesh.repair.fix_normals(m, multibody=True)
    G = m.faces
    # a face turned over by trimesh has its corners in the other cycle; only the region may change
    same = (G == F).all(1) | (np.roll(G, 1, 1) == F).all(1) | (np.roll(G, -1, 1) == F).all(1)
    turned = ~same & mask
    t = h.tris.copy()
    t[turned] = t[turned][:, ::-1]
    h.tris, h._weld = t, None
    return f'orient: {int(turned.sum())} faces turned over'


TOOLS = {
    'hull': (hull, {'blend': 1.0, 'rounds': 4}, 'втянуть область внутрь силуэтов 12 видов оригинала', 'geometry'),
    'snap': (snap, {'blend': 0.3, 'far': 0.0}, 'притянуть область к поверхности оригинала', 'geometry'),
    'mirror': (mirror, {'blend': 1.0}, 'отразить форму с другой стороны (плоскость симметрии оригинала)', 'geometry'),
    'despike': (despike, {'k': 1.2, 'rounds': 3}, 'убрать шипы и осколки (вершина далеко от соседей)', 'geometry'),
    'orient': (orient, {}, 'развернуть грани, повёрнутые внутрь', 'geometry'),
    'relax': (relax, {'steps': 10, 'lam': 0.5}, 'сгладить форму (Taubin), край области на месте', 'geometry'),
    'membrane': (membrane, {'blend': 0.6}, 'натянуть гладкую плёнку на край области (складки век, ямы)', 'geometry'),
    'push': (push, {'amount': 0.003}, 'выдвинуть/вдавить область по нормали (доля высоты)', 'geometry'),
    'open_relax': (open_relax, {'degree': 0.5, 'tangent': 0, 'crease': 180.}, 'relax как в 3DCoat (без Windows)', 'geometry'),
    'coat_relax': (coat_relax, {'degree': 0.5, 'tangent': 0, 'mode': 'mesh'}, '3DCoat relax (Windows, на экране)', 'geometry'),
    'repaint': (repaint, {'views': 'all', 'align': 1}, 'перекрасить текселы области из видов', 'texture'),
    'hair_to_skin': (hair_to_skin, {}, 'тёмные (волосы) текселы области → ближайшая кожа', 'texture'),
    'skin_to_hair': (skin_to_hair, {}, 'светлые (кожа) текселы волос и хвоста области → ближайшие волосы', 'texture'),
    'blur': (blur, {'sigma': 2.0}, 'размыть текстуру области', 'texture'),
    'lama': (lama, {'grow': 1}, 'LaMa (нейросеть) закрасить текселы области по окружению', 'texture'),
}


def apply(h, name, mask, **kw):
    fn, defaults, _, _ = TOOLS[name]
    p = {**defaults, **{k: type(defaults[k])(v) if k in defaults else v for k, v in kw.items()}}
    return fn(h, mask, **p)


# ---------- the score of a region ----------

def render(h, res=RES):
    """{view: (colour picture of the model, face id buffer)}."""
    out = {}
    ids = hp.view_ids(h.P, h.tris, h.views, h.side, res)
    for n in pv.NAMES:
        col, _ = hc.draw(h.P, h.tris, h.UV, h.img, h.views, n, h.side, res)
        out[n] = (col, ids[n])
    return out


def dihedral(h, mask):
    """Angles (degrees) between the neighbouring faces of the region."""
    pid, F = h.weld()
    G = hp.face_graph(h.P0, h.tris).tocoo()
    a, b = G.row, G.col
    k = (a < b) & mask[a] & mask[b]
    a, b = a[k], b[k]
    N = np.cross(h.P[h.tris[:, 1]] - h.P[h.tris[:, 0]], h.P[h.tris[:, 2]] - h.P[h.tris[:, 0]])
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-30
    return np.degrees(np.arccos(np.clip((N[a] * N[b]).sum(1), -1, 1)))


def region_score(h, mask, pics=None):
    """0-100 (higher is better) and the parts of it: colour difference to the views on the pixels of the region,
    skin of the views painted as hair, skin coloured texels on hair, detail lost against the start, folds (sharp angles
    between faces), how far the region moved from the start."""
    from scipy.ndimage import laplace
    pics = pics or render(h)
    err, hair, npx = 0., 0., 0
    for n in pv.NAMES:
        col, ids = pics[n]
        sel = (ids >= 0) & mask[np.maximum(ids, 0)]
        if sel.sum() < 20:
            continue
        f = hc.small(h.views[n][0], RES)
        vc = pv.pixel_classes(f, f.max(2) > 8)
        mc = pv.pixel_classes(col, ids >= 0)
        err += np.abs(col[sel] - f[sel]).mean() * sel.sum()
        hair += ((vc[sel] == 1) & (mc[sel] == 2)).sum()
        npx += sel.sum()
    ht = hair_texels(h, mask)  # texels, not pixels: the underside of the ponytail no view sees counts too
    light = float((pv.pixel_classes(h.img, ht) == 1)[ht].mean()) if ht.sum() > 50 else 0.
    rt = texels(h, mask)
    loss = 0.
    if rt.sum() > 50:  # strands, pores, lashes: blurring the region matches the 512 px views better but loses them
        d = lambda im: np.abs(laplace(im.astype(np.float32).mean(2)))[rt].mean()
        d0 = d(h.img0)
        loss = float(max(0., 1 - d(h.img) / d0)) if d0 > 0 else 0.
    ang = dihedral(h, mask)
    hgt = np.ptp(h.P0[:, 1])
    moved = np.linalg.norm(h.P - h.P0, axis=1)
    pid, F = h.weld()
    vm = np.zeros(pid.max() + 1, bool)
    vm[F[mask].ravel()] = True
    drift = float(moved[vm[pid]].mean() / hgt) if vm.any() else 0.
    r = {'colour': round(err / max(npx, 1), 2), 'skin_as_hair': round(hair / max(npx, 1), 4),
         'hair_light': round(light, 4), 'detail_loss': round(loss, 4),
         'angle': round(float(ang.mean()) if len(ang) else 0., 2),
         'folds': round(float((ang > 50).mean()) if len(ang) else 0., 4), 'drift': round(drift, 5), 'pixels': int(npx)}
    # the colour against the views is the truth the region is fixed to; the angles only break ties (the eyelid crease is a
    # real fold: with 0.6 per degree relax always won and dragged the eye white under the lid)
    r['score'] = round(float(np.clip(100 - 1.2 * r['colour'] - 80 * r['skin_as_hair']
                                     - 40 * r['hair_light'] - 30 * r['detail_loss'] - 0.3 * r['angle']
                                     - 60 * r['folds'] - 3000 * max(0., drift - 0.002), 0, 100)), 2)
    return r


def pass_picture(before, after, mask, h, path, label=''):
    """The two views that see the region most: the region zoomed, before | after | the view; magenta: region border."""
    from scipy.ndimage import binary_dilation
    rows = []
    cnt = {n: ((after[n][1] >= 0) & mask[np.maximum(after[n][1], 0)]).sum() for n in pv.NAMES}
    for n in sorted(cnt, key=lambda k: -cnt[k])[:2]:
        sel = (after[n][1] >= 0) & mask[np.maximum(after[n][1], 0)]
        if not sel.any():
            continue
        ys, xs = np.where(sel)
        c = max(ys.max() - ys.min(), xs.max() - xs.min()) // 2 + 24
        cy, cx = (ys.max() + ys.min()) // 2, (xs.max() + xs.min()) // 2
        y0, x0 = max(cy - c, 0), max(cx - c, 0)
        y1, x1 = min(cy + c, RES), min(cx + c, RES)
        edge = binary_dilation(sel, iterations=1) & ~sel
        tiles = []
        for img in (before[n][0], after[n][0], hc.small(h.views[n][0], RES)):
            t = img.copy()
            t[edge] = (255, 40, 200)
            tiles.append(np.asarray(Image.fromarray(t[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)).resize((256, 256))))
        rows.append(np.concatenate(tiles, 1))
    if rows:
        from PIL import ImageDraw, ImageFont
        im = Image.fromarray(np.concatenate(rows, 0))
        try:  # the default bitmap font has no Cyrillic
            font = ImageFont.truetype('DejaVuSans.ttf', 13)
        except OSError:
            font, label = None, label.encode('ascii', 'replace').decode()
        ImageDraw.Draw(im).text((4, 4), label, fill=(255, 255, 0), font=font)
        im.save(path)


def main():
    a = sys.argv[1:]
    if '--list' in a:
        for k, (_, d, ru, kind) in TOOLS.items():
            print(f'{k:13s} {kind:8s} {ru}; ' + ' '.join(f'{p}={v}' for p, v in d.items()))
        return

    def opt(name, n=1):
        i = a.index(name)
        v = a[i + 1:i + 1 + n]
        del a[i:i + 1 + n]
        return v if n > 1 else v[0]
    vp = opt('--views', 4)
    parts = opt('--parts') if '--parts' in a else None
    spec = opt('--region') if '--region' in a else 'all'
    src, dst, tool = a[:3]
    kw = dict(s.split('=', 1) for s in a[3:])
    views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, vp)}
    h = Head(src, views, parts)
    mask = region(h, spec)
    before = render(h)
    s0 = region_score(h, mask, before)
    note = apply(h, tool, mask, **kw)
    after = render(h)
    s1 = region_score(h, mask, after)
    h.save(dst)
    pass_picture(before, after, mask, h, os.path.splitext(dst)[0] + '_pass.png', f'{tool} {kw} {s0["score"]}->{s1["score"]}')
    print(note)
    print('before', json.dumps(s0))
    print('after ', json.dumps(s1))


if __name__ == '__main__':
    main()
