#!/usr/bin/env python3
"""The head checked against the original from twelve sides: the reference shape, the views, the mesh (ours).

head_views.py model.glb --game pdm-game --model hero1 --ref ref12/ [--views f l b r] [--parts parts.npy] [--out dir]
  ref12/: <model>_head_a000.png ... a330.png of pdm_model_views.py --parts --turns 12 --bg 0,0,0
  -> the score and its parts (json on stdout), out/views12.png: the reference | the model | the difference per view

The four views of Qwen (head_check.py) show the head the model was made of, but only from four sides: a bulge
between them (at 45 degrees), a wrong ponytail seen from behind at an angle, a flat side of the skull pass. The
original model of the game is the reference shape: the head part of <model>.gm (pdm_model_views.PARTS) is drawn from
twelve sides (every 30 degrees) the same way as the reference pictures, the glb is fitted to it (the turn and mirror of
the generator frame, then the scale and the shift), and every view is compared:
  - silhouette: the model against the reference picture, above the lowest point of the original (the generated neck is
    longer); the model pixels outside the reference make the 'outside' of their faces, a model vertex outside the
    silhouettes (the visual hull of the twelve views) by more than HULL_TOL is a bulge;
  - classes: skin of the reference drawn as hair on the model and the other way round (pdm_project_views.pixel_classes);
  - the reference surface: the distance of every vertex to the original (signed by its normal) - far out is a blob;
  - symmetry: the mirror of every vertex in the symmetry plane of the original against the model (an ear lower than the
    other, a cheek fatter);
  - the mesh: pieces, open and non-manifold edges, faces wound against their neighbours, slivers, spikes, folds.
The faces of each kind of defect are joined into regions (defects()); head_auto.py fixes them one by one.
The original is a low-poly game head and its hair is flatter than the hair Qwen drew, so with --views the reference
silhouettes are combined (Reference.adopt): at 0/90/180/270 degrees the Qwen mask is warped into the reference camera
and is the silhouette; between them the original silhouette is grown by the fullness of the neighbouring Qwen views
(how far Qwen's hair stands out of the original, the 90th percentile over the upper FULL_ROWS of the head, without the
neck). The IoU is still taken against the shape of the view (Qwen or the original), the 'outside' test and the hull
against the grown silhouette, so the hull does not cut the hair down to the game model.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import head_check as hc  # noqa: E402
import pdm_model_views as mv  # noqa: E402
import pdm_project_views as pv  # noqa: E402

RES = 512  # pixels of a view for the check (the reference pictures are 1024)
TURNS = 12
HULL_TOL = 0.012  # share of the head height: a vertex further than this outside a reference silhouette is a bulge
REF_FAR = 0.06  # share of the head height: further than this from the original surface is a blob (the generator adds hair
# volume, a fuller nose and ears of 2-4 %)
ASYM_TOL = 0.025  # share of the height: the mirror of a vertex further than this from the model is asymmetric
SPIKE = 1.2  # a vertex further than this many mean edge lengths from the mean of its neighbours is a spike
SLIVER = 3.0  # degrees: the smallest angle of a sliver face
FOLD = 70.0  # degrees between neighbour faces: a fold (the eyelid crease of the generated head is up to 50)
FULL_ROWS = 0.65  # share of the height of the original from the top: the fullness of Qwen is measured there (hair, skull)
CUT_MARGIN = 6  # pixels above the lowest row of the original that are left out of the silhouette compare


# ---------- the reference ----------

def turn(az):
    """The rotation of pdm_model_views.render for the camera azimuth az (0 front, 90 right): yaw 180 - az."""
    a = np.radians(180 - az)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


class Reference:
    """The original head and its twelve pictures: cameras, silhouettes, pixel classes, the surface."""

    def __init__(self, game, model, ref_dir, turns=TURNS, part='head'):
        from scipy.ndimage import binary_fill_holes, distance_transform_edt
        from scipy.spatial import cKDTree
        from pathlib import Path
        path = mv.find_model(Path(game), model)
        gm = mv.read_gm(path)
        objs = mv.part_objects(gm, mv.parts_of(gm)[part]) if part else gm['objects']
        V, T, N, off = [], [], [], 0
        for o in objs:
            V.append(o[2])
            N.append(o[3])
            T.append(np.asarray(o[6]).reshape(-1, 3) + off)
            off += len(o[2])
        self.V, self.T = np.concatenate(V).astype(np.float64), np.concatenate(T).astype(np.int64)
        self.height = float(np.ptp(self.V[:, 1]))
        self.sym_x = float((self.V[:, 0].min() + self.V[:, 0].max()) / 2)
        self.views = []
        for i in range(turns):
            az = i * 360 / turns
            name = f'{path.stem}_{part}_a{round(az):03d}.png' if part else f'{path.stem}_a{round(az):03d}.png'
            f = np.asarray(Image.open(os.path.join(ref_dir, name)).convert('RGB').resize((RES, RES), Image.LANCZOS))
            f = f.astype(np.float32)
            mask = binary_fill_holes(f.max(2) > 8)
            R = turn(az)
            every = self.V @ R.T
            lo, hi = every.min(0), every.max(0)
            scale = mv.FILL * RES / max(hi[0] - lo[0], hi[1] - lo[1])
            ys = np.where(mask.any(1))[0]
            self.views.append({'az': az, 'name': name, 'img': f, 'mask': mask, 'sil': mask, 'R': R, 'centre': (lo + hi) / 2,
                               'scale': scale, 'cut': int(ys.max()) - CUT_MARGIN,
                               'cls': pv.pixel_classes(f, mask),
                               # distance (pixels) of every pixel outside the silhouette to it, and the nearest inside pixel
                               'out': distance_transform_edt(~mask, return_indices=True)})
        # the surface: points on the faces with their normals, for the distance of the model to it
        A, B, C = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        n = np.cross(B - A, C - A)
        area = np.linalg.norm(n, axis=1)
        rng = np.random.default_rng(0)
        k = rng.choice(len(self.T), 120000, p=area / area.sum())
        r1, r2 = np.sqrt(rng.random(len(k))), rng.random(len(k))
        self.S = A[k] * (1 - r1)[:, None] + B[k] * (r1 * (1 - r2))[:, None] + C[k] * (r1 * r2)[:, None]
        self.SN = n[k] / (area[k][:, None] + 1e-30)
        self.tree = cKDTree(self.S)
        self.low_y = float(self.V[:, 1].min())

    def adopt(self, h):
        """The silhouettes the model is checked against, from the pictures it was made of (h.views, Qwen): at 0, 90,
        180 and 270 degrees the mask of that view, carried into the camera of the original through the fit; at the
        other angles the silhouette of the original grown by the fullness Qwen adds in the two neighbour views (the
        90th percentile of how far its figure lies outside the original's, over the upper FULL_ROWS of the head). The hair of Qwen is fuller than the low
        poly original: without this every hull pass fought the four views."""
        from scipy.ndimage import binary_dilation, binary_fill_holes, distance_transform_edt
        if not h.views:
            return {}
        lo, hi = h.P0.min(0), h.P0.max(0)
        yy, xx = np.mgrid[0:RES, 0:RES]
        grow = {}
        for v in self.views:
            name = CARDINAL.get(round(v['az']))
            if name not in h.views:
                continue
            p = np.stack([(xx.ravel() + .5 - RES / 2) / v['scale'], (RES / 2 - yy.ravel() - .5) / v['scale'],
                          np.zeros(xx.size)], 1) + v['centre']
            G = from_ref(p @ v['R'], h.fit)
            f = h.views[name][0]
            qm = binary_fill_holes(f.max(2) > 8)
            qx, qy = pv.project(G, name, h.views[name], lo, hi)
            ok = (qx >= 0) & (qx < f.shape[1]) & (qy >= 0) & (qy < f.shape[0])
            m = np.zeros(xx.size, bool)
            m[ok] = qm[qy[ok].astype(int), qx[ok].astype(int)]
            v['sil'] = v['shape'] = m.reshape(RES, RES)
            extra = v['sil'] & ~v['mask']
            top = np.where(v['mask'].any(1))[0][0]
            extra[top + int(FULL_ROWS * (v['cut'] - top)):] = False  # the neck of Qwen is no fullness of the head
            grow[round(v['az'])] = float(np.percentile(v['out'][0][extra], 90)) if extra.sum() > 50 else 0.
        for v in self.views:
            az = round(v['az'])
            if az not in grow and grow:
                near = [grow.get((az // 90 * 90) % 360, 0.), grow.get((az // 90 * 90 + 90) % 360, 0.)]
                v['sil'] = binary_dilation(v['mask'], iterations=max(int(round(max(near))), 0)) if max(near) >= 1 else v['mask']
            v['out'] = distance_transform_edt(~v['sil'], return_indices=True)
        self.grow = grow
        return grow

    def project(self, X, v):
        """Pixels (x, y) and the depth (the nearer the larger) of points X of the original frame in view v."""
        p = (X @ v['R'].T - v['centre']) * v['scale']
        return p[:, 0] + RES / 2, RES / 2 - p[:, 1], -p[:, 2]


# ---------- the frame of the model ----------

def frames():
    """The eight frames a generator may give: a turn by k * 90 degrees about y, mirrored or not."""
    out = []
    for k in range(4):
        a = np.radians(90 * k)
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        for m in (1, -1):
            out.append(R @ np.diag([m, 1, 1]))
    return out


CARDINAL = {0: 'front', 90: 'right', 180: 'back', 270: 'left'}  # the Qwen views (pdm_project_views.NAMES) by azimuth


def from_ref(X, fit):
    """Points of the original frame in the glb frame."""
    M, s, t = fit
    return ((X - t) / s) @ M


def to_ref(P, fit):
    M, s, t = fit
    return (P @ M.T) * s + t


def from_ref_vec(D, fit):
    """A displacement of the original frame back into the glb frame."""
    M, s, _ = fit
    return (D / s) @ M  # M is orthogonal: its inverse is the transpose


def bbox_fit(P, ref, M):
    """Scale and shift so that the top, the width and the depth of the model meet the original's (the neck is longer)."""
    Q = P @ M.T
    lo, hi = Q.min(0), Q.max(0)
    rlo, rhi = ref.V.min(0), ref.V.max(0)
    s = np.mean([(rhi[0] - rlo[0]) / (hi[0] - lo[0]), (rhi[2] - rlo[2]) / (hi[2] - lo[2])])
    t = np.array([(rlo[0] + rhi[0]) / 2 - s * (lo[0] + hi[0]) / 2, rhi[1] - s * hi[1], (rlo[2] + rhi[2]) / 2 - s * (lo[2] + hi[2]) / 2])
    return M, s, t


def silhouette_iou(P, tris, ref, fit, views=None):
    ious = []
    for v in views or ref.views:
        buf, _, _ = draw(to_ref(P, fit), tris, ref, v)
        sil, m = buf > -1e8, v['mask'].copy()
        sil[v['cut']:] = m[v['cut']:] = False
        ious.append((sil & m).sum() / max((sil | m).sum(), 1))
    return float(np.mean(ious))


def fit_frame(P, tris, ref):
    """The frame (turn, mirror), scale and shift of the model in the original's frame: the best silhouette match."""
    from scipy.optimize import minimize
    side = ref.views[::3]  # front, right, back, left choose the frame
    best = max((silhouette_iou(P, tris, ref, bbox_fit(P, ref, M), side), i) for i, M in enumerate(frames()))
    M, s, t = bbox_fit(P, ref, frames()[best[1]])
    sub = tris[::4]  # the fine fit on a quarter of the faces: the silhouette is the same

    def cost(x):
        return -silhouette_iou(P, sub, ref, (M, s * np.exp(x[0]), t + x[1:] * ref.height), ref.views[::2])
    r = minimize(cost, np.zeros(4), method='Nelder-Mead', options={'xatol': 1e-3, 'fatol': 1e-4, 'maxiter': 120})
    return M, s * np.exp(r.x[0]), t + r.x[1:] * ref.height


# ---------- drawing ----------

def draw(X, tris, ref, v):
    """Depth buffer, face ids and barycentrics of the mesh X (original frame) in view v."""
    px, py, d = ref.project(X, v)
    return _raster(px.astype(np.float64), py.astype(np.float64), d.astype(np.float64), tris.astype(np.int64), RES)


@pv.njit(cache=True)
def _raster(px, py, depth, tris, res):
    buf = np.full((res, res), -1e9, np.float64)
    fid = np.full((res, res), -1, np.int64)
    bar = np.zeros((res, res, 3), np.float32)
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        x0, x1, x2, y0, y1, y2 = px[i0], px[i1], px[i2], py[i0], py[i1], py[i2]
        ax, ay = int(np.floor(min(x0, x1, x2))), int(np.floor(min(y0, y1, y2)))
        ex, ey = int(np.ceil(max(x0, x1, x2))), int(np.ceil(max(y0, y1, y2)))
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12:
            continue
        for Y in range(max(ay, 0), min(ey, res - 1) + 1):
            for X in range(max(ax, 0), min(ex, res - 1) + 1):
                l0 = ((y1 - y2) * (X + .5 - x2) + (x2 - x1) * (Y + .5 - y2)) / d
                l1 = ((y2 - y0) * (X + .5 - x2) + (x0 - x2) * (Y + .5 - y2)) / d
                l2 = 1 - l0 - l1
                if l0 < 0 or l1 < 0 or l2 < 0:
                    continue
                z = l0 * depth[i0] + l1 * depth[i1] + l2 * depth[i2]
                if z > buf[Y, X]:
                    buf[Y, X] = z
                    fid[Y, X] = t
                    bar[Y, X, 0], bar[Y, X, 1], bar[Y, X, 2] = l0, l1, l2
    return buf, fid, bar


def shade(X, tris, v):
    """The light of pdm_model_views.render (0.45 + 0.55 |n . light|) per face, so that the model is lit as the reference."""
    n = np.cross(X[tris[:, 1]] - X[tris[:, 0]], X[tris[:, 2]] - X[tris[:, 0]]) @ v['R'].T
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-30
    light = mv.LIGHT / np.linalg.norm(mv.LIGHT)
    return 0.45 + 0.55 * np.clip(np.abs(n @ light), 0, 1)


def picture(h, X, v, fid, bar):
    """The colour of the model in a view: the texture at the seen point, lit per face."""
    sel = fid >= 0
    col = np.zeros((RES, RES, 3), np.float32)
    if not sel.any():
        return col
    f = fid[sel]
    uv = (h.UV[h.tris[f]] * bar[sel][..., None]).sum(1)
    H = h.img.shape[0]
    c = h.img[np.clip((uv[:, 1] * H).astype(int), 0, H - 1), np.clip((uv[:, 0] * H).astype(int), 0, H - 1)]
    col[sel] = c * shade(X, h.tris, v)[f][:, None]
    return col


# ---------- the mesh ----------

def mesh_stats(h):
    """How the mesh is made: valence, edge lengths, and the faces of every kind of defect."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pid, F = h.weld()
    W = np.zeros((pid.max() + 1, 3))
    W[pid] = h.P
    nF, nV = len(F), len(W)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])  # directed half edges
    face = np.tile(np.arange(nF), 3)
    key = np.sort(e, 1)
    uk, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    open_e, nonman = cnt == 1, cnt > 2
    # winding: two faces over an edge must run it in opposite directions
    same = np.zeros(len(uk), np.int64)
    np.add.at(same, inv, np.where(e[:, 0] < e[:, 1], 1, -1))
    flipped_e = (cnt == 2) & (np.abs(same) == 2)
    bad = lambda m: np.unique(face[m[inv]])
    L = np.linalg.norm(W[e[:, 0]] - W[e[:, 1]], axis=1)
    # angles of the faces
    A, B, C = W[F[:, 0]], W[F[:, 1]], W[F[:, 2]]

    def ang(p, q, r):
        u, w = q - p, r - p
        return np.degrees(np.arccos(np.clip((u * w).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1) + 1e-30), -1, 1)))
    mina = np.minimum(np.minimum(ang(A, B, C), ang(B, C, A)), ang(C, A, B))
    adj = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nV, nV)).tocsr()
    adj = ((adj + adj.T) > 0).astype(np.float64)
    val = np.asarray(adj.sum(1)).ravel()
    mean_nb = (adj @ W) / np.maximum(val, 1)[:, None]
    el = np.zeros(nV)
    np.add.at(el, e[:, 0], L)
    np.add.at(el, e[:, 1], L)
    el /= np.maximum(2 * val, 1)  # every edge is two half edges of each end on a closed mesh
    spike_v = np.linalg.norm(W - mean_nb, axis=1) > SPIKE * np.maximum(el, 1e-12) * 2
    # folds: the angle between the faces over an edge
    two = cnt == 2
    order = np.argsort(inv, kind='stable')
    fi = face[order].reshape(-1)
    starts = np.r_[0, np.cumsum(cnt)[:-1]]
    fa, fb = fi[starts[two]], fi[starts[two] + 1]
    n = np.cross(B - A, C - A)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-30
    dih = np.degrees(np.arccos(np.clip((n[fa] * n[fb]).sum(1), -1, 1)))
    folds = np.unique(np.r_[fa[dih > FOLD], fb[dih > FOLD]])
    G = coo_matrix((np.ones(len(fa)), (fa, fb)), shape=(nF, nF))
    pieces, lab = connected_components(G, directed=False)
    sizes = np.bincount(lab)
    stats = {'vertices': int(nV), 'faces': int(nF), 'pieces': int(pieces), 'small_piece_faces': int((sizes[lab] < 50).sum()),
             'open_edges': int(open_e.sum()), 'nonmanifold_edges': int(nonman.sum()),
             'flipped_edges': int(flipped_e.sum()), 'slivers': int((mina < SLIVER).sum()),
             'spikes': int(spike_v.sum()), 'folds': int(len(folds)),
             'valence': {str(k): int(c) for k, c in zip(*np.unique(val.astype(int), return_counts=True)) if c > nV * 0.005},
             'valence_mean': round(float(val.mean()), 2),
             'edge_cv': round(float(L.std() / L.mean()), 3)}
    faces = {'flip': bad(flipped_e), 'open': bad(open_e), 'nonmanifold': bad(nonman),
             'sliver': np.where(mina < SLIVER)[0], 'spike': np.where(spike_v[F].any(1))[0], 'fold': folds,
             'piece': np.where(sizes[lab] < 50)[0]}
    return stats, faces


# ---------- the check ----------

FACE_PARTS = ('face', 'eyes', 'mouth', 'nose', 'brows')
SKIP_PARTS = ('neck', 'cut')


def face_parts(h):
    import head_parts as hp
    if h.parts is None:
        return np.zeros(len(h.tris), bool)
    return np.isin(h.parts, [hp.P_ID[p] for p in FACE_PARTS])


def ignored(h, X, ref):
    """Faces left out of the compare: the neck and its cut (head_parts), else the faces under the original's lowest point."""
    import head_parts as hp
    if h.parts is not None:
        return np.isin(h.parts, [hp.P_ID[p] for p in SKIP_PARTS])
    return X[h.tris, 1].max(1) < ref.low_y


def evaluate(h, ref, fit=None, out=None):
    """{score, parts, per view, mesh} and per-face defect weights {kind: float array over the faces}."""
    from scipy.spatial import cKDTree
    fit = fit or h.fit
    X = to_ref(h.P, fit)
    hgt = ref.height
    nF = len(h.tris)
    outside = np.zeros(nF)  # model pixels outside the reference silhouettes, per face
    seen = np.zeros(nF)
    cls_bad = np.zeros(nF)  # pixels of the face whose class (skin/hair) is not the reference's
    hull = np.zeros(len(X))  # the largest distance (share of the height) of a vertex outside a silhouette
    hull_v = np.zeros((len(X), 3))  # and the step back to the silhouette (original frame) for hull()
    per, pics = [], []
    above = X[:, 1] > ref.low_y + 0.02 * hgt
    skip = ignored(h, X, ref)  # the generated neck: the original part ends at the chin
    facey = face_parts(h)
    skip_v = np.zeros(len(X), bool)
    skip_v[h.tris[skip].ravel()] = True
    above &= ~skip_v
    for v in ref.views:
        buf, fid, bar = draw(X, h.tris, ref, v)
        # the shape is compared with what the view shows (Qwen at 0/90/180/270, else the original); what lies outside,
        # with the grown silhouette (Reference.adopt)
        sil, m = buf > -1e8, v.get('shape', v['mask']).copy()
        cut = v['cut']
        s2, m2, o2 = sil.copy(), m, v['sil'].copy()
        s2[cut:] = m2[cut:] = o2[cut:] = False
        neck = sil & skip[np.maximum(fid, 0)]
        s2[neck] = m2[neck] = o2[neck] = False
        iou = (s2 & m2).sum() / max((s2 | m2).sum(), 1)
        col = picture(h, X, v, fid, bar)
        mc = pv.pixel_classes(col, sil)
        both = s2 & m2
        # skin on the hair and hair on the skin; the face is left out: the beard, the brows and the lids of the
        # generated head are darker than the low resolution original, its colour is checked against the Qwen views
        wrong = both & (((v['cls'] == 2) & (mc == 1)) | ((v['cls'] == 1) & (mc == 2) & ~facey[np.maximum(fid, 0)]))
        np.add.at(seen, fid[sil], 1)
        np.add.at(outside, fid[s2 & ~o2], 1)
        np.add.at(cls_bad, fid[wrong], 1)
        # vertices outside the silhouette (the visual hull)
        px, py, _ = ref.project(X, v)
        ix, iy = np.clip(px.astype(int), 0, RES - 1), np.clip(py.astype(int), 0, RES - 1)
        dist, (ny, nx) = v['out']
        dpx = dist[iy, ix] / v['scale'] / hgt
        ok = above & (iy < cut)
        upd = ok & (dpx > hull)
        hull[upd] = dpx[upd]
        # the step to the nearest silhouette pixel, in the picture plane, back into the original frame
        step = np.stack([(nx[iy, ix] - px), -(ny[iy, ix] - py), np.zeros(len(X))], 1) / v['scale']
        hull_v[upd] = step[upd] @ v['R']
        per.append({'az': int(v['az']), 'iou': round(float(iou), 4),
                    'outside': round(float((s2 & ~o2).sum() / max(m2.sum(), 1)), 4),
                    'missing': round(float((m2 & ~s2).sum() / max(m2.sum(), 1)), 4),
                    'class_wrong': round(float(wrong.sum() / max(both.sum(), 1)), 4)})
        pics.append((v['img'], col, s2, m2, o2, wrong))
    # the reference surface
    d, k = ref.tree.query(X)
    sgn = np.sign(((X - ref.S[k]) * ref.SN[k]).sum(1))
    sd = d * sgn / hgt
    sd[~above] = 0  # the generated neck under the original's cut is not compared
    # symmetry about the original's plane
    Xm = X.copy()
    Xm[:, 0] = 2 * ref.sym_x - Xm[:, 0]
    asym = cKDTree(X).query(Xm)[0] / hgt
    stats, mfaces = mesh_stats(h)
    pid, F = h.weld()
    fv = lambda a: a[h.tris].max(1)  # a vertex value per face
    faces = {'outside': outside / np.maximum(seen, 1), 'class': cls_bad / np.maximum(seen, 1),
             'bulge': fv(hull) > HULL_TOL, 'blob': fv(sd) > REF_FAR, 'asym': fv(asym) > ASYM_TOL}
    for kname, ids in mfaces.items():
        m = np.zeros(nF, bool)
        m[ids] = True
        faces[kname] = m
    parts = {
        'iou': round(float(np.mean([p['iou'] for p in per])), 4),
        'iou_min': round(float(min(p['iou'] for p in per)), 4),
        'class_wrong': round(float(np.mean([p['class_wrong'] for p in per])), 4),
        'bulge': round(float((hull > HULL_TOL).mean()), 4),
        'hull_mean': round(float(hull.mean()), 5),
        'blob': round(float((sd > REF_FAR).mean()), 4),
        'ref_dist': round(float(np.abs(sd[above]).mean()), 4),
        'asym': round(float(asym[above].mean()), 4),
        'asym_far': round(float((asym[above] > ASYM_TOL).mean()), 4),
    }
    nf = stats['faces']
    # points per 1 % of the faces (spikes: of the vertices)
    mesh_pen = 100 * (1.0 * stats['folds'] + 2 * stats['slivers'] + 3 * stats['flipped_edges'] + 3 * stats['small_piece_faces']
                      + 5 * stats['nonmanifold_edges'] + 2 * stats['open_edges']) / nf + 300 * stats['spikes'] / stats['vertices']
    score = 100 - (150 * (1 - parts['iou']) + 60 * (1 - parts['iou_min']) + 120 * parts['class_wrong']
                   + 300 * parts['hull_mean'] + 100 * parts['blob'] + 200 * parts['asym'] + 40 * parts['asym_far']
                   + mesh_pen)
    rep = {'score': round(float(np.clip(score, 0, 100)), 2), 'parts': parts, 'mesh': stats, 'views': per,
           'mesh_penalty': round(float(mesh_pen), 2)}
    h._hull_step, h._hull = hull_v, hull  # for the hull tool
    if out:
        sheet(pics, per, os.path.join(out, 'views12.png'))
    return rep, faces


def hull_steps(h, ref, fit=None):
    """Per glb vertex: how far it is outside the reference silhouettes (share of the height, the worst view) and the
    step that brings it back inside that view (glb frame). Projection only, no drawing: cheap enough for every pass."""
    fit = fit or h.fit
    X = to_ref(h.P, fit)
    hull, step = np.zeros(len(X)), np.zeros((len(X), 3))
    skip = ignored(h, X, ref)
    keep = np.ones(len(X), bool)
    keep[h.tris[skip].ravel()] = False
    keep &= X[:, 1] > ref.low_y + 0.02 * ref.height
    for v in ref.views:
        px, py, _ = ref.project(X, v)
        ix, iy = np.clip(px.astype(int), 0, RES - 1), np.clip(py.astype(int), 0, RES - 1)
        dist, (ny, nx) = v['out']
        d = dist[iy, ix] / v['scale'] / ref.height
        upd = keep & (iy < v['cut']) & (d > hull)
        hull[upd] = d[upd]
        st = np.stack([(nx[iy, ix] + 0.5 - px), -(ny[iy, ix] + 0.5 - py), np.zeros(len(X))], 1) / v['scale']
        step[upd] = st[upd] @ v['R']
    return hull, from_ref_vec(step, fit)


def sheet(pics, per, path, cols=6, tile=192):
    """Three rows per six views: the reference, the model, the difference (red: missing, blue: outside, magenta: class)."""
    from PIL import ImageDraw
    rows = []
    for r0 in range(0, len(pics), cols):
        trip = [[], [], []]
        for (img, col, s2, m2, o2, wrong), p in zip(pics[r0:r0 + cols], per[r0:r0 + cols]):
            diff = np.zeros((RES, RES, 3), np.float32)
            diff[m2 & ~s2] = (255, 40, 40)
            diff[s2 & ~m2] = (40, 70, 120)  # outside the shape, within the fullness of Qwen
            diff[s2 & ~o2] = (40, 120, 255)
            diff[s2 & m2] = 70
            diff[wrong] = (255, 0, 255)
            for i, a in enumerate((img, col, diff)):
                im = Image.fromarray(a.clip(0, 255).astype(np.uint8)).resize((tile, tile))
                if i == 2:
                    ImageDraw.Draw(im).text((3, 3), f"{p['az']} iou {p['iou']:.3f}", fill=(255, 255, 0))
                trip[i].append(np.asarray(im))
        rows += [np.concatenate(t, 1) for t in trip]
    Image.fromarray(np.concatenate(rows, 0)).save(path)


# ---------- the defect regions ----------

DEFECT_MIN = {'bulge': 8, 'blob': 8, 'asym': 30, 'outside': 8, 'class': 15, 'flip': 1, 'spike': 1, 'fold': 3,
              'sliver': 3, 'piece': 1, 'open': 1, 'nonmanifold': 1}
INTENT = {'bulge': 'outside', 'blob': 'outside', 'outside': 'outside', 'asym': 'asym', 'class': 'wrong_class',
          'flip': 'flip', 'spike': 'spike', 'fold': 'fold', 'sliver': 'spike', 'piece': 'spike',
          'open': 'shape', 'nonmanifold': 'shape'}


def defects(h, faces, grow_rings=2, limit=12):
    """[(kind, face mask, size, part names)]: the connected regions of every kind, the largest first."""
    import head_parts as hp
    from scipy.sparse.csgraph import connected_components
    G = hp.face_graph(h.P0, h.tris).tocsr()
    out = []
    for kind, w in faces.items():
        m = w > 0.25 if w.dtype != bool else w.copy()
        if m.sum() < DEFECT_MIN.get(kind, 5):
            continue
        sub = G[m][:, m]
        n, lab = connected_components(sub, directed=False)
        ids = np.where(m)[0]
        for c in np.argsort(-np.bincount(lab))[:4]:
            reg = np.zeros(len(h.tris), bool)
            reg[ids[lab == c]] = True
            if reg.sum() < DEFECT_MIN.get(kind, 5):
                break
            size = int(reg.sum())
            for _ in range(grow_rings):
                reg |= (G @ reg.astype(np.float32)) > 0
            names = []
            if h.parts is not None:
                pc = np.bincount(h.parts[reg], minlength=len(hp.EN))
                names = [hp.EN[i] for i in np.argsort(-pc)[:2] if pc[i] > 0.2 * reg.sum()]
            out.append((kind, reg, size, names))
    out.sort(key=lambda d: -d[2])
    return out[:limit]


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('glb')
    ap.add_argument('--game', required=True)
    ap.add_argument('--model', default='hero1')
    ap.add_argument('--ref', required=True)
    ap.add_argument('--parts')
    ap.add_argument('--views', nargs=4, help='the four Qwen views (front left back right): their silhouettes at 0/90/180/270')
    ap.add_argument('--out')
    a = ap.parse_args()
    import head_tools as ht
    ref = Reference(a.game, a.model, a.ref)
    views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, a.views)} if a.views else None
    h = ht.Head(a.glb, views, a.parts, side=1.)
    h.fit = fit_frame(h.P, h.tris, ref)
    grow = ref.adopt(h)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    rep, faces = evaluate(h, ref, out=a.out)
    rep['fit'] = {'frame': h.fit[0].round(3).tolist(), 'scale': round(float(h.fit[1]), 5), 'qwen_fullness_px': grow}
    rep['defects'] = [{'kind': k, 'faces': s, 'parts': p} for k, _, s, p in defects(h, faces)]
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
