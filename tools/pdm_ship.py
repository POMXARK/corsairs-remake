#!/usr/bin/env python3
"""Assembles one ship of the original Sea Dogs (PDM 1.061) into a Storm 2 ship model.

A PDM ship is a DESC/<Ship>.def: a tree of parts (hull, masts, rigging, cannons; the Patch lid is skipped) whose
offsets are summed along the links; the parts are separate .cff files in MODELS. Storm 2 loads a
ship from models/ships/<Name>/<Name>.gm, so all parts go into one model, scaled to metres, with
their textures converted to textures/ships/<name>/*.tga.tx.

usage: pdm_ship.py <PDM_dir> <resource_out> <Ship> [--name Name] [--scale K]
"""
import argparse
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import Mesh, write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_def  # noqa: E402

# DEF units: the brig ABrig is 1.17 long; a real brig of the time is about 30 m
DEFAULT_SCALE = 26.0


def index_files(folder: Path):
    """Lower-case stem -> path: PDM names files in any case and the CFF texture names say .tga for .tf."""
    files = {}
    for f in folder.iterdir():
        files.setdefault(f.stem.lower(), f)
        files.setdefault(f.name.lower(), f)
    return files


def placed(items, kind="Model"):
    """Items of a class with their offset summed along the link chain (the models are not rotated).

    The Patch item is skipped: a black lid over the hull facing down (ABrig_Patch.cff, texture "black"),
    a mask of the original against its sea inside the hull. Storm 2 does not need it and, with the faces
    double-sided, it covered the deck."""
    by_index = {}
    for it in items:
        by_index.setdefault(it["index"], it)
    out = []
    for it in items:
        if it["class"] != kind or not it["file"]:
            continue
        pos, link, seen = list(it["pos"]), it["link"], set()
        while link >= 0 and link in by_index and link not in seen:
            seen.add(link)
            parent = by_index[link]
            pos = [a + b for a, b in zip(pos, parent["pos"])]
            link = parent["link"]
        out.append((it, pos))
    return out


def parse_sls(path: Path):
    """DESC/<Ship>.sls: per Sail item of the DEF (by its index) the sail corners and the yard meshes.

    Record: u32 item, u32 0, f32 belly (the depth of the sail, negative), 4 x f32[3] corners
    (top left, top right, bottom right, bottom left, from the item position), u32 meshes; a mesh is
    char texture[32], u32 vertices, u32 triangles, vertices of f32 pos[3], f32 normal[3], u32 colour
    and triangles of u16 a, b, c, pad, f32 uv[3][2] (UVs per corner, not per vertex).
    """
    data = path.read_bytes()
    sails, o = {}, 0
    while o < len(data):
        item, _ = struct.unpack_from("<2I", data, o)
        belly, *c = struct.unpack_from("<13f", data, o + 8)
        count, = struct.unpack_from("<I", data, o + 60)
        o += 64
        meshes = []
        for _ in range(count):
            tex = data[o:o + 32].split(b"\0")[0].decode("latin1")
            nv, nt = struct.unpack_from("<2I", data, o + 32)
            o += 40
            verts = [struct.unpack_from("<6fI", data, o + 28 * i) for i in range(nv)]
            o += 28 * nv
            tris = [(struct.unpack_from("<3H", data, o + 32 * i), struct.unpack_from("<6f", data, o + 32 * i + 8))
                    for i in range(nt)]
            o += 32 * nt
            meshes.append((tex, verts, tris))
        sails[item] = dict(belly=belly, corners=[tuple(c[i:i + 3]) for i in range(0, 12, 3)], meshes=meshes)
    return sails


def yard_mesh(name, tex, verts, tris, place):
    """A yard of the .sls: UVs are per corner, so every corner is a vertex of its own; both sides drawn
    as the CFF parts are."""
    m = Mesh(name, tex)
    for side in (1, -1):
        for (a, b, c), uv in tris:
            ids = [m.vertex(place(verts[i][:3]), tuple(side * n for n in verts[i][3:6]), uv[2 * k:2 * k + 2])
                   for k, i in enumerate((a, b, c))]
            m.triangles.append(tuple(ids) if side == 1 else (ids[0], ids[2], ids[1]))
    return m


def rope_ends(positions, faces):
    """The stays of the original are thin triangles in one plane: one corner at an end of the rope, the
    other two close together at its other end. Storm draws ropes itself (the rope entity) from the
    two ends, round and seen from every side."""
    ropes = []
    for f in faces:
        p = [positions[i] for i in f]
        dist = [sum((p[(k + 1) % 3][j] - p[(k + 2) % 3][j]) ** 2 for j in range(3)) for k in range(3)]
        k = dist.index(min(dist))
        near = [(p[(k + 1) % 3][j] + p[(k + 2) % 3][j]) / 2 for j in range(3)]
        ropes.append((tuple(p[k]), tuple(near)))
    return ropes


def write_tx(dst: Path, size, pixel):
    """A TX texture (A8R8G8B8) from pixel(x, y) -> (r, g, b, a) on a size x size grid. The mips keep the
    largest alpha of every 2 x 2 block: thin lines stay opaque far away, the ship techniques test alpha."""
    img = [[pixel(x, y) for x in range(size)] for y in range(size)]
    mips = []
    while True:
        mips.append(b"".join(bytes((b, g, r, a)) for row in img for r, g, b, a in row))
        if len(img) == 1:
            break
        half = []
        for y in range(0, len(img), 2):
            row = []
            for x in range(0, len(img), 2):
                block = [img[y][x], img[y][x + 1], img[y + 1][x], img[y + 1][x + 1]]
                solid = [c for c in block if c[3]] or block
                row.append(tuple(sum(c[k] for c in solid) // len(solid) for k in range(3)) + (max(c[3] for c in block),))
            half.append(row)
        img = half
    dst.parent.mkdir(parents=True, exist_ok=True)
    # TX header: flags, width, height, mips, format (21 = A8R8G8B8), size of the first mip
    dst.write_bytes(struct.pack("<6i", 0, size, size, len(mips), 21, size * size * 4) + b"".join(mips))


ROPE = (42, 32, 22, 255)  # tarred hemp
WOOD = (92, 64, 38, 255)
CLEAR = (42, 32, 22, 0)


def write_rope_texture(dst: Path):
    """The rope entity's texture: tarred hemp with the twist as diagonal stripes. PDM's black.tf does not
    fit: its alpha falls with the mip (255, 187, 136, 85, 34), so the original faded its thin stays with
    the distance, and ShipRope, which tests alpha, drops them a few tens of metres away."""
    def pixel(x, y):
        k = 0.75 + 0.25 * ((x + y) // 4 % 2)
        return tuple(int(c * k) for c in ROPE[:3]) + (255,)
    write_tx(dst, 32, pixel)


# Where write_vant_texture puts the parts of a shroud; the vant entity reads them from rigging.ini
VANT_INI = """fWidth = 0.08
fVRopeXbeg = 0.0
fVRopeXend = 0.1
fTreangXbeg = 0.125
fTreangXend = 0.5
fTreangYbeg = 0.0
fTreangYend = 0.6
fBalkYbeg = 0.6
fBalkYend = 1.0
fHRopeXbeg = 0.5
fHRopeXend = 1.0
fHRopeHeight = 0.45
fVRopeHeight = 1.0
fTreangWidth = 0.6
fTreangHeight = 0.9
fVantMaxDist = 200000
"""


def write_vant_texture(dst: Path, size=128):
    """The vant entity's texture: a column of rope for the vertical ropes (x < 0.1), the triangle of
    ropes from the masthead (x 0.125-0.5, y < 0.6), the wooden beam under it (y > 0.6) and a ratline
    across x 0.5-1, repeated along the shroud; the rest is transparent."""
    def pixel(x, y):
        u, v = (x + 0.5) / size, (y + 0.5) / size
        if u < 0.1:
            return ROPE
        if u < 0.5:
            if v >= 0.6:
                return WOOD
            # five ropes from the top middle to the beam
            if 0.125 <= u and v > 0.02:
                for k in range(5):
                    end = 0.14 + 0.345 * k / 4
                    at = 0.3125 + (end - 0.3125) * v / 0.6
                    if abs(u - at) < 1.5 / size:
                        return ROPE
            return CLEAR
        return ROPE if abs(v - 0.5) < 3 / size else CLEAR
    write_tx(dst, size, pixel)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdm")
    ap.add_argument("out")
    ap.add_argument("ship")
    ap.add_argument("--name", help="Storm ship name (default: the DEF name)")
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    a = ap.parse_args()

    res = Path(a.pdm)
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    desc, models, textures = (index_files(res / d) for d in ("DESC", "MODELS", "TEXTURES"))
    name = a.name or a.ship
    out = Path(a.out)
    tex_dir = f"ships\\{name.lower()}"

    used = set()

    def texture(stem):
        used.add(stem.lower())
        return f"{tex_dir}\\{stem.lower()}.tga"

    k = a.scale
    meshes, labels, vants = [], [], []
    items = parse_def(desc[a.ship.lower() + ".def"])["items"]
    for it, pos in placed(items):
        cff = models.get(it["file"].lower())
        if cff is None:
            print(f"  missing model {it['file']}")
            continue

        def place(p, pos=pos):
            # summed DEF offset, then metres
            return tuple((v + o) * k for v, o in zip(p, pos))
        parts = cff2gm.cff_to_meshes(cff, place=place, texture=texture)
        for part in parts:
            if part.texture.endswith("\\takelag_new.tga"):
                # the shrouds: a triangle each, the masthead and two points at the side; the vant entity
                # draws them as ropes with ratlines. Its labels carry one digit: vant1..9, then vanx1..9
                # for the vantl entity (half the triangles are the back side)
                for a, b, c in part.triangles[:len(part.triangles) // 2]:
                    up, left, right = sorted((part.vertices[i][0] for i in (a, b, c)), key=lambda p: -p[1])
                    n = len(vants) + 1
                    vant = f"vant{n}" if n <= 9 else f"vanx{n - 9}"
                    vants.append(n)
                    labels += [("vant", vant + "u", up), ("vant", vant + "l", left), ("vant", vant + "r", right)]
            elif part.texture.endswith("\\black.tga"):
                # the stays: ropes of the rope entity instead of flat strips (half the vertices are the back side)
                front = len(part.vertices) // 2
                positions = [v[0] for v in part.vertices[:front]]
                for b, e in rope_ends(positions, part.triangles[:len(part.triangles) // 2]):
                    n = sum(1 for g, *_ in labels if g == "rope") // 2 + 1
                    labels += [("rope", f"ropeb{n}", b), ("rope", f"ropee{n}", e)]
            else:
                meshes.append(part)
        print(f"  {it['file']:<20} {len(parts):3d} meshes at {[round(v, 3) for v in pos]}")
    ropes = sum(1 for g, *_ in labels if g == "rope") // 2

    # the sails: their yards go into the model, the cloth is drawn by the sail entity from the corners
    sls = {}
    for it, pos in placed(items, "Sail"):
        if it["file"].lower() not in sls:
            sls[it["file"].lower()] = parse_sls(desc[it["file"].lower()])
        sail = sls[it["file"].lower()].get(it["index"])
        if sail is None:
            print(f"  no sail {it['index']} in {it['file']}")
            continue

        def place(p, pos=pos):
            return tuple((v + o) * k for v, o in zip(p, pos))
        for tex, verts, tris in sail["meshes"]:
            meshes.append(yard_mesh(f"yard{it['index']}", texture(tex.split(".")[0]), verts, tris, place))
        # sub 4 is the gaff sail of the mizzen: a trapezium that does not roll up ("sailf"); the rest
        # are square sails ("sails"); the corners go in the order the sail entity expects
        group = f"sail{'f' if it['sub'] == 4 else 's'}{it['index']}"
        labels += [(group, f"sail{n + 1}", place(c)) for n, c in enumerate(sail["corners"])]
    sails = sum(1 for g, *_ in labels if g.startswith("sail")) // 4
    print(f"  {ropes} ropes, {len(vants)} shrouds, {sails} sails")
    # the cloth of the sails (parus1..3 are the same cloth torn); the script gives it to the sail entity
    texture("parus_all")

    gm = out / "models" / "ships" / name / f"{name}.gm"
    gm.parent.mkdir(parents=True, exist_ok=True)
    write_gm(meshes, gm, bsp=True, labels=labels)
    for stem in sorted(used):
        src = textures.get(stem)
        if src is None:
            print(f"  missing texture {stem}")
            continue
        dst = out / "textures" / "ships" / name.lower() / f"{stem}.tga.tx"
        dst.parent.mkdir(parents=True, exist_ok=True)
        convert_texture(src, dst)
    # the rope entity takes its texture by the name in rigging.ini, sail_rope.tga by default
    write_rope_texture(out / "textures" / "sail_rope.tga.tx")
    write_vant_texture(out / "textures" / "vant.tga.tx")
    # the rope and vant settings for rigging.ini, appended by run.sh
    (out / "ini").mkdir(parents=True, exist_ok=True)
    (out / "ini" / "rigging_pdm.ini").write_text(
        "[ROPES]\nfWIDTH = 0.12\nfMaxDist = 200000\n\n[VANTS]\n" + VANT_INI + "\n[VANTS_L]\n" + VANT_INI)
    print(f"{gm}: {len(meshes)} meshes, {len(used)} textures")


if __name__ == "__main__":
    main()
