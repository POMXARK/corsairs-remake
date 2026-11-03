#!/usr/bin/env python3
"""Mix the realistic texture into the generated one by how well they agree: <trellis.glb> <painted.glb> <dst.glb> [--max 0.6] [--tau 30] [--sigma 6].
Both files share the UV (painted = pdm_project_views.py of the same mesh). Per texel the blurred colours are compared:
match = exp(-(d/tau)^2), d = mean abs difference of the 0..255 channels. The result is trellis*(1-a) + painted*a, a = max*match:
where the generated texture roughly agrees with the views the detail of the views is added, where it does not (a hallucinated or
misregistered area) the generated colour stays. Also writes <dst>_match.png (the match map). pip: numpy Pillow opencv-python."""
import io
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from pdm_project_views import read_glb, write_glb  # noqa: E402


def opt(name, default):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def atlas_of(j, b):
    prim = j["meshes"][0]["primitives"][0]
    mat = j["materials"][prim.get("material", 0)]
    img = j["images"][j["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]
    bv = j["bufferViews"][img["bufferView"]]
    o = bv.get("byteOffset", 0)
    return img, np.asarray(Image.open(io.BytesIO(b[o:o + bv["byteLength"]])).convert("RGB"))


def main():
    src, painted, dst = [a for a in sys.argv[1:] if not a.startswith("--")][:3]
    amax, tau, sigma = opt("--max", 0.6), opt("--tau", 30.0), opt("--sigma", 6.0)
    jt, bt = read_glb(src)
    jp, bp = read_glb(painted)
    _, T = atlas_of(jt, bt)
    img, P = atlas_of(jp, bp)
    if T.shape != P.shape:
        T = cv2.resize(T, (P.shape[1], P.shape[0]), interpolation=cv2.INTER_CUBIC)
    T, P = T.astype(np.float32), P.astype(np.float32)
    d = np.abs(cv2.GaussianBlur(T, (0, 0), sigma) - cv2.GaussianBlur(P, (0, 0), sigma)).mean(2)
    match = np.exp(-(d / tau) ** 2)
    changed = np.abs(T - P).sum(2) > 1  # texels the views repainted; the rest of the atlas is already the generated colour
    a = (amax * match * changed)[..., None]
    out = np.clip(T * (1 - a) + P * a, 0, 255).astype(np.uint8)
    n = changed.sum()
    print(f"repainted texels {n} ({100 * n / changed.size:.0f} % of the atlas); agreement: mean {match[changed].mean():.2f}, "
          f"> 0.5 in {100 * (match[changed] > 0.5).mean():.0f} %, < 0.1 in {100 * (match[changed] < 0.1).mean():.0f} %")
    Image.fromarray((match * changed * 255).astype(np.uint8)).save(dst.rsplit(".", 1)[0] + "_match.png")
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, "PNG")
    png = buf.getvalue()
    b = bytearray(bp)
    b += b"\0" * (-len(b) % 4)
    jp["bufferViews"].append({"buffer": 0, "byteOffset": len(b), "byteLength": len(png)})
    b += png
    img["bufferView"] = len(jp["bufferViews"]) - 1
    img["mimeType"] = "image/png"
    jp["buffers"][0]["byteLength"] = len(b)
    write_glb(dst, jp, bytes(b))
    print(dst, "written")


if __name__ == "__main__":
    main()
