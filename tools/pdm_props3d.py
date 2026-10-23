#!/usr/bin/env python3
"""Replaces the flat sprites of a location by models (docs/pdm-formats.md, ours).

The original draws a tree as two or three crossed planes with an alpha-tested picture and a shop sign as one
plane seen from both sides. From close up both look like paper. pdm_world.py calls build() on the meshes of a
location before they are merged by texture:
- a tree (tree, tree2, tree3, kust2): the planes of one tree are found by their common foot; a trunk of rings and a
  crown of lumpy blobs take its place. The blobs are laid in the silhouette of the picture (its alpha), the leaves
  are the opaque part of the same picture with the holes filled, so the colours stay where they were;
- a sign (viveska_*): the silhouette of its alpha is extruded to a board with a front and a back, the sides are
  the colour of the picture edge.
New pictures (leaves, bark) are handed back in `generated` and written next to the other textures.
Every number comes from the position of the sprite, so a second run gives the same files.
"""
import math
import random

import numpy as np
from PIL import Image, ImageFilter

TREES = {"tree", "tree2", "tree3", "kust2"}
SIGN_PREFIX = "viveska_"
BARK = "pdm_bark.tga"

BLOBS = 26        # most blobs in a crown
SIGN_ROWS = 96    # rows of the mask a sign is cut into
SIGN_THICK = 0.045  # board thickness, m per m of the longer side


def stem_of(mesh):
    name = mesh.texture.lower()
    return name[:-4] if name.endswith(".tga") else name


def is_quad(mesh):
    return len(mesh.vertices) == 8 and len(mesh.triangles) == 4


def positions(mesh):
    return np.array([v[0] for v in mesh.vertices], dtype=float)


# ---------- the shapes ----------

def unit_sphere():
    """An icosahedron cut once: 42 vertices and 80 faces on the unit sphere."""
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
         (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, dtype=float) / np.linalg.norm(p) for p in v]
    middle = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in middle:
            p = verts[a] + verts[b]
            verts.append(p / np.linalg.norm(p))
            middle[key] = len(verts) - 1
        return middle[key]

    faces = []
    for a, b, c in f:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    return np.array(verts), faces


SPHERE = unit_sphere()


def normalized(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


# ---------- trees ----------

def planes(ms):
    """Foot (x, y, z), width and height of the vertical planes."""
    out = []
    for m in ms:
        p = positions(m)
        lo, hi = p.min(0), p.max(0)
        out.append(((lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2, math.hypot(hi[0] - lo[0], hi[2] - lo[2]),
                    hi[1] - lo[1]))
    return out


def clusters(ms):
    """The planes of one tree stand on one foot."""
    groups = []
    for m, pl in zip(ms, planes(ms)):
        for g in groups:
            c = g[0][1]
            if math.hypot(pl[0] - c[0], pl[2] - c[2]) < 0.5 * max(pl[3], c[3]) and abs(pl[4] - c[4]) < 0.15 * c[4]:
                g.append((m, pl))
                break
        else:
            groups.append([(m, pl)])
    return groups


def foliage(img):
    """The opaque part of the picture with the holes filled by the nearest colour: the leaves of a blob."""
    rgba = np.asarray(img.convert("RGBA"))
    solid = rgba[..., 3] > 200
    if not solid.any():
        return Image.new("RGB", img.size, (60, 90, 40))
    rgb = rgba[..., :3].astype(float)
    # holes grow over from their solid neighbours, a ring per pass
    while not solid.all():
        w = np.pad(solid, 1).astype(float)
        c = np.pad(rgb * solid[..., None], ((1, 1), (1, 1), (0, 0)))
        n = sum(w[1 + dy:1 + dy + solid.shape[0], 1 + dx:1 + dx + solid.shape[1]]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        total = sum(c[1 + dy:1 + dy + solid.shape[0], 1 + dx:1 + dx + solid.shape[1]]
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        grow = ~solid & (n > 0)
        rgb[grow] = total[grow] / n[grow][:, None]
        solid = solid | grow
    filled = rgb.astype(np.uint8)
    return Image.fromarray(filled).filter(ImageFilter.GaussianBlur(1.2)).convert("RGBA")


def bark(size=64):
    rng = np.random.default_rng(7)
    streak = rng.random(size)
    streak = (streak + np.roll(streak, 1) + np.roll(streak, -1)) / 3
    rows = rng.random((size, size))
    k = (0.65 * streak[None, :] + 0.35 * rows)
    lo, hi = np.array((46, 32, 22)), np.array((112, 84, 58))
    rgb = lo + (hi - lo) * k[..., None]
    return Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")


def crown(mask):
    """Rows of the picture: width of the mask and the lowest row of the crown (above it the trunk is thin)."""
    h, w = mask.shape
    width = mask.sum(1).astype(float)
    k = np.ones(5) / 5
    width = np.convolve(width, k, "same")
    wide = np.nonzero(width >= 0.25 * width.max())[0]
    return width, int(wide.max()) if len(wide) else h // 2


def tree_meshes(group, img, name, generated, mesh_cls):
    stem = name
    pls = [pl for _, pl in group]
    cx = sum(p[0] for p in pls) / len(pls)
    cz = sum(p[2] for p in pls) / len(pls)
    y0 = min(p[1] for p in pls)
    w = sum(p[3] for p in pls) / len(pls)
    h = sum(p[4] for p in pls) / len(pls)
    rng = random.Random(f"{stem}:{cx:.2f}:{cz:.2f}")
    leaves = f"{stem}_leaves.tga"
    if leaves not in generated:
        generated[leaves] = foliage(img)
    generated.setdefault(BARK, bark())

    mask = np.asarray(img.convert("RGBA").getchannel("A")) > 128
    ph, pw = mask.shape
    width, jc = crown(mask)
    ys, xs = np.nonzero(mask[:jc + 1])
    if len(xs) == 0:
        return None

    def local(i, j):
        return (i / pw - 0.5) * w, (1 - j / ph) * h

    # the blobs of the crown, in the silhouette
    radius = 0.15 * max(w, 0.7 * h)
    centres = []
    for _ in range(600):
        if len(centres) >= BLOBS:
            break
        k = rng.randrange(len(xs))
        x, y = local(xs[k], ys[k])
        if all(math.hypot(x - c[0], y - c[1]) > 0.55 * radius for c in centres):
            span = max(width[ys[k]] / pw * w * 0.5 - abs(x), 0.0)
            centres.append((x, y, rng.uniform(-1, 1) * min(span, 0.4 * w) * 0.8))
    if not centres:
        return None
    top = max(c[1] for c in centres)
    low = min(c[1] for c in centres)
    mid = np.mean([c[:3] for c in centres], axis=0)

    turn = rng.uniform(0, math.tau)
    cs, sn = math.cos(turn), math.sin(turn)

    def place(p):
        return (cx + p[0] * cs - p[2] * sn, y0 + p[1], cz + p[0] * sn + p[2] * cs)

    def turned(n):
        return (n[0] * cs - n[2] * sn, n[1], n[0] * sn + n[2] * cs)

    out = []
    leaf = mesh_cls(f"{stem}_crown", leaves)
    verts, faces = SPHERE
    for x, y, z in centres:
        r = radius * rng.uniform(0.85, 1.25)
        noise = [rng.uniform(0.82, 1.18) for _ in verts]
        base = len(leaf.vertices)
        centre = np.array((x, y, z))
        for v, nz in zip(verts, noise):
            p = centre + v * r * nz * np.array((1.0, 0.85, 1.0))
            # the light sees one lump, not a heap of balls: the normal leans away from the crown centre
            n = normalized(0.55 * normalized(v) + 0.45 * normalized(p - mid))
            # the picture is not repeated: a blob over its edge would show the trunk at the other end
            u = min(max((p[0] + 0.6 * p[2]) / w + 0.5, 0.03), 0.97)
            leaf.vertex(place(p), turned(n), (u, min(max(1 - p[1] / h, 0.03), 0.9)))
        for a, b, c in faces:
            leaf.triangle(base + a, base + b, base + c)
    out.append(leaf)

    # the trunk: from the foot through the crown, thinner upwards
    base_w = np.median(width[jc: min(jc + max(ph // 10, 2), ph)]) / pw * w
    r0 = min(max(base_w * 0.5, 0.03 * w), 0.07 * w)
    top_y = low + 0.55 * (top - low)
    rings = [(0.0, 1.35 * r0), (0.08 * h, r0), (0.5 * top_y, 0.78 * r0), (top_y, 0.5 * r0)]
    trunk = mesh_cls(f"{stem}_trunk", BARK)
    sides = 8
    for k, (y, r) in enumerate(rings):
        for s in range(sides + 1):
            a = math.tau * s / sides
            n = (math.cos(a), 0.0, math.sin(a))
            trunk.vertex(place((r * n[0], y, r * n[2])), turned(n), (s / sides * 2, y * 1.6))
    for k in range(len(rings) - 1):
        for s in range(sides):
            a = k * (sides + 1) + s
            trunk.triangle(a, a + 1, a + sides + 1)
            trunk.triangle(a + 1, a + sides + 2, a + sides + 1)
    out.append(trunk)
    return out


# ---------- signs ----------

def sign_axes(mesh):
    """Origin and the two edges of a quad by its uv: u runs along `u_axis`, v (down the picture) along `v_axis`."""
    pts = {}
    for p, _, uv, _ in mesh.vertices:
        pts.setdefault((round(uv[0]), round(-uv[1])), np.array(p, dtype=float))
    o = pts.get((0, 0))
    ue = pts.get((1, 0))
    ve = pts.get((0, 1))
    if o is None or ue is None or ve is None:
        return None
    return o, ue - o, ve - o


def sign_mesh(mesh, img, mesh_cls, thick_k=SIGN_THICK):
    """A board with the silhouette of the alpha of the picture, its front and back on the same picture."""
    axes = sign_axes(mesh)
    if axes is None:
        return None
    o, ue, ve = axes     # o: v = 0 (the foot, the bottom of the picture), ve: to v = -1 (the top)
    rows = SIGN_ROWS
    cols = SIGN_ROWS
    small = img.convert("RGBA").getchannel("A").resize((cols, rows), Image.BOX)
    mask = np.asarray(small) > 127
    if not mask.any():
        return None
    thick = thick_k * max(np.linalg.norm(ue), np.linalg.norm(ve))
    normal = normalized(np.cross(ue, ve))
    half = normal * thick / 2
    out = mesh_cls(mesh.name, mesh.texture)

    def point(i, j, side):
        # picture column i of cols, row j of rows (0 is the top); the top is the end of ve
        return o + ue * (i / cols) + ve * (1 - j / rows) + (half if side else -half)

    def uv(i, j):
        return (i / cols, j / rows - 1)

    def face(side, i0, i1, j):
        # a strip of the face: columns i0..i1 of row j
        n = normal if side else -normal
        quad = []
        for (i, jj) in ((i0, j), (i1, j), (i1, j + 1), (i0, j + 1)):
            u, v = uv(i, jj)
            # the back is the same picture seen from behind: mirrored along the board
            if side:
                u = 1 - u
            quad.append(out.vertex(point(i, jj, side), n, (u, v)))
        # the first copy faces the front of the board; triangle() turns it along the normal
        out.triangle(quad[0], quad[1], quad[2])
        out.triangle(quad[0], quad[2], quad[3])

    def edge(i0, j0, i1, j1, n):
        """A piece of the rim between two corners of the picture grid; its colour is the picture's edge."""
        u, v = uv((i0 + i1) / 2, (j0 + j1) / 2)
        q = [out.vertex(point(i0, j0, 1), n, (u, v)), out.vertex(point(i1, j1, 1), n, (u, v)),
             out.vertex(point(i1, j1, 0), n, (u, v)), out.vertex(point(i0, j0, 0), n, (u, v))]
        out.triangle(q[0], q[1], q[2])
        out.triangle(q[0], q[2], q[3])

    u_dir = normalized(ue)
    v_dir = normalized(-ve)     # down the picture
    for j in range(rows):
        i = 0
        while i < cols:
            if not mask[j, i]:
                i += 1
                continue
            i0 = i
            while i < cols and mask[j, i]:
                i += 1
            for side in (1, 0):
                face(side, i0, i, j)
            edge(i0, j, i0, j + 1, -u_dir)
            edge(i, j, i, j + 1, u_dir)
            # top and bottom of the run, where the row above / below is empty
            for a in range(i0, i):
                if j == 0 or not mask[j - 1, a]:
                    edge(a, j, a + 1, j, -v_dir)
                if j == rows - 1 or not mask[j + 1, a]:
                    edge(a, j + 1, a + 1, j + 1, v_dir)
    return out


# ---------- the entry ----------

def build(meshes, image, generated, mesh_cls):
    """The meshes of a location with the sprites replaced. image(stem) is the RGBA picture of a texture,
    generated receives {name: PIL image} of the new textures."""
    out = []
    trees, signs = {}, {}
    for m in meshes:
        stem = stem_of(m)
        if stem in TREES and is_quad(m):
            trees.setdefault(stem, []).append(m)
        elif stem.startswith(SIGN_PREFIX) and is_quad(m):
            signs.setdefault(stem, []).append(m)
        else:
            out.append(m)
    counts = {"trees": 0, "signs": 0}
    for stem, ms in trees.items():
        img = image(stem)
        for group in clusters(ms):
            made = tree_meshes(group, img, stem, generated, mesh_cls)
            if made:
                out += made
                counts["trees"] += 1
            else:
                out += [m for m, _ in group]
    for stem, ms in signs.items():
        img = image(stem)
        seen = []
        for m in ms:
            p = positions(m)
            key = tuple(np.round(np.concatenate([p.min(0), p.max(0)]), 2))
            if key in seen:
                continue            # the back of a board is another plane of the original; the board has both
            seen.append(key)
            made = sign_mesh(m, img, mesh_cls)
            if made:
                out.append(made)
                counts["signs"] += 1
            else:
                out.append(m)
    return out, counts
