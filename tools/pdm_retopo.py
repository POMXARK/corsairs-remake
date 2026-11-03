#!/usr/bin/env python3
"""Light mesh for the game: <src.glb> <dst.glb> [--faces 12000] [--cell 0.4].

The painted head has 48 thousand faces and hair of thin ribbons. Uniform resampling (voxels of --cell % of the size) closes the
ribbons into one shell, quadric decimation brings it to --faces. The result has no UV and no colour: pdm_view_uv.py <dst> --colour <src>
unwraps it and carries the colour of the painted mesh (nearest surface point), pdm_project_views.py then paints the views anew.
pip: pymeshlab trimesh."""
import sys

import numpy as np


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    faces = int(sys.argv[sys.argv.index("--faces") + 1]) if "--faces" in sys.argv else 12000
    cell = float(sys.argv[sys.argv.index("--cell") + 1]) if "--cell" in sys.argv else 0.4
    import pymeshlab as ml
    import trimesh
    m = trimesh.load(args[0], force="mesh", process=False)
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(np.asarray(m.vertices, np.float64), np.asarray(m.faces, np.int32)))
    ms.generate_resampled_uniform_mesh(cellsize=ml.PercentageValue(cell), mergeclosevert=True, multisample=True)
    print(f"resampled: {ms.current_mesh().face_number()} faces")
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=faces, preserveboundary=True, preservenormal=True, qualitythr=0.5)
    ms.meshing_remove_connected_component_by_face_number(mincomponentsize=50)
    ms.meshing_repair_non_manifold_edges(method=0)
    ms.meshing_repair_non_manifold_vertices()
    try:
        ms.meshing_re_orient_faces_coherently()
    except Exception as e:  # pdm_outer_shell.py fixes the winding by visibility anyway
        print("orientation skipped:", str(e).splitlines()[-1])
    r = ms.current_mesh()
    out = trimesh.Trimesh(r.vertex_matrix(), r.face_matrix(), process=False)
    out.export(args[1])
    print(f"{args[1]}: {len(out.faces)} faces")


if __name__ == "__main__":
    main()
