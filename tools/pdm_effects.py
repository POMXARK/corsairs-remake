#!/usr/bin/env python3
"""The effects of the original game: converts the textures of fire, smoke, flares, fountains and the flying pieces of
EXPLOSION_X (particle0..4.cff) into the resource tree of pdm-game. The behaviour of the effects sits in the code of the
original modules (EXPLOSION_X.dll, Smoke.dll, FIRE*.dll ...), it is not in the data, so only the pictures come from here.
The sprite atlas of the particle service (particles_list, 4x4 cells like fire.tf of the original) gets rows 0..2 of
fire.tf (flame, burst, smoke: the 12 frames EXPLOSION_X plays through the life of a sprite); the row of sparks stays from the particles demo.
usage: pdm_effects.py <original game dir> <resource dir>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "particles"))
import numpy as np  # noqa: E402
import make_particles  # noqa: E402
import tf2tx  # noqa: E402
from PIL import Image  # noqa: E402
from pdm2storm import convert_model, convert_texture  # noqa: E402

TEXTURES = ["fire", "fire1", "fire2", "fire3", "fire4", "fire_fort", "fakel_fire", "smoke", "smoke_n", "cannonball",
            "fountan", "spl_rain", "lensflare0", "lensflare1", "lensflare2", "lensflare3"]
PIECES = [f"particle{i}" for i in range(5)]


def patch_atlas(game, res):
    """fire.tf: row 0 flames, row 1 the burst with sparks, row 2 grey smoke that thins out, row 3 empty."""
    fire = tf2tx.tf_image(game / "TEXTURES" / "fire.tf")
    # the original draws these on black with a sum of colours; the alpha of a pixel is its brightest channel, the colour what is left
    px = np.asarray(fire.convert("RGB"), dtype=np.float64) / 255
    alpha = px.max(axis=2)
    # the colour comes from the brightness (the sum of colours of the original goes from orange to white-hot); the smoke row stays grey
    heat = np.clip(alpha * 2.2, 0, 1)[..., None]
    flame = np.array([1.0, 0.55, 0.15]) * (1 - heat) + np.array([1.0, 0.97, 0.8]) * heat
    smoke = np.array([0.93, 0.93, 0.91])
    rows = np.arange(px.shape[0])[:, None, None] // (px.shape[0] // 4)
    rgb = np.where(rows == 2, smoke, flame)
    fire = Image.fromarray((np.dstack([rgb, np.clip(alpha * 1.6, 0, 1)]) * 255).astype(np.uint8), "RGBA")
    cell = fire.width // 4
    atlas = make_particles.atlas()
    for row, src in ((0, 0), (1, 1), (2, 2)):
        strip = fire.crop((0, src * cell, fire.width, (src + 1) * cell)).resize((make_particles.ATLAS, make_particles.CELL), Image.LANCZOS)
        atlas.paste(strip, (0, row * make_particles.CELL))
    # a flying piece of a hull: a hard-edged dark square (column 1 of the row of sparks)
    cs = make_particles.CELL
    block = np.zeros((cs, cs, 4), dtype=np.uint8)
    m = cs // 5
    block[m:cs - m, m:cs - m] = (255, 255, 255, 255)
    atlas.paste(Image.fromarray(block, "RGBA"), (cs, 3 * cs))
    # a splinter (a thin long slat) and a plank (a short wide one): they tumble when they spin
    sliver = np.zeros((cs, cs, 4), dtype=np.uint8)
    sliver[cs // 12:cs - cs // 12, cs * 5 // 12:cs * 7 // 12] = (255, 255, 255, 255)
    atlas.paste(Image.fromarray(sliver, "RGBA"), (2 * cs, 3 * cs))
    plank = np.zeros((cs, cs, 4), dtype=np.uint8)
    plank[cs * 3 // 10:cs * 7 // 10, cs // 8:cs - cs // 8] = (255, 255, 255, 255)
    atlas.paste(Image.fromarray(plank, "RGBA"), (3 * cs, 3 * cs))
    make_particles.write_tx(atlas, res / "textures" / "particles_list.tga.tx")


def main(game, res):
    game, res = Path(game) / "RESOURCE", Path(res)
    (res / "textures" / "effects").mkdir(parents=True, exist_ok=True)
    (res / "models" / "effects").mkdir(parents=True, exist_ok=True)
    done = 0
    for name in TEXTURES:
        src = game / "TEXTURES" / f"{name}.tf"
        if src.exists():
            convert_texture(src, res / "textures" / "effects" / f"{name}.tx")
            done += 1
    for name in PIECES:
        src = next((p for p in (game / "MODELS").glob("*") if p.stem.lower() == name and p.suffix.lower() == ".cff"), None)
        if src:
            convert_model(src, res / "models" / "effects" / f"{name}.gm")
            done += 1
    patch_atlas(game, res)
    print(f"{done} effect files")


if __name__ == "__main__":
    main(*sys.argv[1:3])
