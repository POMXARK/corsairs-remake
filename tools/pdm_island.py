#!/usr/bin/env python3
"""Assembles one island of the original Sea Dogs (PDM 1.061) into the model of the Storm 2 island entity.

A PDM island is a DESC/<Island>.def like a ship: the land (<Island>.cff), its forts (Model items linked
to it) and the points of the fort guns and the flag (Cannon, Flag). The land and the forts go into one
model, in metres by the scale of the ships, with their textures in textures/islands/<name>/*.tga.tx.
The island entity takes models/islands/<Name>/<Name>.gm and the depth map round it, foam/islands/<Name>.tga
and .ini: made here from the same model (the engine would trace it at the first start, minutes in Debug).

Where the ship of the hero appears at the island, the harbour it sails into and how far from the harbour
the world map opens (exit_r) and its Russian name from TEXTS/RUSSIAN/GOODS/ISLANDS/<Island>.nme (label, the
list of the map) go to <data>/islands/<Name>.json (pdm_data2c.py puts it into PdmIslands):
the open water nearest the harbour of the town, facing it. The harbour is the shallows strip of the
model (wsea*), or the middle of the island when there is none.

usage: pdm_island.py <PDM_dir> <resource_out> <Island|all> [--name Name] [--scale K] [--data DIR]
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_def, parse_idf  # noqa: E402
from pdm_ship import DEFAULT_SCALE, index_files, placed  # noqa: E402

# the shallows of the original: a flat strip of sea at the coast, drawn over its sea; the sea of Storm
# draws its own water there (ours: dropped)
SEA_TEXTURES = ("wsea",)
# the depth map: island/src/island.cpp reads a square 8-bit tga over the box of the model grown by
# MAP_MARGIN, a pixel 2 on land and 2 + 253 * depth / 20 under water, 20 m and deeper 255
MAP_SIZE = 512
MAP_MARGIN = 50.0
HMAP_START = 2
HMAP_NUMBERS = 253
HMAP_MAXDEPTH = 20.0
# the ship keeps this far from land and from water shallower than a hull (ours)
PORT_CLEARANCE = 120.0
LAND_DEPTH = -6.0
# the ship leaves for the world map this far beyond the farthest corner of the island from the harbour (ours)
MAP_EXIT_MARGIN = 600.0


def island_model(name):
    """The Storm name of the island of an islands_x.idf object: letters and digits of its name ("Gray Sails"
    -> GraySails); the dead towns (Highrock_) share the island."""
    return "".join(c for c in name if c.isalnum())


def sample(meshes, step):
    """Points over the triangles of the meshes, no farther apart than about a step."""
    out = []
    for m in meshes:
        if not m.triangles:
            continue
        p = np.array([v[0] for v in m.vertices], float)
        tri = p[np.array(m.triangles)]
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        n = int(np.clip(max(np.linalg.norm(b - a, axis=1).max(), np.linalg.norm(c - a, axis=1).max()) / step, 1, 256))
        u, w = np.meshgrid(np.linspace(0, 1, n + 1), np.linspace(0, 1, n + 1))
        keep = u + w <= 1.0
        u, w = u[keep][:, None, None], w[keep][:, None, None]
        out.append((a + (b - a) * u + (c - a) * w).reshape(-1, 3))
    return np.concatenate(out)


def height_map(meshes):
    """The top of the model over the map grid (-inf where there is none), the centre and the size of the box."""
    vs = np.array([v[0] for m in meshes for v in m.vertices])
    lo, hi = vs.min(axis=0), vs.max(axis=0)
    centre = (lo + hi) / 2
    size = hi - lo + MAP_MARGIN
    step = size[[0, 2]] / MAP_SIZE
    pts = sample(meshes, 0.7 * step.min())
    ij = np.floor((pts[:, [0, 2]] - centre[[0, 2]]) / step + MAP_SIZE / 2).astype(int)
    ok = ((ij >= 0) & (ij < MAP_SIZE)).all(axis=1)
    h = np.full((MAP_SIZE, MAP_SIZE), -np.inf)
    np.maximum.at(h, (ij[ok, 1], ij[ok, 0]), pts[ok, 1])
    # close the pixels the sampling missed between its points
    filled = h.copy()
    for dz, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        filled = np.maximum(filled, np.roll(np.roll(h, dz, 0), dx, 1))
    h = np.where(np.isinf(h), filled, h)
    return h, centre, size, step


def write_depth_map(foam, name, h, centre, size):
    depth = np.clip(-h, 0.0, HMAP_MAXDEPTH)
    pixels = np.where(h >= 0.0, HMAP_START, HMAP_START + HMAP_NUMBERS * depth / HMAP_MAXDEPTH)
    pixels = np.clip(np.round(pixels), HMAP_START, 255).astype(np.uint8)
    foam.mkdir(parents=True, exist_ok=True)
    # renderer/include/tga.h TGA_H: an 8-bit grey image, rows from z = -size / 2
    (foam / f"{name}.tga").write_bytes(struct.pack("<BBB9xHHBB", 0, 0, 3, MAP_SIZE, MAP_SIZE, 8, 8) + pixels.tobytes())
    # the engine packs the map into <name>.tga.zap on the first load and prefers it after
    (foam / f"{name}.tga.zap").unlink(missing_ok=True)
    (foam / f"{name}.ini").write_text("\r\n".join([
        "[Main]",
        f"DepthFile = resource\\foam\\islands\\{name}.tga",
        f"vBoxCenter = {centre[0]:.6f},0.000000,{centre[2]:.6f}",
        f"vBoxSize = {size[0] / 2:.6f},0.000000,{size[2] / 2:.6f}",
        "", "[GraphPoints]", ""]))
    return float((pixels == HMAP_START).mean())


def port_place(h, centre, step, harbour):
    """x, z and the heading of the ship: the nearest point to the harbour that is PORT_CLEARANCE off land."""
    land = h > LAND_DEPTH
    # the map ends MAP_MARGIN / 2 beyond the model: the sea goes on past it
    pad = int(PORT_CLEARANCE / step.min()) + 1
    land = np.pad(land, pad)
    near = land.copy()
    rx, rz = (PORT_CLEARANCE / step).astype(int)
    for dz in range(-rz, rz + 1):
        for dx in range(-rx, rx + 1):
            if (dx / rx) ** 2 + (dz / rz) ** 2 <= 1.0:
                near |= np.roll(np.roll(land, dz, 0), dx, 1)
    zs, xs = np.nonzero(~near)
    x = centre[0] + (xs - pad - MAP_SIZE / 2 + 0.5) * step[0]
    z = centre[2] + (zs - pad - MAP_SIZE / 2 + 0.5) * step[1]
    best = int(np.argmin((x - harbour[0]) ** 2 + (z - harbour[1]) ** 2))
    x, z = float(x[best]), float(z[best])
    # the ship engine: heading 0 is along +z, pi/2 along +x
    return x, z, math.atan2(harbour[0] - x, harbour[1] - z)


def convert(res, out, island, name, k, data=None):
    desc, models, textures = (index_files(res / d) for d in ("DESC", "MODELS", "TEXTURES"))
    tex_dir = f"islands\\{name.lower()}"

    def texture(stem):
        return f"{tex_dir}\\{stem.lower()}.tga"

    items = parse_def(desc[island.lower() + ".def"])["items"]
    meshes, harbour = [], []
    for it, pos in placed(items, "Model"):
        cff = models.get(it["file"].lower()) or models.get(Path(it["file"]).stem.lower())
        if cff is None:
            print(f"  missing model {it['file']}")
            continue
        cos, sin = math.cos(it["rot"][1]), math.sin(it["rot"][1])

        def place(p, pos=pos, cos=cos, sin=sin):
            p = (p[0] * cos + p[2] * sin, p[1], -p[0] * sin + p[2] * cos)
            return tuple((v + o) * k for v, o in zip(p, pos))
        for m in cff2gm.cff_to_meshes(cff, place=place, texture=texture):
            if Path(m.texture.replace("\\", "/")).stem.lower().startswith(SEA_TEXTURES):
                harbour += [v[0] for v in m.vertices]
            else:
                meshes.append(m)
    used = {Path(m.texture.replace("\\", "/")).stem for m in meshes}
    guns = [it for it in items if it["class"] == "Cannon"]

    gm = out / "models" / "islands" / name / f"{name}.gm"
    gm.parent.mkdir(parents=True, exist_ok=True)
    write_gm(meshes, gm, bsp=True)
    for stem in sorted(used):
        src = textures.get(stem)
        if src is None:
            print(f"  missing texture {stem}")
            continue
        dst = out / "textures" / "islands" / name.lower() / f"{stem}.tga.tx"
        dst.parent.mkdir(parents=True, exist_ok=True)
        convert_texture(src, dst)
    h, centre, size, step = height_map(meshes)
    land = write_depth_map(out / "foam" / "islands", name, h, centre, size)
    line = f"{name}: {len(meshes)} meshes, {len(used)} textures, {len(guns)} guns, {size[0]:.0f} x {size[2]:.0f} m, land {land:.0%}"
    if data:
        port = np.mean(harbour, axis=0) if harbour else centre
        x, z, ay = port_place(h, centre, step, (port[0], port[2]))
        corners = [(centre[0] + sx * size[0] / 2, centre[2] + sz * size[2] / 2) for sx in (-1, 1) for sz in (-1, 1)]
        exit_r = max(math.hypot(cx - port[0], cz - port[2]) for cx, cz in corners) + MAP_EXIT_MARGIN
        nme = index_files(res / "TEXTS" / "RUSSIAN" / "GOODS" / "ISLANDS").get(island.lower() + ".nme")
        label = nme.read_bytes().decode("cp1251").strip() if nme else name
        dst = Path(data) / "islands" / f"{name}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps({"model": name, "port_x": round(x, 1), "port_z": round(z, 1),
                                   "port_ay": round(ay, 3), "harbour_x": round(float(port[0]), 1),
                                   "harbour_z": round(float(port[2]), 1),
                                   "exit_r": round(exit_r), "label": label}, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        line += f", the ship at {x:.0f}, {z:.0f} heading {math.degrees(ay):.0f}"
    print(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdm")
    ap.add_argument("out")
    ap.add_argument("island", help="the DEF name, or all: every island of WORLDS/islands_x.idf")
    ap.add_argument("--name", help="Storm island name (default: the DEF name)")
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    ap.add_argument("--data", help="where islands/<Name>.json with the place of the ship goes")
    a = ap.parse_args()

    res = Path(a.pdm)
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    if a.island != "all":
        convert(res, Path(a.out), a.island, a.name or a.island, a.scale, a.data)
        return
    # the islands_x objects name their DEF ("Gray Sails" -> DESC/Gray Sails.def); a dead town (Highrock_)
    # stands on the island of the living one
    done = set()
    for o in parse_idf(res / "WORLDS" / "islands_x.idf")["objects"]:
        island = dict(o)["name"].rstrip("_")
        if island_model(island) not in done:
            done.add(island_model(island))
            convert(res, Path(a.out), island, island_model(island), a.scale, a.data)


if __name__ == "__main__":
    main()
