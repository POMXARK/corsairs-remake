#!/usr/bin/env python3
"""Removes the green-screen spill from a Qwen view before Pixal3D: the views are drawn on green, the hair edges keep a
green tint, and TRELLIS spreads it over the whole hair of the texture. Green above max(red, blue) is cut down to it.

usage: python despill_view.py in.png out.png
"""
import sys

import numpy as np
from PIL import Image


def main():
    im = Image.open(sys.argv[1])
    a = np.asarray(im.convert("RGBA")).copy()
    a[..., 1] = np.minimum(a[..., 1], np.maximum(a[..., 0], a[..., 2]))
    Image.fromarray(a if im.mode == "RGBA" else a[..., :3]).save(sys.argv[2])


if __name__ == "__main__":
    main()
