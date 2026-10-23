#!/usr/bin/env python3
"""The invisible walls of the floor pdm_world.py makes for the locations (ours).

The engine walks from triangle to triangle across shared edges, so a floor cut apart where it goes on
is a wall nobody sees: the hero stops in the middle of a street and goes around. Prints for every
location
- seams: the edges with no neighbour beyond which, 3 cm on, lies floor of the same height, the longest
  first (a seam of a step or a stair may be the edge of a real step);
- the parts of the floor not joined by any edge, by area: the yards behind the walls are parts of
  their own, a street or a room cut in two is the bug.

usage: ptc_seams.py <PDM RESOURCE dir> [<location> ...]   (all WORLDS/locations/*.loc by default)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdm_world as w  # noqa: E402

AWAY = 0.03  # metres beyond an open edge
HEIGHT = 0.25  # metres: floor that near in height goes on there
SHOW = 5


def check(floor):
    ids = {}
    tris = [[ids.setdefault(tuple(round(c, 4) for c in p), len(ids)) for p in t] for t in floor]
    edges = {}
    for n, t in enumerate(tris):
        for j in range(3):
            edges.setdefault(frozenset((t[j], t[j - 1])), []).append((n, j))

    grid = {}
    for n, t in enumerate(floor):
        for i in range(math.floor(min(p[0] for p in t)), math.floor(max(p[0] for p in t)) + 1):
            for k in range(math.floor(min(p[2] for p in t)), math.floor(max(p[2] for p in t)) + 1):
                grid.setdefault((i, k), []).append(n)

    def floor_at(x, z, y, skip):
        for n in grid.get((math.floor(x), math.floor(z)), ()):
            poly = [(p[0], p[2]) for p in floor[n]]
            s = [w.area2([poly[k - 1], poly[k], (x, z)]) for k in range(3)]
            if n != skip and (all(v >= -1e-9 for v in s) or all(v <= 1e-9 for v in s)) \
                    and abs(w.plane(floor[n])(x, z) - y) < HEIGHT:
                return True
        return False

    seams = []
    for ts in edges.values():
        if len(ts) != 1:
            continue
        n, j = ts[0]
        a, b, c = floor[n][j - 1], floor[n][j], floor[n][(j + 1) % 3]
        length = math.dist((a[0], a[2]), (b[0], b[2]))
        if length < 0.05:
            continue
        mx, mz = (a[0] + b[0]) / 2, (a[2] + b[2]) / 2
        nx, nz = (a[2] - b[2]) / length, (b[0] - a[0]) / length
        if nx * (c[0] - mx) + nz * (c[2] - mz) > 0:
            nx, nz = -nx, -nz
        if floor_at(mx + nx * AWAY, mz + nz * AWAY, (a[1] + b[1]) / 2, n):
            seams.append((length, mx, (a[1] + b[1]) / 2, mz))

    part = [-1] * len(tris)
    areas = []
    for s in range(len(tris)):
        if part[s] >= 0:
            continue
        part[s], todo, area = len(areas), [s], 0.0
        while todo:
            t = todo.pop()
            area += abs(w.area2([(p[0], p[2]) for p in floor[t]])) / 2
            for j in range(3):
                for o, _ in edges[frozenset((tris[t][j], tris[t][j - 1]))]:
                    if part[o] < 0:
                        part[o] = part[s]
                        todo.append(o)
        areas.append(area)
    return sorted(seams, reverse=True), sorted(areas, reverse=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = Path(sys.argv[1])
    cffs = {p.stem.lower(): p for p in root.rglob("*.cff")}
    locs = sorted((root / "WORLDS" / "locations").glob("*.loc"))
    if len(sys.argv) > 2:
        want = {a.lower() for a in sys.argv[2:]}
        locs = [p for p in locs if p.stem.lower() in want]
    for loc_file in locs:
        loc = w.parse_loc(loc_file)
        patch, model = (cffs.get(Path(loc[k].replace("\\", "/")).stem.lower()) for k in ("patch", "model"))
        if patch is None or model is None:
            print(f"{loc_file.stem}: no patch or model")
            continue
        seams, areas = check([t for t, _ in w.walk_floor(patch, model, loc)])
        print(f"{loc_file.stem}: {len(seams)} seams, {sum(s[0] for s in seams):.1f} m; "
              f"parts {len(areas)}, m2: {', '.join(f'{a:.0f}' for a in areas[:SHOW])}")
        for length, x, y, z in seams[:SHOW]:
            print(f"    {length:.2f} m at x {x:.2f} y {y:.2f} z {z:.2f}")


if __name__ == "__main__":
    sys.exit(main())
