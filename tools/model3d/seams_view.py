#!/usr/bin/env python3
"""Draw seam edges over a head from the front, side and back: seams_view.py mesh.obj seams.txt out.png
(seams.txt as head_seams.py writes it; only seam edges on the side facing the camera are drawn)."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_from_obj import read_obj  # noqa: E402

V, _, F, _ = read_obj(sys.argv[1])
S = np.loadtxt(sys.argv[2], dtype=np.int64).reshape(-1, 2)
n = np.zeros_like(V)
fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
for k in range(3):
    np.add.at(n, F[:, k], fn)
n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-30
R, pad = 500, 20
lo, hi = V.min(0), V.max(0)
sc = (R - 2 * pad) / (hi - lo).max()
img = Image.new('RGB', (3 * R, R), (24, 24, 24))
d = ImageDraw.Draw(img)
for i, yaw in enumerate((0, 90, 180)):
    a = np.radians(yaw)
    x = V[:, 0] * np.cos(a) + V[:, 2] * np.sin(a)
    facing = -V[:, 0] * 0 + n[:, 0] * np.sin(a) + n[:, 2] * np.cos(a)
    px = i * R + R / 2 + (x - 0) * sc
    py = R - pad - (V[:, 1] - lo[1]) * sc
    vis = facing > 0
    for j in np.nonzero(vis)[0][::7]:
        d.point((px[j], py[j]), fill=(int(90 + 120 * facing[j]),) * 3)
    for a_, b_ in S:
        if vis[a_] and vis[b_]:
            d.line([(px[a_], py[a_]), (px[b_], py[b_])], fill=(255, 40, 40), width=2)
img.save(sys.argv[3])
