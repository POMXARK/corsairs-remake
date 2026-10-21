#!/usr/bin/env python3
"""The way a character takes over a .ptc patch, read from its path table, seen from above.

The table holds per triangle and destination the edge to leave through (2 bits, 3 = unreachable),
the engine walks it triangle by triangle (PtcData::FindPathDir). Green: the patch. Orange: the
triangles of the way, red: the line through their centres. Blue: the start, magenta: the goal,
black: extra points (where the autotest stopped, the NPCs).

usage: ptc_path.py <patch.ptc> <start x> <start z> <goal x> <goal z> <out.png> [x z ...]
       SCALE=<pixels per metre> (12 by default)
"""
import math
import os
import struct
import sys

from PIL import Image, ImageDraw

HEAD = "<13i6f"
TRIANGLE = "<4H3hbb"


def main():
    data = open(sys.argv[1], "rb").read()
    head = struct.unpack_from(HEAD, data, 0)
    tri_count, vertex_count, normal_count, map_l, map_w, index_count, line_size = head[6:13]
    lo, hi = head[13:16], head[16:19]
    at = struct.calcsize(HEAD)
    tris = []
    for _ in range(tri_count):
        v = struct.unpack_from(TRIANGLE, data, at)
        at += struct.calcsize(TRIANGLE)
        tris.append((v[0:3], v[4:7]))
    verts = [struct.unpack_from("<3f", data, at + 12 * i) for i in range(vertex_count)]
    at += 12 * vertex_count + 12 * normal_count + 8 * map_l * map_w + 2 * index_count
    table = data[at:at + line_size * tri_count]

    def inside(t, x, z):
        ids = tris[t][0]
        for j in range(3):
            a, b = verts[ids[j]], verts[ids[(j + 1) % 3]]
            if (b[2] - a[2]) * (x - a[0]) - (b[0] - a[0]) * (z - a[2]) < -1e-6:
                return False
        return True

    def find(x, z):
        return next((t for t in range(tri_count) if inside(t, x, z)), -1)

    def centre(t):
        return [sum(verts[i][k] for i in tris[t][0]) / 3 for k in (0, 2)]

    sx, sz, gx, gz = map(float, sys.argv[2:6])
    start, goal = find(sx, sz), find(gx, gz)
    if start < 0 or goal < 0:
        sys.exit(f"off the patch: start {start}, goal {goal}")
    path = [start]
    while path[-1] != goal and len(path) < 2000:
        cur = path[-1]
        edge = (table[cur * line_size + (goal >> 2)] >> ((goal & 3) * 2)) & 3
        if edge == 3:
            print("unreachable")
            break
        path.append(tris[cur][1][edge])
    length = sum(math.dist(centre(a), centre(b)) for a, b in zip(path, path[1:]))
    print(f"{len(path)} triangles, {length:.1f} m via centres, {math.dist((sx, sz), (gx, gz)):.1f} m straight")

    scale = int(os.environ.get("SCALE", 12))
    size = (int((hi[0] - lo[0]) * scale) + 1, int((hi[2] - lo[2]) * scale) + 1)

    def px(x, z):
        return (x - lo[0]) * scale, (hi[2] - z) * scale

    im = Image.new("RGB", size, "white")
    dr = ImageDraw.Draw(im)
    for ids, _ in tris:
        dr.polygon([px(verts[i][0], verts[i][2]) for i in ids], fill=(200, 235, 200), outline=(150, 200, 150))
    for t in path:
        dr.polygon([px(verts[i][0], verts[i][2]) for i in tris[t][0]], fill=(250, 200, 120))
    dr.line([px(*centre(t)) for t in path], fill="red", width=2)
    extra = sys.argv[7:]
    marks = [(sx, sz, "blue"), (gx, gz, "magenta")]
    marks += [(float(x), float(z), "black") for x, z in zip(extra[0::2], extra[1::2])]
    for x, z, colour in marks:
        cx, cy = px(x, z)
        dr.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=colour)
    im.save(sys.argv[6])


if __name__ == "__main__":
    main()
