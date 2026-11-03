#!/usr/bin/env python3
"""Keep the outer shell of the mesh: <src.glb> <dst.glb> [--dirs 66] [--res 1536].

TRELLIS meshes of hair and beard hold layers under the visible surface; no view sees them, they only take texels and get a
flat colour. Faces that no ray of a parallel bundle from many directions around the model hits first are dropped.
pip: open3d trimesh numpy."""
import sys

import numpy as np


def sphere_dirs(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)


def visible_faces(V, F, ndir=66, res=1536, dirs=None):
    import open3d as o3d
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
    centre = (V.min(0) + V.max(0)) / 2
    r = float(np.linalg.norm(V.max(0) - V.min(0))) / 2 * 1.05
    g = (np.arange(res) + 0.5) / res * 2 * r - r
    gx, gy = np.meshgrid(g, g)
    seen = np.zeros(len(F), bool)
    for d in (sphere_dirs(ndir) if dirs is None else np.asarray(dirs, float)):
        up = np.array([0, 1., 0]) if abs(d[1]) < 0.99 else np.array([1., 0, 0])
        a = np.cross(up, d)
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        o = centre + gx[..., None] * a + gy[..., None] * b - d * 2 * r
        rays = np.concatenate([o, np.broadcast_to(d, o.shape)], -1).reshape(-1, 6).astype(np.float32)
        ids = scene.cast_rays(o3d.core.Tensor(rays))["primitive_ids"].numpy()
        seen[ids[ids < len(F)]] = True
    return seen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ndir = int(sys.argv[sys.argv.index("--dirs") + 1]) if "--dirs" in sys.argv else 66
    res = int(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 1536
    import trimesh
    m = trimesh.load(args[0], force="mesh", process=False)
    seen = visible_faces(np.asarray(m.vertices), np.asarray(m.faces), ndir, res)
    print(f"outer shell: {seen.sum()} of {len(seen)} faces")
    m.update_faces(seen)
    m.remove_unreferenced_vertices()
    m.export(args[1])
    print(f"{args[1]} written")


if __name__ == "__main__":
    main()
