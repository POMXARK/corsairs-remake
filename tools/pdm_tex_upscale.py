#!/usr/bin/env python3
"""Makes the textures of a model sharper and bigger and leaves its mesh alone (docs/ai-models-textures.md, ours).

The textures of the original are 64..256 pixels; the UV of the mesh does not depend on the size, so a texture of
1024 pixels goes in place of the old one with the same name, the .gm stays what it was. An image model of ComfyUI
(Real-ESRGAN x4plus, BSD-3-Clause; 4x-UltraSharp is CC BY-NC-SA: the nodes Load Upscale Model and Upscale Image (using Model) of the core) draws the new
colours, the alpha channel is scaled by Lanczos; --method lanczos needs no ComfyUI (a sharpened Lanczos: it stays soft, the detail is not there; Real-ESRGAN draws it
result).

Every texture is taken from its original: the first run copies it to <game>/data/ai_models/tex_orig, a run
again (another --scale, another model) starts from that copy and not from the result of the last run. --restore
puts the originals back. The textures are shared: hero1 uses hero_head, hero_hvostik and hero_new_hand of hero
too, so they change in both models.

usage: pdm_tex_upscale.py <game dir> <model> ... [--scale 4] [--max 1024] [--method esrgan|lanczos]
         [--upscaler RealESRGAN_x4plus.pth] [--comfy http://127.0.0.1:8188]
         [--depth 0.4] [--only-tex hero_body ...] [--skip-tex hero_head ...] [--restore]
"""
import argparse
import io
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageFilter

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "engine" / "demos" / "common"))
from pdm_model_views import find_model, read_gm, texture_index, texture_of  # noqa: E402
from storm_formats import read_tx, write_tx  # noqa: E402

UPSCALER = "RealESRGAN_x4plus.pth"


def graph_of(image: str, upscaler: str):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image}, "_meta": {"title": "IMAGE"}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": upscaler}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "pdm_tex"},
              "_meta": {"title": "SAVE"}},
    }


def by_model(comfy, rgb: Image.Image, name: str, upscaler: str, work: Path) -> Image.Image:
    """The picture through the upscale model of ComfyUI, as big as the model makes it (4x)."""
    png = work / f"{name}.png"
    work.mkdir(parents=True, exist_ok=True)
    rgb.save(png)
    comfy.upload(png, "pdm_models")
    pid = comfy.queue(graph_of(f"pdm_models/{png.name}", upscaler))
    while (f := comfy.result(pid)) is None:
        time.sleep(0.5)
    out = work / f"{name}_up.png"
    comfy.fetch(f, out)
    return Image.open(out).convert("RGB")


def sharpen(img: Image.Image, size: tuple) -> Image.Image:
    big = img.resize(size, Image.LANCZOS)
    return big.filter(ImageFilter.UnsharpMask(radius=1.6, percent=170, threshold=1))


def cavities(img: Image.Image, depth: float) -> Image.Image:
    """Folds, seams and the gaps of the embroidery darker, the raised places lighter: the engine has no normal maps
    for a model, so the relief is in the colour. A place darker than its surroundings (a blur of 1/24 of the side)
    goes down by depth, a lighter one goes up by half of that."""
    import numpy as np
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    lum = a @ np.array((0.299, 0.587, 0.114), dtype=np.float32)
    near = np.asarray(Image.fromarray(lum.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(max(img.width // 24, 2))), dtype=np.float32)
    d = np.clip((lum - near) / 64.0, -1.0, 1.0)  # < 0 a hollow, > 0 a ridge
    k = 1.0 + depth * np.where(d < 0, d, d * 0.5)
    return Image.fromarray(np.clip(a * k[..., None], 0, 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--scale", type=int, default=4, help="times bigger")
    ap.add_argument("--max", type=int, default=1024, help="the side of a texture is not bigger than this")
    ap.add_argument("--method", choices=("esrgan", "lanczos"), default="esrgan")
    ap.add_argument("--upscaler", default=UPSCALER, help="the file of models/upscale_models of ComfyUI")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--depth", type=float, default=0.0, help="0..1: the folds and the seams darker (cavities), 0.4 is a start")
    ap.add_argument("--only-tex", nargs="*", default=[], help="the textures that are changed (without .tga)")
    ap.add_argument("--skip-tex", nargs="*", default=[], help="the textures that stay (the head that is made of 3D)")
    ap.add_argument("--restore", action="store_true", help="the originals back")
    a = ap.parse_args()

    index = texture_index(a.game)
    orig = a.game / "data" / "ai_models" / "tex_orig"
    work = a.game / "data" / "ai_models" / "tex_work"
    stems = {}  # texture file of the game -> its name
    for model in a.models:
        gm = read_gm(find_model(a.game, model))
        for name in sorted({o[1] for o in gm["objects"] if o[1]}):
            path = texture_of(index, name)
            short = Path(name.replace("\\", "/")).name.lower()
            short = short[:-4] if short.endswith(".tga") else short
            if not path:
                print(f"pdm_tex_upscale: no texture {name}")
            elif (not a.only_tex or short in a.only_tex) and short not in a.skip_tex:
                stems[path] = short
    if not stems:
        sys.exit("pdm_tex_upscale: no textures")

    comfy = None
    if a.method == "esrgan" and not a.restore:
        from comfy_view_refine import ComfyImage  # noqa: E402
        comfy = ComfyImage(a.comfy)
    for path, short in stems.items():
        saved = orig / path.name
        if a.restore:
            if saved.exists():
                shutil.copy2(saved, path)
                print(f"{path.name}: restored")
            continue
        if not saved.exists():
            orig.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
        src = read_tx(saved)
        k = min(a.scale, a.max // max(src.size))
        size = (src.width * k, src.height * k)
        if k <= 1:
            print(f"{path.name}: {src.width} px stays")
            continue
        rgb = src.convert("RGB")
        if comfy is not None:
            new = by_model(comfy, rgb, short, a.upscaler, work).resize(size, Image.LANCZOS)
        else:
            new = sharpen(rgb, size)
        if a.depth:
            new = cavities(new, a.depth)
        alpha = src.getchannel("A").resize(size, Image.LANCZOS)
        new = new.convert("RGBA")
        new.putalpha(alpha)
        write_tx(new, path)
        print(f"{path.name}: {src.width} -> {size[0]} px ({a.method})")


if __name__ == "__main__":
    main()
