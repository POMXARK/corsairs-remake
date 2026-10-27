#!/usr/bin/env python3
"""The eyes of the character heads: what the engine needs to blink them and dart them (Character::UpdateEyeBlink).

The head of a PDM character has 130..270 vertices and none of them lies in the eye, so the engine can not move the
texture of the eye by the UV of the vertices (the way it blinks the hero). Two things make it possible:
  * tools/eyes.json: where the eyes of every head texture are, in texels of a texture taken as 256x256 (the position
    is marked by eye, the size comes from tools/make_eyes.py);
  * add_eye_vertices(): the triangles over the window of each eye are cut by a grid of lines, so every piece lies in
    one cell and its corners have the position, normal and bone of the surface and the UV of their own place.
The engine finds the window of a vertex by its UV; the table of the windows goes to resource/ini/eyes.ini (write_ini).

  python tools/pdm_eyes.py <resource_out>     writes <resource_out>/ini/eyes.ini
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TEX = 256.0
# inner grid lines of a window: fractions of the half height, fractions of the half width
ROWS = (-0.6, -0.3, -0.1, 0.0, 0.1, 0.3, 0.6)
COLS = (-0.8, -0.4, 0.0, 0.4, 0.8)


# the ramp of the engine on the edge of a window (texels): the cells of it show the rows between the lid and the
# skin, so the thinner it is the smaller the streak; the hero has a dense mesh and keeps the soft one
RAMP = 0.15
REACH = 6.0  # texels beyond the grid up to which the cuts are kept free of T-junctions
RAMPS = {"hero_head": 3.0}


def ramp(name):
    return RAMPS.get(name, RAMP)


def key(texture):
    """The name of a head texture as a section of eyes.ini and a key of eyes.json: hero_head, pirat_shopper_head."""
    return Path(str(texture).replace("\\", "/")).name.lower().split(".")[0].replace(" ", "_")


# the eye of the hero was set by hand on his dense mesh (window 40..80 x 129..143, skin row 145)
HERO = {"hero_head": [{"cx": 60.0, "cy": 136.0, "rx": 11.0, "ry": 3.0, "skin": 145.0}]}


def load():
    return {**json.loads((TOOLS / "eyes.json").read_text()), **HERO}


def window(e):
    """x0, x1, y0, y1, skin of an eye (cx, cy, rx, ry): the lids meet on the middle row, a skin row below shows on them."""
    hx, hy = e["rx"] + 9.0, e["ry"] + 4.0
    return e["cx"] - hx, e["cx"] + hx, e["cy"] - hy, e["cy"] + hy, e.get("skin", e["cy"] + hy + 2.0)


def lines(e, r):
    """Grid lines (texels) through the window of an eye: x, y. The outermost lie beyond the ramp of the engine
    (RAMP texels, weight 0), the one between them softens it."""
    x0, x1, y0, y1, _ = window(e)
    cx, mid, hx, hy = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
    xs = [x0 - r - 0.05, x0 - r * 0.5, x0] + [cx + c * hx for c in COLS] + [x1, x1 + r * 0.5, x1 + r + 0.05]
    ys = [y0 - r - 0.05, y0 - r * 0.5, y0] + [mid + c * hy for c in ROWS] + [y1, y1 + r * 0.5, y1 + r + 0.05]
    return sorted(set(round(v, 3) for v in xs)), sorted(set(round(v, 3) for v in ys))


def _crossing(mesh, tri, axis, at):
    """The edges (as sorted vertex pairs) of a triangle that the line uv[axis] = at crosses."""
    ds = [mesh.vertices[i][2][axis] * TEX - at for i in tri]
    ds = [0.0 if abs(v) < 1e-6 else v for v in ds]
    return [(min(tri[k], tri[(k + 1) % 3]), max(tri[k], tri[(k + 1) % 3]))
            for k in range(3) if ds[k] * ds[(k + 1) % 3] < 0.0]


def _cut(mesh, cache, tri, axis, at):
    """Cuts a triangle by the line uv[axis] = at (texels): the pieces keep the winding; the point on a shared edge is
    made once, so the neighbours stay joined."""
    def d(i):
        v = mesh.vertices[i][2][axis] * TEX - at
        return 0.0 if abs(v) < 1e-6 else v

    def cross(a, b):
        key = (min(a, b), max(a, b), axis, at)
        if key not in cache:
            da, db = d(a), d(b)
            t = da / (da - db)
            va, vb = mesh.vertices[a], mesh.vertices[b]
            lerp = lambda k: tuple(va[k][j] + t * (vb[k][j] - va[k][j]) for j in range(len(va[k])))
            nrm = lerp(1)
            length = sum(c * c for c in nrm) ** 0.5 or 1.0
            near = a if t < 0.5 else b
            mesh.vertices.append((lerp(0), tuple(c / length for c in nrm), lerp(2), mesh.vertices[near][3]))
            if mesh.colors is not None:
                mesh.colors.append(mesh.colors[near])
            cache[key] = len(mesh.vertices) - 1
        return cache[key]

    ds = [d(i) for i in tri]
    if not (min(ds) < 0.0 < max(ds)):
        return [tri]
    side = [[], []]  # polygons of the two sides, in the order of the triangle
    for k in range(3):
        a, b = tri[k], tri[(k + 1) % 3]
        da, db = ds[k], ds[(k + 1) % 3]
        for poly, ok in ((side[0], da <= 0.0), (side[1], da >= 0.0)):
            if ok:
                poly.append(a)
        if da * db < 0.0:
            m = cross(a, b)
            side[0].append(m)
            side[1].append(m)
    out = []
    for poly in side:
        out += [(poly[0], poly[k], poly[k + 1]) for k in range(1, len(poly) - 1)]
    return out


def _cut_line(mesh, cache, box, axis, at):
    """Cuts every triangle that the line crosses inside the box, and the triangles that share a cut edge with them
    (the cut edge is cut on both sides, otherwise a T-junction leaves a hole of a pixel)."""
    other = 1 - axis
    cut = set()  # edges the line is to cut
    for tri in mesh.triangles:
        for a, b in _crossing(mesh, tri, axis, at):
            p = [mesh.vertices[a][2], mesh.vertices[b][2]]
            lo, hi = min(q[other] for q in p) * TEX, max(q[other] for q in p) * TEX
            if lo <= box[2 * other + 1] and hi >= box[2 * other]:
                cut.add((a, b))
    near = (box[2 * other] - REACH, box[2 * other + 1] + REACH)  # further from the eye a T-junction is let be
    grown = True
    while grown:
        grown = False
        for tri in mesh.triangles:
            edges = _crossing(mesh, tri, axis, at)
            if any(max(mesh.vertices[v][2][other] for v in e) * TEX < near[0] or
                   min(mesh.vertices[v][2][other] for v in e) * TEX > near[1] for e in edges):
                continue
            if any(e in cut for e in edges) and not all(e in cut for e in edges):
                cut.update(edges)
                grown = True
    out = []
    for tri in mesh.triangles:
        edges = _crossing(mesh, tri, axis, at)
        out += _cut(mesh, cache, tri, axis, at) if edges and edges[0] in cut else [tri]
    mesh.triangles = out


def add_eye_vertices(mesh):
    """Cuts the triangles over the window of every eye of this head texture by a grid of lines, so every piece lies in
    one cell and the engine moves the UV of the corners of the cells; returns the number of vertices added."""
    eyes = load().get(key(mesh.texture))
    if not eyes:
        return 0
    before = len(mesh.vertices)
    for e in eyes:
        xs, ys = lines(e, ramp(key(mesh.texture)))
        cache = {}
        box = (xs[0], xs[-1], ys[0], ys[-1])
        for axis, values in ((0, xs), (1, ys)):
            for at in values:
                _cut_line(mesh, cache, box, axis, at)
    return len(mesh.vertices) - before


def write_ini(out):
    """resource/ini/eyes.ini: a section per head texture, one `eye = x0, x1, y0, y1, skin` per window; mirror = 1 when
    the atlas shows one eye for both (the half face), so the two eyes of the head look to opposite sides of the texture."""
    lines = ["; the eye windows of the heads, texels of a 256x256 texture; written by tools/pdm_eyes.py from tools/eyes.json",
             "; read by Character::UpdateEyeBlink (location/src/character.cpp)"]
    for name, eyes in sorted(load().items()):
        lines += ["", f"[{name}]", f"mirror = {1 if len(eyes) == 1 else 0}", f"ramp = {ramp(name):g}"]
        for e in eyes:
            lines.append("eye = " + ", ".join(f"{v:.1f}" for v in window(e)))
    path = Path(out) / "ini" / "eyes.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(write_ini(sys.argv[1]))
