#!/usr/bin/env python3
"""UV layout coloured by the facing of the 3D faces: uv_layout.py model.obj out.png [size]"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_from_obj import read_obj  # noqa: E402

V, T, F, FT = read_obj(sys.argv[1])
size = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-30
col = ((n * 0.5 + 0.5) * 255).astype(int)
im = Image.new('RGB', (size, size))
d = ImageDraw.Draw(im)
for t, c in zip(T[FT], col):
    d.polygon([(x * size, (1 - y) * size) for x, y in t], fill=tuple(c))
im.save(sys.argv[2])
