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
from scipy.ndimage import binary_fill_holes, gaussian_filter1d, median_filter

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
        if not skin[int(0.25 * N):int(0.6 * N)].any():
            return None  # ears under the hair or not skin-coloured
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


def neck(m, box):
    """The narrowest place of the neck and its cut (the last row still as wide as the neck: below it only the tail)."""
    w = widths(m, box)
    i = int(0.65 * N) + int(np.argmin(w[int(0.65 * N):int(0.9 * N)]))
    wide = np.nonzero(w[i:] > 0.8 * w[i])[0]
    return i / N, (i + wide.max()) / N


def edges(m):
    """Outer left and right edge of the outline for every row, smoothed over the rows (stray hairs), -1 for none."""
    l, r = np.full(m.shape[0], -1.0), np.full(m.shape[0], -1.0)
    rows = np.nonzero(m.any(1))[0]
    l[rows] = m[rows].argmax(1)
    r[rows] = m.shape[1] - 1 - m[rows, ::-1].argmax(1)
    for e in (l, r):
        e[rows] = median_filter(e[rows], 41)
    return l, r


def stretch_x(res, m, ref):
    """Every row is stretched from the edges of its own outline to the mirrored edges of the reference row at the same
    height: the back seen from behind and the front have one outline, mirrored, the left and the right side too."""
    rm = binary_fill_holes(ref.max(2) > 8)
    ry = np.nonzero(rm.any(1))[0]
    sy = np.nonzero(m.any(1))[0]
    rl, rr = edges(rm)
    sl, sr = edges(m)
    W = res.shape[1]
    out = res.copy()
    x = np.arange(W, dtype=np.float32)
    yr = np.round(ry[0] + (sy - sy[0]) / (sy[-1] - sy[0]) * (ry[-1] - ry[0])).astype(int)
    L, R = W - 1 - rr[yr], W - 1 - rl[yr]
    ws, wr = sr[sy] - sl[sy], R - L
    # scale and shift of every row, smooth over the height: row by row they jump on stray hairs and wave the strands;
    # where the outline is narrow (the crown, the tail tip) the edges say little and the scale of the neighbours is kept
    ok = (rl[yr] >= 0) & (ws > 0.5 * ws.max()) & (wr > 0.5 * wr.max())
    idx = np.arange(len(sy))
    s = np.interp(idx, idx[ok], ws[ok] / wr[ok])
    cr = np.interp(idx, idx[ok], ((L + R) / 2)[ok])
    cs = np.interp(idx, idx[ok], ((sl[sy] + sr[sy]) / 2)[ok])
    s, cr, cs = (gaussian_filter1d(v, 60) for v in (s, cr, cs))
    diff = np.abs(np.r_[sl[sy] - L, sr[sy] - R][np.r_[ok, ok]])
    for i, y in enumerate(sy):
        src = cs[i] + (x - cr[i]) * s[i]
        j0 = np.clip(np.floor(src).astype(int), 0, W - 1)
        k = (src - np.floor(src))[:, None]
        row = res[y, j0] * (1 - k) + res[y, np.clip(j0 + 1, 0, W - 1)] * k
        row[(src < 0) | (src > W - 1)] = 0
        out[y] = row
    return out, float(np.mean(diff)) / W * 1024


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
        if ef is None or es is None or abs(ef[0] - es[0]) > 0.08 or abs(ef[1] - es[1]) > 0.08:
            print(f"{o.side}: ears not found or too far from the front ({ef}, {es}), height left as it is")
            ef = es = np.array(BAND)
        # the neck: its narrowest place and its cut; the tail below the cut of the back goes out of the frame
        nf, ns = neck(fm, fbox), neck(sm, sbox)
        if not (ef[1] < nf[0] < nf[1] and es[1] < ns[0] < ns[1]):
            nf = ns = (1.0, 1.0)
        tf, ts = np.array([0.0, *ef, *nf]), np.array([0.0, *es, *ns])
        tf, ts = np.append(tf, 1.0), np.append(ts, ts[-1] + 1.0 - tf[-1])
        keep = np.r_[True, np.diff(tf) > 1e-6]
        tf, ts = tf[keep], ts[keep]
        h = (sbox[3] - sbox[1]) / sa.shape[0] * 1024
        print(f"{o.side}: ears {es[0]:.3f}..{es[1]:.3f}, front {ef[0]:.3f}..{ef[1]:.3f}; "
              f"top moved {(ef[0] - es[0]) * h:+.0f} px, bottom {(ef[1] - es[1]) * h:+.0f} px of 1024; "
              f"neck {ns[0]:.3f}..{ns[1]:.3f}, front {nf[0]:.3f}..{nf[1]:.3f}")
    else:
        f = profile(fa, fm, fbox, "front")
        fits = {}
        for facing in ("left", "right"):  # the face side is found by itself, the argument only tells it is a side
            p = profile(sa, sm, sbox, facing)
            fits[facing] = (max((corr(f, p, a, b), a, b) for a in np.arange(0.90, 1.12, 0.005)
                                for b in np.arange(-0.08, 0.08, 0.001)), p)
        facing = max(fits, key=lambda k: fits[k][0][0])
        if facing != o.facing:
            print(f"{o.side}: the face looks {facing}, not {o.facing} ({fits[facing][0][0]:.2f} > {fits[o.facing][0][0]:.2f})")
        (c, a, b), s = fits[facing]
        if c < 0.3 or c - corr(f, s, 1, 0) < 0.1:  # the bands do not match: a wrong facing or another head
            print(f"{o.side}: face bands not matched (match {c:.2f}), height left as it is")
            a, b = 1.0, 0.0
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
        res, dx = stretch_x(res, binary_fill_holes(res[..., :3].max(2) > 8),
                            np.asarray(Image.open(o.width).convert("RGB")))
        print(f"{o.side}: outline edges moved {dx:.1f} px of 1024 on average to the mirrored {o.width}")
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8)).save(o.out)
    if o.facing != "back":
        shift = [(BAND[j] - ((BAND[j] - b) / a)) * (y1 - y0) / sa.shape[0] * 1024 for j in (0, 1)]
        print(f"{o.side}: scale {a:.3f}, shift {b:+.3f}; brows moved {shift[0]:+.0f} px, mouth {shift[1]:+.0f} px "
              f"of 1024; match {corr(f, s, 1, 0):.2f} -> {c:.2f}")
    if o.check:
        check(Image.open(o.front).convert("RGB"), Image.open(o.out).convert("RGB"), o.check, ("front", o.facing + " aligned"))


if __name__ == "__main__":
    main()
