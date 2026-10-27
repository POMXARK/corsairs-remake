#!/usr/bin/env python3
"""The moon disc of the movies at night: a generated texture (no third-party art), a soft-edged disc with dim maria.
usage: make_moon.py [out.tga]; the engine reads .tx: pdm2storm.tga_to_tx turns it into moon.tga.tx"""
import math
import random
import sys
from pathlib import Path

from PIL import Image

N = 128
out = Path(sys.argv[1] if len(sys.argv) > 1 else "pdm-game/resource/textures/weather/moon.tga")
rnd = random.Random(7)
maria = [(rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0.1, 0.28)) for _ in range(7)]
img = Image.new("RGBA", (N, N))
for y in range(N):
    for x in range(N):
        u, v = (x + 0.5) / N * 2 - 1, (y + 0.5) / N * 2 - 1
        r = math.hypot(u, v)
        shade = 1.0
        for mx, my, mr in maria:
            shade -= 0.22 * max(0.0, 1 - math.hypot(u - mx, v - my) / mr)
        shade *= 1.0 - 0.12 * max(0.0, (u + v * 0.3 + 0.2))  # the terminator: the right side a bit darker
        c = int(max(0.0, min(1.0, shade)) * 255)
        glow = max(0.0, 1 - max(0.0, r - 0.8) / 0.2)  # the soft edge of the disc
        # the engine adds the texture to the sky (one + one): the halo is colour, black outside the disc
        k = 1.0 if r < 0.8 else 0.55 * glow * glow
        img.putpixel((x, y), (int(c * k), int(min(255, c + 4) * k), int(min(255, c + 14) * k), 255))
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out)
