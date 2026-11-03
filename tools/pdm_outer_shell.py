#!/usr/bin/env python3
"""Keep the outer shell of the mesh: <src.glb> <dst.glb> [--dirs 66] [--res 1536].

TRELLIS meshes of hair and beard hold layers under the visible surface; no view sees them, they only take texels and get a
flat colour. Faces that no ray of a parallel bundle from many directions around the model hits first are dropped; faces seen mostly
from behind (inverted winding, 40 % of the hero1 head after coherent re-orientation) are turned over.
pip: open3d trimesh numpy."""
import sys

import numpy as np


def sphere_dirs(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)


def visible_faces(V, F, ndir=66, res=1536, dirs=None, with_votes=False):
    import open3d as o3d
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
    centre = (V.min(0) + V.max(0)) / 2
    r = float(np.linalg.norm(V.max(0) - V.min(0))) / 2 * 1.05
    g = (np.arange(res) + 0.5) / res * 2 * r - r
    gx, gy = np.meshgrid(g, g)
    seen = np.zeros(len(F), bool)
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    votes = np.zeros(len(F))
    for d in (sphere_dirs(ndir) if dirs is None else np.asarray(dirs, float)):
        up = np.array([0, 1., 0]) if abs(d[1]) < 0.99 else np.array([1., 0, 0])
        a = np.cross(up, d)
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        o = centre + gx[..., None] * a + gy[..., None] * b + d * 2 * r  # the viewer sits on the side of d and looks along -d
        rays = np.concatenate([o, np.broadcast_to(-d, o.shape)], -1).reshape(-1, 6).astype(np.float32)
        ids = scene.cast_rays(o3d.core.Tensor(rays))["primitive_ids"].numpy()
        hit = np.unique(ids[ids < len(F)])
        seen[hit] = True
        votes[hit] += np.sign(n[hit] @ d)  # a face the viewer sees should face it: otherwise the winding is inverted
    return (seen, votes) if with_votes else seen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ndir = int(sys.argv[sys.argv.index("--dirs") + 1]) if "--dirs" in sys.argv else 66
    res = int(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 1536
    import trimesh
    m = trimesh.load(args[0], force="mesh", process=False)
    F = np.asarray(m.faces)
    seen, votes = visible_faces(np.asarray(m.vertices), F, ndir, res, with_votes=True)
    print(f"outer shell: {seen.sum()} of {len(seen)} faces, {(votes < 0).sum()} with inverted winding turned over")
    F[votes < 0] = F[votes < 0][:, [0, 2, 1]]
    m.faces = F
    m.update_faces(seen)
    m.remove_unreferenced_vertices()
    m.export(args[1])
    print(f"{args[1]} written")


if __name__ == "__main__":
    main()
