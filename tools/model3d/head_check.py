#!/usr/bin/env python3
"""Find the defects of a generated head and say how to fix them (before and after a fix, head_fix.py runs it twice).

head_check.py model.glb --views front.png left.png back.png right.png [--ref src.glb] [--out dir] [--json r.json]

Every number is measured, then rules turn the bad ones into issues with a fix (the recipe of docs/head-model-fix.md):
  geometry  - pieces, open edges (holes), edges on 3+ faces, double wall (a surface right behind the surface, facing it:
              the second wall of the Pixal3D/TRELLIS shell), faceting (share of sharp edges, the worst zone: face, ponytail,
              top, sides), with --ref the distance to the source both ways (a lost piece, a glued gap);
  views     - the model is drawn as each view sees it (the same orthographic frame as pdm_project_views): silhouette IoU,
              colour difference inside the figure, skin of the view painted as hair; a picture per view in --out;
  face      - MediaPipe Face Mesh (468 points) on the front view and on the drawing of the model: the mean shift of the
              eyes, the nose, the mouth, the jaw in inter-ocular distances (a face that slid or swelled in the generation);
  texture   - black texels, hair colour on the texels that are skin by the views (pdm_project_views.skin_points), the
              colour jump across the UV seams against the jump inside the charts;
  uv        - uv_score.py.
score = 100 minus the weights of the issues (ours, a ranking of runs of one head, not an absolute grade).
"""
import io
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import pdm_project_views as pv  # noqa: E402

RES = 512  # pixels of the view drawings (silhouette, colour)
FACE_RES = 1024  # pixels of the front drawing for the face landmarks
BLACK = 3  # a texel no channel above this is unpainted (hero1 ponytail is 17 15 16 with 8 of noise: < 15 counted the hair)

# rules: (id, test on the report, weight, what is wrong, how to fix); the thresholds are ours, set on hero1 runs
HAIR_FACES = 15000  # from here the sharp edges of the crown and the ponytail are the hair grooves, not the facets


def faceted(g):
    """(zone, share) of the most faceted zone; hair zones are not counted when the mesh has HAIR_FACES or more."""
    sharp = {k: v for k, v in g['sharp'].items() if g['faces'] < HAIR_FACES or k in ('лицо', 'бока')}
    k = max(sharp, key=sharp.get) if sharp else g['sharp_zone']
    return k, sharp.get(k, 0.)


RULES = [
    ('pieces', lambda r: r['geometry']['pieces'] > 1, 10,
     lambda r: f"{r['geometry']['pieces']} отдельных кусков (крошки внутри шеи и носа, оторванные пряди)",
     'solidify.py — берёт самый большой кусок'),
    ('holes', lambda r: r['geometry']['open_edges'] > 0, 10,
     lambda r: f"{r['geometry']['open_edges']} открытых рёбер — дыры или открытая шея",
     'solidify.py (дыры до 4·SEAL вокселей и шея закрываются); если дыры крупнее — SEAL=4'),
    ('nonmanifold', lambda r: r['geometry']['nonmanifold_share'] > 0.001, 10,
     lambda r: f"{r['geometry']['nonmanifold_share'] * 100:.2f} % рёбер на 3+ гранях",
     'solidify.py: ремеш, прореживание и UV ломаются на таких рёбрах'),
    ('double_wall', lambda r: r['geometry']['double_wall'] > 0.05, 25,
     lambda r: f"двойная стенка на {r['geometry']['double_wall'] * 100:.0f} % поверхности (оболочка UDF)",
     'solidify.py: одна внешняя стенка; иначе двойные края ушей и складки у глаз'),
    ('faces', lambda r: r['geometry']['faces'] > 60000, 5,
     lambda r: f"{r['geometry']['faces']} граней — много для игры",
     'solidify.py … <faces> 20000 (или 10000)'),
    ('faceted', lambda r: faceted(r['geometry'])[1] > 0.30, 8,
     lambda r: "гранёность: {1:.0%} острых рёбер в зоне «{0}»".format(*faceted(r['geometry'])),
     lambda r: (f"больше граней: solidify.py … {2 * r['geometry']['faces']}" if r['geometry']['faces'] < HAIR_FACES else
                'лицо или бока гранёные при достаточном числе граней: смотреть кадр зоны, сгладить её')),
    ('lost', lambda r: r['geometry'].get('ref_to_model_p99', 0) > 0.015, 8,
     lambda r: f"часть исходника потеряна: 1 % точек исходника дальше {r['geometry']['ref_to_model_p99'] * 100:.1f} % высоты",
     'меньше SEAL (склеенная щель) или проверить, не отброшен ли кусок'),
    ('silhouette', lambda r: r.get('views') and min(v['iou'] for v in r['views'].values()) < 0.95, 8,
     lambda r: 'силуэт расходится с видом: ' + ', '.join(f"{n} {v['iou']:.3f}" for n, v in r['views'].items() if v['iou'] < 0.95),
     'смотреть картинку вида в --out (красное — есть в виде, нет в модели; синее — наоборот); сильно — перегенерировать'),
    ('face_shape', lambda r: r.get('face', {}).get('mean', 0) > 0.06, 10,
     lambda r: f"лицо сдвинуто: {r['face']['mean']:.3f} межзрачковых, хуже всего «{r['face']['worst']}»",
     'перегенерировать (другой seed) или поправить вид; проекция видов детали не двигает'),
    ('face_missing', lambda r: r.get('face', {}).get('found') is False, 10,
     lambda r: 'MediaPipe не нашёл лицо на модели', 'смотреть кадр спереди: лицо смазано или закрыто'),
    ('colour', lambda r: r.get('views') and max(v['colour'] for v in r['views'].values()) > 25, 6,
     lambda r: 'цвет расходится с видом: ' + ', '.join(f"{n} {v['colour']:.0f}" for n, v in r['views'].items()),
     'перекрасить из видов: pdm_project_views.py … --no-smooth'),
    ('hair_on_skin', lambda r: r['texture'].get('hair_on_skin', 0) > 0.02, 12,
     lambda r: f"волосы на коже: {r['texture'].get('hair_on_skin', 0) * 100:.1f} % текселей кожи "
               f"(зона «{r['texture'].get('hair_on_skin_zone', '-')}»)",
     'pdm_project_views.py … --skin-guard'),
    ('skin_as_hair_view', lambda r: r.get('views') and max(v['skin_as_hair'] for v in r['views'].values()) > 0.02, 6,
     lambda r: 'по видам кожа модели покрашена волосами: ' + ', '.join(
         f"{n} {v['skin_as_hair'] * 100:.1f} %" for n, v in r['views'].items() if v['skin_as_hair'] > 0.02),
     'обычно виски и линия волос: соседний вид кладёт туда волосы. --skin-guard это не лечит (тексели '
     'не считаются кожей, раз хоть один вид видит волосы); смотреть пурпурное в views.png, '
     'если мешает — красить зону только из вида спереди'),
    ('black', lambda r: r['texture']['black'] > 0.005, 8,
     lambda r: f"чёрные тексели: {r['texture']['black'] * 100:.1f} %",
     'uv_from_obj.py без предела расстояния + pdm_project_views (BIG_FACE): длинные грани крышки не пропускать'),
    ('seams', lambda r: r['texture'].get('seam_jump_ratio', 1) > 2.0, 4,
     lambda r: f"скачок цвета на швах UV в {r['texture']['seam_jump_ratio']:.1f} раза больше, чем внутри островов",
     'перекрасить (combine выравнивает тон); паддинг ≥ 6 текселей'),
    ('uv', lambda r: r.get('uv', {}).get('score', 99) < 3.0, 8,
     lambda r: f"развёртка слабая: uv_score {r['uv']['score']} ({r['uv']['islands']} островов)",
     'coat_run.sh mesh.obj mesh_uv.obj auto (3DCoat Auto Seams)'),
]


def load(path):
    j, b = pv.read_glb(path)
    prim = j['meshes'][0]['primitives'][0]
    P = pv.accessor(j, b, prim['attributes']['POSITION']).astype(np.float64)
    UV = pv.accessor(j, b, prim['attributes']['TEXCOORD_0']).astype(np.float64)
    tris = pv.accessor(j, b, prim['indices']).reshape(-1, 3).astype(np.int64)
    img = None
    try:
        mat = j['materials'][prim.get('material', 0)]
        tex = j['textures'][mat['pbrMetallicRoughness']['baseColorTexture']['index']]
        bv = j['bufferViews'][j['images'][tex['source']]['bufferView']]
        o = bv.get('byteOffset', 0)
        img = np.asarray(Image.open(io.BytesIO(b[o:o + bv['byteLength']])).convert('RGB')).astype(np.float32)
    except (KeyError, IndexError):
        pass
    return P, UV, tris, img


def weld(P, tris):
    _, pid = np.unique(np.round(P, 6), axis=0, return_inverse=True)
    pid = pid.ravel()
    W = np.zeros((pid.max() + 1, 3))
    W[pid] = P
    return W, pid[tris]


def edge_table(F):
    """Sorted (edge, face) list: edges, faces, and the run starts of equal edges."""
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    fi = np.tile(np.arange(len(F)), 3)
    key = E[:, 0] * (F.max() + 1) + E[:, 1]
    o = np.argsort(key, kind='stable')
    return E[o], fi[o], key[o]


def zones(rel):
    """Zone of points by their place in the bounding box (the head looks along +z, y up)."""
    z = np.full(len(rel), 'бока', object)
    z[rel[:, 1] > 0.75] = 'макушка'
    z[(rel[:, 2] > 0.6) & (np.abs(rel[:, 0] - 0.5) < 0.3) & (rel[:, 1] > 0.15) & (rel[:, 1] <= 0.75)] = 'лицо'
    z[(rel[:, 2] < 0.3) & (rel[:, 1] <= 0.6)] = 'хвост/затылок'
    return z


def geometry(P, tris, ref=None):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    V, F = weld(P, tris)
    lo, hi = V.min(0), V.max(0)
    hgt = float(hi[1] - lo[1])
    E, fi, key = edge_table(F)
    starts = np.r_[0, np.nonzero(key[1:] != key[:-1])[0] + 1]
    cnt = np.diff(np.r_[starts, len(key)])
    same = np.nonzero(key[1:] == key[:-1])[0]
    g = coo_matrix((np.ones(len(same)), (fi[same], fi[same + 1])), shape=(len(F), len(F)))
    lab = connected_components(g, directed=False)[1]
    pieces = np.bincount(lab)
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    area = 0.5 * np.linalg.norm(n, axis=1)
    n /= 2 * area[:, None] + 1e-30
    # faceting: the angle between the two faces of every inner manifold edge, sharp above 25 degrees, by length
    two = starts[cnt == 2]
    a, b = fi[two], fi[two + 1]
    ang = np.degrees(np.arccos(np.clip((n[a] * n[b]).sum(1), -1, 1)))
    L = np.linalg.norm(V[E[two, 0]] - V[E[two, 1]], axis=1)
    mid = 0.5 * (V[E[two, 0]] + V[E[two, 1]])
    zn = zones((mid - lo) / (hi - lo))
    sharp = {}
    for z in np.unique(zn):
        m = zn == z
        sharp[z] = float((L[m] * (ang[m] > 25)).sum() / max(L[m].sum(), 1e-30))
    worst = max(sharp, key=sharp.get)
    # double wall: samples of the surface with another surface right behind them that faces them
    rng = np.random.default_rng(0)
    pick = rng.choice(len(F), size=min(len(F), 60000), replace=False, p=area / area.sum())
    r = rng.random((len(pick), 2))
    s = np.sqrt(r[:, 0])
    pts = (1 - s)[:, None] * V[F[pick, 0]] + (s * (1 - r[:, 1]))[:, None] * V[F[pick, 1]] + (s * r[:, 1])[:, None] * V[F[pick, 2]]
    nrm = n[pick]
    tree = cKDTree(pts)
    rad = 0.008 * hgt
    nb = tree.query_ball_point(pts, rad, workers=-1)
    dbl = np.zeros(len(pts), bool)
    for i, js in enumerate(nb):
        if len(js) < 2:
            continue
        js = np.array(js)
        d = pts[js] - pts[i]
        behind = (d @ nrm[i]) < -0.15 * rad
        facing = (nrm[js] @ nrm[i]) < -0.5
        dbl[i] = np.any(behind & facing)
    out = dict(faces=int(len(F)), vertices=int(len(V)), pieces=int(len(pieces)),
               main_piece=round(float(pieces.max() / len(F)), 4), open_edges=int((cnt == 1).sum()),
               nonmanifold_share=round(float((cnt > 2).sum() / len(cnt)), 5), double_wall=round(float(dbl.mean()), 4),
               sharp={k: round(v, 3) for k, v in sharp.items()}, sharp_worst=round(sharp[worst], 3), sharp_zone=worst)
    if ref is not None:
        from solidify import surface_samples
        RP, _, RT, _ = ref
        a_ = surface_samples(V, F, 0.004 * hgt, rng)
        b_ = surface_samples(RP, RT, 0.004 * hgt, rng)
        b_ = b_[rng.choice(len(b_), min(len(b_), 400000), replace=False)]
        d1 = cKDTree(b_).query(a_[rng.choice(len(a_), min(len(a_), 200000), replace=False)], workers=-1)[0] / hgt
        d2 = cKDTree(a_).query(b_, workers=-1)[0] / hgt
        out.update(model_to_ref_p99=round(float(np.percentile(d1, 99)), 4),
                   ref_to_model_p99=round(float(np.percentile(d2, 99)), 4))
    return out


def draw(P, tris, UV, img, views, name, side, res):
    """The model as the view sees it: colour (or None), silhouette, in the frame of the view scaled to res."""
    lo, hi = P.min(0), P.max(0)
    dv = {'front': (0, 0, 1.), 'back': (0, 0, -1.), 'left': (side, 0, 0.), 'right': (-side, 0, 0.)}[name]
    zb, uvm = pv.zbuffer(P.astype(np.float32), tris.astype(np.int64), name, dv, views[name], lo, hi,
                         UV.astype(np.float32), res=res)
    sil = zb > -1e8
    col = None
    if img is not None:
        H = img.shape[0]
        col = img[np.clip((uvm[..., 1] * H).astype(int), 0, H - 1), np.clip((uvm[..., 0] * H).astype(int), 0, H - 1)]
        col[~sil] = 0
    return col, sil


def small(f, res):
    return np.asarray(Image.fromarray(f.clip(0, 255).astype(np.uint8)).resize((res, res), Image.BILINEAR)).astype(np.float32)


def views_check(P, tris, UV, img, views, out):
    from scipy.ndimage import binary_erosion
    cls = pv.view_classes(views)
    best = None
    for side in (1., -1.):  # which side of the mesh the left view sees: the one with the smaller colour difference
        rep, pics = {}, {}
        for n in pv.NAMES:
            col, sil = draw(P, tris, UV, img, views, n, side, RES)
            f = small(views[n][0], RES)
            vm = np.asarray(Image.fromarray((cls[n][0] > 0).astype(np.uint8) * 255).resize((RES, RES))) > 127
            inter, union = (vm & sil).sum(), (vm | sil).sum()
            both = binary_erosion(vm & sil, iterations=3)
            e = {'iou': round(float(inter / max(union, 1)), 4)}
            if col is not None:
                e['colour'] = round(float(np.abs(col[both] - f[both]).mean()), 2)
                vc = pv.pixel_classes(f, vm)
                mc = pv.pixel_classes(col, sil)
                skin = both & (vc == 1)
                e['skin_as_hair'] = round(float((skin & (mc == 2)).sum() / max(skin.sum(), 1)), 4)
            else:
                e['colour'] = e['skin_as_hair'] = 0.
            rep[n] = e
            pics[n] = (f, col, vm, sil, (vc == 1) & (mc == 2) & both if col is not None else None)
        err = np.mean([v['colour'] for v in rep.values()])
        if best is None or err < best[0]:
            best = (err, side, rep, pics)
    _, side, rep, pics = best
    if out:
        rows = []
        for n in pv.NAMES:
            f, col, vm, sil, bad = pics[n]
            diff = np.zeros((RES, RES, 3), np.float32)
            diff[vm & ~sil] = (255, 40, 40)  # in the view, not in the model
            diff[sil & ~vm] = (40, 120, 255)  # in the model, not in the view
            diff[vm & sil] = 60
            mod = col.copy() if col is not None else np.repeat(sil[..., None] * 200., 3, 2)
            if bad is not None:
                mod[bad] = mod[bad] * 0.3 + np.array([255, 0, 255]) * 0.7  # skin of the view painted as hair
            rows.append(np.concatenate([f, mod, diff], 1))
        Image.fromarray(np.concatenate(rows, 0).clip(0, 255).astype(np.uint8)).save(os.path.join(out, 'views.png'))
    return rep, side


# MediaPipe Face Mesh landmark groups (indices of its 468 points)
GROUPS = {
    'глаза': [33, 133, 159, 145, 362, 263, 386, 374, 70, 105, 300, 334],
    'нос': [1, 2, 4, 5, 98, 327, 168, 6],
    'рот': [61, 291, 0, 17, 13, 14, 78, 308],
    'овал': [10, 152, 234, 454, 172, 397, 136, 365, 58, 288],
}


def landmarks(rgb):
    import mediapipe as mp
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=False) as fm:
        r = fm.process(rgb.astype(np.uint8))
    if not r.multi_face_landmarks:
        return None
    return np.array([[p.x, p.y] for p in r.multi_face_landmarks[0].landmark]) * rgb.shape[0]


def face_check(P, tris, UV, img, views, side, out):
    try:
        import mediapipe  # noqa: F401
    except ImportError:
        return {'skipped': 'нет mediapipe (pip install mediapipe)'}
    if img is None:
        return {'skipped': 'нет текстуры'}
    ref = landmarks(small(views['front'][0], FACE_RES))
    if ref is None:
        return {'skipped': 'на виде спереди лицо не найдено'}
    col, _ = draw(P, tris, UV, img, views, 'front', side, FACE_RES)
    got = landmarks(col)
    if got is None:
        return {'found': False}
    iod = np.linalg.norm(ref[33] - ref[263])
    d = np.linalg.norm(got - ref, axis=1) / iod
    per = {g: round(float(d[ix].mean()), 4) for g, ix in GROUPS.items()}
    if out:
        pic = np.concatenate([small(views['front'][0], FACE_RES), col], 1).clip(0, 255).astype(np.uint8)
        import cv2
        pic = np.ascontiguousarray(pic)
        for (x, y), (u, v) in zip(ref, got):
            cv2.circle(pic, (int(x), int(y)), 2, (0, 255, 0), -1)
            cv2.circle(pic, (int(u) + FACE_RES, int(v)), 2, (255, 0, 255), -1)
            cv2.line(pic, (int(x) + FACE_RES, int(y)), (int(u) + FACE_RES, int(v)), (255, 255, 0), 1)
        Image.fromarray(pic).save(os.path.join(out, 'face.png'))
    return {'found': True, 'mean': round(float(d.mean()), 4), 'groups': per, 'worst': max(per, key=per.get)}


def texture_check(P, UV, tris, img, views):
    size = img.shape[0]
    pos, ax, ay = pv._face_texels(P, UV * size, tris, size, np.ones((size, size), np.bool_))
    cols = img[ay, ax]
    rep = {'black': round(float((cols.max(1) <= BLACK).mean()), 4)}
    if views is not None:
        lo, hi = P.min(0), P.max(0)
        skin = pv.skin_points(pos, views, pv.view_classes(views), lo, hi)
        hair = cols.max(1) < pv.HAIR_MAX
        rep['skin_texels'] = round(float(skin.mean()), 4)
        rep['hair_on_skin'] = round(float((skin & hair).sum() / max(skin.sum(), 1)), 4)
        if (skin & hair).any():
            rel = (pos[skin & hair] - lo) / (hi - lo)
            z, c = np.unique(zones(rel), return_counts=True)
            rep['hair_on_skin_zone'] = str(z[c.argmax()])
    # the colour jump over the UV seams against the jump over the edges inside the charts
    V, F = weld(P, tris)
    E, fi, key = edge_table(F)
    same = np.nonzero(key[1:] == key[:-1])[0]
    a, b = fi[same], fi[same + 1]
    e0, e1 = E[same, 0], E[same, 1]

    def uv_at(f, v):  # uv of welded vertex v in face f
        k = np.argmax(F[f] == v[:, None], axis=1)
        return UV[tris[f, k]]

    ua0, ua1, ub0, ub1 = uv_at(a, e0), uv_at(a, e1), uv_at(b, e0), uv_at(b, e1)
    seam = (np.abs(ua0 - ub0).max(1) > 1e-6) | (np.abs(ua1 - ub1).max(1) > 1e-6)
    ca, cb = UV[tris[a]].mean(1), UV[tris[b]].mean(1)

    def sample(uv):
        return img[np.clip((uv[:, 1] * size).astype(int), 0, size - 1), np.clip((uv[:, 0] * size).astype(int), 0, size - 1)]
    jump = np.abs(sample(0.8 * 0.5 * (ua0 + ua1) + 0.2 * ca) - sample(0.8 * 0.5 * (ub0 + ub1) + 0.2 * cb)).mean(1)
    if seam.any() and (~seam).any():
        rep['seam_jump'] = round(float(jump[seam].mean()), 2)
        rep['inner_jump'] = round(float(jump[~seam].mean()), 2)
        rep['seam_jump_ratio'] = round(float(jump[seam].mean() / max(jump[~seam].mean(), 1e-6)), 2)
    return rep


def check(path, views=None, ref=None, out=None):
    P, UV, tris, img = load(path)
    if out:
        os.makedirs(out, exist_ok=True)
    r = {'model': path}
    r['geometry'] = geometry(P, tris, load(ref) if ref else None)
    side = 1.
    if views:
        r['views'], side = views_check(P, tris, UV, img, views, out)
        r['face'] = face_check(P, tris, UV, img, views, side, out)
    r['texture'] = texture_check(P, UV, tris, img, views) if img is not None else {'black': 0}
    import uv_score
    try:
        r['uv'] = uv_score.score(path)
    except Exception as e:  # noqa: BLE001 - a broken UV is a finding, not a crash
        r['uv'] = {'error': str(e), 'score': 0, 'islands': 0}
    issues = []
    for rid, test, w, what, fix in RULES:
        try:
            hit = bool(test(r))
        except (KeyError, TypeError, ValueError):
            hit = False
        if hit:
            issues.append({'id': rid, 'weight': w, 'what': what(r), 'fix': fix(r) if callable(fix) else fix})
    r['issues'] = sorted(issues, key=lambda i: -i['weight'])
    r['score'] = max(0, 100 - sum(i['weight'] for i in issues))
    return r


def report_text(r):
    g = r['geometry']
    L = [f"== {os.path.basename(r['model'])}: оценка {r['score']}/100",
         f"геометрия: {g['faces']} граней, кусков {g['pieces']}, открытых рёбер {g['open_edges']}, "
         f"неманифолд {g['nonmanifold_share'] * 100:.2f} %, двойная стенка {g['double_wall'] * 100:.1f} %, "
         f"острые рёбра {', '.join(f'{k} {v * 100:.0f} %' for k, v in g['sharp'].items())}"]
    if 'ref_to_model_p99' in g:
        L.append(f"  до исходника (p99, доля высоты): модель→исх. {g['model_to_ref_p99']}, исх.→модель {g['ref_to_model_p99']}")
    if r.get('views'):
        L.append('виды: ' + '; '.join(f"{n} IoU {v['iou']:.3f}, цвет {v['colour']:.1f}, кожа→волосы {v['skin_as_hair'] * 100:.1f} %"
                                     for n, v in r['views'].items()))
    f = r.get('face', {})
    if f.get('found'):
        L.append(f"лицо (MediaPipe): сдвиг {f['mean']:.3f} межзрачк.; " + ', '.join(f'{k} {v:.3f}' for k, v in f['groups'].items()))
    elif f:
        L.append(f"лицо: {f.get('skipped', 'не найдено на модели')}")
    t = r['texture']
    L.append(f"текстура: чёрных {t['black'] * 100:.2f} %" +
             (f", волосы на коже {t['hair_on_skin'] * 100:.1f} % ({t.get('hair_on_skin_zone', '-')})" if 'hair_on_skin' in t else '') +
             (f", швы {t['seam_jump']:.1f} против {t['inner_jump']:.1f} внутри" if 'seam_jump' in t else ''))
    u = r.get('uv', {})
    if 'score' in u:
        L.append(f"UV: score {u['score']}, островов {u.get('islands')}, fill {u.get('fill')}")
    if r['issues']:
        L.append('недочёты и что делать:')
        for i in r['issues']:
            L.append(f"  [-{i['weight']}] {i['what']}\n        → {i['fix']}")
    else:
        L.append('недочётов по правилам нет')
    return '\n'.join(L)


def main():
    a = sys.argv[1:]

    def opt(name, n=1):
        if name not in a:
            return None
        i = a.index(name)
        v = a[i + 1:i + 1 + n]
        del a[i:i + 1 + n]
        return v if n > 1 else v[0]
    vp = opt('--views', 4)
    ref, out, js = opt('--ref'), opt('--out'), opt('--json')
    if out:
        os.makedirs(out, exist_ok=True)
    views = {n: pv.load_view(p) for n, p in zip(pv.NAMES, vp)} if vp else None
    r = check(a[0], views, ref, out)
    print(report_text(r))
    if js:
        json.dump(r, open(js, 'w'), indent=1, ensure_ascii=False, default=str)


if __name__ == '__main__':
    main()
