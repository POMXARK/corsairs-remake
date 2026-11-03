#!/usr/bin/env python3
"""Turn the inverted faces of a GLB over, keep everything else (geometry, UV, texture): <src.glb> <dst.glb> [--res 1536].
A face the viewer sees must face the viewer: the vote of 66 ray-cast directions (pdm_outer_shell.visible_faces) decides.
Unlike pdm_outer_shell.py nothing is deleted and the atlas stays, so the generated texture can still be repainted in its own UV.
pip: open3d numpy."""
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from pdm_outer_shell import visible_faces  # noqa: E402
from pdm_project_views import accessor, read_glb, write_glb  # noqa: E402


def main():
    src, dst = [a for a in sys.argv[1:] if not a.startswith("--")][:2]
    res = int(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 1536
    j, b = read_glb(src)
    prim = j["meshes"][0]["primitives"][0]
    P = accessor(j, b, prim["attributes"]["POSITION"]).astype(np.float64)
    T = accessor(j, b, prim["indices"]).reshape(-1, 3).astype(np.int64)
    _, votes = visible_faces(P, T, res=res, with_votes=True)
    flip = votes < 0
    print(f"{flip.sum()} of {len(T)} faces turned over")
    T[flip] = T[flip][:, [0, 2, 1]]
    acc = j["accessors"][prim["indices"]]
    view = j["bufferViews"][acc["bufferView"]]
    dt = {5125: "<u4", 5123: "<u2"}[acc["componentType"]]
    b = bytearray(b)
    off = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    b[off:off + T.size * np.dtype(dt).itemsize] = T.astype(dt).tobytes()
    write_glb(dst, j, bytes(b))
    print(dst, "written")


if __name__ == "__main__":
    main()
