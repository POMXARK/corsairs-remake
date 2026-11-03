#!/usr/bin/env python3
"""Pulls the side views of a head to the proportions of the front view before Pixal3D.

Qwen draws the brows, eyes, nose and mouth of the side views 2-4 % of the frame higher than on the front while the
outline (crown, bottom of the neck) is the same, so the model gets two brow lines and paints both. Every view gets a
row profile of darkness along the face (front: the middle of the face, side: a strip behind the profile line), the
features are the dark bands of it. The side profile is matched to the front one by a vertical scale and shift over the
face band; outside the band the mapping goes linearly back to the crown and the neck, so the outline and therefore
the crop of ImageCropToMask stay as they were.

usage: python align_views.py front.png side.png left|right out.png [--check check.png]
"""
import argparse

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_fill_holes, gaussian_filter1d

BAND = (0.30, 0.70)  # the face band in parts of the outline height: brows .. mouth
N = 1024  # samples of the profile over the outline height


def load(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    m = binary_fill_holes(a.max(2) > 8)
    ys, xs = np.nonzero(m)
    return a, m, (xs.min(), ys.min(), xs.max(), ys.max())


def profile(a, m, box, facing):
    x0, y0, x1, y1 = box
    w = x1 - x0
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    rows = np.linspace(y0, y1, N).astype(int)
    p = np.zeros(N, np.float32)
    for i, y in enumerate(rows):
        xs = np.nonzero(m[y])[0]
        if not len(xs):
            continue
        if facing == "front":
            c = (x0 + x1) / 2
            lo, hi = c - 0.2 * w, c + 0.2 * w
        elif facing == "left":  # the face looks to the left of the picture
            lo, hi = xs.min() + 0.03 * w, xs.min() + 0.25 * w
        else:
            lo, hi = xs.max() - 0.25 * w, xs.max() - 0.03 * w
        sel = xs[(xs >= lo) & (xs <= hi)]
        if len(sel):
            p[i] = 255 - lum[y, sel].mean()
    p = gaussian_filter1d(p, 2)
    return p - gaussian_filter1d(p, 25)  # the bands only, not the overall light of the view


def corr(f, s, a, b):
    t = np.linspace(BAND[0], BAND[1], 400)
    vf = np.interp(t, np.linspace(0, 1, N), f)
    vs = np.interp((t - b) / a, np.linspace(0, 1, N), s)
    vf, vs = vf - vf.mean(), vs - vs.mean()
    return float((vf * vs).sum() / (np.linalg.norm(vf) * np.linalg.norm(vs) + 1e-9))


def check(front, side, out, labels):
    strips = []
    for img, lab in zip((front, side), labels):
        a = np.asarray(img)
        m = a.max(2) > 8
        ys, xs = np.nonzero(m)
        y0, y1 = ys.min(), ys.max()
        h = y1 - y0
        s = img.crop((0, int(y0 + 0.25 * h), img.width, int(y0 + 0.75 * h))).resize((800, int(800 * 0.5 * h / img.width)))
        d = ImageDraw.Draw(s)
        for k in range(0, s.height, 20):
            d.line([(0, k), (800, k)], fill=(255, 0, 0) if k % 100 == 0 else (90, 0, 0))
        d.text((5, 5), lab, fill=(255, 255, 0))
        strips.append(s)
    o = Image.new("RGB", (800, sum(s.height for s in strips)))
    y = 0
    for s in strips:
        o.paste(s, (0, y))
        y += s.height
    o.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("front")
    ap.add_argument("side")
    ap.add_argument("facing", choices=("left", "right"))
    ap.add_argument("out")
    ap.add_argument("--check")
    o = ap.parse_args()
    fa, fm, fbox = load(o.front)
    sa, sm, sbox = load(o.side)
    f = profile(fa, fm, fbox, "front")
    s = profile(sa, sm, sbox, o.facing)
    best = max(((corr(f, s, a, b), a, b) for a in np.arange(0.90, 1.12, 0.005) for b in np.arange(-0.08, 0.08, 0.001)))
    c, a, b = best
    # side row for every output row: identity at the crown and the neck, the fitted affine over the face band
    tf = np.array([0.0, BAND[0], BAND[1], 1.0])
    ts = np.array([0.0, (BAND[0] - b) / a, (BAND[1] - b) / a, 1.0])
    y0, y1 = sbox[1], sbox[3]
    rows = np.arange(sa.shape[0], dtype=np.float32)
    t = (rows - y0) / (y1 - y0)
    inside = (t >= 0) & (t <= 1)
    src = rows.copy()
    src[inside] = y0 + np.interp(t[inside], tf, ts) * (y1 - y0)
    i0 = np.clip(np.floor(src).astype(int), 0, sa.shape[0] - 1)
    i1 = np.clip(i0 + 1, 0, sa.shape[0] - 1)
    k = (src - np.floor(src))[:, None, None]
    im = Image.open(o.side)
    raw = np.asarray(im.convert("RGBA") if im.mode == "RGBA" else im.convert("RGB")).astype(np.float32)
    res = raw[i0] * (1 - k) + raw[i1] * k
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8)).save(o.out)
    shift = [(BAND[j] - ((BAND[j] - b) / a)) * (y1 - y0) / sa.shape[0] * 1024 for j in (0, 1)]
    print(f"{o.side}: scale {a:.3f}, shift {b:+.3f}; brows moved {shift[0]:+.0f} px, mouth {shift[1]:+.0f} px of 1024; "
          f"match {corr(f, s, 1, 0):.2f} -> {c:.2f}")
    if o.check:
        check(Image.open(o.front).convert("RGB"), Image.open(o.out).convert("RGB"), o.check, ("front", o.facing + " aligned"))


if __name__ == "__main__":
    main()
