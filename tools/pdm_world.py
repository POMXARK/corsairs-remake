#!/usr/bin/env python3
"""Converts the walkable world of the original Sea Dogs (PDM 1.061): the towns and interiors of
WORLDS/locations/*.loc with their models, character patches and characters.

A .loc (cp1251 text, a value per line):
  model .cff, patch .cff, camera, sound kind (town, tavern, store, sYard, thall, cave ...),
  for a town the interiors (tavern, store, shipyard, townhall of its nation), the number of points
  and per point 12 lines: type, x, y, z, ay, the corner of a box, the size of the box, the link.
Point types: 1 exit (the box is the door, the link the location it leads to: sea, street or an
interior slot), 4 arrival (the player appears there coming from the location of the link), 2 soldiers,
3 walkers, 5..7 seats and counters, 11 traders, 12 priests: a character stands on the points of the
class of his model in anim_types.idf.

Writes, in the units of the engine (metres, pdm_character.DEFAULT_SCALE):
  models/locations/<model>.gm      the location model, a mesh per texture, with the BSP for traces
  models/locations/<patch>.ptc     the floor the characters walk on, from the patch .cff (with the
                                   ground floor of an interior, which the patch leaves out)
  textures/locations/*.tga.tx
  models/characters, animation     every character model of anim_types.idf (pdm_character.py)
  program/data/pdm_world.c         PdmLocations.<loc> and PdmCharModels.<model>, PdmWorld_Init()

usage: pdm_world.py <PDM_dir> <game_dir> [loc ...]   (default: every .loc)
"""
import math
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
import pdm_character  # noqa: E402
from cff2gm import Mesh, write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_idf  # noqa: E402
from pdm_ship import index_files  # noqa: E402
from storm_formats import write_ptc  # noqa: E402

K = pdm_character.DEFAULT_SCALE
# a .gm object indexes its vertices with 16 bits
MAX_VERTICES = 65000
# patch triangles steeper than this are walls, not floor
MIN_FLOOR_NORMAL_Y = 0.3


def parse_loc(path: Path):
    lines = [s.strip() for s in path.read_bytes().decode("cp1251").splitlines()]
    lines = [s for s in lines if s]
    loc = {"model": lines[0], "patch": lines[1], "camera": lines[2], "sound": lines[3], "interiors": []}
    i = 4
    while not lines[i].lstrip("-").isdigit():
        loc["interiors"].append(lines[i])
        i += 1
    count = int(lines[i])
    i += 1
    loc["points"] = []
    for _ in range(count):
        f = lines[i:i + 12]
        i += 12
        x0, y0, z0, sx, sy, sz = (float(v) for v in f[5:11])
        loc["points"].append({
            "type": int(f[0]), "pos": tuple(float(v) for v in f[1:4]), "ay": float(f[4]),
            # the box is axis aligned: its least corner and its size
            "box": (x0, z0, x0 + sx, z0 + sz), "link": f[11]})
    return loc


def merge_by_texture(meshes, name):
    """One mesh per texture (a town is 1500 small meshes), split at MAX_VERTICES."""
    merged = {}
    out = []
    for m in meshes:
        target = merged.get(m.texture)
        if target is None or len(target.vertices) + len(m.vertices) > MAX_VERTICES:
            target = Mesh(f"{name}_{len(out)}", m.texture)
            merged[m.texture] = target
            out.append(target)
        base = len(target.vertices)
        target.vertices += m.vertices
        target.triangles += [(a + base, b + base, c + base) for a, b, c in m.triangles]
    return out


def patch_triangles(cff: Path):
    """The floor triangles of a patch .cff in metres, each once (cff_to_meshes doubles the faces)."""
    seen, triangles = set(), []
    for m in cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p)):
        for tri in m.triangles:
            pts = tuple(m.vertices[i][0] for i in tri)
            key = frozenset(tuple(round(c, 3) for c in p) for p in pts)
            if len(key) < 3 or key in seen:
                continue
            e1 = [pts[1][k] - pts[0][k] for k in range(3)]
            e2 = [pts[2][k] - pts[0][k] for k in range(3)]
            n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            length = math.sqrt(sum(c * c for c in n))
            if length < 1e-9 or abs(n[1]) / length < MIN_FLOOR_NORMAL_Y:
                continue
            seen.add(key)
            triangles.append(pts)
    return triangles


# ---------- the floor an interior leaves out ----------
# A tavern patch holds the gallery, the stairs and the walls standing on the ground, not the ground
# floor itself: the original walks on y = 0 inside the walls. The feet of the walls close a loop
# around the hall; the loop is the floor.

WALL_FOOT = 0.1  # metres above the lowest point of the patch: the foot of a wall
LOOP_SNAP = 0.03  # metres: the feet of two walls closer than this meet


def wall_loops(cff: Path):
    """Closed outlines (x, z) drawn by the feet of the patch walls."""
    feet = []
    meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p))
    ground = min(v[0][1] for m in meshes for v in m.vertices)
    for m in meshes:
        for tri in m.triangles:
            low = [m.vertices[i][0] for i in tri if m.vertices[i][0][1] < ground + WALL_FOOT]
            if len(low) == 2:
                feet.append(((low[0][0], low[0][2]), (low[1][0], low[1][2])))
    nodes = []

    def node(p):
        for i, q in enumerate(nodes):
            if math.dist(p, q) < LOOP_SNAP:
                return i
        nodes.append(p)
        return len(nodes) - 1

    links = {}
    for a, b in feet:
        i, j = node(a), node(b)
        if i != j:
            links.setdefault(i, set()).add(j)
            links.setdefault(j, set()).add(i)
    loops, used = [], set()
    for start in links:
        if start in used or len(links[start]) != 2:
            continue
        loop, prev, cur = [start], None, start
        while True:
            nxt = [n for n in links[cur] if n != prev]
            if len(links[cur]) != 2 or not nxt:
                loop = None
                break
            prev, cur = cur, nxt[0]
            if cur == start:
                break
            loop.append(cur)
        used.update(loop or [])
        if loop and len(loop) >= 3:
            loops.append(([nodes[i] for i in loop], ground))
    return loops


def inside(poly, x, z):
    hit = False
    for i in range(len(poly)):
        (x0, z0), (x1, z1) = poly[i - 1], poly[i]
        if (z0 > z) != (z1 > z) and x < x0 + (z - z0) * (x1 - x0) / (z1 - z0):
            hit = not hit
    return hit


def ear_clip(poly):
    """Triangles of a simple polygon (x, z)."""
    poly = ccw(list(poly))
    out = []
    while len(poly) > 3:
        for i in range(len(poly)):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
            if area2([a, b, c]) <= EPS:
                continue
            if any(p not in (a, b, c) and all(area2(e) >= 0 for e in ([a, b, p], [b, c, p], [c, a, p]))
                   for p in poly):
                continue
            out.append((a, b, c))
            del poly[i]
            break
        else:
            break  # not simple: what is left stays out
    if len(poly) == 3:
        out.append(tuple(poly))
    return out


def implicit_floor(cff: Path, triangles, points):
    """Floor triangles for the wall loops holding a point of the location off the patch."""
    def on_patch(x, z):
        for t in triangles:
            d = [area2([(t[i - 1][0], t[i - 1][2]), (t[i][0], t[i][2]), (x, z)]) for i in range(3)]
            if all(v >= -EPS for v in d) or all(v <= EPS for v in d):
                return True
        return False

    floor = []
    off = [(x, z) for x, z in points if not on_patch(x, z)]
    for loop, ground in wall_loops(cff):
        if any(inside(loop, x, z) for x, z in off):
            floor += [tuple((p[0], ground, p[1]) for p in tri) for tri in ear_clip(loop)]
    return floor


# ---------- making the patch a mesh the engine walks on ----------
# The original tests a point against every patch triangle, so its patches overlap: a big triangle
# lies over the small ones of a square. The engine walks from triangle to neighbour triangle across
# shared edges, so the floor has to be cut into triangles that do not overlap and meet edge to edge.

EPS = 1e-6
SNAP = 1e-3  # metres: points closer than this are one vertex
LEVEL = 0.4  # metres: floors farther apart in height are different floors
MIN_AREA = 1e-4  # square metres: slivers smaller than this are dropped
GRID = 1.0  # metres: the cell of the vertex lookup


def area2(poly):
    return sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))


def ccw(poly):
    return poly if area2(poly) > 0 else poly[::-1]


def clip(poly, a, b, keep_left):
    """Sutherland-Hodgman: the part of a convex polygon left (or right) of the line a -> b."""
    def side(p):
        s = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        return s if keep_left else -s
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        sc, sp = side(cur), side(prev)
        if sc >= -EPS:
            if sp < -EPS:
                t = sp / (sp - sc)
                out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
            out.append(cur)
        elif sp >= -EPS:
            t = sp / (sp - sc)
            out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
    return out


def subtract(poly, hole):
    """Convex poly minus convex hole (both counter-clockwise): convex pieces."""
    pieces, rest = [], poly
    for i in range(len(hole)):
        a, b = hole[i - 1], hole[i]
        outside = clip(rest, a, b, keep_left=False)
        if len(outside) >= 3 and abs(area2(outside)) > 1e-6:
            pieces.append(outside)
        rest = clip(rest, a, b, keep_left=True)
        if len(rest) < 3:
            break
    else:
        return pieces  # what is left of rest is inside the hole
    return pieces + ([rest] if len(rest) >= 3 and abs(area2(rest)) > 1e-6 else [])


def bounds(poly):
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(zs), max(xs), max(zs)


def overlaps(b1, b2):
    return b1[0] < b2[2] - EPS and b2[0] < b1[2] - EPS and b1[1] < b2[3] - EPS and b2[1] < b1[3] - EPS


def plane(tri):
    """y = f(x, z) over the triangle."""
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri
    det = (x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)
    a = ((y1 - y0) * (z2 - z0) - (y2 - y0) * (z1 - z0)) / det
    c = ((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) / det
    return lambda x, z: y0 + a * (x - x0) + c * (z - z0)


def clean_patch(triangles):
    """Non-overlapping triangles meeting edge to edge, for write_ptc.

    - a triangle keeps only the part not covered by the ones before it on the same level: the
      floors of a house and the flights of a stair lie over each other and are all kept
    - the vertices are snapped to SNAP with one height per level, so that neighbours share them
    - a vertex lying on another piece's edge on the same level splits the edge (no T-junctions)
    - the engine knows one neighbour per edge on the other side of it: where a fold or a third
      triangle shares an edge, the extra triangles get a vertex of their own there (a wall)
    """
    def solid(poly):
        # not a sliver: thicker than SNAP and bigger than MIN_AREA
        if len(poly) < 3:
            return False
        a = abs(area2(poly))
        side = max(math.dist(poly[i - 1], poly[i]) for i in range(len(poly)))
        return a > 2 * MIN_AREA and a / side > SNAP

    holes = []  # the triangles before: (convex polygon in x/z, height function, bounds)
    pieces = []
    for tri in triangles:
        height = plane(tri)
        poly = ccw([(p[0], p[2]) for p in tri])
        todo = [poly]
        # cut by the whole triangles before, not by their pieces: a piece cut by pieces splits
        # into ever thinner slivers
        for done, done_height, bd in holes:
            nxt = []
            for part in todo:
                if not overlaps(bounds(part), bd):
                    nxt.append(part)
                    continue
                common = part
                for i in range(len(done)):
                    common = clip(common, done[i - 1], done[i], keep_left=True)
                    if len(common) < 3:
                        break
                same = solid(common) and all(abs(height(*q) - done_height(*q)) < LEVEL for q in common)
                nxt += [p for p in subtract(part, done) if solid(p)] if same else [part]
            todo = nxt
        holes.append((poly, height, bounds(poly)))
        pieces += [(part, height) for part in todo]

    # a vertex: (x, z in SNAP units, height); the heights of one (x, z) are levels LEVEL apart
    levels = {}

    def vertex(x, z, y):
        key = (round(x / SNAP), round(z / SNAP))
        for v in levels.setdefault(key, []):
            if abs(v[2] - y) < LEVEL:
                return v
        v = (key[0], key[1], y)
        levels[key].append(v)
        return v

    polys = []
    for poly, height in pieces:
        ring = []
        for x, z in poly:
            v = vertex(x, z, height(x, z))
            if not ring or ring[-1] != v:
                ring.append(v)
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if len(ring) >= 3:
            polys.append((ring, height))

    # the vertices in cells of GRID metres, to find those on an edge
    cell = round(GRID / SNAP)
    grid = {}
    for vs in levels.values():
        for v in vs:
            grid.setdefault((v[0] // cell, v[1] // cell), []).append(v)

    def on_edge(a, b):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dz * dz
        found = []
        for cx in range(min(a[0], b[0]) // cell, max(a[0], b[0]) // cell + 1):
            for cz in range(min(a[1], b[1]) // cell, max(a[1], b[1]) // cell + 1):
                for q in grid.get((cx, cz), ()):
                    if q == a or q == b:
                        continue
                    t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dz) / length2
                    if not 0 < t < 1 or ((q[0] - a[0]) * dz - (q[1] - a[1]) * dx) ** 2 / length2 >= 1.0:
                        continue
                    if abs(a[2] + t * (b[2] - a[2]) - q[2]) < LEVEL:
                        found.append((t, q))
        return [q for _, q in sorted(found)]

    out = []
    for keys, height in polys:
        ring = []
        for i, a in enumerate(keys):
            ring.append(a)
            ring += on_edge(a, keys[(i + 1) % len(keys)])
        if len(ring) == 3:
            fan = [ring]
        else:
            # a fan from the centre: the outline is convex, with points in a line on its edges
            cx = sum(v[0] for v in ring) / len(ring) * SNAP
            cz = sum(v[1] for v in ring) / len(ring) * SNAP
            fan = [[vertex(cx, cz, height(cx, cz)), ring[i - 1], ring[i]] for i in range(len(ring))]
        for tri in fan:
            if abs(area2([(v[0], v[1]) for v in tri])) * SNAP * SNAP > MIN_AREA:
                out.append(list(tri))

    # one neighbour per edge, on its other side
    edges = {}
    for t, tri in enumerate(out):
        for j in range(3):
            edges.setdefault(frozenset((tri[j], tri[j - 1])), []).append(t)

    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0

    walled = {}  # triangle -> its vertices on the edges it does not share
    for edge, ts in edges.items():
        if len(ts) < 2:
            continue
        a, b = tuple(edge)
        third = {t: next(v for v in out[t] if v not in edge) for t in ts}
        keep = [ts[0]]
        for t in ts[1:]:
            if len(keep) == 1 and side(a, b, third[t]) != side(a, b, third[keep[0]]):
                keep.append(t)
            else:
                walled.setdefault(t, set()).update(edge)
    for n, (t, lifted) in enumerate(sorted(walled.items())):
        # a copy of the vertices a little higher, its own for each triangle: write_ptc merges
        # vertices rounded to 0.1 mm
        out[t] = [(v[0], v[1], v[2] + 2e-4 * (n + 1)) if v in lifted else v for v in out[t]]
    return [(tuple((v[0] * SNAP, v[2], v[1] * SNAP) for v in tri), 0) for tri in out]


class World:
    def __init__(self, res: Path, game: Path):
        self.res, self.game = res, game
        self.out = game / "resource"
        self.models = index_files(res / "MODELS")
        self.textures = index_files(res / "TEXTURES")
        self.used_textures = set()
        self.done_models = {}
        self.lines = []

    def texture(self, stem):
        self.used_textures.add(stem.lower())
        return f"{stem.lower()}.tga"

    def model(self, name: str):
        """Converts a location model and its patch once; returns the stem the script loads."""
        stem = Path(name).stem.lower()
        if stem in self.done_models:
            return stem
        cff = self.models.get(Path(name).name.lower())
        if cff is None:
            print(f"  missing model {name}")
            self.done_models[stem] = None
            return None
        if (self.out / "models" / "locations" / f"{stem}.gm").exists():
            # the BSP of a town takes a minute: models written before are kept (RECONVERT=1 redoes them)
            self.done_models[stem] = 0
            return stem
        meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p), texture=self.texture)
        meshes = merge_by_texture(meshes, stem)
        write_gm(meshes, self.out / "models" / "locations" / f"{stem}.gm", bsp=True)
        self.done_models[stem] = len(meshes)
        return stem

    def patch(self, name: str, points):
        cff = self.models.get(Path(name).name.lower())
        if cff is None:
            print(f"  missing patch {name}")
            return None
        triangles = patch_triangles(cff)
        # the floor goes last: where the patch has a floor of its own, that one is kept
        triangles = clean_patch(triangles + implicit_floor(cff, triangles, points))
        # named by the patch: locations with one model can have different patches
        stem = cff.stem.lower()
        write_ptc(triangles, self.out / "models" / "locations" / f"{stem}.ptc")
        return stem

    def location(self, path: Path):
        loc = parse_loc(path)
        key = path.stem
        model = self.model(loc["model"])
        # only an interior walks on the ground inside its walls; the walls of a town are houses
        points = [] if loc["interiors"] else [(p["pos"][0] * K, p["pos"][2] * K) for p in loc["points"]]
        patch = self.patch(loc["patch"], points) if model else None
        at = f"PdmLocations.{key}"
        add = self.lines.append
        add(f'\t{at}.id = "{key}";')
        add(f'\t{at}.model = "{model or ""}";')
        add(f'\t{at}.patch = "{patch or ""}";')
        add(f'\t{at}.sound = "{loc["sound"]}";')
        # the interior slots of a town: the exits name them by kind
        for slot, interior in zip(("tavern", "store", "shipyard", "townhall"), loc["interiors"]):
            add(f'\t{at}.interiors.{slot} = "{interior}";')
        add(f'\t{at}.points = {len(loc["points"])};')
        for i, p in enumerate(loc["points"]):
            x, y, z = (c * K for c in p["pos"])
            bx0, bz0, bx1, bz1 = (c * K for c in p["box"])
            add(f'\t{at}.p{i}.type = {p["type"]}; {at}.p{i}.x = {x:.3f}; {at}.p{i}.y = {y:.3f}; '
                f'{at}.p{i}.z = {z:.3f}; {at}.p{i}.ay = {p["ay"]:.4f};')
            add(f'\t{at}.p{i}.bx0 = {bx0:.3f}; {at}.p{i}.bz0 = {bz0:.3f}; {at}.p{i}.bx1 = {bx1:.3f}; '
                f'{at}.p{i}.bz1 = {bz1:.3f}; {at}.p{i}.link = "{p["link"]}";')
        return f"{key}: {model}, patch {patch}, {len(loc['points'])} points"

    def characters(self):
        """Every model of anim_types.idf with its class (the point type it stands on)."""
        chars = index_files(self.res / "MODELS" / "CHARACTERS")
        anims = index_files(self.res / "WORLDS" / "CHARACTERS")
        report = []
        for obj in parse_idf(self.res / "WORLDS" / "anim_types.idf")["objects"]:
            f = dict(obj)
            name, cls, anim = f.get("name", "0"), f.get("class", "0"), f.get("anim_file", "null")
            stem = Path(name).stem.lower()
            if name == "0" or stem not in chars:
                continue
            converted = anim != "null" and anim.lower() in anims
            if converted:
                line = pdm_character.convert(self.res, self.out, name, anim, stem, K, self.textures)
                converted = "static" not in line
                report.append(line)
            at = f"PdmCharModels.{stem}"
            self.lines.append(f'\t{at}.class = {cls}; {at}.model = "{stem if converted else ""}";')
        return report

    def write_textures(self):
        missing = []
        for stem in sorted(self.used_textures):
            src = self.textures.get(stem)
            if src is None:
                missing.append(stem)
                continue
            dst = self.out / "textures" / "locations" / f"{stem}.tga.tx"
            dst.parent.mkdir(parents=True, exist_ok=True)
            convert_texture(src, dst)
        return missing

    def write_script(self):
        path = self.game / "program" / "data" / "pdm_world.c"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = ("// written by tools/pdm_world.py from WORLDS/locations/*.loc and WORLDS/anim_types.idf\n"
                "object PdmLocations;\nobject PdmCharModels;\n\nvoid PdmWorld_Init()\n{\n"
                + "\n".join(self.lines) + "\n}\n")
        path.write_text(text, encoding="cp1251")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    res = Path(sys.argv[1])
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    world = World(res, Path(sys.argv[2]))
    locs = sorted((res / "WORLDS" / "locations").glob("*.loc"))
    if sys.argv[3:]:
        wanted = {n.lower() for n in sys.argv[3:]}
        locs = [p for p in locs if p.stem.lower() in wanted]
    for path in locs:
        print(world.location(path))
    for line in world.characters():
        print(line)
    missing = world.write_textures()
    world.write_script()
    print(f"{len(locs)} locations, {len(world.done_models)} models, {len(world.used_textures)} textures"
          + (f", missing {' '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
