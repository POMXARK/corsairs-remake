#!/usr/bin/env python3
"""Assembles one ship of the original Sea Dogs (PDM 1.061) into a Storm 2 ship model.

A PDM ship is a DESC/<Ship>.def: a tree of parts (hull, masts, rigging, cannons; the Patch lid is skipped) whose
offsets are summed along the links; the parts are separate .cff files in MODELS. Storm 2 loads a
ship from models/ships/<Name>/<Name>.gm, so all parts go into one model, scaled to metres, with
their textures converted to textures/ships/<name>/*.tga.tx.

usage: pdm_ship.py <PDM_dir> <resource_out> <Ship> [--name Name] [--scale K]
"""
import argparse
import math
import re
import struct
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import Mesh, write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_def, parse_idf  # noqa: E402

# DEF units: the brig ABrig is 1.17 long; a real brig of the time is about 30 m
DEFAULT_SCALE = 26.0


def index_files(folder: Path):
    """Lower-case stem -> path: PDM names files in any case and the CFF texture names say .tga for .tf."""
    files = {}
    for f in folder.iterdir():
        files.setdefault(f.stem.lower(), f)
        files.setdefault(f.name.lower(), f)
    return files


# the masts are the parts *_MS_<n> / *_ms<n> standing on the hull (0 is the bowsprit)
MAST_FILE = re.compile(r"_?ms_?(\d)")


# the side of a gun by its turn about the vertical in quarters: 0 fore, pi/2 right, pi aft, -pi/2 left;
# the names are the borts of SEA_AI (Cannons.Borts of the ship type)
GUN_BORTS = ("cannonf", "cannonr", "cannonb", "cannonl")

# the DEF sub of the sails with the coat of arms
EMBLEM_SAIL = 6


class Node:
    """A node of the Storm model: its meshes and labels, relative to its origin (metres, from the hull)."""
    def __init__(self, origin=(0.0, 0.0, 0.0), parent=None):
        self.origin, self.parent, self.meshes, self.labels = origin, parent, [], []


def placed(items, kind="Model", points=False):
    """Items of a class (or of several, "Model,Rey") with their offset summed along the link chain (the models are not rotated).

    The Patch item is skipped: a black lid over the hull facing down (ABrig_Patch.cff, texture "black"),
    a mask of the original against its sea inside the hull. Storm 2 does not need it and, with the faces
    double-sided, it covered the deck. points: the items without a model too (a Flag always is a point)."""
    by_index = {}
    for it in items:
        by_index.setdefault(it["index"], it)
    out = []
    for it in items:
        # a Flag is a point (the masthead, the ensign staff): it has no model
        if it["class"] not in kind.split(",") or not (it["file"] or points or kind == "Flag"):
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
# the shrouds of the original are light hemp ladders, the stays dark lines
HEMP = (150, 128, 96, 255)
WOOD = (92, 64, 38, 255)
CLEAR = (150, 128, 96, 0)


def write_rope_texture(dst: Path):
    """The rope entity's texture: tarred hemp with the twist as diagonal stripes. PDM's black.tf does not
    fit: its alpha falls with the mip (255, 187, 136, 85, 34), so the original faded its thin stays with
    the distance, and ShipRope, which tests alpha, drops them a few tens of metres away."""
    def pixel(x, y):
        k = 0.75 + 0.25 * ((x + y) // 4 % 2)
        return tuple(int(c * k) for c in ROPE[:3]) + (255,)
    write_tx(dst, 32, pixel)


# Where write_vant_texture puts the parts of a shroud; the vant entity reads them from rigging.ini
VANT_INI = """fWidth = 0.03
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
fHRopeHeight = 0.9
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
            return HEMP
        if u < 0.5:
            if v >= 0.6:
                return WOOD if v < 0.75 else CLEAR
            # five ropes from the top middle to the beam
            if 0.125 <= u and v > 0.02:
                for k in range(5):
                    end = 0.14 + 0.345 * k / 4
                    at = 0.3125 + (end - 0.3125) * v / 0.6
                    if abs(u - at) < 1 / size:
                        return HEMP
            return CLEAR
        return HEMP if abs(v - 0.5) < 1.5 / size else CLEAR
    write_tx(dst, size, pixel)


# The flags: the flag entity draws them as cloth in the wind from four labels of a group flag<N>: f1 and
# f4 the edge at the mast (top, bottom), f2 and f3 the free edge (top, bottom). A DEF Flag item is only
# the point the flag hangs from; sub 2 is the pennant of the foremast. Length aft and height, metres:
# the flags at the mastheads are small and long; the ensign on the stern staff (a flag of the hull)
# follows the hull, STERN_FLAG below.
FLAG_SIZE = {0: (2.0, 0.8), 2: (4.0, 0.35)}
# ours: the ensign is as long as this share of the hull and 0.6 of that high (1.6 m on the pink, 4 m on
# the frigate); a fixed 4.2 m flag covered a third of the small hulls and swung into the stern
STERN_FLAG = 0.12
# the atlas of the flags: a column per nation of WORLDS/nations.idf, in its order (the .nation of a
# character is that index); the script returns the column in GetRiggingData/GetShipFlagTexNum
FLAG_COLUMNS = 8


def flag_labels(n, sub, at, stern=0.0):
    """The labels of flag n hanging from the point at (in its node); stern: the hull length, for the ensign."""
    length, height = (STERN_FLAG * stern, 0.6 * STERN_FLAG * stern) if stern else FLAG_SIZE[sub if sub in FLAG_SIZE else 0]
    x, y, z = at
    return [(f"flag{n}", "f1", (x, y, z)), (f"flag{n}", "f4", (x, y - height, z)),
            (f"flag{n}", "f2", (x, y, z - length)), (f"flag{n}", "f3", (x, y - height, z - length))]


def write_flag_texture(res: Path, textures: dict, dst: Path):
    """The flags of the nations (the flag field of nations.idf, 128 x 64 .tf) side by side."""
    nations = [dict(o) for o in parse_idf(res / "WORLDS" / "nations.idf")["objects"]]
    w, h = 128, 64
    rows = [bytearray(w * FLAG_COLUMNS * 4) for _ in range(h)]
    with tempfile.TemporaryDirectory() as tmp:
        for col, nation in enumerate(nations[:FLAG_COLUMNS]):
            src = textures.get(nation.get("flag", "").lower())
            if src is None:
                continue
            tx = Path(tmp) / "flag.tx"
            convert_texture(src, tx)
            data = tx.read_bytes()
            fw, fh = struct.unpack_from("<6i", data)[1:3]
            for y in range(h):
                sy = y * fh // h
                for x in range(w):
                    o = 24 + (sy * fw + x * fw // w) * 4
                    rows[y][(col * w + x) * 4:(col * w + x) * 4 + 4] = data[o:o + 4]
    dst.parent.mkdir(parents=True, exist_ok=True)
    width = w * FLAG_COLUMNS
    dst.write_bytes(struct.pack("<6i", 0, width, h, 1, 21, width * h * 4) + b"".join(rows))


def read_tx(src: Path, tmp: Path):
    """A .tf/.tga of the original as (width, height, BGRA bytes of the first mip)."""
    convert_texture(src, tmp)
    data = tmp.read_bytes()
    w, h = struct.unpack_from("<6i", data)[1:3]
    return w, h, data[24:24 + w * h * 4]


def write_nation_sails(res: Path, textures: dict, out: Path):
    """The sails of the nations (nations.idf): the cloth (sail, textures/ships/sails/<sail>.tga) and the
    coat of arms (emb_sail, the same cloth with the arms painted on). Storm draws the arms over the sail
    as a texture of their own (Gerald of the sail entity), so the arms are cut out: where emb_sail
    differs from the cloth they are opaque, elsewhere clear (textures/ships/gerald/<nation>.tga)."""
    nations = [dict(o) for o in parse_idf(res / "WORLDS" / "nations.idf")["objects"]]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp) / "t.tx"
        for nation in nations:
            sail, emb = (textures.get(nation.get(f, "").lower()) for f in ("sail", "emb_sail"))
            if sail is None:
                continue
            dst = out / "textures" / "ships" / "sails" / f"{nation['sail'].lower()}.tga.tx"
            dst.parent.mkdir(parents=True, exist_ok=True)
            convert_texture(sail, dst)
            if emb is None or emb == sail:
                continue
            w, h, cloth = read_tx(sail, tmp)
            ew, eh, arms = read_tx(emb, tmp)
            if (w, h) != (ew, eh):
                continue
            px = bytearray(arms)
            for i in range(0, len(px), 4):
                diff = sum(abs(arms[i + c] - cloth[i + c]) for c in range(3))
                px[i + 3] = 255 if diff > 40 else 0
            dst = out / "textures" / "ships" / "gerald" / f"{nation['name'].lower()}.tga.tx"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(struct.pack("<6i", 0, w, h, 1, 21, w * h * 4) + bytes(px))


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
    items = parse_def(desc[a.ship.lower() + ".def"])["items"]
    by_index = {}
    for it in items:
        by_index.setdefault(it["index"], it)
    # the nodes of the Storm model: the hull, a node per mast (the engine breaks and drops a node named
    # mast<N>) and in it a node per yard with its sail (rey...: they fall with the mast). A node is
    # loaded from <name>_<node>.gm where its parent has a "geometry" label; its parts are relative to it
    nodes = {"": Node()}
    masts = {}
    for it, pos in placed(items):
        m = MAST_FILE.search(Path(it["file"]).stem.lower())
        if m and by_index.get(it["link"], {}).get("class") == "Model" and by_index[it["link"]]["link"] < 1:
            masts[it["index"]] = f"mast{int(m.group(1)) + 1}"
            nodes[masts[it["index"]]] = Node(tuple(v * k for v in pos), "")

    def node_of(it):
        """The mast an item stands on (the one nearest the hull along its links), or the hull."""
        found, link, seen = "", it["index"], set()
        while link in by_index and link not in seen:
            seen.add(link)
            found = masts.get(link, found)
            link = by_index[link]["link"]
        return found

    vants, ropes = 0, 0
    # the parts: hull, masts, the yards of the ships without .sls (Rey: Shnyava) and the deck guns (a
    # Cannon with a model; the ones without are the ports of the lower decks, the points they fire from)
    for it, pos in placed(items, "Model,Rey,Cannon"):
        # Tartana.def names Tartana.clf, which is not in the release: the .cff of the same name is
        cff = models.get(it["file"].lower()) or models.get(Path(it["file"]).stem.lower())
        if cff is None:
            print(f"  missing model {it['file']}")
            continue
        node = nodes[node_of(it)]
        # a gun is turned to its side about the vertical (rot y: -pi/2 left, pi/2 right, pi aft)
        cos, sin = math.cos(it["rot"][1]), math.sin(it["rot"][1])

        def place(p, pos=pos, cos=cos, sin=sin, origin=node.origin):
            # turned, summed DEF offset, metres, then from the node
            p = (p[0] * cos + p[2] * sin, p[1], -p[0] * sin + p[2] * cos)
            return tuple((v + o) * k - c for v, o, c in zip(p, pos, origin))
        parts = cff2gm.cff_to_meshes(cff, place=place, texture=texture)
        hull = nodes[""]
        for part in parts:
            # the shrouds and stays are drawn by the vant and rope entities from labels of the hull node
            to_hull = lambda q, origin=node.origin: tuple(a + b for a, b in zip(q, origin))
            if part.texture.endswith(("\\takelag_new.tga", "\\mf_takelag.tga")):
                # the shrouds: a triangle each, the masthead and two points at the side; the vant entity
                # draws them as ropes with ratlines. Its labels carry one digit: vant1..9, then vanx1..9
                # for the vantl entity (half the triangles are the back side)
                for a, b, c in part.triangles[:len(part.triangles) // 2]:
                    up, left, right = sorted((to_hull(part.vertices[i][0]) for i in (a, b, c)), key=lambda p: -p[1])
                    vants += 1
                    vant = f"vant{vants}" if vants <= 9 else f"vanx{vants - 9}"
                    hull.labels += [("vant", vant + "u", up), ("vant", vant + "l", left), ("vant", vant + "r", right)]
            elif part.texture.endswith("\\black.tga"):
                # the stays: ropes of the rope entity instead of flat strips (half the vertices are the back side)
                front = len(part.vertices) // 2
                positions = [to_hull(v[0]) for v in part.vertices[:front]]
                for b, e in rope_ends(positions, part.triangles[:len(part.triangles) // 2]):
                    ropes += 1
                    hull.labels += [("rope", f"ropeb{ropes}", b), ("rope", f"ropee{ropes}", e)]
            else:
                node.meshes.append(part)
        print(f"  {it['file']:<20} {len(parts):3d} meshes at {[round(v, 3) for v in pos]} {node_of(it)}")

    # the sails: their yards go into the model, the cloth is drawn by the sail entity from the corners.
    # The yard of each sail on a mast is a node of its own. Sub 6 is the sail with the coat of arms of
    # the nation (the topsails of the original): its yard is rey_emblem<n>, the script gives those
    # nodes the arms (Gerald of the sail entity)
    sls, yards = {}, []
    for it, pos in placed(items, "Sail"):
        if it["file"].lower() not in sls:
            sls[it["file"].lower()] = parse_sls(desc[it["file"].lower()])
        sail = sls[it["file"].lower()].get(it["index"])
        if sail is None:
            print(f"  no sail {it['index']} in {it['file']}")
            continue
        yards.append((it, pos, sail))
    emblems = 0
    for it, pos, sail in yards:
        mast = node_of(it)
        origin = tuple(v * k for v in pos)
        # a sail without a yard mesh stays in its mast node: a node has to have geometry
        if mast and sail["meshes"]:
            if it["sub"] == EMBLEM_SAIL:
                emblems += 1
                yard = f"rey_emblem{emblems}"
            else:
                yard = f"rey{it['index']}"
            nodes[yard] = Node(origin, mast)
        else:
            yard = mast
            origin = nodes[mast].origin
        node = nodes[yard]

        def place(p, pos=pos, origin=origin):
            return tuple((v + o) * k - c for v, o, c in zip(p, pos, origin))
        for tex, verts, tris in sail["meshes"]:
            node.meshes.append(yard_mesh(f"yard{it['index']}", texture(tex.split(".")[0]), verts, tris, place))
        # sub 4 is the gaff sail of the mizzen: a trapezium that does not roll up ("sailf"); the rest
        # are square sails ("sails"); the corners go in the order the sail entity expects
        group = f"sail{'f' if it['sub'] == 4 else 's'}{it['index']}"
        node.labels += [(group, f"sail{n + 1}", place(c)) for n, c in enumerate(sail["corners"])]
    # the guns: a label per Cannon item (the deck guns and the ports of the lower decks) in the group of
    # its side, its z axis along the shot; SEA_AI fires the side from these points (AICannon, ours)
    guns = {}
    for it, pos in placed(items, "Cannon", points=True):
        r = it["rot"][1] % (2 * math.pi)
        bort = GUN_BORTS[round(r / (math.pi / 2)) % 4]
        guns[bort] = guns.get(bort, 0) + 1
        at = tuple(v * k for v in pos)
        nodes[""].labels.append((bort, f"gun{guns[bort]}", at, (round(math.sin(r), 6), round(math.cos(r), 6))))
    print("  guns " + ", ".join(f"{b} {n}" for b, n in sorted(guns.items())))
    hull_z = [v[0][2] for m in nodes[""].meshes for v in m.vertices]
    hull_length = max(hull_z) - min(hull_z)
    for it, pos in placed(items, "Flag"):
        mast = node_of(it)
        node = nodes[mast]
        n = sum(1 for nd in nodes.values() for g, *_ in nd.labels if g.startswith("flag")) // 4 + 1
        at = tuple(v * k - c for v, c in zip(pos, node.origin))
        node.labels += flag_labels(n, it["sub"], at, stern=hull_length if not mast and it["sub"] == 0 else 0.0)
    flags = sum(1 for nd in nodes.values() for g, *_ in nd.labels if g.startswith("flag")) // 4
    print(f"  {ropes} ropes, {vants} shrouds, {len(yards)} sails, {flags} flags, {len(masts)} masts, {emblems} arms")

    # a node is placed by a label of its parent
    for nm, nd in nodes.items():
        if nm:
            parent = nodes[nd.parent]
            parent.labels.append(("geometry", nm, tuple(a - b for a, b in zip(nd.origin, parent.origin))))
    gm = out / "models" / "ships" / name / f"{name}.gm"
    gm.parent.mkdir(parents=True, exist_ok=True)
    for old in gm.parent.glob(f"{name}_*.gm"):
        old.unlink()
    for nm, nd in nodes.items():
        write_gm(nd.meshes, gm.with_name(f"{name}_{nm}.gm" if nm else f"{name}.gm"), bsp=True, labels=nd.labels)
    meshes = [m for nd in nodes.values() for m in nd.meshes]
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
    write_flag_texture(res, textures, out / "textures" / "flags_pdm.tga.tx")
    write_nation_sails(res, textures, out)
    # the rope and vant settings for rigging.ini, appended by run.sh
    (out / "ini").mkdir(parents=True, exist_ok=True)
    (out / "ini" / "rigging_pdm.ini").write_text(
        "[ROPES]\nfWIDTH = 0.04\nfMaxDist = 200000\n\n[VANTS]\n" + VANT_INI + "\n[VANTS_L]\n" + VANT_INI +
        f"\n[FLAGS]\nTextureName = flags_pdm.tga\nTextureCountColumn = {FLAG_COLUMNS}\nTextureCountRow = 1\n")
    print(f"{gm}: {len(meshes)} meshes, {len(used)} textures")


if __name__ == "__main__":
    main()
