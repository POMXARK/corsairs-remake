#!/usr/bin/env python3
"""Paint the base colour texture of a generated .glb from the four views it was generated from.

The Pixal3D/TRELLIS.2 texture is generated per voxel and smears small details (eyes, eyebrows, lips). The views
(front, left, back, right, orthographic, cropped to the figure) are sharp and the mesh is built to match them, so every
texel is projected into the views and coloured from the view that faces it; where no view sees the texel the generated
colour stays. Usage: pdm_project_views.py in.glb out.glb front.png left.png back.png right.png
Before projecting, every view is aligned to the mesh: the mesh is drawn with its own generated texture from the view's side
and the view is moved by the dense optical flow towards that drawing (the mesh differs from the view by a few pixels at the
nostrils, the mouth corners, the eyelids), so the sharp details land where the geometry has them.
Needs numpy, Pillow, scipy and OpenCV (opencv-python-headless)."""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

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
    buf = np.full((res, res), -1e9, np.float32)
    uvmap = np.zeros((res, res, 2), np.float32)
    for f in tris:
        x, y, z = px[f], py[f], depth[f]
        a = np.floor([x.min(), y.min()]).astype(int)
        e = np.ceil([x.max(), y.max()]).astype(int)
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(d) < 1e-9 or (e - a).max() > 300:
            continue
        X, Y = np.meshgrid(np.arange(a[0], e[0] + 1), np.arange(a[1], e[1] + 1))
        l0 = ((y[1] - y[2]) * (X + .5 - x[2]) + (x[2] - x[1]) * (Y + .5 - y[2])) / d
        l1 = ((y[2] - y[0]) * (X + .5 - x[2]) + (x[0] - x[2]) * (Y + .5 - y[2])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= -.02) & (l1 >= -.02) & (l2 >= -.02) & (X >= 0) & (X < res) & (Y >= 0) & (Y < res)
        if ok.any():
            xs, ys, zz = X[ok], Y[ok], (l0 * z[0] + l1 * z[1] + l2 * z[2])[ok]
            win = zz > buf[ys, xs]
            buf[ys[win], xs[win]] = zz[win]
            for k in range(2):
                uvmap[ys[win], xs[win], k] = (l0 * UV[f[0], k] + l1 * UV[f[1], k] + l2 * UV[f[2], k])[ok][win]
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
    acc = {n: np.zeros_like(atlas) for n in dirs}  # per view: sum of w*colour and sum of w
    wsum = {n: np.zeros(atlas.shape[:2], np.float32) for n in dirs}
    cover = np.zeros(atlas.shape[:2], np.float32)
    used = np.zeros(atlas.shape[:2], bool)  # texels some triangle lies on
    snorm = smooth_normals(P, tris)
    for fi in range(0, len(tris), step):
        f = tris[fi]
        pp = P[f]
        if np.linalg.norm(np.cross(pp[1] - pp[0], pp[2] - pp[0])) < 1e-12:
            continue
        nrm = snorm[fi]
        uv = UV[f] * size
        a = np.floor(uv.min(0)).astype(int)
        e = np.ceil(uv.max(0)).astype(int)
        if (e - a).max() > 200:
            continue
        d = (uv[1, 1] - uv[2, 1]) * (uv[0, 0] - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (uv[0, 1] - uv[2, 1])
        if abs(d) < 1e-9:
            continue
        X, Y = np.meshgrid(np.arange(a[0], e[0] + 1), np.arange(a[1], e[1] + 1))
        l0 = ((uv[1, 1] - uv[2, 1]) * (X + .5 - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (Y + .5 - uv[2, 1])) / d
        l1 = ((uv[2, 1] - uv[0, 1]) * (X + .5 - uv[2, 0]) + (uv[0, 0] - uv[2, 0]) * (Y + .5 - uv[2, 1])) / d
        l2 = 1 - l0 - l1
        ok = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not ok.any():
            continue
        ax, ay = X[ok], Y[ok]
        used[ay, ax] = True
        for name, dv in dirs.items():
            lim = 0.05  # holes between the views stay with the smeared generated colour: let every view reach far, SHARP keeps the best one on top
            # no cap below 1: with /0.5 every view facing the texel at more than 55 % weighed 1, the front and the side view
            # met half and half in the eye sockets and on the cheeks (ghost irises, ComfyUI_00016) and SHARP had nothing to sharpen
            w = np.clip((nrm @ np.array(dv) - lim) / (1 - lim), 0, 1)
            wc = min(1., w * (1 - lim) / 0.5)  # the cover keeps the old scale: which texels count as seen does not change
            if w <= 0:
                continue
            px, py = project(pp, name, views[name], lo, hi)
            sx = (l0 * px[0] + l1 * px[1] + l2 * px[2])[ok]
            sy = (l0 * py[0] + l1 * py[1] + l2 * py[2])[ok]
            img = views[name][0]
            c = img[np.clip(sy.astype(int), 0, img.shape[0] - 1), np.clip(sx.astype(int), 0, img.shape[1] - 1)]
            zr = zbufs[name].shape[0]
            seen = zbufs[name][np.clip((sy / img.shape[0] * zr).astype(int), 0, zr - 1),
                               np.clip((sx / img.shape[1] * zr).astype(int), 0, zr - 1)]
            here = (l0[ok] * (pp[0] @ np.array(dv)) + l1[ok] * (pp[1] @ np.array(dv)) + l2[ok] * (pp[2] @ np.array(dv)))
            iy, ix = np.clip(sy.astype(int), 0, img.shape[0] - 1), np.clip(sx.astype(int), 0, img.shape[1] - 1)
            vis = (here >= seen - reach) & views[name][2][iy, ix]
            acc[name][ay[vis], ax[vis]] += c[vis] * w ** SHARP
            wsum[name][ay[vis], ax[vis]] += w ** SHARP
            cover[ay[vis], ax[vis]] += wc ** 2
    return acc, wsum, cover, used


TONE_SIGMA = 40  # texels: the views differ in tone (lighting, colour grading) and the seams between them show; level the low frequencies


def combine(atlas, acc, wsum):
    """Blend the views; the low frequencies (tone) of every view are levelled to the weighted mean of all views around the
    texel, so the seams between the views vanish, its own detail stays. The generated texture is not used: its colour is off."""
    import cv2
    tot = sum(wsum.values())
    cols, lows, ws = {}, {}, {}
    for n in acc:
        m = (wsum[n] > 1e-6).astype(np.float32)
        cols[n] = acc[n] / np.maximum(wsum[n], 1e-6)[..., None]
        norm = np.maximum(cv2.GaussianBlur(m, (0, 0), TONE_SIGMA), 1e-4)[..., None]
        lows[n] = cv2.GaussianBlur(cols[n] * m[..., None], (0, 0), TONE_SIGMA) / norm
        ws[n] = cv2.GaussianBlur(wsum[n] ** (1 / 3), (0, 0), TONE_SIGMA)[..., None]  # w**2: a view that faces the texel sets the tone, a grazing one does not
    target = sum(lows[n] * ws[n] for n in acc) / np.maximum(sum(ws.values()), 1e-6)
    out = np.zeros_like(atlas)
    for n in acc:
        out += (cols[n] + (target - lows[n]) * (wsum[n] > 1e-6)[..., None]) * wsum[n][..., None]
    return out / np.maximum(tot, 1e-6)[..., None], tot


BAD_SHARE = 0.5  # faces painted by a view on less than this share of their texels take the colour of the painted faces around (0.2: light shards remain)


def fill_faces(P, UV, tris, good, out):
    """Faces whose texels no view paints well (a flap under the skin, a sliver edge-on to every view) take the mean colour of the
    nearest well painted faces in space: the generated texture has the wrong tone there (orange spots), the UV neighbours are other charts."""
    from scipy.spatial import cKDTree
    size = out.shape[0]
    cen, col, bad = [], [], []
    for i, f in enumerate(tris):
        uv = UV[f] * size
        a = np.floor(uv.min(0)).astype(int)
        e = np.ceil(uv.max(0)).astype(int)
        if (e - a).max() > 200:
            continue
        d = (uv[1, 1] - uv[2, 1]) * (uv[0, 0] - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (uv[0, 1] - uv[2, 1])
        if abs(d) < 1e-9:
            continue
        X, Y = np.meshgrid(np.arange(a[0], e[0] + 1), np.arange(a[1], e[1] + 1))
        l0 = ((uv[1, 1] - uv[2, 1]) * (X + .5 - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (Y + .5 - uv[2, 1])) / d
        l1 = ((uv[2, 1] - uv[0, 1]) * (X + .5 - uv[2, 0]) + (uv[0, 0] - uv[2, 0]) * (Y + .5 - uv[2, 1])) / d
        ok = (l0 >= 0) & (l1 >= 0) & (l0 + l1 <= 1)
        if not ok.any():
            continue
        ax, ay = np.clip(X[ok], 0, size - 1), np.clip(Y[ok], 0, size - 1)
        share = good[ay, ax].mean()
        if share >= 0.5:
            cen.append(P[f].mean(0))
            col.append(out[ay, ax][good[ay, ax]].mean(0))
        elif share < BAD_SHARE:
            bad.append((P[f], l0[ok], l1[ok], ax, ay))
    if not bad or not cen:
        return 0
    tree = cKDTree(np.array(cen))
    col = np.array(col)
    for pp, b0, b1, ax, ay in bad:  # per texel, not per face: inverse-distance blend of the 12 nearest painted faces, no flat patches
        pos = b0[:, None] * pp[0] + b1[:, None] * pp[1] + (1 - b0 - b1)[:, None] * pp[2]
        dist, k = tree.query(pos, k=12)
        w = 1 / (dist + 1e-4 * float(np.ptp(P, axis=0).max())) ** 2
        out[ay, ax] = (col[k] * w[..., None]).sum(1) / w.sum(1, keepdims=True)
    return len(bad)


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
    painted, w = combine(atlas, acc, ws)
    # texels no view sees well (folded slivers, faces edge-on to every view) keep the generated pattern, but in the tone of the
    # painted texels around: the generated texture is off in colour and shows there as orange spots
    import cv2
    good = cover > 0.05
    g = good[..., None].astype(np.float32)
    norm = np.maximum(cv2.GaussianBlur(good.astype(np.float32), (0, 0), 10), 1e-4)[..., None]
    lowp = cv2.GaussianBlur(painted * g, (0, 0), 10) / norm
    lowa = cv2.GaussianBlur(atlas * g, (0, 0), 10) / norm
    near = cv2.GaussianBlur(good.astype(np.float32), (0, 0), 10)[..., None] > 0.01
    fill = np.where(near, atlas + lowp - lowa, atlas)
    out = np.where(good[..., None], painted, np.where(used[..., None], fill, atlas))
    # padding: faces smaller than a texel have no texel centre of their own and sample the neighbours / the generated colour
    from scipy.ndimage import distance_transform_edt
    dist, (py_, px_) = distance_transform_edt(~used, return_indices=True)
    pad = (~used) & (dist <= 6)
    out[pad] = out[py_[pad], px_[pad]]
    print(f"{fill_faces(P, UV, tris, good, out)} faces without a view filled from their neighbours in space")
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
