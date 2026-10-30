#!/usr/bin/env python3
"""Finds the shop signs of the towns and prints, for every side of every board, the CAM string that
puts the camera in front of it (docs/autotests.md, TOWN_AUTO=50).

usage: pdm_signs_find.py <Корсары> [City_Name ...]    (no names: every town with signs)
output, a line per side, tab separated:
  town  texture  x y z (the centre of the board)  side (+1 / -1 along the normal)  CAM

The signs are the quads of pdm_props3d.is_sign(); the normal of a board is the cross product of its
edges (pdm_props3d.sign_axes). The camera stands DIST metres from the board along the normal, at the
height of the board; the hero stands under the board on the ground (y 0: the towns lie at 0), so the
camera looks at the board and the hero is in the frame below it. The side +1 is the face of the normal.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cff2gm  # noqa: E402
import pdm_props3d as P  # noqa: E402
import pdm_world as W  # noqa: E402

DIST = 2.5


def signs_of(world, loc):
    """[(texture, centre, normal)] of the boards of a town model, one per board (the original has a plane per face)."""
    cff = world.models[Path(loc["model"]).name.lower()]
    meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * W.K for c in p), texture=world.texture)
    found = []
    seen = set()
    for m in meshes:
        stem = P.stem_of(m)
        if not P.is_sign(stem) or not P.is_quad(m):
            continue
        pts = P.positions(m)
        key = tuple(np.round(np.concatenate([pts.min(0), pts.max(0)]), 2))
        if key in seen:
            continue
        seen.add(key)
        axes = P.sign_axes(m)
        if axes is None:
            continue
        n = np.cross(axes[1], axes[2])
        found.append((stem, pts.mean(0), n / np.linalg.norm(n)))
    return found


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    res = Path(sys.argv[1])
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    world = W.World(res, Path("/nonexistent"))
    wanted = {n.lower() for n in sys.argv[2:]}
    for path in sorted((res / "WORLDS" / "locations").glob("City_*.loc")):
        if wanted and path.stem.lower() not in wanted:
            continue
        for stem, c, n in signs_of(world, W.parse_loc(path)):
            for side in (1, -1):
                cam = c + n * side * DIST
                print("\t".join([path.stem, stem, f"{c[0]:.2f} {c[1]:.2f} {c[2]:.2f}", f"{side:+d}",
                                 f"{cam[0]:.2f},{c[1] + 0.2:.2f},{cam[2]:.2f},{c[0]:.2f},0,{c[2]:.2f}"]))


if __name__ == "__main__":
    main()
