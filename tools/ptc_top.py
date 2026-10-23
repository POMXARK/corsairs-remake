#!/usr/bin/env python3
"""The floor of a location seen from above, as pdm_world.py makes it, to check the cut obstacles.

Green: the patch the characters walk on after the obstacles are cut out. Red: the triangles of the
location model in the band of the body (pdm_world.BODY). Blue: the points of the .loc (the
character points stay free) and the exit boxes.

usage: ptc_top.py <PDM RESOURCE dir> <WORLDS/locations/*.loc> <out.png>
"""
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cff2gm  # noqa: E402
import pdm_world as w  # noqa: E402


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    root, loc_file, out = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    loc = w.parse_loc(loc_file)

    def find(name):
        stem = Path(name).stem.lower()
        return next(p for p in root.rglob("*.cff") if p.stem.lower() == stem)

    patch_cff, model_cff = find(loc["patch"]), find(loc["model"])
    start = time.time()
    floor = [t for t, _ in w.walk_floor(patch_cff, model_cff, loc)]
    print(f"{len(floor)} floor triangles, {time.time() - start:.1f} s")
    keep = [(p["pos"][0] * w.K, p["pos"][2] * w.K) for p in loc["points"]]
    boxes = [tuple(c * w.K for c in p["box"]) for p in loc["points"] if p["type"] == 1]

    xs = [p[0] for t in floor for p in t]
    zs = [p[2] for t in floor for p in t]
    x0, x1, z0, z1 = min(xs) - 1, max(xs) + 1, min(zs) - 1, max(zs) + 1
    s = 1400 / max(x1 - x0, z1 - z0)
    img = Image.new("RGB", (int((x1 - x0) * s), int((z1 - z0) * s)), "white")
    draw = ImageDraw.Draw(img)

    def at(p):
        return (p[0] - x0) * s, (z1 - p[2]) * s

    for t in floor:
        draw.polygon([at(p) for p in t], fill=(190, 235, 190), outline=(120, 180, 120))
    low, high = w.BODY
    for mesh in cff2gm.cff_to_meshes(model_cff, place=lambda p: tuple(c * w.K for c in p)):
        for tri in mesh.triangles:
            q = [mesh.vertices[i][0] for i in tri]
            if max(p[1] for p in q) > low and min(p[1] for p in q) < high:
                draw.polygon([at(p) for p in q], outline=(220, 40, 40))
    for x, z in keep:
        draw.ellipse([at((x - .2, 0, z + .2)), at((x + .2, 0, z - .2))], outline=(0, 0, 255))
    for x0_, z0_, x1_, z1_ in boxes:
        draw.rectangle([at((x0_, 0, z1_)), at((x1_, 0, z0_))], outline=(0, 0, 255))
    img.save(out)
    print(out)


if __name__ == "__main__":
    main()
