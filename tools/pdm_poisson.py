#!/usr/bin/env python3
"""Watertight body from the outer shell: <src.glb> <dst.glb> [--points 600000] [--depth 9] [--faces 20000].
The shell (pdm_outer_shell.py) has the right winding, so its surface samples with normals feed the screened Poisson
reconstruction; the result is closed (neck included). pip: pymeshlab trimesh numpy."""
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from pdm_project_views import accessor, read_glb  # noqa: E402


def opt(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    import pymeshlab as ml
    import trimesh
    src, dst = [a for a in sys.argv[1:] if not a.startswith("--")][:2]
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P = accessor(j, b, prim["attributes"]["POSITION"]).astype(np.float64)
    T = accessor(j, b, prim["indices"]).reshape(-1, 3).astype(np.int32)
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(P, T))
    ms.generate_sampling_poisson_disk(samplenum=opt("--points", 600000), subsample=False)
    ms.generate_surface_reconstruction_screened_poisson(depth=opt("--depth", 9), preclean=True)
    ms.meshing_remove_connected_component_by_face_number(mincomponentsize=500)
    print("poisson:", ms.current_mesh().face_number(), "faces")
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=opt("--faces", 20000), preservenormal=True, qualitythr=0.5)
    m = ms.current_mesh()
    trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=False).export(dst)
    print(dst, "written", m.face_number(), "faces")


if __name__ == "__main__":
    main()
