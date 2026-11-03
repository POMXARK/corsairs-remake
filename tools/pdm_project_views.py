#!/usr/bin/env python3
"""Paint the base colour texture of a generated .glb from the four views it was generated from.

The Pixal3D/TRELLIS.2 texture is generated per voxel and smears small details (eyes, eyebrows, lips). The views
(front, left, back, right, orthographic, cropped to the figure) are sharp and the mesh is built to match them, so every
texel is projected into the views and coloured from the view that faces it; where no view sees the texel the generated
colour stays. Usage: pdm_project_views.py in.glb out.glb front.png left.png back.png right.png
Before projecting, every view is aligned to the mesh: the mesh is drawn with its own generated texture from the view's side
and the view is moved by the dense optical flow towards that drawing (the mesh differs from the view by a few pixels at the
nostrils, the mouth corners, the eyelids), so the sharp details land where the geometry has them.
Needs numpy, Pillow, scipy, OpenCV (opencv-python-headless) and numba (the rasterizers: per-face Python loops took hours on
the 700 000 faces of the bf16 mesh, compiled they take seconds; without numba the same loops run as plain Python)."""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

try:
    from numba import njit
except ImportError:  # same code, interpreted: correct but slow
    def njit(*a, **k):
        return (lambda f: f) if not a or not callable(a[0]) else a[0]

SHARP = 6  # the view that faces the texel most dominates (power of the weight): blended views ghost the lips and the nose
NAMES = ("front", "left", "back", "right")


def read_glb(path):
    d = open(path, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]
    return json.loads(d[20:20 + jl]), d[28 + jl:]


def write_glb(path, j, b):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    b += b"\0" * (-len(b) % 4)
    open(path, "wb").write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(b)) + struct.pack("<II", len(js), 0x4E4F534A)
                           + js + struct.pack("<II", len(b), 0x004E4942) + b)


def accessor(j, b, i):
    a = j["accessors"][i]
    v = j["bufferViews"][a["bufferView"]]
    n = {"VEC3": 3, "VEC2": 2, "SCALAR": 1, "VEC4": 4}[a["type"]]
    dt = {5126: "<f4", 5125: "<u4", 5123: "<u2"}[a["componentType"]]
    return np.frombuffer(b, dt, a["count"] * n, v.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, n)


SMOOTH = 12  # Taubin steps for the voxel mesh: jagged slivers and pits at the lip, the nostril and the chin look like holes


def smooth_positions(P, tris, steps=SMOOTH):
    """Taubin smoothing of the mesh as it is (vertices and UV stay), duplicated vertices of one place move together."""
    from scipy.sparse import coo_matrix
    key = np.round(P / max(float(np.ptp(P, axis=0).max()), 1e-9) * 1e6).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    W, pos = inv[tris], P[first].astype(np.float64)
    n = len(pos)
    a = np.concatenate([W[:, 0], W[:, 1], W[:, 2], W[:, 1], W[:, 2], W[:, 0]])
    b = np.concatenate([W[:, 1], W[:, 2], W[:, 0], W[:, 0], W[:, 1], W[:, 2]])
    adj = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)).tocsr()
    adj.data[:] = 1
    deg = np.maximum(np.asarray(adj.sum(axis=1)).reshape(-1), 1)[:, None]
    for _ in range(steps):
        for k in (0.5, -0.53):
            pos = pos + k * (adj @ pos / deg - pos)
    return pos[inv].astype(np.float32)


def load_view(path):
    f = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    f[..., 1] = np.minimum(f[..., 1], np.maximum(f[..., 0], f[..., 2]))  # green background spill
    from scipy.ndimage import binary_erosion, binary_fill_holes
    # holes filled: the black pupil (and the erosion ring around it, the iris) counted as background and took the skin
    # colour of the neighbours, a skin patch in the eye of ComfyUI_00016
    mask = binary_fill_holes(f.max(2) > 8)
    ys, xs = np.where(mask)
    # the rim of the figure is blended with the background (dark lines at the temple, the neck, the ear): do not sample it
    inner = binary_erosion(mask, iterations=max(3, f.shape[0] // 400))
    return f, (xs.min(), xs.max(), ys.min(), ys.max()), inner


def project(positions, name, view, lo, hi):
    _, (x0, x1, y0, y1), _ = view
    y = y1 - (positions[:, 1] - lo[1]) / (hi[1] - lo[1]) * (y1 - y0)
    if name == "front":
        t = (positions[:, 0] - lo[0]) / (hi[0] - lo[0])
    elif name == "back":
        t = (hi[0] - positions[:, 0]) / (hi[0] - lo[0])
    elif name == "left":  # the face is on the left of the image
        t = (hi[2] - positions[:, 2]) / (hi[2] - lo[2])
    else:
        t = (positions[:, 2] - lo[2]) / (hi[2] - lo[2])
    return x0 + t * (x1 - x0), y


ZCACHE = {}


def zbuffer(P, tris, name, dv, view, lo, hi, UV, res=1024):
    """Depth (along the view direction, the nearer the larger) of the mesh as the view sees it: res x res over the picture,
    and the texture coordinate of the surface seen in every pixel."""
    img = view[0]
    px, py = project(P, name, view, lo, hi)
    px, py = px / img.shape[1] * res, py / img.shape[0] * res
    depth = P @ np.array(dv)
    return _zbuffer(px, py, depth, UV, tris, res)


@njit(cache=True)
def _zbuffer(px, py, depth, UV, tris, res):
    buf = np.full((res, res), -1e9, np.float32)
    uvmap = np.zeros((res, res, 2), np.float32)
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        x0, x1, x2, y0, y1, y2 = px[i0], px[i1], px[i2], py[i0], py[i1], py[i2]
        ax, ay = int(np.floor(min(x0, x1, x2))), int(np.floor(min(y0, y1, y2)))
        ex, ey = int(np.ceil(max(x0, x1, x2))), int(np.ceil(max(y0, y1, y2)))
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-9 or max(ex - ax, ey - ay) > 300:
            continue
        for Y in range(max(ay, 0), min(ey, res - 1) + 1):
            for X in range(max(ax, 0), min(ex, res - 1) + 1):
                l0 = ((y1 - y2) * (X + .5 - x2) + (x2 - x1) * (Y + .5 - y2)) / d
                l1 = ((y2 - y0) * (X + .5 - x2) + (x0 - x2) * (Y + .5 - y2)) / d
                l2 = 1 - l0 - l1
                if l0 < -.02 or l1 < -.02 or l2 < -.02:
                    continue
                z = l0 * depth[i0] + l1 * depth[i1] + l2 * depth[i2]
                if z > buf[Y, X]:
                    buf[Y, X] = z
                    for k in range(2):
                        uvmap[Y, X, k] = l0 * UV[i0, k] + l1 * UV[i1, k] + l2 * UV[i2, k]
    return buf, uvmap


FLOW_MAX = 0.03  # the largest shift of a view, as a share of its size: more than that is a different thing, not a misfit


def align(name, view, zbuf, uvmap, atlas):
    """Move the view onto the mesh: dense optical flow from the mesh drawn with its generated texture to the view."""
    import cv2
    from scipy.ndimage import binary_erosion
    img, bbox, inner = view
    res = zbuf.shape[0]
    covered = zbuf > -1e8
    size = atlas.shape[0]
    drawn = atlas[np.clip((uvmap[..., 1] * size).astype(int), 0, size - 1), np.clip((uvmap[..., 0] * size).astype(int), 0, size - 1)]
    drawn = drawn * covered[..., None]
    small = cv2.resize(img, (res, res), interpolation=cv2.INTER_AREA)

    def prep(a):  # the generated texture is smeared and the views are lit differently: compare the structure, not the colour
        g = cv2.cvtColor(a.clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        return cv2.createCLAHE(2.0, (8, 8)).apply(cv2.GaussianBlur(g, (0, 0), 2))

    flow = cv2.calcOpticalFlowFarneback(prep(drawn), prep(small), None, 0.5, 5, 41, 5, 7, 1.5, 0)
    area = binary_erosion(covered & (small.max(2) > 8), iterations=8)  # outside the figure the flow means nothing
    flow *= cv2.GaussianBlur(area.astype(np.float32), (0, 0), 6)[..., None]
    flow = cv2.GaussianBlur(flow, (0, 0), 6)
    lim = FLOW_MAX * res
    flow = np.clip(flow, -lim, lim)
    h, w = img.shape[:2]
    big = cv2.resize(flow, (w, h), interpolation=cv2.INTER_LINEAR) * (w / res)
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    mx, my = gx + big[..., 0], gy + big[..., 1]
    warped = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    mask = cv2.remap(inner.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT) > 0
    mag = np.hypot(flow[..., 0], flow[..., 1])[area]
    print(f"{name}: view moved to the mesh, shift mean {mag.mean():.1f} px, 95 % {np.percentile(mag, 95):.1f} px of {res}")
    return warped, bbox, mask


NORMAL_STEPS = 6  # the weight of a view follows the normal averaged over the neighbours: the raw normals of the generated mesh are noisy
OCCLUDED = 0.005  # share of the model size: the weight of a view fades by exp(-(depth behind what the view sees / this)^2);
# REACH lets hidden texels take a view at all, this keeps a view that really sees the texel on top (the nose side took the inner eye corner)
REACH = 0.05  # share of the model size: a texel deeper than this behind what the view sees is hidden; 1.5 % and 3 % hid the faces under shards of the mesh and left flat patches


def smooth_normals(P, tris, steps=NORMAL_STEPS):
    """Per-face normals averaged over the neighbouring faces (through the welded vertices), `steps` times."""
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    t = inv[tris]
    n = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
    nv = len(inv)
    for _ in range(steps):
        vn = np.zeros((inv.max() + 1, 3))
        for k in range(3):
            np.add.at(vn, t[:, k], n)
        n = vn[t[:, 0]] + vn[t[:, 1]] + vn[t[:, 2]]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return n


def vertex_normals(P, tris):
    """Smooth vertex normals: area-weighted over the faces around each welded position (the UV seams do not break the shading)."""
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    n = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
    vn = np.zeros((inv.max() + 1, 3))
    for k in range(3):
        np.add.at(vn, inv[tris[:, k]], n)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    return vn[inv].astype(np.float32)


FACING_EDGE = 1  # pixels of the depth buffer: the facing of a pixel is the worst around it, the outline of an ear seen edge-on included
FACING_BLUR = 1.5  # pixels: gaussian of the depth before its slope is taken


def zfacing(zb, view, lo, hi):
    """How squarely the surface seen in every pixel of the depth buffer faces the view: cos of the slope of the depth (1 facing,
    0 edge-on or a depth jump). The weight by the normal does not see it: the averaged normals of a thin ear rim point like the
    head behind it, and the front view painted the rim with its dark outline (stripes along the helix)."""
    import cv2
    from scipy.ndimage import grey_erosion
    img, (x0, x1, y0, y1), _ = view
    pix = (hi[1] - lo[1]) / (y1 - y0) * img.shape[0] / zb.shape[0]  # model units per pixel of the depth buffer
    z = zb.astype(np.float32).copy()
    bg = z < -1e8
    z[bg] = z[~bg].min() if (~bg).any() else 0
    # depth smoothed first: a lone spike of the mesh (a shard in the sideburn) dropped the weight of the view around it and
    # another view painted a square patch there; the rims of the ear and the nose are wider than the blur
    z = cv2.GaussianBlur(z, (0, 0), FACING_BLUR)
    slope = np.hypot(cv2.Sobel(z, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(z, cv2.CV_32F, 0, 1, ksize=3)) / (8 * pix)
    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)  # a square window printed square patches
    f = 1 / np.sqrt(1 + slope ** 2)
    for _ in range(FACING_EDGE):
        f = grey_erosion(f, footprint=cross)
    return f.astype(np.float32)


def paint(P, UV, tris, atlas, views, side, step=1, do_align=False):
    """Colours of the texels covered by the triangles, per view: ({view: sum of w*colour}, {view: sum of w}, cover)."""
    size = atlas.shape[0]
    lo, hi = P.min(0), P.max(0)
    dirs = {"front": (0, 0, 1.), "back": (0, 0, -1.), "left": (side, 0, 0.), "right": (-side, 0, 0.)}
    reach = REACH * float((hi - lo).max())  # a texel deeper than this behind what the view sees is hidden (a ponytail behind the jaw)
    zbufs = {}
    for n, dv in dirs.items():
        if (n, dv) not in ZCACHE:
            ZCACHE[(n, dv)] = zbuffer(P, tris, n, dv, views[n], lo, hi, UV)
        zbufs[n] = ZCACHE[(n, dv)][0]
        if do_align:
            views[n] = align(n, views[n], *ZCACHE[(n, dv)], atlas)
    names = list(dirs)
    snorm = smooth_normals(P, tris)
    facing = tuple(zfacing(zbufs[n], views[n], lo, hi) for n in names)
    vp = [project(P, n, views[n], lo, hi) for n in names]
    A, W, cover, used = _paint(P, (UV * size).astype(np.float32), tris, np.arange(0, len(tris), step), snorm,
                               np.array([dirs[n] for n in names]), np.array([v[0] for v in vp]), np.array([v[1] for v in vp]),
                               tuple(views[n][0].astype(np.float32) for n in names), tuple(views[n][2].astype(np.bool_) for n in names),
                               tuple(zbufs[n] for n in names), facing, size, reach,
                               OCCLUDED * float((hi - lo).max()), SHARP)
    return dict(zip(names, A)), dict(zip(names, W)), cover, used


@njit(cache=True)
def _paint(P, uvs, tris, faces, snorm, dirs, vpx, vpy, imgs, inners, zbufs, facing, size, reach, occ, sharp):
    nv = dirs.shape[0]
    acc = np.zeros((nv, size, size, 3), np.float32)  # per view: sum of w*colour and sum of w
    wsum = np.zeros((nv, size, size), np.float32)
    cover = np.zeros((size, size), np.float32)
    used = np.zeros((size, size), np.bool_)  # texels some triangle lies on
    lim = 0.05  # holes between the views stay with the smeared generated colour: let every view reach far, SHARP keeps the best one on top
    w = np.zeros(nv)
    wc = np.zeros(nv)
    dep = np.zeros((nv, 3))
    for fi in faces:
        i0, i1, i2 = tris[fi, 0], tris[fi, 1], tris[fi, 2]
        e1, e2 = P[i1] - P[i0], P[i2] - P[i0]
        cx, cy, cz = e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]
        if np.sqrt(cx * cx + cy * cy + cz * cz) < 1e-12:
            continue
        u0, u1, u2, v0, v1, v2 = uvs[i0, 0], uvs[i1, 0], uvs[i2, 0], uvs[i0, 1], uvs[i1, 1], uvs[i2, 1]
        ax, ay = int(np.floor(min(u0, u1, u2))), int(np.floor(min(v0, v1, v2)))
        ex, ey = int(np.ceil(max(u0, u1, u2))), int(np.ceil(max(v0, v1, v2)))
        if max(ex - ax, ey - ay) > 200:
            continue
        d = (v1 - v2) * (u0 - u2) + (u2 - u1) * (v0 - v2)
        if abs(d) < 1e-9:
            continue
        for k in range(nv):
            # no cap below 1: with /0.5 every view facing the texel at more than 55 % weighed 1, the front and the side view
            # met half and half in the eye sockets and on the cheeks (ghost irises, ComfyUI_00016) and SHARP had nothing to sharpen
            w[k] = min(max((snorm[fi, 0] * dirs[k, 0] + snorm[fi, 1] * dirs[k, 1] + snorm[fi, 2] * dirs[k, 2] - lim) / (1 - lim), 0.), 1.)
            wc[k] = min(1., w[k] * (1 - lim) / 0.5)  # the cover keeps the old scale: which texels count as seen does not change
            for j in range(3):
                q = tris[fi, j]
                dep[k, j] = P[q, 0] * dirs[k, 0] + P[q, 1] * dirs[k, 1] + P[q, 2] * dirs[k, 2]
        for Y in range(ay, ey + 1):
            for X in range(ax, ex + 1):
                l0 = ((v1 - v2) * (X + .5 - u2) + (u2 - u1) * (Y + .5 - v2)) / d
                l1 = ((v2 - v0) * (X + .5 - u2) + (u0 - u2) * (Y + .5 - v2)) / d
                l2 = 1 - l0 - l1
                if l0 < 0 or l1 < 0 or l2 < 0:
                    continue
                used[Y, X] = True
                for k in range(nv):
                    if w[k] <= 0:
                        continue
                    img, zb = imgs[k], zbufs[k]
                    h, wd, zr = img.shape[0], img.shape[1], zb.shape[0]
                    sx = l0 * vpx[k, i0] + l1 * vpx[k, i1] + l2 * vpx[k, i2]
                    sy = l0 * vpy[k, i0] + l1 * vpy[k, i1] + l2 * vpy[k, i2]
                    iy, ix = min(max(int(sy), 0), h - 1), min(max(int(sx), 0), wd - 1)
                    seen = zb[min(max(int(sy / h * zr), 0), zr - 1), min(max(int(sx / wd * zr), 0), zr - 1)]
                    here = l0 * dep[k, 0] + l1 * dep[k, 1] + l2 * dep[k, 2]
                    if here >= seen - reach and inners[k][iy, ix]:
                        zy, zx = min(max(int(sy / h * zr), 0), zr - 1), min(max(int(sx / wd * zr), 0), zr - 1)
                        hid = max(seen - here, 0.) / occ
                        ws = (w[k] * facing[k][zy, zx] * np.exp(-hid * hid)) ** sharp
                        for c in range(3):
                            acc[k, Y, X, c] += img[iy, ix, c] * ws
                        wsum[k, Y, X] += ws
                        cover[Y, X] += wc[k] ** 2
    return acc, wsum, cover, used


SEEN_W = 1e-20  # a view weight above this counts as seen
TONE_CELL = 0.02  # share of the model size: the views differ in tone (lighting, colour grading) and the seams between them
TONE_SIGMA = 0.04  # show; the low frequencies of every view are levelled over cells of the surface this big, blurred this wide
# in 3D, not in the texture: a gaussian of 40 texels over the 4096 atlas of the bf16 mesh, cut into small UV charts, mixed the
# colours of unrelated neighbouring charts (hair into the nose) and printed sharp-edged light and dark patches along the charts


def combine(atlas, acc, wsum, P, UV, tris):
    """Blend the views; the low frequencies (tone) of every view are levelled to the weighted mean of all views around the
    texel on the surface, so the seams between the views vanish, its own detail stays. The generated texture is not used: its colour is off."""
    from scipy.spatial import cKDTree
    size = atlas.shape[0]
    uvs = UV * size
    ext = float(np.ptp(P, axis=0).max())
    cen = P[tris].mean(1)
    _, cell = np.unique(np.floor(cen / (TONE_CELL * ext)).astype(np.int64), axis=0, return_inverse=True)
    cell = cell.reshape(-1)
    nc = cell.max() + 1

    def per_cell(v, w):  # sums over the faces of every cell
        return np.stack([np.bincount(cell, v[:, k] * w, nc) for k in range(v.shape[1])], 1), np.bincount(cell, w, nc)

    cc, cn = per_cell(cen, np.ones(len(cen)))
    cc /= cn[:, None]
    tree = cKDTree(cc)
    d, k = tree.query(cc, k=min(64, nc), workers=-1)
    g = np.exp(-(d / (TONE_SIGMA * ext)) ** 2)  # cell to cell blur
    tot = sum(wsum.values())
    ones = np.ones(atlas.shape[:2], np.bool_)
    lows, ws, cols = {}, {}, {}
    for n in acc:
        m = wsum[n] > SEEN_W  # the weights are powers (SHARP) of products of fractions: 1e-10 is a real weight
        cols[n] = acc[n] / np.maximum(wsum[n], 1e-30)[..., None]
        fs, fc = _face_sums(uvs, tris, cols[n], m)
        fw, fa = _face_sums(uvs, tris, (wsum[n] ** (1 / 3))[..., None], ones)  # w**2: a view that faces the texel sets the tone, a grazing one does not
        s, c = per_cell(fs, np.ones(len(fs)))
        s, c = s[:, :3], np.bincount(cell, fc, nc)
        ww, wa = np.bincount(cell, fw[:, 0], nc), np.bincount(cell, fa, nc)
        lows[n] = (g[..., None] * s[k]).sum(1) / np.maximum((g * c[k]).sum(1), 1e-6)[:, None]
        ws[n] = (g * ww[k]).sum(1) / np.maximum((g * wa[k]).sum(1), 1e-6)
    target = sum(lows[n] * ws[n][:, None] for n in acc) / np.maximum(sum(ws.values()), 1e-6)[:, None]
    # cells to faces: gaussian over the nearest cells, no steps at the cell borders
    d, k = tree.query(cen, k=min(8, nc), workers=-1)
    g = np.exp(-(d / (TONE_CELL * ext)) ** 2) + 1e-12
    g /= g.sum(1, keepdims=True)
    out = np.zeros_like(atlas)
    for n in acc:
        off = _face_image(uvs, tris, ((target - lows[n])[k] * g[..., None]).sum(1).astype(np.float32), size)
        out += (cols[n] + off * (wsum[n] > SEEN_W)[..., None]) * wsum[n][..., None]
    return out / np.maximum(tot, 1e-30)[..., None], tot


@njit(cache=True)
def _face_sums(uvs, tris, img, mask):
    """Per face: the sum of img over its texels where mask is set, and their number."""
    size = img.shape[0]
    s = np.zeros((tris.shape[0], img.shape[2]))
    c = np.zeros(tris.shape[0])
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        u0, u1, u2, v0, v1, v2 = uvs[i0, 0], uvs[i1, 0], uvs[i2, 0], uvs[i0, 1], uvs[i1, 1], uvs[i2, 1]
        ax, ay = int(np.floor(min(u0, u1, u2))), int(np.floor(min(v0, v1, v2)))
        ex, ey = int(np.ceil(max(u0, u1, u2))), int(np.ceil(max(v0, v1, v2)))
        if max(ex - ax, ey - ay) > 200:
            continue
        d = (v1 - v2) * (u0 - u2) + (u2 - u1) * (v0 - v2)
        if abs(d) < 1e-9:
            continue
        for Y in range(ay, ey + 1):
            for X in range(ax, ex + 1):
                l0 = ((v1 - v2) * (X + .5 - u2) + (u2 - u1) * (Y + .5 - v2)) / d
                l1 = ((v2 - v0) * (X + .5 - u2) + (u0 - u2) * (Y + .5 - v2)) / d
                if l0 < 0 or l1 < 0 or l0 + l1 > 1:
                    continue
                yy, xx = min(max(Y, 0), size - 1), min(max(X, 0), size - 1)
                if mask[yy, xx]:
                    c[t] += 1
                    for k in range(img.shape[2]):
                        s[t, k] += img[yy, xx, k]
    return s, c


@njit(cache=True)
def _face_image(uvs, tris, vals, size):
    """Texture with every texel set to the value of the face it lies on."""
    out = np.zeros((size, size, vals.shape[1]), np.float32)
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        u0, u1, u2, v0, v1, v2 = uvs[i0, 0], uvs[i1, 0], uvs[i2, 0], uvs[i0, 1], uvs[i1, 1], uvs[i2, 1]
        ax, ay = int(np.floor(min(u0, u1, u2))), int(np.floor(min(v0, v1, v2)))
        ex, ey = int(np.ceil(max(u0, u1, u2))), int(np.ceil(max(v0, v1, v2)))
        d = (v1 - v2) * (u0 - u2) + (u2 - u1) * (v0 - v2)
        if max(ex - ax, ey - ay) > 200 or abs(d) < 1e-9:
            continue
        for Y in range(max(ay, 0), min(ey, size - 1) + 1):
            for X in range(max(ax, 0), min(ex, size - 1) + 1):
                l0 = ((v1 - v2) * (X + .5 - u2) + (u2 - u1) * (Y + .5 - v2)) / d
                l1 = ((v2 - v0) * (X + .5 - u2) + (u0 - u2) * (Y + .5 - v2)) / d
                if l0 < 0 or l1 < 0 or l0 + l1 > 1:
                    continue
                for k in range(vals.shape[1]):
                    out[Y, X, k] = vals[t, k]
    return out


BAD_SHARE = 0.5  # faces painted by a view on less than this share of their texels take the colour of the painted faces around (0.2: light shards remain)


def fill_faces(P, UV, tris, good, used, out):
    """Texels no view paints well (a flap under the skin, a sliver edge-on to every view, a strand in a crevice of the hair) take
    the colour of the nearest well painted faces in space: the generated texture has the wrong tone there (orange spots, light
    specks in the hair), and the UV neighbours are other charts."""
    from scipy.spatial import cKDTree
    size = out.shape[0]
    colsum, ng = _face_sums(UV * size, tris, out, good)
    _, na = _face_sums(UV * size, tris, out[..., :1], np.ones(good.shape, np.bool_))
    ok = (na > 0) & (ng >= 0.5 * na)
    if not ok.any():
        return 0
    tree = cKDTree(P[tris[ok]].mean(1))
    col = colsum[ok] / ng[ok][:, None]
    # per texel, not per face: inverse-distance blend of the 12 nearest painted faces, no flat patches
    pos, ax, ay = _face_texels(P, UV * size, tris, size, used & ~good)
    dist, k = tree.query(pos, k=12, workers=-1)
    w = 1 / (dist + 1e-4 * float(np.ptp(P, axis=0).max())) ** 2
    out[ay, ax] = (col[k] * w[..., None]).sum(1) / w.sum(1, keepdims=True)
    return len(pos)


@njit(cache=True)
def _face_texels(P, uvs, tris, size, mask):
    """Texels where mask is set: their position in space (on the face they lie on), x and y in the texture."""
    cnt = 0
    for rep in range(2):  # count, then fill
        if rep:
            pos, ox, oy = np.zeros((cnt, 3)), np.zeros(cnt, np.int64), np.zeros(cnt, np.int64)
            cnt = 0
        for t in range(tris.shape[0]):
            i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
            u0, u1, u2, v0, v1, v2 = uvs[i0, 0], uvs[i1, 0], uvs[i2, 0], uvs[i0, 1], uvs[i1, 1], uvs[i2, 1]
            ax, ay = int(np.floor(min(u0, u1, u2))), int(np.floor(min(v0, v1, v2)))
            ex, ey = int(np.ceil(max(u0, u1, u2))), int(np.ceil(max(v0, v1, v2)))
            d = (v1 - v2) * (u0 - u2) + (u2 - u1) * (v0 - v2)
            if max(ex - ax, ey - ay) > 200 or abs(d) < 1e-9:
                continue
            for Y in range(ay, ey + 1):
                for X in range(ax, ex + 1):
                    l0 = ((v1 - v2) * (X + .5 - u2) + (u2 - u1) * (Y + .5 - v2)) / d
                    l1 = ((v2 - v0) * (X + .5 - u2) + (u0 - u2) * (Y + .5 - v2)) / d
                    yy, xx = min(max(Y, 0), size - 1), min(max(X, 0), size - 1)
                    if l0 < 0 or l1 < 0 or l0 + l1 > 1 or not mask[yy, xx]:
                        continue
                    if rep:
                        for c in range(3):
                            pos[cnt, c] = l0 * P[i0, c] + l1 * P[i1, c] + (1 - l0 - l1) * P[i2, c]
                        ox[cnt], oy[cnt] = xx, yy
                    cnt += 1
    return pos, ox, oy


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src, dst = args[:2]
    views = {n: load_view(p) for n, p in zip(NAMES, args[2:6])}
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P = accessor(j, b, prim["attributes"]["POSITION"])
    UV = accessor(j, b, prim["attributes"]["TEXCOORD_0"])
    tris = accessor(j, b, prim["indices"]).reshape(-1, 3)
    if "--no-smooth" not in sys.argv:
        P = smooth_positions(P, tris)
        acc = j["accessors"][prim["attributes"]["POSITION"]]
        off = j["bufferViews"][acc["bufferView"]].get("byteOffset", 0) + acc.get("byteOffset", 0)
        b = bytearray(b)
        b[off:off + P.nbytes] = P.tobytes()
        b = bytes(b)
        print(f"mesh smoothed, {SMOOTH} Taubin steps")
    mat = j["materials"][prim.get("material", 0)]
    tex = j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    bv = j["bufferViews"][j["images"][tex["source"]]["bufferView"]]
    atlas = np.asarray(Image.open(io.BytesIO(b[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB")).astype(np.float32)
    # which side of the mesh the "left" view looks at: the sign with the smaller difference to the generated colour
    best = None
    for side in (1., -1.):
        acc, ws, _, _ = paint(P, UV, tris, atlas, views, side, step=12)
        w = sum(ws.values())
        acc = sum(acc.values())
        m = w > 1e-3
        err = np.abs(acc[m] / w[m][:, None] - atlas[m]).mean() if m.any() else 1e9
        print(f"left view sees {'+' if side > 0 else '-'}x: difference {err:.2f}")
        if best is None or err < best[0]:
            best = (err, side)
    acc, ws, cover, used = paint(P, UV, tris, atlas, views, best[1], do_align="--no-align" not in sys.argv)
    painted, w = combine(atlas, acc, ws, P, UV, tris)
    good = (cover > 0.05) & (w > SEEN_W)
    out = np.where(good[..., None], painted, atlas)
    print(f"{fill_faces(P, UV, tris, good, used, out)} texels without a view filled from their neighbours in space")
    # padding: faces smaller than a texel have no texel centre of their own and sample the neighbours / the generated colour
    from scipy.ndimage import distance_transform_edt
    dist, (py_, px_) = distance_transform_edt(~used, return_indices=True)
    pad = (~used) & (dist <= 6)
    out[pad] = out[py_[pad], px_[pad]]
    # the mesh was smoothed (or came without normals): the shading follows the final positions, not a stale or missing NORMAL
    nrm = vertex_normals(P, tris)
    b = b + b"\0" * (-len(b) % 4)
    if "NORMAL" in prim["attributes"]:
        na = j["accessors"][prim["attributes"]["NORMAL"]]
        nv = j["bufferViews"][na["bufferView"]]
        if nv.get("byteStride", 12) == 12 and nv["byteLength"] >= nrm.nbytes:
            off = nv.get("byteOffset", 0) + na.get("byteOffset", 0)
            b = b[:off] + nrm.tobytes() + b[off + nrm.nbytes:]
    else:
        j["bufferViews"].append({"buffer": 0, "byteOffset": len(b), "byteLength": nrm.nbytes, "target": 34962})
        j["accessors"].append({"bufferView": len(j["bufferViews"]) - 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
        prim["attributes"]["NORMAL"] = len(j["accessors"]) - 1
        b += nrm.tobytes()
    prim["attributes"].pop("TANGENT", None)  # stale after the smoothing
    # the normal, occlusion and metal-roughness maps were baked for the unsmoothed mesh: Blender showed their chart borders as
    # cracks over the face and a glossy see-through ponytail. The views carry the shading already, the engine ignores the maps.
    mat.pop("normalTexture", None)
    mat.pop("occlusionTexture", None)
    pbr = mat.setdefault("pbrMetallicRoughness", {})
    pbr.pop("metallicRoughnessTexture", None)
    pbr["metallicFactor"], pbr["roughnessFactor"] = 0.0, 1.0
    buf = io.BytesIO()
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(buf, format="PNG")
    b = b + b"\0" * (-len(b) % 4)
    bv["byteOffset"], bv["byteLength"] = len(b), len(buf.getvalue())
    b += buf.getvalue()
    j["buffers"][0]["byteLength"] = len(b) + (-len(b) % 4)
    write_glb(dst, j, b)
    print(f"{dst}: texture painted from the views, {int((cover > 0).mean() * 100)} % of the texels")


if __name__ == "__main__":
    main()
