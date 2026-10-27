#!/usr/bin/env python3
"""The eyes of the character heads: what the engine needs to blink them and dart them (Character::UpdateEyeBlink).

The head of a PDM character has 130..270 vertices and none of them lies in the eye, so the engine can not move the
texture of the eye by the UV of the vertices (the way it blinks the hero). Two things make it possible:
  * tools/eyes.json: where the eyes of every head texture are, in texels of a texture taken as 256x256 (the position
    is marked by eye, the size comes from tools/make_eyes.py);
  * add_eye_vertices(): the edges of the triangles over the window of each eye are halved until they are at most
    DENSITY texels long, so the mesh is as dense as the hero's and the lids close smoothly (the hero is left as he is).
The engine finds the window of a vertex by its UV; the table of the windows goes to resource/ini/eyes.ini (write_ini).

  python tools/pdm_eyes.py <resource_out>     writes <resource_out>/ini/eyes.ini
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TEX = 256.0
# the ramp of the engine on the edge of a window (texels): the cells of it show the rows between the lid and the
# skin, soft, as on the dense mesh of the hero, the heads of the others are made as dense (DENSITY)
RAMP = 3.0
DENSITY = 2.0  # texels: the longest edge of the mesh over an eye
RAMPS = {}


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


def _split_edges(mesh, boxes, limit):
    """One pass: splits at the middle every edge longer than limit texels (in UV) that touches a box; the triangle
    is cut by the edges split in it (1, 2 or 3 of them), so neighbours stay joined; returns whether any was split."""
    def inside(i):
        u, v = mesh.vertices[i][2][0] * TEX, mesh.vertices[i][2][1] * TEX
        return any(x0 <= u <= x1 and y0 <= v <= y1 for x0, x1, y0, y1 in boxes)

    def length(a, b):
        ua, ub = mesh.vertices[a][2], mesh.vertices[b][2]
        return ((ua[0] - ub[0]) ** 2 + (ua[1] - ub[1]) ** 2) ** 0.5 * TEX

    mid = {}
    for tri in mesh.triangles:
        for k in range(3):
            a, b = tri[k], tri[(k + 1) % 3]
            e = (min(a, b), max(a, b))
            if e not in mid and (inside(a) or inside(b)) and length(a, b) > limit:
                mid[e] = None
    if not mid:
        return False
    for a, b in mid:
        va, vb = mesh.vertices[a], mesh.vertices[b]
        lerp = lambda k: tuple(0.5 * (va[k][j] + vb[k][j]) for j in range(len(va[k])))
        nrm = lerp(1)
        norm = sum(c * c for c in nrm) ** 0.5 or 1.0
        mesh.vertices.append((lerp(0), tuple(c / norm for c in nrm), lerp(2), va[3]))
        if mesh.colors is not None:
            mesh.colors.append(mesh.colors[a])
        mid[(a, b)] = len(mesh.vertices) - 1
    out = []
    for tri in mesh.triangles:
        v = list(tri)
        m = [mid.get((min(v[k], v[(k + 1) % 3]), max(v[k], v[(k + 1) % 3]))) for k in range(3)]  # on edge k -> k+1
        n = sum(x is not None for x in m)
        if n == 0:
            out.append(tri)
            continue
        # rotate so that the first edge is a split one (and, with two splits, the first two)
        while not (m[0] is not None and (n != 2 or m[1] is not None)):
            v, m = v[1:] + v[:1], m[1:] + m[:1]
        if n == 1:
            out += [(v[0], m[0], v[2]), (m[0], v[1], v[2])]
        elif n == 2:
            out += [(v[0], m[0], m[1]), (m[0], v[1], m[1]), (v[0], m[1], v[2])]
        else:
            out += [(v[0], m[0], m[2]), (m[0], v[1], m[1]), (m[2], m[1], v[2]), (m[0], m[1], m[2])]
    mesh.triangles = out
    return True


def add_eye_vertices(mesh):
    """Makes the mesh over the eye windows of this head texture as dense as the hero's (edges of at most DENSITY
    texels): the engine moves the UV of the vertices, so a dense mesh closes the lids smoothly; returns the number
    of vertices added."""
    if key(mesh.texture) in HERO:  # his mesh is dense already
        return 0
    eyes = load().get(key(mesh.texture))
    if not eyes:
        return 0
    r = ramp(key(mesh.texture))
    boxes = []
    for e in eyes:
        x0, x1, y0, y1, _ = window(e)
        boxes.append((x0 - r - DENSITY, x1 + r + DENSITY, y0 - r - DENSITY, y1 + r + DENSITY))
    before = len(mesh.vertices)
    for _ in range(8):
        if not _split_edges(mesh, boxes, DENSITY):
            break
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
