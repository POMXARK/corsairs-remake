"""Builds the first scene: a ship deck with cargo: static geometry in the engine's .gm format and procedural .tx textures.

Usage: make_models.py <output resource dir>
Writes models/ship/{barrel,crate,deck}.gm and textures/ship/*.tga.tx. Nothing is downloaded: the wood
textures are generated, so the scene has no third-party assets.
"""
import math
import random
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

TXF_A8R8G8B8 = 21

# geometry/src/rdf.h
RDF_VERSION = (ord("1") << 24) | (ord(".") << 16) | (ord("0") << 8) | ord("5")
OBJECT_VISIBLE = 1
TEXTURE_BASE = 1
# vertex colour is the albedo the lighting multiplies; the texture stage then applies MODULATE2X,
# so 0x80 grey keeps the texture as is under full light
VERTEX_COLOR = 0xFF808080


# ---------------------------------------------------------------- textures

def write_tx(image, path):
    """Writes an A8R8G8B8 texture with the full mip chain, the engine's native format."""
    image = image.convert("RGBA")
    width, height = image.size
    mips = []
    while True:
        r, g, b, a = image.split()
        mips.append(Image.merge("RGBA", (b, g, r, a)).tobytes())  # D3DFMT_A8R8G8B8 is BGRA in memory
        if image.width == 1 or image.height == 1:
            break
        image = image.resize((image.width // 2, image.height // 2), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as out:
        out.write(struct.pack("<6i", 0, width, height, len(mips), TXF_A8R8G8B8, len(mips[0])))
        for mip in mips:
            out.write(mip)


def wood(width, height, boards, base, rng, gap=3):
    """Vertical boards with grain streaks and dark gaps between them."""
    image = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(image)
    board_w = width / boards
    for i in range(boards):
        x0, x1 = round(i * board_w), round((i + 1) * board_w)
        shade = rng.uniform(0.82, 1.12)
        tone = tuple(min(255, int(c * shade)) for c in base)
        draw.rectangle([x0, 0, x1, height], fill=tone)
        for _ in range(int(board_w * 0.6)):
            x = rng.uniform(x0, x1)
            k = rng.uniform(0.75, 0.95)
            streak = tuple(int(c * k) for c in tone)
            draw.line([(x, 0), (x + rng.uniform(-3, 3), height)], fill=streak, width=1)
        draw.rectangle([x0, 0, x0 + gap - 1, height], fill=tuple(c // 3 for c in base))
    noise = Image.effect_noise((width, height), 18).convert("RGB")
    image = Image.blend(image, Image.composite(image, noise, Image.new("L", image.size, 200)), 0.5)
    return image.filter(ImageFilter.GaussianBlur(0.6))


def barrel_side(rng):
    image = wood(512, 512, 12, (150, 98, 52), rng)
    draw = ImageDraw.Draw(image)
    # iron hoops: two near each end, v grows from bottom to top
    for v in (0.06, 0.16, 0.84, 0.94):
        y = round((1 - v) * 512)
        draw.rectangle([0, y - 9, 512, y + 9], fill=(52, 50, 48))
        draw.line([(0, y - 9), (512, y - 9)], fill=(95, 92, 88), width=2)
        draw.line([(0, y + 8), (512, y + 8)], fill=(28, 27, 26), width=2)
    return image


def barrel_lid(rng):
    image = wood(256, 256, 5, (160, 110, 64), rng)
    draw = ImageDraw.Draw(image)
    draw.ellipse([2, 2, 253, 253], outline=(52, 50, 48), width=10)
    return image


def crate(rng):
    image = wood(256, 256, 4, (176, 136, 82), rng)
    draw = ImageDraw.Draw(image)
    frame = (128, 92, 50)
    draw.rectangle([0, 0, 255, 255], outline=frame, width=22)
    draw.line([(18, 238), (238, 18)], fill=frame, width=26)
    draw.rectangle([0, 0, 255, 255], outline=(60, 42, 24), width=3)
    return image


def deck(rng):
    return wood(512, 512, 8, (120, 86, 56), rng, gap=4).transpose(Image.ROTATE_90)


# ---------------------------------------------------------------- geometry

class Mesh:
    """One .gm object: vertices (pos, normal, uv) and triangles facing along the vertex normals."""

    def __init__(self, name, texture):
        self.name = name
        self.texture = texture
        self.vertices = []
        self.triangles = []

    def vertex(self, pos, normal, uv):
        self.vertices.append((pos, normal, uv))
        return len(self.vertices) - 1

    def triangle(self, a, b, c):
        # D3D culls counter-clockwise faces by default: in its left-handed space a front face has
        # cross(b - a, c - a) pointing to the viewer, so orient every triangle along its normals
        pa, pb, pc = (self.vertices[i][0] for i in (a, b, c))
        e1 = [pb[k] - pa[k] for k in range(3)]
        e2 = [pc[k] - pa[k] for k in range(3)]
        cross = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        normal = [sum(self.vertices[i][1][k] for i in (a, b, c)) for k in range(3)]
        if sum(cross[k] * normal[k] for k in range(3)) < 0:
            b, c = c, b
        self.triangles.append((a, b, c))

    def quad(self, a, b, c, d):
        self.triangle(a, b, c)
        self.triangle(a, c, d)


def barrel_meshes(height=1.2, r_end=0.36, r_mid=0.43, segments=32, rings=12):
    body = Mesh("body", "ship\\barrel_side.tga")
    # radius is a parabola over the height; the normal tilts by the slope of the profile
    for j in range(rings + 1):
        t = j / rings
        y = t * height
        r = r_end + (r_mid - r_end) * (1 - (2 * t - 1) ** 2)
        slope = (r_mid - r_end) * -4 * (2 * t - 1) / height  # dr/dy
        for i in range(segments + 1):
            a = 2 * math.pi * i / segments
            n = (math.cos(a), -slope, math.sin(a))
            length = math.sqrt(sum(c * c for c in n))
            body.vertex((r * math.cos(a), y, r * math.sin(a)), tuple(c / length for c in n), (3 * i / segments, 1 - t))
    row = segments + 1
    for j in range(rings):
        for i in range(segments):
            body.quad(j * row + i, j * row + i + 1, (j + 1) * row + i + 1, (j + 1) * row + i)

    lids = Mesh("lids", "ship\\barrel_lid.tga")
    for y, ny in ((0.03, -1.0), (height - 0.03, 1.0)):
        r = r_end - 0.01
        center = lids.vertex((0, y, 0), (0, ny, 0), (0.5, 0.5))
        ring = [lids.vertex((r * math.cos(a), y, r * math.sin(a)), (0, ny, 0),
                            (0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)))
                for a in (2 * math.pi * i / segments for i in range(segments + 1))]
        for i in range(segments):
            lids.triangle(center, ring[i], ring[i + 1])
    return [body, lids]


def box_meshes(size=0.8):
    mesh = Mesh("box", "ship\\crate.tga")
    h = size / 2
    for axis in range(3):
        for sign in (-1, 1):
            n = [0, 0, 0]
            n[axis] = sign
            u_axis, v_axis = [k for k in range(3) if k != axis]
            corners = []
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis] = sign * h
                p[u_axis] = du * h
                p[v_axis] = dv * h
                p[1] += h  # stands on the ground
                corners.append(mesh.vertex(tuple(p), tuple(n), ((du + 1) / 2, (1 - dv) / 2)))
            mesh.quad(*corners)
    return [mesh]


def deck_meshes(size=120.0, cells=40, tiles=44.0):
    mesh = Mesh("planks", "ship\\deck.tga")
    # a grid instead of one quad: per-vertex lighting and fog need vertices across the surface
    index = {}
    for j in range(cells + 1):
        for i in range(cells + 1):
            x = (i / cells - 0.5) * size
            z = (j / cells - 0.5) * size
            index[i, j] = mesh.vertex((x, 0.0, z), (0, 1, 0), (tiles * i / cells, tiles * j / cells))
    for j in range(cells):
        for i in range(cells):
            mesh.quad(index[i, j], index[i + 1, j], index[i + 1, j + 1], index[i, j + 1])
    return [mesh]


def write_gm(meshes, path):
    """Writes a static .gm: one material and texture per mesh, one vertex buffer, no BSP."""
    strings = bytearray()
    offsets = {}

    def name(text):
        if text not in offsets:
            offsets[text] = len(strings)
            strings.extend(text.encode("ascii") + b"\0")
        return offsets[text]

    group = name("geometry")
    textures = []
    for mesh in meshes:
        if mesh.texture not in textures:
            textures.append(mesh.texture)
    texture_names = [name(t) for t in textures]
    object_names = [name(m.name) for m in meshes]
    material_names = [name(m.name + "_mtl") for m in meshes]

    all_pos = [v[0] for m in meshes for v in m.vertices]
    lo = [min(p[k] for p in all_pos) for k in range(3)]
    hi = [max(p[k] for p in all_pos) for k in range(3)]
    bbox_size = [hi[k] - lo[k] for k in range(3)]
    bbox_center = [(hi[k] + lo[k]) / 2 for k in range(3)]
    radius = max(math.dist(p, bbox_center) for p in all_pos)

    materials = b""
    objects = b""
    triangles = b""
    vertices = b""
    striangle = svertex = 0
    for o, mesh in enumerate(meshes):
        texture_type = [TEXTURE_BASE, 0, 0, 0]
        texture = [textures.index(mesh.texture), 0, 0, 0]
        materials += struct.pack("<2i4f4i4i", group, material_names[o], 1.0, 0.0, 1.0, 0.0, *texture_type, *texture)

        pos = [v[0] for v in mesh.vertices]
        lo_o = [min(p[k] for p in pos) for k in range(3)]
        hi_o = [max(p[k] for p in pos) for k in range(3)]
        center = [(hi_o[k] + lo_o[k]) / 2 for k in range(3)]
        obj_radius = max(math.dist(p, center) for p in pos)
        objects += struct.pack("<3i3ff6i8i4ii", group, object_names[o], OBJECT_VISIBLE, *center, obj_radius,
                               0, len(mesh.triangles), striangle, len(mesh.vertices), svertex, o,
                               *([-1] * 8), *([-1] * 4), 0)
        # indices are relative to the object's first vertex (DrawIndexedPrimitive BaseVertexIndex)
        for tri in mesh.triangles:
            triangles += struct.pack("<3H", *tri)
        for p, n, uv in mesh.vertices:
            vertices += struct.pack("<3f3fI2f", *p, *n, VERTEX_COLOR, *uv)
        striangle += len(mesh.triangles)
        svertex += len(mesh.vertices)
    assert svertex < 65536, "16-bit indices"

    names = list(offsets.values())
    head = struct.pack("<11i3f3ff", RDF_VERSION, 0, len(strings), len(names), len(textures), len(meshes), 0, 0,
                       len(meshes), striangle, 1, *bbox_size, *bbox_center, radius)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as out:
        out.write(head)
        out.write(bytes(strings))
        out.write(struct.pack(f"<{len(names)}i", *names))
        out.write(struct.pack(f"<{len(textures)}i", *texture_names))
        out.write(materials)
        out.write(objects)
        out.write(triangles)
        out.write(struct.pack("<2i", 0, len(vertices)))  # RDF_VERTEXBUFF: type 0 = one uv set
        out.write(vertices)


def main():
    resource = Path(sys.argv[1])
    rng = random.Random(1715)  # fixed seed: identical assets on every run
    for name, make in (("barrel_side", barrel_side), ("barrel_lid", barrel_lid), ("crate", crate), ("deck", deck)):
        write_tx(make(rng), resource / "textures" / "ship" / f"{name}.tga.tx")
    write_gm(barrel_meshes(), resource / "models" / "ship" / "barrel.gm")
    write_gm(box_meshes(), resource / "models" / "ship" / "crate.gm")
    write_gm(deck_meshes(), resource / "models" / "ship" / "deck.gm")


if __name__ == "__main__":
    main()
