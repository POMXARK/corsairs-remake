#!/usr/bin/env python3
"""Rebuild a generated head as one closed outer surface with a clean UV atlas.

solidify.py in.glb out.glb [voxel] [faces] [tex]

The TRELLIS/Pixal3D mesh (from an unsigned distance) is a closed thin shell: an outer and an inner wall a few mm apart.
At thin places both sides show: a double rim of the ear, a fold at the inner eye corner, a lower lid drawn twice. Here
the shell is drawn into voxels, the outside is flooded from the top and the sides (the open neck cut gets a lid), the
rest is solid, and its boundary (marching cubes) is the new mesh: one wall.
The mesh is simplified to `faces`, unwrapped with xatlas and gets the colour of the nearest point of in.glb; then
pdm_project_views.py paints it from the views as any other generated head.
Needs numpy, scipy, Pillow, scikit-image, fast-simplification, xatlas, numba.
"""
import io
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pdm_project_views import _face_texels, accessor, read_glb, vertex_normals, write_glb  # noqa: E402

DILATE = 1  # voxels: the shell is thickened by this to close the tears between faces, the solid is eroded back by it
SEAL = int(os.environ.get("SEAL", 4))  # voxels: the outside is flooded around a shell this thick (tears up to twice this are closed), then grows back
LID = 0.06  # share of the height: the neck cut is wavy and open; below this over its lowest point the neck is solid (its
# outline from below), the bottom stays where it was: pdm_project_views fits the mesh height to the figure in the views
t0 = time.time()


def log(*a):
    print(f'[solidify {time.time() - t0:6.1f}s]', *a, flush=True)


def load(path):
    j, b = read_glb(path)
    prim = j['meshes'][0]['primitives'][0]
    P = accessor(j, b, prim['attributes']['POSITION']).astype(np.float64)
    UV = accessor(j, b, prim['attributes']['TEXCOORD_0']).astype(np.float64)
    tris = accessor(j, b, prim['indices']).reshape(-1, 3).astype(np.int64)
    mat = j['materials'][prim.get('material', 0)]
    tex = j['textures'][mat['pbrMetallicRoughness']['baseColorTexture']['index']]
    bv = j['bufferViews'][j['images'][tex['source']]['bufferView']]
    o = bv.get('byteOffset', 0)
    img = np.asarray(Image.open(io.BytesIO(b[o:o + bv['byteLength']])).convert('RGB'))
    return P, UV, tris, img


def surface_samples(P, tris, step, rng, UV=None):
    """Points over the faces no farther than `step` apart (and their UV)."""
    a, b, c = P[tris[:, 0]], P[tris[:, 1]], P[tris[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = np.maximum(1, np.ceil(area / (step * step) * 2)).astype(np.int64)
    f = np.repeat(np.arange(len(tris)), n)
    r1, r2 = rng.random(len(f)), rng.random(len(f))
    s = np.sqrt(r1)
    l0, l1, l2 = 1 - s, s * (1 - r2), s * r2
    pts = l0[:, None] * a[f] + l1[:, None] * b[f] + l2[:, None] * c[f]
    if UV is None:
        return pts
    t = UV[tris[f]]
    return pts, l0[:, None] * t[:, 0] + l1[:, None] * t[:, 1] + l2[:, None] * t[:, 2]


def solid(P, tris, vox):
    from scipy import ndimage as nd
    lo = P.min(0) - 3 * vox
    shape = np.ceil((P.max(0) + 3 * vox - lo) / vox).astype(int)
    pts = surface_samples(P, tris, vox / 3, np.random.default_rng(0))
    ijk = np.clip(((pts - lo) / vox).astype(int), 0, shape - 1)
    shell = np.zeros(shape, bool)
    shell[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
    thin = nd.binary_dilation(shell, iterations=DILATE)
    thick = nd.binary_dilation(shell, iterations=SEAL)
    # lid: the neck cut seen from below, filled, is solid up to LID over the lowest point
    bottom = int((P[:, 1].min() - lo[1]) / vox)
    top = bottom + int(LID * np.ptp(P[:, 1]) / vox)
    # going down, the gaps of the neck ring are closed by the outline of the slice above: the neck goes on straight
    prev = nd.binary_fill_holes(thin[:, top, :])
    for y in range(top, bottom - 1, -1):
        cur = nd.binary_fill_holes(thin[:, y, :] | (prev & ~nd.binary_erosion(prev, iterations=2)))
        thin[:, y, :] |= cur
        thick[:, y, :] |= cur
        prev = cur
    thin[:, :bottom, :] = thick[:, :bottom, :] = False
    lab, _ = nd.label(~thick)
    seeds = np.unique(np.concatenate([lab[0].ravel(), lab[-1].ravel(), lab[:, -1].ravel(), lab[:, :, 0].ravel(),
                                      lab[:, :, -1].ravel(), lab[:, 0].ravel()]))
    outside = np.isin(lab, seeds[seeds > 0])
    # back to the thin shell: a few steps only, not through the tears
    outside = nd.binary_dilation(outside, iterations=SEAL - DILATE + 1, mask=~thin)
    inside = nd.binary_erosion(~outside, iterations=DILATE)
    log('voxels', shape, 'solid share', round(float(inside.mean()), 3))
    return inside, lo


def main():
    from scipy import ndimage as nd
    from scipy.spatial import cKDTree
    import fast_simplification
    import xatlas
    from skimage.measure import marching_cubes

    args = sys.argv[1:]
    src, dst = args[:2]
    vox = float(args[2]) if len(args) > 2 else 0.002
    faces = int(args[3]) if len(args) > 3 else 200000
    size = int(args[4]) if len(args) > 4 else 4096
    P, UV, tris, img = load(src)
    log('source', len(tris), 'faces')
    inside, lo = solid(P, tris, vox)
    vol = nd.gaussian_filter(inside.astype(np.float32), 1.0)
    V, F, _, _ = marching_cubes(vol, 0.5, spacing=(vox, vox, vox))
    V += lo
    F = F[:, ::-1].copy()  # outward winding for the glTF front face
    log('marching cubes', len(F), 'faces')
    lab = connected(F, len(V))
    keep = lab[F[:, 0]] == np.bincount(lab[F[:, 0]]).argmax()
    F = F[keep]
    V, F = fast_simplification.simplify(V.astype(np.float32), F.astype(np.int32), max(0., 1 - faces / len(F)))
    log('simplified', len(F), 'faces')
    vmap, F2, uvs = xatlas.parametrize(V, F)
    V2 = V[vmap].astype(np.float32)
    log('xatlas', len(F2), 'faces', len(V2), 'vertices')
    # colour of the nearest point of the source surface, per texel
    pts, puv = surface_samples(P, tris, 0.001, np.random.default_rng(1), UV)
    H = img.shape[0]
    col = img[np.clip((puv[:, 1] * H).astype(int), 0, H - 1), np.clip((puv[:, 0] * img.shape[1]).astype(int), 0, img.shape[1] - 1)]
    tree = cKDTree(pts)
    log('colour samples', len(pts))
    tpos, tx, ty = _face_texels(V2.astype(np.float64), uvs.astype(np.float64) * size, F2.astype(np.int64), size,
                                np.ones((size, size), np.bool_))
    log('texels', len(tpos))
    # bounded: texels far from the source (the new lid of the neck) made the unbounded search take minutes
    _, k = tree.query(tpos, k=1, workers=-1, distance_upper_bound=0.02)
    hit = k < len(pts)
    out = np.zeros((size, size, 3), np.uint8)
    used = np.zeros((size, size), bool)
    out[ty[hit], tx[hit]], used[ty[hit], tx[hit]] = col[k[hit]], True
    dist, (iy, ix) = nd.distance_transform_edt(~used, return_indices=True)
    pad = ~used & (dist <= 8)
    out[pad] = out[iy[pad], ix[pad]]
    log('texture', size, 'used share', round(float(used.mean()), 3))
    save(dst, V2, uvs.astype(np.float32), F2.astype(np.uint32), out)
    log('saved', dst)


def connected(F, n):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    a = np.concatenate([F[:, 0], F[:, 1]])
    b = np.concatenate([F[:, 1], F[:, 2]])
    return connected_components(coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)), directed=False)[1]


def save(path, V, UV, F, img):
    nrm = vertex_normals(V, F.astype(np.int64)).astype(np.float32)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format='PNG')
    parts = [V.tobytes(), nrm.tobytes(), UV.tobytes(), F.tobytes(), buf.getvalue()]
    views, b = [], b''
    for i, p in enumerate(parts):
        b += b'\0' * (-len(b) % 4)
        v = {'buffer': 0, 'byteOffset': len(b), 'byteLength': len(p)}
        if i < 3:
            v['target'] = 34962
        elif i == 3:
            v['target'] = 34963
        views.append(v)
        b += p
    j = {
        'asset': {'version': '2.0', 'generator': 'solidify.py'},
        'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3, 'material': 0}]}],
        'accessors': [
            {'bufferView': 0, 'componentType': 5126, 'count': len(V), 'type': 'VEC3',
             'min': V.min(0).tolist(), 'max': V.max(0).tolist()},
            {'bufferView': 1, 'componentType': 5126, 'count': len(V), 'type': 'VEC3'},
            {'bufferView': 2, 'componentType': 5126, 'count': len(V), 'type': 'VEC2'},
            {'bufferView': 3, 'componentType': 5125, 'count': F.size, 'type': 'SCALAR'}],
        'bufferViews': views,
        'buffers': [{'byteLength': len(b) + (-len(b) % 4)}],
        'images': [{'bufferView': 4, 'mimeType': 'image/png'}],
        'textures': [{'source': 0}],
        'materials': [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0.0, 'roughnessFactor': 1.0}}],
    }
    write_glb(path, j, b)


if __name__ == '__main__':
    main()
