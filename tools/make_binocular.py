#!/usr/bin/env python3
"""The view through a spyglass (record 0x1e "binokular" of Scene4): black bars above and below and soft dark edges at the sides.
A black texture whose alpha is the darkness; the movie lays it over the screen with the fader.
usage: make_binocular.py <resource dir>; writes textures/cinema/binocular.tga.tx"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "common"))
from storm_formats import write_tx  # noqa: E402

WIDTH, HEIGHT = 512, 256
BAR = 0.955  # |y| over this is the black bar (the original shows bars of about 3% of the height)


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


u, v = np.meshgrid((np.arange(WIDTH) + 0.5) / WIDTH * 2 - 1, (np.arange(HEIGHT) + 0.5) / HEIGHT * 2 - 1)
# a round soft frame: the darkness grows with the distance to the middle (an ellipse that stretches over the screen)
r = np.hypot(u / 1.15, v / 1.0)
round_ = smooth((r - 0.62) / 0.62) ** 1.4 * 0.97
bars = smooth((np.abs(v) - BAR) / 0.03)
alpha = np.clip(np.maximum(round_, bars), 0.0, 1.0)
image = np.zeros((HEIGHT, WIDTH, 4), np.uint8)
image[..., 3] = (alpha * 255).astype(np.uint8)
write_tx(Image.fromarray(image, "RGBA"), Path(sys.argv[1]) / "textures" / "cinema" / "binocular.tga.tx")
