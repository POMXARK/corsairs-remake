#!/usr/bin/env python3
"""Parts of a generated head: every face of the mesh gets a part (face, eyes, mouth, nose, brows, ears, neck, hair,
ponytail, neck cut), voted by the 4 views it is seen in.

head_parts.py model.glb|mesh.obj --views front.png left.png back.png right.png [--out dir] [--side 1|-1]
  -> dir/parts.npy (part of every face), dir/parts.json (faces and area share per part, side), dir/parts.png (the model
     drawn in the 4 views coloured by part), dir/ids_<view>.npy (face seen in every pixel of the view at RES)
Models (local, free): MediaPipe Selfie Multiclass (Apache 2.0: background, hair, body skin, face skin, clothes, other)
for the classes of the views, MediaPipe Face Mesh (Apache 2.0) on the front view for eyes, mouth, nose, brows. Ears: the
face skin of a side view that is not joined to the face. Ponytail: hair below the ear line in the back half. Neck cut:
faces looking down at the bottom of the neck (the lid of solidify.py). Faces no view sees take the part of their
neighbours. Used by head_tools.py (a part = a region to change) and head_seams.py (UV templates cut along the parts).
"""
import json
import os
import sys

import numpy as np
from numba import njit
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pdm_project_views as pv  # noqa: E402

MODELS = os.environ.get('MP_MODELS', os.path.join(HERE, '..', '..', '..', 'models'))
SEG_MODEL = 'selfie_multiclass_256x256.tflite'  # storage.googleapis.com/mediapipe-models/image_segmenter/...
PARTS = ['?', 'лицо', 'глаза', 'рот', 'нос', 'брови', 'уши', 'шея', 'волосы', 'хвост', 'срез']
EN = ['unknown', 'face', 'eyes', 'mouth', 'nose', 'brows', 'ears', 'neck', 'hair', 'ponytail', 'cut']
COLOURS = np.array([[60, 60, 60], [240, 200, 160], [40, 120, 255], [220, 30, 60], [250, 140, 0], [120, 60, 20],
                    [190, 60, 220], [255, 235, 120], [70, 40, 25], [0, 170, 120], [255, 255, 255]], np.uint8)
P_ID = {n: i for i, n in enumerate(EN)}
RES = 1024
# MediaPipe Selfie Multiclass classes
BG, HAIR, BODY, FACE, CLOTHES, OTHER = range(6)
EYE_GROW = 0.012  # share of the view: the eye contour of Face Mesh grows by this (the lids and the corner folds go with it)
EAR_CUT = 0.012  # share of the view: the face skin is eroded by this to cut the ear from the cheek
TAIL_Y, TAIL_Z = 0.45, 0.40  # share of the height and depth: hair below and behind this is the ponytail
EAR_OUT = 0.01  # share of the width: skin this far outside the face oval of the front view is the ear
SEEN = 0.15  # cosine: a face seen more sideways than this does not vote


def model_path(name):
    p = os.path.join(MODELS, name)
    if not os.path.exists(p):
        raise SystemExit(f'{p} is missing: curl -Lo {p} https://storage.googleapis.com/mediapipe-models/image_segmenter/'
                         'selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite')
    return p


def segment(img):
    """Class of every pixel of a view (Selfie Multiclass at 1024, back to the size of the view). Clothes and 'other'
    (the crown of the back view, wisps) are hair when dark and body skin when skin coloured: there are no clothes."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=model_path(SEG_MODEL)), output_category_mask=True))
    a = np.asarray(Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((RES, RES), Image.BILINEAR))
    c = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(a))).category_mask.numpy_view()
    c = np.asarray(Image.fromarray(c.squeeze().astype(np.uint8)).resize(img.shape[1::-1], Image.NEAREST)).copy()
    odd = (c == CLOTHES) | (c == OTHER)
    pc = pv.pixel_classes(img, img.max(2) > 8)
    c[odd] = np.where(pc[odd] == 1, BODY, HAIR)
    c[img.max(2) <= 8] = BG
    return c


def face_marks(img):
    """Masks of the front view (view size): eyes, mouth, nose, brows from the 468 points of Face Mesh."""
    import cv2
    import mediapipe as mp
    fm = mp.solutions.face_mesh
    H, W = img.shape[:2]
    small = np.asarray(Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((RES, RES), Image.BILINEAR))
    with fm.FaceMesh(static_image_mode=True, refine_landmarks=True) as m:
        r = m.process(small)
    out = {k: np.zeros((H, W), bool) for k in ('eyes', 'mouth', 'nose', 'brows')}
    out['oval'] = None
    if not r.multi_face_landmarks:
        return out, False
    pts = np.array([(p.x * W, p.y * H) for p in r.multi_face_landmarks[0].landmark])

    def poly(edges, grow):
        ids = sorted({i for e in edges for i in e})
        hull = cv2.convexHull(pts[ids].astype(np.float32)).astype(np.int32)
        m_ = np.zeros((H, W), np.uint8)
        cv2.fillConvexPoly(m_, hull, 1)
        if grow:
            m_ = cv2.dilate(m_, np.ones((3, 3), np.uint8), iterations=int(grow * H))
        return m_.astype(bool)

    out['eyes'] = poly(fm.FACEMESH_LEFT_EYE, EYE_GROW) | poly(fm.FACEMESH_RIGHT_EYE, EYE_GROW)
    out['mouth'] = poly(fm.FACEMESH_LIPS, 0.004)
    out['brows'] = (poly(fm.FACEMESH_LEFT_EYEBROW, 0.004) | poly(fm.FACEMESH_RIGHT_EYEBROW, 0.004)) & ~out['eyes']
    oval = pts[sorted({i for e in fm.FACEMESH_FACE_OVAL for i in e})]
    eye_y = pts[[33, 263], 1].mean()
    mouth_y = pts[[13, 14], 1].mean()
    band = oval[(oval[:, 1] > eye_y) & (oval[:, 1] < mouth_y)]
    out['oval'] = (band[:, 0].min(), band[:, 0].max(), pts[[70, 300], 1].mean(), mouth_y)  # pixels of the view
    nose = [(i, i) for i in (1, 2, 98, 327, 168, 6, 197, 195, 5, 4, 45, 275, 129, 358, 49, 279, 64, 294)]
    out['nose'] = poly(nose, 0.002) & ~out['eyes'] & ~out['mouth']
    return out, True


def ear_mask(cls, name):
    """Face skin of a side view that is cut from the face by a small erosion: the ear (the face is the component with
    the most frontal pixel: on the left of the left view, on the right of the right view)."""
    from scipy import ndimage as nd
    skin = cls == FACE
    k = max(2, int(EAR_CUT * cls.shape[0]))
    lab, n = nd.label(nd.binary_erosion(skin, iterations=k))
    if n < 2:
        return np.zeros_like(skin)
    ys, xs = np.nonzero(lab)
    front = lab[ys, xs][xs.argmin() if name == 'left' else xs.argmax()]
    size = np.bincount(lab.ravel())
    ears = np.isin(lab, [i for i in range(1, n + 1) if i != front and size[i] > 0.02 * size[front]])
    return nd.binary_dilation(ears, iterations=k + 2) & skin


@njit(cache=True)
def face_ids(px, py, depth, tris, res):
    """Face seen in every pixel (-1 none): a z-buffer that keeps the face number."""
    buf = np.full((res, res), -1e9, np.float32)
    ids = np.full((res, res), -1, np.int32)
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        x0, x1, x2, y0, y1, y2 = px[i0], px[i1], px[i2], py[i0], py[i1], py[i2]
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12:
            continue
        for Y in range(max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), res - 1) + 1):
            for X in range(max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), res - 1) + 1):
                l0 = ((y1 - y2) * (X + .5 - x2) + (x2 - x1) * (Y + .5 - y2)) / d
                l1 = ((y2 - y0) * (X + .5 - x2) + (x0 - x2) * (Y + .5 - y2)) / d
                l2 = 1 - l0 - l1
                if l0 < 0 or l1 < 0 or l2 < 0:
                    continue
                z = l0 * depth[i0] + l1 * depth[i1] + l2 * depth[i2]
                if z > buf[Y, X]:
                    buf[Y, X] = z
                    ids[Y, X] = t
    return ids


def view_dir(name, side):
    return {'front': (0, 0, 1.), 'back': (0, 0, -1.), 'left': (side, 0, 0.), 'right': (-side, 0, 0.)}[name]


def view_ids(P, tris, views, side, res=RES):
    """{view: face id buffer at res over the picture of the view}."""
    lo, hi = P.min(0), P.max(0)
    out = {}
    for n in pv.NAMES:
        img = views[n][0]
        x, y = pv.project(P, n, views[n], lo, hi)
        out[n] = face_ids((x / img.shape[1] * res).astype(np.float32), (y / img.shape[0] * res).astype(np.float32),
                          (P @ np.array(view_dir(n, side))).astype(np.float32), tris.astype(np.int64), res)
    return out


def find_side(P, tris, UV, atlas, views):
    """Which side of the mesh the left view sees: the sign with the smaller difference of the mesh colour to the view."""
    best = None
    for side in (1., -1.):
        err = 0.
        for n in ('left', 'right'):
            img = views[n][0]
            lo, hi = P.min(0), P.max(0)
            x, y = pv.project(P, n, views[n], lo, hi)
            ids = face_ids((x / img.shape[1] * 256).astype(np.float32), (y / img.shape[0] * 256).astype(np.float32),
                           (P @ np.array(view_dir(n, side))).astype(np.float32), tris.astype(np.int64), 256)
            m = ids >= 0
            uv = UV[tris[ids[m]]].mean(1)
            H = atlas.shape[0]
            col = atlas[np.clip((uv[:, 1] * H).astype(int), 0, H - 1), np.clip((uv[:, 0] * H).astype(int), 0, H - 1)]
            small = np.asarray(Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((256, 256))).astype(np.float32)
            err += np.abs(col - small[m]).mean()
        if best is None or err < best[0]:
            best = (err, side)
    return best[1]


def face_graph(P, tris):
    import head_check as hc
    from scipy.sparse import coo_matrix
    V, F = hc.weld(P, tris)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    f = np.tile(np.arange(len(F)), 3)
    e.sort(1)
    key = e[:, 0] * (len(V) + 1) + e[:, 1]
    o = np.argsort(key, kind='stable')
    k, f = key[o], f[o]
    same = k[1:] == k[:-1]
    a, b = f[:-1][same], f[1:][same]
    n = len(F)
    return coo_matrix((np.ones(2 * len(a)), (np.concatenate([a, b]), np.concatenate([b, a]))), shape=(n, n)).tocsr()


def spread(lab, G, keep, steps=200):
    """Faces with lab 0 take the most common part of their labelled neighbours, step by step; keep: faces not changed."""
    lab = lab.copy()
    for _ in range(steps):
        free = lab == 0
        if not free.any():
            break
        oh = np.zeros((len(lab), len(PARTS)))
        oh[np.arange(len(lab)), lab] = 1
        oh[:, 0] = 0
        votes = G @ oh
        got = free & (votes.max(1) > 0)
        if not got.any():
            break
        lab[got] = votes[got].argmax(1)
    return lab


def smooth(lab, G, keep, steps=2):
    """Majority of the face and its neighbours: specks of one face go."""
    for _ in range(steps):
        oh = np.zeros((len(lab), len(PARTS)))
        oh[np.arange(len(lab)), lab] = 1
        votes = G @ oh + 1.5 * oh
        new = votes.argmax(1)
        lab = np.where(keep, lab, new)
    return lab


def islands(lab, G, part):
    """Pieces of one part apart from its biggest piece take the most common other part around them. The neck inside
    the ponytail: faces of the ponytail turned to the neck vote "skin" by the views, and the projection paints them as
    the neck (light spots on the ponytail)."""
    from scipy.sparse.csgraph import connected_components
    m = lab == part
    if m.sum() == 0:
        return lab
    idx = np.nonzero(m)[0]
    _, comp = connected_components(G[idx][:, idx], directed=False)
    big = np.bincount(comp).argmax()
    lab = lab.copy()
    for c in np.unique(comp):
        if c == big:
            continue
        f = idx[comp == c]
        nb = G[f].indices
        nb = nb[lab[nb] != part]
        if len(nb):
            lab[f] = np.bincount(lab[nb], minlength=len(PARTS)).argmax()
    return lab


NECK_BACK = 0.02  # share of the depth behind the back of the neck the side views see


def neck_behind(lab, rel, ids, N, side, bins=40):
    """Neck faces behind the back of the neck the side views see (at the same height) are inside the ponytail: they
    become the ponytail. The faces of the ponytail turned to the neck and its underside are seen by no view and took
    the neck from the neighbours; the projection then painted them skin (light spots on the ponytail)."""
    neck = lab == P_ID['neck']
    seen = np.zeros(len(lab), bool)
    for n in ('left', 'right'):
        f = ids[n][ids[n] >= 0]
        f = f[(N[f] @ np.array(view_dir(n, side))) > SEEN]
        seen[f] = True
    b = np.clip((rel[:, 1] * bins).astype(int), 0, bins - 1)
    sv = neck & seen
    back = np.full(bins, np.inf)
    np.minimum.at(back, b[sv], rel[sv, 2])
    lab = lab.copy()
    inside = neck & np.isfinite(back[b]) & (rel[:, 2] < back[b] - NECK_BACK) & (rel[:, 2] < TAIL_Z)
    lab[inside] = P_ID['ponytail']
    return lab


def label(P, tris, UV, atlas, views, side=None):
    """Part of every face, the side and the id buffers of the views."""
    if side is None:
        side = find_side(P, tris, UV, atlas, views)
    lo, hi = P.min(0), P.max(0)
    C = P[tris].mean(1)
    N = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-30
    rel = (C - lo) / (hi - lo)
    ids = view_ids(P, tris, views, side)
    nf = len(tris)
    oval = None
    vote = np.zeros((nf, len(PARTS)))
    for n in pv.NAMES:
        img = views[n][0]
        H, W = img.shape[:2]
        cls = segment(img)
        part = np.zeros((H, W), np.uint8)
        part[cls == HAIR] = P_ID['hair']
        part[cls == BODY] = P_ID['neck']
        part[cls == FACE] = P_ID['face']
        if n == 'front':
            marks, found = face_marks(img)
            oval = marks['oval']
            for k in ('nose', 'mouth', 'brows', 'eyes'):  # eyes last: they win over the brows and the nose
                part[marks[k]] = P_ID[k]
        if n in ('left', 'right'):
            part[ear_mask(cls, n)] = P_ID['ears']
        ib = ids[n]
        m = ib >= 0
        ys, xs = np.nonzero(m)
        f = ib[m]
        pp = part[np.clip((ys + .5) / RES * H, 0, H - 1).astype(int), np.clip((xs + .5) / RES * W, 0, W - 1).astype(int)]
        cos = N[f] @ np.array(view_dir(n, side))
        w = np.where(cos > SEEN, cos, 0.)
        # a view sees the parts of its own: the front its marks, the sides the ears; elsewhere they are a weak vote
        if n == 'front':
            w = w * np.where(np.isin(pp, [P_ID[k] for k in ('eyes', 'mouth', 'nose', 'brows')]), 3., 1.)
        if n in ('left', 'right'):
            w = w * np.where(pp == P_ID['ears'], 3., 1.)
        np.add.at(vote, (f, pp), w)
    vote[:, 0] = 0
    lab = np.where(vote.max(1) > 0, vote.argmax(1), 0)
    G = face_graph(P, tris)
    cut = (rel[:, 1] < pv.LID_Y) & (N[:, 1] < -0.7)
    lab[cut] = 0
    lab = spread(lab, G, None)
    lab = smooth(lab, G, np.zeros(nf, bool))
    # ears: the cut of the ear from the cheek in the side views fails when the ear touches the cheek (hero1); then the
    # skin outside the face oval of the front view, between the brows and the mouth, in the middle of the depth
    if oval is not None:
        _, (x0, x1, y0, y1), _ = views['front']
        ox0, ox1 = (oval[0] - x0) / (x1 - x0), (oval[1] - x0) / (x1 - x0)
        ytop, ybot = (y1 - oval[2]) / (y1 - y0), (y1 - oval[3]) / (y1 - y0)
        ear = (np.isin(lab, [P_ID['face'], P_ID['neck']]) & ((rel[:, 0] < ox0 - EAR_OUT) | (rel[:, 0] > ox1 + EAR_OUT)) &
               (rel[:, 1] < ytop) & (rel[:, 1] > ybot) & (rel[:, 2] > 0.2) & (rel[:, 2] < 0.75))
        lab[ear] = P_ID['ears']
    tail = (lab == P_ID['hair']) & (rel[:, 1] < TAIL_Y) & (rel[:, 2] < TAIL_Z)
    lab[tail] = P_ID['ponytail']
    lab = islands(lab, G, P_ID['neck'])
    lab = neck_behind(lab, rel, ids, N, side)
    lab[cut & (lab == P_ID['neck'])] = P_ID['cut']
    return lab.astype(np.uint8), side, ids


def area(P, tris):
    return 0.5 * np.linalg.norm(np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]), axis=1)


def preview(P, tris, lab, views, side, ids, path, mark=None):
    """The 4 views of the model coloured by part (mark: faces drawn brighter, a selected region)."""
    rows = []
    for n in pv.NAMES:
        ib = ids[n]
        col = COLOURS[lab][np.maximum(ib, 0)].astype(np.float32)
        N = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-30
        shade = np.clip(0.35 + 0.65 * (N @ np.array(view_dir(n, side))), 0.2, 1)[np.maximum(ib, 0)]
        col *= shade[..., None]
        if mark is not None:
            sel = mark[np.maximum(ib, 0)] & (ib >= 0)
            col[sel] = col[sel] * 0.4 + np.array([255, 40, 200]) * 0.6
        col[ib < 0] = 30
        rows.append(np.asarray(Image.fromarray(col.clip(0, 255).astype(np.uint8)).resize((384, 384))))
    Image.fromarray(np.concatenate(rows, 1)).save(path)


def legend(lab, P, tris):
    a = area(P, tris)
    tot = a.sum()
    return {EN[i]: {'ru': PARTS[i], 'faces': int((lab == i).sum()), 'area': round(float(a[lab == i].sum() / tot), 4),
                    'colour': COLOURS[i].tolist()} for i in range(len(PARTS)) if (lab == i).any()}


def run(path, views, out, side=None):
    import head_check as hc
    os.makedirs(out, exist_ok=True)
    if path.endswith('.obj'):  # a mesh without texture (before the UV): the side must be given, default +x
        from uv_from_obj import read_obj
        P, _, tris, _ = read_obj(path)
        P, tris = P.astype(np.float64), tris.astype(np.int64)
        UV, img, side = np.zeros((len(P), 2)), None, 1. if side is None else side
    else:
        P, UV, tris, img = hc.load(path)
    if img is None:
        img = np.zeros((8, 8, 3), np.float32)
    lab, side, ids = label(P, tris, UV, img, views, side)
    np.save(os.path.join(out, 'parts.npy'), lab)
    for n, b in ids.items():
        np.save(os.path.join(out, f'ids_{n}.npy'), b)
    info = {'model': path, 'side': side, 'parts': legend(lab, P, tris)}
    json.dump(info, open(os.path.join(out, 'parts.json'), 'w'), ensure_ascii=False, indent=1)
    preview(P, tris, lab, views, side, ids, os.path.join(out, 'parts.png'))
    return lab, info


def main():
    a = sys.argv[1:]
    if '--views' not in a:
        raise SystemExit(__doc__)
    i = a.index('--views')
    vp = a[i + 1:i + 5]
    out = a[a.index('--out') + 1] if '--out' in a else os.path.splitext(a[0])[0] + '_parts'
    side = float(a[a.index('--side') + 1]) if '--side' in a else None
    views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, vp)}
    _, info = run(a[0], views, out, side)
    print('side', info['side'])
    for k, v in info['parts'].items():
        print(f"  {v['ru']:8s} {v['faces']:6d} граней  {v['area'] * 100:5.1f} % площади")
    print('->', out)


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    main()
