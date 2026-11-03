#!/usr/bin/env python3
"""Give a textured glb the UV of an .obj with the same surface (e.g. unwrapped in 3DCoat by coat_autouv.py).

uv_from_obj.py src.glb unwrapped.obj out.glb [tex]

The .obj keeps its faces and per-corner UV; vertices are split per (position, uv) pair. Every texel gets the colour of
the nearest point of src.glb (as solidify.py does), then pdm_project_views.py can paint it from the views.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from solidify import load, log, save, surface_samples  # noqa: E402
from pdm_project_views import _face_texels  # noqa: E402


def read_obj(path):
    V, T, F, FT = [], [], [], []
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == 'v':
            V.append([float(x) for x in p[1:4]])
        elif p[0] == 'vt':
            T.append([float(x) for x in p[1:3]])
        elif p[0] == 'f':
            c = [q.split('/') for q in p[1:]]
            for i in range(1, len(c) - 1):  # fan for polygons
                tri = (c[0], c[i], c[i + 1])
                F.append([int(q[0]) - 1 for q in tri])
                FT.append([int(q[1]) - 1 if len(q) > 1 and q[1] else -1 for q in tri])  # -1: no uv
    return np.array(V), np.array(T), np.array(F), np.array(FT)


def main():
    from scipy import ndimage as nd
    from scipy.spatial import cKDTree
    src, obj, dst = sys.argv[1:4]
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 4096
    V, T, F, FT = read_obj(obj)
    pairs, inv = np.unique(np.stack([F.ravel(), FT.ravel()], 1), axis=0, return_inverse=True)
    V2, UV, F2 = V[pairs[:, 0]], T[pairs[:, 1]], inv.reshape(-1, 3)
    log('obj', len(F), 'faces', len(V2), 'vertices after the uv split')
    P, SUV, tris, img = load(src)
    pts, puv = surface_samples(P, tris, 0.001, np.random.default_rng(1), SUV)
    H, W = img.shape[:2]
    col = img[np.clip((puv[:, 1] * H).astype(int), 0, H - 1), np.clip((puv[:, 0] * W).astype(int), 0, W - 1)]
    tree = cKDTree(pts)
    # obj UV has v up, glTF has v down
    uvg = np.stack([UV[:, 0], 1 - UV[:, 1]], 1)
    tpos, tx, ty = _face_texels(V2.astype(np.float64), uvg * size, F2.astype(np.int64), size,
                                np.ones((size, size), np.bool_))
    log('texels', len(tpos))
    _, k = tree.query(tpos, k=1, workers=-1, distance_upper_bound=0.02)
    hit = k < len(pts)
    out = np.zeros((size, size, 3), np.uint8)
    used = np.zeros((size, size), bool)
    out[ty[hit], tx[hit]], used[ty[hit], tx[hit]] = col[k[hit]], True
    dist, (iy, ix) = nd.distance_transform_edt(~used, return_indices=True)
    pad = ~used & (dist <= 8)
    out[pad] = out[iy[pad], ix[pad]]
    log('texture', size, 'used share', round(float(used.mean()), 3))
    save(dst, V2.astype(np.float32), uvg.astype(np.float32), F2.astype(np.uint32), out)
    log('saved', dst)


if __name__ == '__main__':
    main()
