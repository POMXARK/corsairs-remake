#!/usr/bin/env python3
"""Pulls the side views of a head to the proportions of the front view before Pixal3D.

Qwen draws the brows, eyes, nose and mouth of the side views 2-4 % of the frame higher than on the front while the
outline (crown, bottom of the neck) is the same, so the model gets two brow lines and paints both. Every view gets a
row profile of darkness along the face (front: the middle of the face, side: a strip behind the profile line), the
features are the dark bands of it. The side profile is matched to the front one by a vertical scale and shift over the
face band; outside the band the mapping goes linearly back to the crown and the neck, so the outline and therefore
the crop of ImageCropToMask stay as they were.

usage: python align_views.py front.png side.png left|right|back out.png [--width ref.png] [--check check.png]
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


def ears(a, m, box):
    """Top and bottom of the ears in parts of the outline height, the mean of both sides.

    Top: the first row from the upper quarter where the edge of the outline turns from hair to skin. Bottom: the
    largest jump of the edge inwards below it (under the lobe the outline goes back to the jaw or the neck)."""
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    res = []
    for side in (0, 1):
        edge, skin = np.zeros(N), np.zeros(N, bool)
        for i, y in enumerate(np.linspace(y0, y1, N).astype(int)):
            xs = np.nonzero(m[y])[0]
            if not len(xs):
                continue
            e = xs.min() if side == 0 else xs.max()
            edge[i] = e - x0 if side == 0 else x1 - e
            k = int(0.015 * w)
            c = a[y, e + k:e + 3 * k].mean(0) if side == 0 else a[y, e - 3 * k:e - k].mean(0)
            skin[i] = c.mean() > 70 and c[0] - c[2] > 20
        i0 = int(0.25 * N) + int(np.argmax(skin[int(0.25 * N):int(0.6 * N)]))
        d = np.diff(gaussian_filter1d(edge, 1))
        lo, hi = i0 + int(0.03 * N), i0 + int(0.2 * N)
        i1 = lo + int(np.argmax(d[lo:hi]))
        res.append((i0 / N, i1 / N))
    return np.mean(res, axis=0)


def widths(m, box):
    x0, y0, x1, y1 = box
    w = np.zeros(N)
    for i, y in enumerate(np.linspace(y0, y1, N).astype(int)):
        xs = np.nonzero(m[y])[0]
        if len(xs):
            w[i] = xs.max() - xs.min()
    return w


def stretch_x(res, m, ref):
    """Horizontal scale about the centre of the outline so that its row widths match the reference view (the back to
    the front, one side to the other). The height is larger than the width, so the square crop does not change."""
    rm = binary_fill_holes(ref.max(2) > 8)
    ys, xs = np.nonzero(rm)
    wr = widths(rm, (xs.min(), ys.min(), xs.max(), ys.max()))
    ys, xs = np.nonzero(m)
    box = (xs.min(), ys.min(), xs.max(), ys.max())
    ws = widths(m, box)
    sel = slice(int(0.1 * N), int(0.9 * N))
    ok = (wr[sel] > 0) & (ws[sel] > 0)
    s = float(np.median(wr[sel][ok] / ws[sel][ok]))
    cx = (box[0] + box[2]) / 2
    src = cx + (np.arange(res.shape[1], dtype=np.float32) - cx) / s
    j0 = np.clip(np.floor(src).astype(int), 0, res.shape[1] - 1)
    j1 = np.clip(j0 + 1, 0, res.shape[1] - 1)
    k = (src - np.floor(src))[None, :, None]
    out = res[:, j0] * (1 - k) + res[:, j1] * k
    out[:, (src < 0) | (src > res.shape[1] - 1)] = 0
    return out, s


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
    ap.add_argument("facing", choices=("left", "right", "back"))
    ap.add_argument("out")
    ap.add_argument("--check")
    ap.add_argument("--width", help="match the row widths of the outline to this view (the back to the front, "
                                    "the right side to the aligned left one)")
    o = ap.parse_args()
    fa, fm, fbox = load(o.front)
    sa, sm, sbox = load(o.side)
    if o.facing == "back":  # no face on the back: the ears are the only common marks
        ef, es = ears(fa, fm, fbox), ears(sa, sm, sbox)
        tf, ts = np.array([0.0, *ef, 1.0]), np.array([0.0, *es, 1.0])
        h = (sbox[3] - sbox[1]) / sa.shape[0] * 1024
        print(f"{o.side}: ears {es[0]:.3f}..{es[1]:.3f}, front {ef[0]:.3f}..{ef[1]:.3f}; "
              f"top moved {(ef[0] - es[0]) * h:+.0f} px, bottom {(ef[1] - es[1]) * h:+.0f} px of 1024")
    else:
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
    if o.width:
        res, sx = stretch_x(res, binary_fill_holes(res[..., :3].max(2) > 8),
                            np.asarray(Image.open(o.width).convert("RGB")))
        print(f"{o.side}: width x{sx:.3f} to {o.width}")
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8)).save(o.out)
    if o.facing != "back":
        shift = [(BAND[j] - ((BAND[j] - b) / a)) * (y1 - y0) / sa.shape[0] * 1024 for j in (0, 1)]
        print(f"{o.side}: scale {a:.3f}, shift {b:+.3f}; brows moved {shift[0]:+.0f} px, mouth {shift[1]:+.0f} px "
              f"of 1024; match {corr(f, s, 1, 0):.2f} -> {c:.2f}")
    if o.check:
        check(Image.open(o.front).convert("RGB"), Image.open(o.out).convert("RGB"), o.check, ("front", o.facing + " aligned"))


if __name__ == "__main__":
    main()
