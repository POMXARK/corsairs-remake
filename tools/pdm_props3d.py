#!/usr/bin/env python3
"""Replaces the flat sprites of a location by models (docs/pdm-formats.md, ours).

The original draws a tree as two or three crossed planes with an alpha-tested picture and a shop sign as one
plane seen from both sides. From close up both look like paper. pdm_world.py calls build() on the meshes of a
location before they are merged by texture:
- a tree (tree, tree2, tree3, kust2): the planes of one tree are found by their common foot; a trunk of rings and a
  crown of lumpy blobs take its place. The blobs are laid in the silhouette of the picture (its alpha), the leaves
  are the opaque part of the same picture with the holes filled, so the colours stay where they were;
- a sign (viveska_*, or tavern, ship_yard, store in High Rock): the silhouette of its alpha is extruded to a board with a front and a back, the sides are
  the colour of the picture edge.
New pictures (leaves, bark) are handed back in `generated` and written next to the other textures.
Every number comes from the position of the sprite, so a second run gives the same files.
"""
import math
import random

import numpy as np
from PIL import Image, ImageFilter

TREES = {"tree", "tree2", "tree3", "kust2"}
PALMS = {"palma-stvol"}
SIGN_PREFIX = "viveska_"
SIGN_NAMES = {"tavern", "ship_yard", "store"}   # the English towns (High Rock) name them without the prefix
BARK = "pdm_bark.tga"

BLOBS = 50        # most blobs in a crown
SIGN_ROWS = 96    # rows of the mask a sign is cut into
SIGN_THICK = 0.045  # board thickness, m per m of the longer side


def stem_of(mesh):
    name = mesh.texture.lower()
    return name[:-4] if name.endswith(".tga") else name


def is_quad(mesh):
    return len(mesh.vertices) <= 9 and len(mesh.triangles) == 4


def is_sign(stem):
    return stem.startswith(SIGN_PREFIX) or stem in SIGN_NAMES


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


# ---------- add_tube: sweep an 8-sided tube along a polyline (module-level helper) ----------
def add_tube(mesh, pts, radii, place=None, turned=None):
    """Sweep an 8-sided tube along a polyline of points with given radii at each point.
    
    Args:
        mesh: The target mesh to add vertices/triangles to.
        pts: List of (x, y, z) tuples for the tube centerline.
        radii: List of radii corresponding to each point in pts.
        place: A function that transforms a 3D point to world coordinates.
              If None, identity transform is used.
        turned: A function that rotates a normal vector around the same axis as place.
                If None, identity transform is used.
    """
    n = len(pts)
    base = len(mesh.vertices)
    sides = 8
    dirs = []
    for k in range(n):
        if k == 0:
            d = np.array(pts[1]) - np.array(pts[0])
        elif k == n - 1:
            d = np.array(pts[-1]) - np.array(pts[-2])
        else:
            d = np.array(pts[k + 1]) - np.array(pts[k - 1])
        dirs.append(normalized(d))
    for k in range(n):
        p, r, d = np.array(pts[k]), radii[k], dirs[k]
        ref = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        side = normalized(np.cross(d, ref))
        up2 = normalized(np.cross(side, d))
        for s in range(sides + 1):
            a = math.tau * s / sides
            off = (math.cos(a) * side + math.sin(a) * up2) * r
            vpos = p + off
            mesh.vertex(place(vpos), turned(off / r), (s / sides * 2, vpos[1] * 1.6))
    for k in range(n - 1):
        a0 = k * (sides + 1)
        for s in range(sides):
            mesh.triangle(base + a0 + s, base + a0 + s + 1, base + a0 + sides + 1 + s)
            mesh.triangle(base + a0 + s + 1, base + a0 + sides + 2 + s, base + a0 + sides + 1 + s)


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

    # the crown's reach in the picture plane
    top = float(np.max((1 - ys / ph) * h))
    low = float(np.min((1 - ys / ph) * h))
    span = max(top - low, 1e-3)
    ccx = float(np.mean((xs / pw - 0.5) * w))
    ccy = float(np.mean((1 - ys / ph) * h))

    def inside(x, y):
        i = int(round(x / w * pw + pw / 2))
        j = int(round((1 - y / h) * ph))
        return 0 <= i < pw and 0 <= j < ph and bool(mask[j, i])

    def in_crown(x, y):
        for _ in range(24):
            if inside(x, y):
                return x, y
            x += 0.25 * (ccx - x)
            y += 0.25 * (ccy - y)
        return ccx, ccy

    turn = rng.uniform(0, math.tau)
    cs, sn = math.cos(turn), math.sin(turn)

    def place(p):
        return (cx + p[0] * cs - p[2] * sn, y0 + p[1], cz + p[0] * sn + p[2] * cs)

    def turned(n):
        return (n[0] * cs - n[2] * sn, n[1], n[0] * sn + n[2] * cs)

    # ---------- branch growth: recursive midpoint-displacement skeleton ----------
    tips = []

    def make_branch(start, d, length, radius):
        start = np.array(start, dtype=float)
        d = np.array(d, dtype=float)
        end = start + d * length
        ref = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        side = normalized(np.cross(d, ref))
        up2 = normalized(np.cross(side, d))
        bend_angle = rng.uniform(0, math.tau)
        bend_mag = 0.15 * length * rng.uniform(0.3, 1.0)
        bend_dir = math.cos(bend_angle) * side + math.sin(bend_angle) * up2
        mid = (start + end) / 2 + bend_dir * bend_mag
        pts = [tuple(start), tuple(mid), tuple(end)]
        radii = [radius, radius * 0.6, radius * 0.28]
        return pts, radii, tuple(end)

    def grow(start, d, level, length, radius, place, turned):
        pts, radii, end = make_branch(start, d, length, radius)
        add_tube(trunk, pts, radii, place, turned)
        if level < 2:
            nch = rng.choice([2, 3])
            for _ in range(nch):
                a0 = math.atan2(d[2], d[0])
                ang = rng.uniform(-spread_val, spread_val)
                az = a0 + ang
                horiz = (math.cos(az), 0.0, math.sin(az))
                cd = np.array(horiz) * 0.7 + np.array([0.0, up_child, 0.0])
                cdn = normalized(cd)
                if cdn[1] < 0.05:
                    cdn = normalized(np.array([cdn[0], 0.05, cdn[2]]))
                grow(end, cdn, level + 1, length * rng.uniform(0.62, 0.78), radius * rng.uniform(0.55, 0.68), place, turned)
        else:
            tips.append(end)

    # ---------- trunk tube ----------
    out = []
    trunk = mesh_cls(f"{stem}_trunk", BARK)

    base_w = np.median(width[jc: min(jc + max(ph // 10, 2), ph)]) / pw * w
    r0 = min(max(base_w * 0.5, 0.03 * w), 0.07 * w)
    R = 0.5 * max(w, span)

    bush = stem == "kust2"
    up_first = 0.25 if bush else 0.5
    up_child = 0.15 if bush else 0.3
    spread_val = 1.4 if bush else 1.1
    L0 = (0.5 if bush else 0.45) * R
    rb0 = 0.45 * r0
    lean_az = rng.uniform(0, math.tau)
    lean_mag = (0.02 if bush else 0.06) * w
    trunk_top_y = low + (0.7 if bush else 0.9) * span

    def trunk_centre(y):
        t = y / trunk_top_y if trunk_top_y > 0 else 0.0
        lean_factor = lean_mag * t * t
        off_x = math.cos(lean_az) * lean_factor
        off_z = math.sin(lean_az) * lean_factor
        return (off_x, y, off_z)

    trunk_ys = [0.0, 0.1 * h, low, trunk_top_y]
    trunk_rs = [1.35 * r0, r0, 0.78 * r0, 0.5 * r0]
    trunk_pts = [trunk_centre(y) for y in trunk_ys]
    add_tube(trunk, trunk_pts, trunk_rs, place, turned)

    # ---------- branches ----------
    branch_f = (0.45, 0.68, 0.9)
    crown_span = span
    for i in range(3):
        az = math.tau * i / 3 + rng.uniform(-0.6, 0.6)
        horiz = (math.cos(az), 0.0, math.sin(az))
        d = normalized(np.array(horiz) * 0.7 + np.array([0.0, up_first, 0.0]))
        y_attach = low + branch_f[i] * crown_span
        start = trunk_centre(y_attach)
        grow(start, d, 0, L0, rb0, place, turned)

    # ---------- foliage: a dense irregular mass of leafy blobs ----------
    # more, smaller, overlapping blobs with smooth noise and flattening: a leafy mass,
    # not distinct balls
    radius = 0.11 * max(w, 0.7 * h)
    centres = []

    def far_enough(x, y, z):
        for (cx2, cy2, cz2) in centres:
            if math.sqrt((x - cx2)**2 + (y - cy2)**2 + (z - cz2)**2) < 0.35 * radius:
                return False
        return True

    # tip blobs
    for tip in tips:
        if len(centres) >= BLOBS:
            break
        x, y = in_crown(tip[0], tip[1])
        z = tip[2] * 0.7
        if far_enough(x, y, z):
            centres.append((x, y, z))

    # Poisson filler from the mask
    for _ in range(900):
        if len(centres) >= BLOBS:
            break
        k = rng.randrange(len(xs))
        x, y = local(xs[k], ys[k])
        z = rng.uniform(-1, 1) * 0.35 * w * 0.5
        if far_enough(x, y, z):
            centres.append((x, y, z))

    if not centres:
        return None

    mid = np.mean(np.array(centres), axis=0)

    # leaf blobs: flattened, irregular, smoothly-noised
    leaf = mesh_cls(f"{stem}_crown", leaves)
    verts, faces = SPHERE
    for x, y, z in centres:
        r = radius * rng.uniform(0.7, 1.3)
        squash = rng.uniform(0.55, 0.8)  # flatten in y: a leafy cluster, not a ball
        # smooth noise: a few random frequency vectors, correlated between nearby vertices
        freqs = [np.array([rng.uniform(-3, 3) for _ in range(3)]) for _ in range(4)]
        phases = [rng.uniform(0, math.tau) for _ in range(4)]
        base = len(leaf.vertices)
        centre = np.array((x, y, z))
        for v in verts:
            d = normalized(v)
            noise = sum(math.sin(d @ f + ph) for f, ph in zip(freqs, phases)) / len(freqs)
            scale = 1.0 + 0.3 * noise
            p = centre + v * r * scale * np.array((1.0, squash, 1.0))
            n = normalized(0.3 * normalized(v) + 0.7 * normalized(p - mid))
            u = min(max((p[0] + 0.6 * p[2]) / w + 0.5, 0.03), 0.97)
            leaf.vertex(place(p), turned(n), (u, min(max(1 - p[1] / h, 0.03), 0.9)))
        for a, b, c in faces:
            leaf.triangle(base + a, base + b, base + c)
    out.append(leaf)

    # trunk is already built with branches; return it
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
            # the faces are seen from opposite sides, so one of them is mirrored along the board: in the
            # engine's left-handed frame it is the face of the normal, and the text reads right from both sides
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

def palm_meshes(group, img, name, generated, mesh_cls):
    """Palm trunk: curved tapered tube with ring bumps. Fronds are separate sprites (unchanged)."""
    stem = name
    pls = [pl for _, pl in group]
    cx = sum(p[0] for p in pls) / len(pls)
    cz = sum(p[2] for p in pls) / len(pls)
    y0 = min(p[1] for p in pls)
    w = sum(p[3] for p in pls) / len(pls)
    h = sum(p[4] for p in pls) / len(pls)
    rng = random.Random(f"{stem}:{cx:.2f}:{cz:.2f}")
    generated.setdefault(BARK, bark())

    mask = np.asarray(img.convert("RGBA").getchannel("A")) > 128
    ph, pw = mask.shape

    trunk_width = np.median(mask.sum(1).astype(float)) / pw * w
    r0 = min(max(trunk_width * 0.5, 0.03 * w), 0.08 * w)

    turn = rng.uniform(0, math.tau)
    cs, sn = math.cos(turn), math.sin(turn)

    def place(p):
        return (cx + p[0] * cs - p[2] * sn, y0 + p[1], cz + p[0] * sn + p[2] * cs)

    def turned(n):
        return (n[0] * cs - n[2] * sn, n[1], n[0] * sn + n[2] * cs)

    # curved trunk: 6 points, bowing in one direction, tapering, with ring bumps
    lean_az = rng.uniform(0, math.tau)
    bow = 0.15 * h
    npts = 6
    pts, radii = [], []
    for k in range(npts):
        t = k / (npts - 1)
        y = t * h
        # bow grows as t^1.5
        lean_factor = bow * (t ** 1.5)
        off_x = math.cos(lean_az) * lean_factor
        off_z = math.sin(lean_az) * lean_factor
        # taper: from r0 to 0.5*r0 at top
        r = r0 * (1.0 - 0.4 * t)
        # ring bumps: subtle sinusoidal modulation
        r *= 1.0 + 0.08 * math.sin(t * 20)
        pts.append((off_x, y, off_z))
        radii.append(r)

    trunk = mesh_cls(f"{stem}_trunk", BARK)
    add_tube(trunk, pts, radii, place, turned)
    return [trunk]


# ---------- the entry ----------

def build(meshes, image, generated, mesh_cls):
    """The meshes of a location with the sprites replaced. image(stem) is the RGBA picture of a texture,
    generated receives {name: PIL image} of the new textures. Returns (out, veg, board, counts): out is the
    non-vegetation, non-sign meshes, veg the trees and palms (they get their own .gm, rendered with the wind
    technique), board the signs (their own .gm: they are redone without the BSP of the town), counts the
    numbers modelled."""
    out = []
    veg = []
    board = []
    trees, signs, palms = {}, {}, {}
    for m in meshes:
        stem = stem_of(m)
        if stem in TREES and is_quad(m):
            trees.setdefault(stem, []).append(m)
        elif stem in PALMS and is_quad(m):
            palms.setdefault(stem, []).append(m)
        elif is_sign(stem) and is_quad(m):
            signs.setdefault(stem, []).append(m)
        else:
            out.append(m)
    counts = {"trees": 0, "signs": 0}
    for stem, ms in trees.items():
        img = image(stem)
        for group in clusters(ms):
            made = tree_meshes(group, img, stem, generated, mesh_cls)
            if made:
                veg += made
                counts["trees"] += 1
            else:
                veg += [m for m, _ in group]
    for stem, ms in palms.items():
        img = image(stem)
        for group in clusters(ms):
            made = palm_meshes(group, img, stem, generated, mesh_cls)
            if made:
                veg += made
                counts["trees"] += 1
            else:
                veg += [m for m, _ in group]
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
                board.append(made)
                counts["signs"] += 1
            else:
                board.append(m)
    return out, veg, board, counts
