#!/usr/bin/env python3
"""Assembles one ship of the original Sea Dogs (PDM 1.061) into a Storm 2 ship model.

A PDM ship is a DESC/<Ship>.def: a tree of parts (hull, masts, rigging, cannons; the Patch lid is skipped) whose
offsets are summed along the links; the parts are separate .cff files in MODELS. Storm 2 loads a
ship from models/ships/<Name>/<Name>.gm, so all parts go into one model, scaled to metres, with
their textures converted to textures/ships/<name>/*.tga.tx.

usage: pdm_ship.py <PDM_dir> <resource_out> <Ship> [--name Name] [--scale K]
"""
import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import write_gm  # noqa: E402
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


def placed(items):
    """Model items with their offset summed along the link chain (the models are not rotated).

    The Patch item is skipped: a black lid over the hull facing down (ABrig_Patch.cff, texture "black"),
    a mask of the original against its sea inside the hull. Storm 2 does not need it and, with the faces
    double-sided, it covered the deck."""
    by_index = {}
    for it in items:
        by_index.setdefault(it["index"], it)
    out = []
    for it in items:
        if it["class"] != "Model" or not it["file"]:
            continue
        pos, link, seen = list(it["pos"]), it["link"], set()
        while link >= 0 and link in by_index and link not in seen:
            seen.add(link)
            parent = by_index[link]
            pos = [a + b for a, b in zip(pos, parent["pos"])]
            link = parent["link"]
        out.append((it, pos))
    return out


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

    meshes = []
    for it, pos in placed(parse_def(desc[a.ship.lower() + ".def"])["items"]):
        cff = models.get(it["file"].lower())
        if cff is None:
            print(f"  missing model {it['file']}")
            continue
        k = a.scale

        def place(p, pos=pos):
            # summed DEF offset, then metres
            return tuple((v + o) * k for v, o in zip(p, pos))
        parts = cff2gm.cff_to_meshes(cff, place=place, texture=texture)
        meshes += parts
        print(f"  {it['file']:<20} {len(parts):3d} meshes at {[round(v, 3) for v in pos]}")

    gm = out / "models" / "ships" / name / f"{name}.gm"
    gm.parent.mkdir(parents=True, exist_ok=True)
    write_gm(meshes, gm, bsp=True)
    for stem in sorted(used):
        src = textures.get(stem)
        if src is None:
            print(f"  missing texture {stem}")
            continue
        dst = out / "textures" / "ships" / name.lower() / f"{stem}.tga.tx"
        dst.parent.mkdir(parents=True, exist_ok=True)
        convert_texture(src, dst)
    print(f"{gm}: {len(meshes)} meshes, {len(used)} textures")


if __name__ == "__main__":
    main()
