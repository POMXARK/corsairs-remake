#!/usr/bin/env python3
"""tools/eyes.json from tools/eyes_marks.json: the size of every marked eye, measured on its texture.

The marks are the centres of the irises, put by looking at the textures (the OpenCV Haar eye cascades found the
right eye on one head in two and took ears and hair for eyes on the rest, so they only propose). Here each mark
is snapped to the darkest point of the iris and the eye opening is the part around it that differs from the skin
(Lab distance to the median of the rows above and below), its ellipse is kept within 16x6 texels.

  python tools/make_eyes.py <resource>      needs numpy, Pillow, OpenCV (opencv-python)
  <resource>/textures/characters/*.tga.tx is read; the position and size are texels of the texture taken as 256x256
"""
import io
import json
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent


def load_tx(path):
    d = path.read_bytes()
    _, w, h, _, fmt, size = struct.unpack("<6i", d[:24])
    raw = d[24:24 + size]
    if fmt == 21:
        return Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRA", 0, 1).convert("RGB")
    if fmt == 22:
        return Image.frombuffer("RGBX", (w, h), raw, "raw", "BGRX", 0, 1).convert("RGB")
    cc = {0x31545844: b"DXT1", 0x33545844: b"DXT3", 0x35545844: b"DXT5"}
    hdr = (b"DDS " + struct.pack("<7I", 124, 0x1007, h, w, size, 0, 1) + bytes(44)
           + struct.pack("<2I4s5I", 32, 4, cc[fmt], 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0))
    return Image.open(io.BytesIO(hdr + raw)).convert("RGB")


def measure(im, p):
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), (0, 0), 1.5).astype(float)
    px, py = p
    x0, x1, y0, y1 = max(px - 7, 0), min(px + 8, 256), max(py - 5, 0), min(py + 6, 256)
    iy, ix = np.unravel_index(np.argmin(g[y0:y1, x0:x1]), g[y0:y1, x0:x1].shape)
    px, py = x0 + ix, y0 + iy
    lab = cv2.cvtColor(im, cv2.COLOR_RGB2LAB).astype(np.float32)
    X0, X1, Y0, Y1 = max(px - 16, 0), min(px + 16, 256), max(py - 9, 0), min(py + 9, 256)
    crop = lab[Y0:Y1, X0:X1]
    ref = np.median(np.concatenate([crop[:2].reshape(-1, 3), crop[-2:].reshape(-1, 3)]), axis=0)
    dist = cv2.GaussianBlur(np.linalg.norm(crop - ref, axis=2), (0, 0), 0.8)
    m = (dist > max(14.0, 0.35 * dist[py - Y0, px - X0])).astype(np.uint8)
    _, lbl = cv2.connectedComponents(m)
    rx, ry = 11.0, 4.0
    if lbl[py - Y0, px - X0]:
        ys, xs = np.nonzero(lbl == lbl[py - Y0, px - X0])
        if len(xs) > 20:
            rx, ry = (xs.max() - xs.min() + 1) / 2, (ys.max() - ys.min() + 1) / 2
            px, py = X0 + (xs.max() + xs.min()) / 2, Y0 + (ys.max() + ys.min()) / 2
    return {"cx": round(float(px), 1), "cy": round(float(py), 1),
            "rx": round(float(np.clip(rx, 8, 16)), 1), "ry": round(float(np.clip(ry, 3, 6)), 1)}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    tex = Path(sys.argv[1]) / "textures" / "characters"
    files = {p.name.lower().split(".")[0].replace(" ", "_"): p for p in tex.glob("*.tga.tx")}
    out = {}
    for name, marks in json.loads((TOOLS / "eyes_marks.json").read_text()).items():
        im = np.asarray(load_tx(files[name]).resize((256, 256), Image.BICUBIC))
        out[name] = [measure(im, p) for p in marks]
    (TOOLS / "eyes.json").write_text(json.dumps(out, indent=1) + "\n")
    print(len(out), "heads ->", TOOLS / "eyes.json")


if __name__ == "__main__":
    main()
