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
                                   ground floor of an interior, which the patch leaves out), its
                                   material the floor of the steps (pdm_sound.step_material)
  textures/locations/*.tga.tx
  models/characters, animation     every character model of anim_types.idf (pdm_character.py)
  program/data/pdm_world.c         PdmLocations.<loc> and PdmCharModels.<model>, PdmWorld_Init()

usage: pdm_world.py <PDM_dir> <game_dir> [loc ...]   (default: every .loc)
"""
import math
import struct
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
import pdm_character  # noqa: E402
import pdm_props3d  # noqa: E402
import pdm_sound  # noqa: E402
from cff2gm import Mesh, write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_idf  # noqa: E402
from pdm_ship import index_files  # noqa: E402
from storm_formats import read_tx, write_ptc, write_tx  # noqa: E402

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


SEAM = 0.003  # metres: a vertex this close to the inside of an edge splits it


def close_seams(meshes):
    """Splits the triangles that have a vertex of the model inside an edge (T-junctions): the original
    lays the cobbles of a street along longer edges of the grass, and the rasteriser leaves a crack of
    single pixels along such an edge, white lines on the floor. A split triangle becomes a fan around
    its centre over its corners and the vertices on its edges."""
    grid = {}
    for m in meshes:
        for v in m.vertices:
            grid.setdefault(tuple(math.floor(c) for c in v[0]), set()).add(v[0])

    def on_edge(a, b):
        """The vertices inside the edge a-b as (t, position), along it."""
        d = [b[k] - a[k] for k in range(3)]
        length = math.sqrt(sum(c * c for c in d))
        if length < 2 * SEAM:
            return []
        lo = [math.floor(min(a[k], b[k]) - SEAM) for k in range(3)]
        hi = [math.floor(max(a[k], b[k]) + SEAM) for k in range(3)]
        found = {}
        for i in range(lo[0], hi[0] + 1):
            for j in range(lo[1], hi[1] + 1):
                for n in range(lo[2], hi[2] + 1):
                    for p in grid.get((i, j, n), ()):
                        t = sum((p[k] - a[k]) * d[k] for k in range(3)) / (length * length)
                        if SEAM < t * length < length - SEAM \
                                and math.dist(p, [a[k] + t * d[k] for k in range(3)]) < SEAM:
                            found[p] = t
        return sorted((t, p) for p, t in found.items())

    def mix(a, b, t):
        return [a[k] + t * (b[k] - a[k]) for k in range(len(a))]

    split = 0
    for m in meshes:
        triangles = []
        for tri in m.triangles:
            ring = []
            for e in range(3):
                a, b = m.vertices[tri[e]], m.vertices[tri[(e + 1) % 3]]
                ring.append(tri[e])
                ring += [m.vertex(p, mix(a[1], b[1], t), mix(a[2], b[2], t), a[3]) for t, p in on_edge(a[0], b[0])]
            if len(ring) == 3:
                triangles.append(tri)
                continue
            split += 1
            corners = [m.vertices[k] for k in tri]
            pos, normal, uv = ([sum(c[n][k] for c in corners) / 3 for k in range(len(corners[0][n]))] for n in range(3))
            centre = m.vertex(pos, normal, uv, corners[0][3])
            triangles += [(centre, ring[k], ring[(k + 1) % len(ring)]) for k in range(len(ring))]
        m.triangles = triangles
    return split


INSET = 1 / 256  # of a texture: how far the UV of a single tile stay off its edges


def inset_tiles(meshes):
    """The floors of the towns are tiles, each a texture of its own laid once (UV from 0 to 1). The
    engine wraps textures, so the filter blends the far edge of a tile into the near one: light lines
    along the tiles. The UV of a texture that stays in one square in the whole model are pulled off its
    edges. Returns the textures pulled."""
    span = {}
    for m in meshes:
        for v in m.vertices:
            for k in range(2):
                lo, hi = span.get((m.texture, k), (math.inf, -math.inf))
                span[(m.texture, k)] = (min(lo, v[2][k]), max(hi, v[2][k]))
    tiles = {t for (t, k), (lo, hi) in span.items()
             if all(math.floor(span[(t, n)][0] + EPS) == math.floor(span[(t, n)][1] - EPS) for n in range(2))}
    for m in meshes:
        if m.texture not in tiles:
            continue
        base = [math.floor(span[(m.texture, k)][0] + EPS) for k in range(2)]
        m.vertices = [(v[0], v[1], tuple(base[k] + 0.5 + (v[2][k] - base[k] - 0.5) * (1 - 2 * INSET)
                                         for k in range(2)), v[3]) for v in m.vertices]
    return tiles


def unframe(tx: Path):
    """The tiles of the floors are drawn with a light frame a pixel wide: laid side by side, they
    show light lines along the joints. The frame is replaced by the row next to it and the mips are
    made again from the cleaned picture (the mips of the original keep the frame)."""
    data = tx.read_bytes()
    flags, w, h, mips, fmt, _ = struct.unpack_from("<6i", data)
    if fmt != 21 or w < 4 or h < 4:  # A8R8G8B8 only, as tf2tx writes them
        return
    px = [bytearray(data[24 + (y * w) * 4:24 + (y * w + w) * 4]) for y in range(h)]
    px[0][:], px[h - 1][:] = px[1], px[h - 2]
    for row in px:
        row[0:4], row[(w - 1) * 4:w * 4] = row[4:8], row[(w - 2) * 4:(w - 1) * 4]
    out = [b"".join(px)]
    for _ in range(mips - 1):
        if w == 1 and h == 1:
            break
        nw, nh = max(w // 2, 1), max(h // 2, 1)
        small = bytearray(nw * nh * 4)
        for y in range(nh):
            for x in range(nw):
                for c in range(4):
                    s = (px[min(2 * y, h - 1)][min(2 * x, w - 1) * 4 + c] + px[min(2 * y, h - 1)][min(2 * x + 1, w - 1) * 4 + c]
                         + px[min(2 * y + 1, h - 1)][min(2 * x, w - 1) * 4 + c] + px[min(2 * y + 1, h - 1)][min(2 * x + 1, w - 1) * 4 + c])
                    small[(y * nw + x) * 4 + c] = (s + 2) // 4
        w, h = nw, nh
        px = [small[y * w * 4:(y + 1) * w * 4] for y in range(h)]
        out.append(bytes(small))
    tx.write_bytes(struct.pack("<6i", flags, *struct.unpack_from("<2i", data, 4), len(out), fmt,
                               len(out[0])) + b"".join(out))


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
    """Triangles of a simple polygon (x, z): the fattest ear first (ours: the first ear made a fan of
    needles from one corner, cut by the obstacles into slivers that met at no edge, invisible walls)."""
    poly = ccw(list(poly))
    out = []
    while len(poly) > 3:
        best = None
        for i in range(len(poly)):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
            if area2([a, b, c]) <= EPS:
                continue
            if any(p not in (a, b, c) and all(area2(e) >= 0 for e in ([a, b, p], [b, c, p], [c, a, p]))
                   for p in poly):
                continue
            fat = area2([a, b, c]) / max(math.dist(a, b), math.dist(b, c), math.dist(c, a)) ** 2
            if best is None or fat > best[0]:
                best = (fat, i)
        if best is None:
            break  # not simple: what is left stays out
        i = best[1]
        out.append((poly[i - 1], poly[i], poly[(i + 1) % len(poly)]))
        del poly[i]
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
MERGE = 4  # SNAP: vertices of one level this near are one, a sliver between them goes (ours)
GRID = 1.0  # metres: the cell of the vertex lookup
STITCHED = {"patch_city_highrock", "patch_city_sharkisland", "patch_grot"}  # the patches stitch() is used on
STITCH = 20  # SNAP: two ends of open edges this near are one vertex (ours), 2 cm


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
    """y = f(x, z) over the triangle, or over a flat convex polygon: by its widest corner."""
    k = max(range(1, len(tri) - 1), key=lambda k: abs((tri[k][0] - tri[0][0]) * (tri[k + 1][2] - tri[0][2])
                                                      - (tri[k + 1][0] - tri[0][0]) * (tri[k][2] - tri[0][2])))
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri[0], tri[k], tri[k + 1]
    det = (x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)
    a = ((y1 - y0) * (z2 - z0) - (y2 - y0) * (z1 - z0)) / det
    c = ((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) / det
    return lambda x, z: y0 + a * (x - x0) + c * (z - z0)


def stitch(out):
    """Closes the gaps of a few centimetres between the open edges of the floor (ours).

    Pieces cut apart by obstacles leave vertices 1-2 cm from each other (a wedge 7 m long, its three
    corners within 2 cm): the neighbours share no edge, an invisible wall across a street. The ends of open
    edges (one triangle) that are closer than STITCH at one level become one vertex; the triangles that
    collapse or turn over by it go. Repeated while something joins and the open edges get fewer."""
    def count(tris):
        edges = {}
        for tri in tris:
            for j in range(3):
                edges[frozenset((tri[j], tri[j - 1]))] = edges.get(frozenset((tri[j], tri[j - 1])), 0) + 1
        return edges

    for _ in range(8):
        edges = count(out)
        ends = sorted({v for e, n in edges.items() if n == 1 for v in e})
        cells = {}
        for v in ends:
            cells.setdefault((v[0] // STITCH, v[1] // STITCH), []).append(v)
        parent = {}

        def root(v):
            while parent.get(v, v) != v:
                v = parent[v]
            return v

        for (i, j), vs in cells.items():
            for v in vs:
                for q in (q for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in cells.get((i + di, j + dj), ())):
                    if q < v and (q[0] - v[0]) ** 2 + (q[1] - v[1]) ** 2 <= STITCH * STITCH and abs(q[2] - v[2]) < LEVEL:
                        a, b = root(q), root(v)
                        if a != b:
                            parent[max(a, b)] = min(a, b)
        if not parent:
            break
        fresh = []
        for tri in out:
            t = [root(v) for v in tri]
            if len(set(t)) == 3 and area2([(v[0], v[1]) for v in t]) * SNAP * SNAP > MIN_AREA:
                fresh.append(t)
        if sum(n == 1 for n in count(fresh).values()) >= sum(n == 1 for n in edges.values()):
            break
        out = fresh
    return out


def clean_patch(triangles, joined=False):
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

    # vertices of one level closer than MERGE are one (ours): two pieces cut apart by a few mm met at
    # no edge, the sliver between them was a fold or a gap, an invisible wall across the floor
    parent = {}

    def root(v):
        while parent.get(v, v) != v:
            v = parent[v]
        return v

    near = {}
    for vs in levels.values():
        for v in vs:
            near.setdefault((v[0] // MERGE, v[1] // MERGE), []).append(v)
    for (i, j), vs in near.items():
        for v in vs:
            for q in (q for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in near.get((i + di, j + dj), ())):
                if q < v and abs(q[0] - v[0]) <= MERGE and abs(q[1] - v[1]) <= MERGE and abs(q[2] - v[2]) < LEVEL:
                    a, b = root(q), root(v)
                    if a != b:
                        parent[max(a, b)] = min(a, b)
    merged = []
    for ring, height in polys:
        r = []
        for v in map(root, ring):
            if not r or r[-1] != v:
                r.append(v)
        if len(r) > 1 and r[0] == r[-1]:
            r.pop()
        if len(r) >= 3 and area2([(v[0], v[1]) for v in r]) > 0:
            merged.append((r, height))
    polys = merged

    # the vertices in cells of GRID metres, to find those on an edge
    cell = round(GRID / SNAP)
    grid = {}
    for v in {root(v) for vs in levels.values() for v in vs}:
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
        # a piece thinner than 2 SNAP (ours): a sliver along a long edge, its points split the edges of
        # the neighbours on both sides already; kept, its fan folded and was walled off as a fold, an
        # invisible wall across the floor
        flat = [(v[0], v[1]) for v in ring]
        if abs(area2(flat)) / max(math.dist(p, q) for p in flat for q in flat) < 2:
            continue
        if len(ring) == 3:
            fan = [ring]
        else:
            # a fan from the centre: the outline is convex, with points in a line on its edges
            cx = sum(v[0] for v in ring) / len(ring) * SNAP
            cz = sum(v[1] for v in ring) / len(ring) * SNAP
            fan = [[vertex(cx, cz, height(cx, cz)), ring[i - 1], ring[i]] for i in range(len(ring))]
        for tri in fan:
            # counter-clockwise as the outline (ours): snapped to SNAP, a fan of a narrow piece may turn over
            if area2([(v[0], v[1]) for v in tri]) * SNAP * SNAP > MIN_AREA:
                out.append(list(tri))

    if joined:
        out = stitch(out)

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


# ---------- what stands on the floor ----------
# The original stops the hero at the geometry of the location: MAN.dll traces five feelers at 0.3 m
# over the floor, 0.285 m ahead, 0.275 m back, 0.395 m at 45 degrees and 0.375 m to the sides, and
# slides the hero along what they touch. The engine only walks the patch, and the patches run under
# tables, barrels, carts and along the walls of houses. The floor is cut into CELL squares; a square
# where the location model crosses the height of a body over that floor is cut out of the patch,
# grown by the reach of the feelers. The squares just outside the patch take the height of the floor
# next to them: the edge of a patch often runs right along a wall.

CELL = 0.15  # metres
BODY = (0.3, 1.6)  # metres above the floor: what a walking body bumps into, from the height of the feelers
REACH = 2  # cells: a blocked square grows by this, 0.3-0.375 m, the reach of the feelers
FREE = 0.45  # metres around a point a character stands on stay walkable
PAD = 0.25  # metres: half the side of the floor laid under a point the patch has no floor at the height of


def cell_range(lo, hi):
    return range(math.floor(lo / CELL), math.floor(hi / CELL) + 1)


def blocked_cells(model: Path, triangles, points):
    """{(i, j): [floor heights]} of the squares a body cannot stand on. The exits are not kept: a door
    box runs into the house, the walls and the door leaf cut it like any other wall (ours)."""
    floors = {}  # the floor heights over the centre of a square
    for t in triangles:
        height, poly = plane(t), ccw([(p[0], p[2]) for p in t])
        x0, z0, x1, z1 = bounds(poly)
        for i in cell_range(x0, x1):
            for j in cell_range(z0, z1):
                x, z = (i + 0.5) * CELL, (j + 0.5) * CELL
                if all(area2([poly[k - 1], poly[k], (x, z)]) >= -EPS for k in range(3)):
                    floors.setdefault((i, j), []).append(height(x, z))

    near = {}  # the floor heights of a square and of the squares within REACH of it
    for (i, j), hs in floors.items():
        for di in range(-REACH, REACH + 1):
            for dj in range(-REACH, REACH + 1):
                near.setdefault((i + di, j + dj), set()).update(hs)

    hit = {}
    lo, hi = BODY
    for m in cff2gm.cff_to_meshes(model, place=lambda p: tuple(c * K for c in p)):
        for tri in m.triangles:
            pts = [m.vertices[k][0] for k in tri]
            ys = [p[1] for p in pts]
            x0, z0, x1, z1 = bounds([(p[0], p[2]) for p in pts])
            for i in cell_range(x0, x1):
                for j in cell_range(z0, z1):
                    hs = [h for h in near.get((i, j), ()) if max(ys) > h + lo and min(ys) < h + hi]
                    if not hs:
                        continue
                    # the part of the triangle over the square: (x, z, y) clipped in x/z
                    part = [(p[0], p[2], p[1]) for p in pts]
                    sx, sz = i * CELL, j * CELL
                    for a, b in (((sx, sz), (sx + CELL, sz)), ((sx + CELL, sz), (sx + CELL, sz + CELL)),
                                 ((sx + CELL, sz + CELL), (sx, sz + CELL)), ((sx, sz + CELL), (sx, sz))):
                        part = clip3(part, a, b)
                        if not part:
                            break
                    if not part:
                        continue
                    ylo, yhi = min(p[2] for p in part), max(p[2] for p in part)
                    for h in hs:
                        if yhi > h + lo and ylo < h + hi:
                            hit.setdefault((i, j), []).append(h)

    grown = {}
    for (i, j), hs in hit.items():
        for di in range(-REACH, REACH + 1):
            for dj in range(-REACH, REACH + 1):
                grown.setdefault((i + di, j + dj), []).extend(hs)

    def free(i, j):
        x, z = (i + 0.5) * CELL, (j + 0.5) * CELL
        return any(math.dist((x, z), p) < FREE for p in points)
    return {c: hs for c, hs in grown.items() if not free(*c)}


def clip3(poly, a, b):
    """clip() for points (x, z, y): the y rides along."""
    def side(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    out = []
    for k, cur in enumerate(poly):
        prev = poly[k - 1]
        sc, sp = side(cur), side(prev)
        if (sc >= -EPS) != (sp >= -EPS):
            t = sp / (sp - sc)
            out.append(tuple(prev[n] + t * (cur[n] - prev[n]) for n in range(3)))
        if sc >= -EPS:
            out.append(cur)
    return out


def cut_obstacles(triangles, blocked):
    """The patch triangles without the blocked squares of their floor: convex pieces, not cut into
    triangles here (ours): the diagonals of the long thin strips between the squares, cut again by
    clean_patch, went a few cm apart and left invisible walls across the streets."""
    out = []
    for t in triangles:
        height, poly = plane(t), ccw([(p[0], p[2]) for p in t])
        x0, z0, x1, z1 = bounds(poly)
        cells = {(i, j) for i in cell_range(x0, x1) for j in cell_range(z0, z1)
                 if any(abs(h - height((i + 0.5) * CELL, (j + 0.5) * CELL)) < LEVEL
                        for h in blocked.get((i, j), ()))}
        # the squares merged into rectangles: runs along x, equal runs of the next rows joined
        runs = {}
        for i, j in sorted(cells, key=lambda c: (c[1], c[0])):
            row = runs.setdefault(j, [])
            if row and row[-1][1] == i - 1:
                row[-1][1] = i
            else:
                row.append([i, i])
        rects, open_, last = [], {}, None
        for j in sorted(runs):
            if last is not None and j != last + 1:
                rects += [(i0, s, i1, last) for (i0, i1), s in open_.items()]
                open_ = {}
            nxt = {run: open_.pop(run, j) for run in map(tuple, runs[j])}
            rects += [(i0, s, i1, last) for (i0, i1), s in open_.items()]
            open_, last = nxt, j
        rects += [(i0, s, i1, last) for (i0, i1), s in open_.items()]
        pieces = [poly]
        for i0, j0, i1, j1 in rects:
            hole = [(i0 * CELL, j0 * CELL), ((i1 + 1) * CELL, j0 * CELL),
                    ((i1 + 1) * CELL, (j1 + 1) * CELL), (i0 * CELL, (j1 + 1) * CELL)]
            hb = bounds(hole)
            pieces = [q for p in pieces for q in (subtract(p, hole) if overlaps(bounds(p), hb) else [p])]
        out += [tuple((q[0], height(*q), q[1]) for q in p) for p in pieces]
    return out


def heights_at(triangles, x, z):
    out = []
    for t in triangles:
        poly = ccw([(p[0], p[2]) for p in t])
        if all(area2([poly[k - 1], poly[k], (x, z)]) >= -EPS for k in range(len(poly))):
            out.append(plane(t)(x, z))
    return out


def point_pads(triangles, loc):
    """Floor squares at the height of the points standing under a floor of the patch and over none:
    the shipwright of shipyard_eng stands at y = 0 behind his counter, under the lid of the patch over
    it, the drinkers by the wall of the tavern under its gallery. The engine puts a character on the
    floor nearest in height, without these on the lid (ours)."""
    pads = []
    for p in loc["points"]:
        if p["type"] == 1:
            continue
        x, y, z = (c * K for c in p["pos"])
        hs = heights_at(triangles, x, z)
        if hs and all(abs(h - y) >= LEVEL for h in hs):
            a, b, c, d = ((x - PAD, y, z - PAD), (x + PAD, y, z - PAD), (x + PAD, y, z + PAD), (x - PAD, y, z + PAD))
            pads += [(a, c, b), (a, d, c)]
    return pads


def walk_floor(patch_cff: Path, model_cff: Path, loc):
    """The patch the characters walk on, for write_ptc."""
    triangles = patch_triangles(patch_cff)
    # only an interior walks on the ground inside its walls; the walls of a town are houses
    points = [] if loc["interiors"] else [(p["pos"][0] * K, p["pos"][2] * K) for p in loc["points"]]
    # the floor goes last: where the patch has a floor of its own, that one is kept
    triangles = triangles + implicit_floor(patch_cff, triangles, points)
    keep = [(p["pos"][0] * K, p["pos"][2] * K) for p in loc["points"] if p["type"] != 1]
    triangles = cut_obstacles(triangles, blocked_cells(model_cff, triangles, keep))
    # the stitch closes the long gaps of these locations and opens short ones in the others (checked with ptc_seams.py)
    return clean_patch(triangles + point_pads(triangles, loc), Path(patch_cff).stem.lower() in STITCHED)


class World:
    def __init__(self, res: Path, game: Path):
        self.res, self.game = res, game
        self.out = game / "resource"
        self.models = index_files(res / "MODELS")
        self.textures = index_files(res / "TEXTURES")
        self.used_textures = set()
        self.tile_textures = set()
        self.done_models = {}
        self.lines = []
        self.pictures = {}
        self.generated = {}
        self.signs_only = False

    def texture(self, stem):
        self.used_textures.add(stem.lower())
        return f"{stem.lower()}.tga"

    def picture(self, stem):
        """The RGBA picture of a texture of the original (the sprites are cut out of its alpha)."""
        if stem not in self.pictures:
            with tempfile.TemporaryDirectory() as tmp:
                dst = Path(tmp) / "t.tx"
                convert_texture(self.textures[stem], dst)
                self.pictures[stem] = read_tx(dst)
        return self.pictures[stem]

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
        meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p), texture=self.texture)
        seams = close_seams(meshes)
        tiles = inset_tiles(meshes)
        # the textures need the tiles of every model, the cached ones too
        self.tile_textures |= {Path(t).stem.lower() for t in tiles}
        locations = self.out / "models" / "locations"
        if self.signs_only:
            # only the signs: no BSP of the town, its .gm stays (docs/pdm-formats.md, signs)
            if not (locations / f"{stem}.gm").exists():
                return self.model_full(stem, meshes)
            _, _, board, props = pdm_props3d.build(meshes, self.picture, self.generated, Mesh)
            self.write_signs(board, stem, props)
            self.done_models[stem] = 0
            return stem
        return self.model_full(stem, meshes)

    def write_signs(self, board, stem, props):
        path = self.out / "models" / "locations" / f"{stem}_signs.gm"
        if board:
            write_gm(merge_by_texture(board, stem + "_signs"), path, bsp=True)
            print(f"  {stem}: {props['signs']} signs modelled")
        elif path.exists():
            path.unlink()

    def model_full(self, stem, meshes):
        if (self.out / "models" / "locations" / f"{stem}.gm").exists():
            # the BSP of a town takes a minute: models written before are kept (RECONVERT=1 redoes them)
            self.done_models[stem] = 0
            return stem
        if seams:
            print(f"  {stem}: {seams} triangles split at T-junctions")
        if tiles:
            print(f"  {stem}: {len(tiles)} textures laid once, kept off their edges")
        meshes, veg, board, props = pdm_props3d.build(meshes, self.picture, self.generated, Mesh)
        if props["trees"]:
            print(f"  {stem}: {props['trees']} trees modelled")
        self.write_signs(board, stem, props)
        meshes = merge_by_texture(meshes, stem)
        write_gm(meshes, self.out / "models" / "locations" / f"{stem}.gm", bsp=True)
        # the vegetation gets its own .gm: the engine renders it with the wind technique (WindLeaf)
        if veg:
            veg = merge_by_texture(veg, stem + "_veg")
            write_gm(veg, self.out / "models" / "locations" / f"{stem}_veg.gm", bsp=True)
        self.done_models[stem] = len(meshes)
        return stem

    def patch(self, name: str, loc):
        cff = self.models.get(Path(name).name.lower())
        if cff is None:
            print(f"  missing patch {name}")
            return None
        triangles = walk_floor(cff, self.models[Path(loc["model"]).name.lower()], loc)
        # named by the patch: locations with one model can have different patches
        stem = cff.stem.lower()
        # the material of the floor gives the sound of the steps on it
        write_ptc(triangles, self.out / "models" / "locations" / f"{stem}.ptc",
                  materials=(pdm_sound.step_material(self.res, loc["sound"]),))
        return stem

    def location(self, path: Path):
        loc = parse_loc(path)
        key = path.stem
        model = self.model(loc["model"])
        patch = self.patch(loc["patch"], loc) if model else None
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
        """Every model of anim_types.idf with its class (the point type it stands on).
        The whole conversion of models and textures lives in pdm_character.convert_all();
        this only turns its report into the PdmCharModels lines of the generated script."""
        report = []
        for stem, cls, line in pdm_character.convert_all(self.res, self.out, self.textures, K):
            converted = line is not None and "static" not in line
            if converted:
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
            if stem in self.tile_textures:
                unframe(dst)
        for name, image in self.generated.items():
            write_tx(image, self.out / "textures" / "locations" / f"{name}.tx")
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
    names = sys.argv[3:]
    if names[:1] == ["--signs"]:
        # only the signs of the towns again (their own _signs.gm), without the town models and the script
        world.signs_only = True
        names = names[1:]
    locs = sorted((res / "WORLDS" / "locations").glob("*.loc"))
    if names:
        wanted = {n.lower() for n in names}
        locs = [p for p in locs if p.stem.lower() in wanted]
    for path in locs:
        print(world.location(path))
    if world.signs_only:
        print(f"{len(locs)} locations, signs only")
        return
    for line in world.characters():
        print(line)
    missing = world.write_textures()
    # the table of all the locations is written only from all of them: a few would drop the rest
    if not names and not world.signs_only:
        world.write_script()
    print(f"{len(locs)} locations, {len(world.done_models)} models, {len(world.used_textures)} textures"
          + (f", missing {' '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
