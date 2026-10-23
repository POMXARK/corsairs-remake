#!/usr/bin/env python3
"""Checks the models of the networks against the views they were made from (docs/ai-models.md, ours), as
pdm_voice_check.py does with the voiced speeches.

Every <name>.glb of data/ai_models/glb is drawn from four sides without perspective (points of its surface, the
colours of its texture) and compared with <name>_{front,right,back,left}.png of the views, both fitted to their
bounding box. The model may be turned around the vertical axis by a quarter turn: the best of the four is taken.
- shape: the overlap (IoU) of the silhouettes, the lowest of the four sides. A grown body, a lost hand or a
  fused sleeve make it fall;
- colour: the mean colour of the model against the mean colour of the view, per cent. A black sleeve that became
  red makes it rise.
Writes data/ai_models/report.tsv (name, shape, colour, turn, tries, verdict) and
- data/ai_models/redo.txt: the names for comfy_model_batch.py --redo, with the next seed;
  after --max-tries a name goes to data/ai_models/listen.txt for the eye instead.

usage: pdm_model_check.py <game dir> [<name> ...] [--views data/ai_models/views] [--iou 0.75] [--colour 0.18]
                          [--max-tries 3] [--glb data/ai_models/glb]
Needs numpy, Pillow, scipy, trimesh.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing

VIEWS = ("front", "right", "back", "left")
SIZE = 256
FILL = 0.85
BACKGROUND = 128
POINTS = 400000


def points_of(path: Path):
    """Points of the surface and their colours (0..1) of a GLB, every mesh of it."""
    import trimesh
    scene = trimesh.load(str(path), force="scene")
    meshes = [g for g in scene.dump() if isinstance(g, trimesh.Trimesh) and len(g.faces)]
    area = np.array([m.area for m in meshes])
    pts, cols = [], []
    for m, share in zip(meshes, area / area.sum()):
        n = max(int(POINTS * share), 1000)
        p, face = trimesh.sample.sample_surface(m, n)
        try:
            vc = m.visual.to_color().vertex_colors[:, :3] / 255.0
            bary = trimesh.triangles.points_to_barycentric(m.triangles[face], p)
            c = (vc[m.faces[face]] * bary[..., None]).sum(1)
        except Exception:
            c = np.full((n, 3), 0.5)
        pts.append(p)
        cols.append(c)
    return np.concatenate(pts), np.concatenate(cols)


def fit(mask, colour):
    """The mask and colours cropped to the bounding box and put in the middle of a SIZE square, as the views are."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return np.zeros((SIZE, SIZE), bool), np.zeros((SIZE, SIZE, 3))
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    m = Image.fromarray(mask[y0:y1, x0:x1].astype(np.uint8) * 255)
    c = Image.fromarray((colour[y0:y1, x0:x1] * 255).astype(np.uint8))
    k = FILL * SIZE / max(y1 - y0, x1 - x0)
    size = (max(int((x1 - x0) * k), 1), max(int((y1 - y0) * k), 1))
    m, c = m.resize(size, Image.BILINEAR), c.resize(size, Image.BILINEAR)
    om, oc = Image.new("L", (SIZE, SIZE)), Image.new("RGB", (SIZE, SIZE))
    at = ((SIZE - size[0]) // 2, (SIZE - size[1]) // 2)
    om.paste(m, at)
    oc.paste(c, at)
    return np.asarray(om) > 127, np.asarray(oc) / 255.0


def splat(pts, cols, yaw):
    """The points turned by yaw degrees around y and seen along +z, the nearest colour on every pixel."""
    a = math.radians(yaw)
    turn = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    p = pts @ turn.T
    lo, hi = p.min(0), p.max(0)
    big = 2 * SIZE
    k = big / max(hi[0] - lo[0], hi[1] - lo[1], 1e-9) * 0.98
    x = ((p[:, 0] - (lo[0] + hi[0]) / 2) * k + big / 2).astype(int).clip(0, big - 1)
    y = (big / 2 - (p[:, 1] - (lo[1] + hi[1]) / 2) * k).astype(int).clip(0, big - 1)
    order = np.argsort(-p[:, 2])  # far first, the near ones are drawn over
    colour = np.zeros((big, big, 3))
    mask = np.zeros((big, big), bool)
    colour[y[order], x[order]] = cols[order]
    mask[y[order], x[order]] = True
    mask = binary_closing(mask, np.ones((5, 5), bool))
    return fit(mask, colour)


def view(path: Path):
    im = np.asarray(Image.open(path).convert("RGB")).astype(float)
    mask = np.abs(im - BACKGROUND).max(-1) > 10
    return fit(mask, im / 255.0)


def compare(pts, cols, views):
    """(lowest IoU of the four sides, colour distance, quarter turns) of the best turn of the model."""
    best = None
    for turn in range(4):
        ious = []
        mine, theirs = [], []
        for i, (vm, vc) in enumerate(views):
            m, c = splat(pts, cols, 90 * (i + turn))
            ious.append((m & vm).sum() / max((m | vm).sum(), 1))
            if m.any() and vm.any():
                mine.append(c[m].mean(0))
                theirs.append(vc[vm].mean(0))
        score = (min(ious), float(np.mean(ious)))
        if best is None or score > best[0]:
            dist = float(np.abs(np.mean(mine, 0) - np.mean(theirs, 0)).mean()) if mine else 1.0
            best = (score, dist, turn)
    return best[0][0], best[1], best[2]


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--views", type=Path)
    ap.add_argument("--glb", type=Path)
    ap.add_argument("--iou", type=float, default=0.75)
    ap.add_argument("--colour", type=float, default=0.18)
    ap.add_argument("--max-tries", type=int, default=3)
    a = ap.parse_args()

    ai = a.game / "data" / "ai_models"
    glbs = a.glb or ai / "glb"
    views = a.views or ai / "views"
    names = a.names or sorted(p.stem for p in glbs.glob("*.glb"))
    seeds = json.loads((glbs / "seeds.json").read_text()) if (glbs / "seeds.json").exists() else {}
    rows, redo, listen = ["name\tshape\tcolour\tturn\ttries\tverdict"], [], []
    for name in names:
        if not (glbs / f"{name}.glb").exists() or not (views / f"{name}_front.png").exists():
            continue
        pts, cols = points_of(glbs / f"{name}.glb")
        iou, dist, turn = compare(pts, cols, [view(views / f"{name}_{v}.png") for v in VIEWS])
        tries = seeds.get(name, 0) + 1
        ok = iou >= a.iou and dist <= a.colour
        verdict = "ok" if ok else ("redo" if tries < a.max_tries else "listen")
        if verdict == "redo":
            redo.append(name)
        elif verdict == "listen":
            listen.append(name)
        rows.append(f"{name}\t{iou:.2f}\t{dist * 100:.0f}%\t{turn}\t{tries}\t{verdict}")
        print(rows[-1], flush=True)
    (ai / "report.tsv").write_text("\n".join(rows) + "\n")
    (ai / "redo.txt").write_text("\n".join(redo) + ("\n" if redo else ""))
    (ai / "listen.txt").write_text("\n".join(listen) + ("\n" if listen else ""))
    print(f"pdm_model_check: {len(redo)} to make again (data/ai_models/redo.txt), {len(listen)} for the eye")


if __name__ == "__main__":
    main()
