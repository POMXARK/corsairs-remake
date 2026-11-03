"""render_glb.py model.glb out.png yaw pitch cx cy half [res] [texture.png]: orthographic albedo render with a simple light, crop
centred at (cx, cy) in model units of the rotated frame (0..1 of the bbox), half-size half (share of bbox)."""
import sys, io
import numpy as np
from PIL import Image
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pdm_project_views as N
from numba import njit

@njit(cache=True)
def ras(xy, z, uv, nz, tris, res, T):
    col = np.zeros((res, res, 3), np.uint8); zb = np.full((res, res), -1e9)
    TW = T.shape[0]
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t]
        x0, x1, x2, y0, y1, y2 = xy[i0, 0], xy[i1, 0], xy[i2, 0], xy[i0, 1], xy[i1, 1], xy[i2, 1]
        ax, ay = max(int(np.floor(min(x0, x1, x2))), 0), max(int(np.floor(min(y0, y1, y2))), 0)
        ex, ey = min(int(np.ceil(max(x0, x1, x2))), res - 1), min(int(np.ceil(max(y0, y1, y2))), res - 1)
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12 or ex - ax > 400 or ey - ay > 400:
            continue
        for Y in range(ay, ey + 1):
            for X in range(ax, ex + 1):
                l0 = ((y1 - y2) * (X + .5 - x2) + (x2 - x1) * (Y + .5 - y2)) / d
                l1 = ((y2 - y0) * (X + .5 - x2) + (x0 - x2) * (Y + .5 - y2)) / d
                l2 = 1 - l0 - l1
                if l0 < 0 or l1 < 0 or l2 < 0:
                    continue
                zz = l0 * z[i0] + l1 * z[i1] + l2 * z[i2]
                if zz > zb[Y, X]:
                    zb[Y, X] = zz
                    u = l0 * uv[i0, 0] + l1 * uv[i1, 0] + l2 * uv[i2, 0]
                    v = l0 * uv[i0, 1] + l1 * uv[i1, 1] + l2 * uv[i2, 1]
                    sh = 0.55 + 0.45 * abs(l0 * nz[i0] + l1 * nz[i1] + l2 * nz[i2])
                    for c in range(3):
                        col[Y, X, c] = min(255., T[min(max(int(v * TW), 0), TW - 1), min(max(int(u * TW), 0), TW - 1), c] * sh)
    return col

a = sys.argv
j, b = N.read_glb(a[1]); p = j['meshes'][0]['primitives'][0]
P = N.accessor(j, b, p['attributes']['POSITION']).astype(float); UV = N.accessor(j, b, p['attributes']['TEXCOORD_0']).astype(float)
T3 = N.accessor(j, b, p['indices']).reshape(-1, 3).astype(np.int64)
if len(a) > 9:
    T = np.asarray(Image.open(a[9]).convert('RGB'))
else:
    m = j['materials'][0]; v = j['bufferViews'][j['images'][j['textures'][m['pbrMetallicRoughness']['baseColorTexture']['index']]['source']]['bufferView']]
    T = np.asarray(Image.open(io.BytesIO(b[v['byteOffset']:v['byteOffset'] + v['byteLength']])).convert('RGB'))
yaw, pit = np.radians(float(a[3])), np.radians(float(a[4]))
Ry = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
Rx = np.array([[1, 0, 0], [0, np.cos(pit), -np.sin(pit)], [0, np.sin(pit), np.cos(pit)]])
Q = P @ (Rx @ Ry).T
vn = N.vertex_normals(P.astype(np.float32), T3.astype(np.uint32)) @ (Rx @ Ry).T
lo, hi = Q.min(0), Q.max(0); ext = (hi - lo)[:2].max()
cx, cy, half = float(a[5]), float(a[6]), float(a[7]); res = int(a[8]) if len(a) > 8 else 1000
c0 = lo[:2] + np.array([cx, cy]) * (hi - lo)[:2]
xy = (Q[:, :2] - (c0 - half * ext)) / (2 * half * ext) * res
img = ras(xy, Q[:, 2], UV, vn[:, 2].copy(), T3, res, np.ascontiguousarray(T))
Image.fromarray(img[::-1]).save(a[2])
