#!/usr/bin/env python3
"""The models and textures of the NPCs and the hero for looking at and replacing by hand (Blender and the like), ours.

  export  <game dir> <folder> [<name> ...]   every character .gm of resource/models/characters as <folder>/models/<name>.glb
                                             (the low-poly original with its texture and UVs) and its textures as
                                             <folder>/textures/<texture>.png; <folder>/manifest.json remembers the files as exported
  apply   <game dir> <folder> [<name> ...]   what differs from the export (or is new) goes into the game:
                                             a changed models/<name>.glb through pdm_glb2gm.py (scaled to the height of the original, stood
                                             where it stood, bound to the skeleton and the animations of the original, its base colour
                                             becomes textures/characters/ai_<name>.tga.tx); a changed textures/<texture>.png is written over
                                             the texture of the game (power-of-two sides). --force takes every file, --tex N the largest side
                                             of a model's texture (1024)
  restore <game dir> [<name> ...]            the originals back (every replaced model and texture without names)
  list    <game dir>                         the names

The <folder> can be anywhere (another disk, a sync folder): the game reads nothing from it, apply copies. The originals are kept once in
<game dir>/data/ai_models/orig (models) and orig_tex (textures), and are what every run fits to, so a repeat gives the same result.
Run run.sh/run.ps1 after apply as always; a reconversion of the characters (pdm_character.py all) writes the originals over the
replacements, apply again then.

usage: pdm_chars_blender.py export|apply|restore|list <game dir> [<folder>] [<name> ...] [--force] [--tex 1024]
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "engine" / "demos" / "common"))
from pdm_gm2glb import build  # noqa: E402
from pdm_model_views import read_gm, read_tx, texture_index, texture_of  # noqa: E402
from storm_formats import write_tx  # noqa: E402

MANIFEST = "manifest.json"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def models_of(game: Path, names):
    folder = game / "resource" / "models" / "characters"
    every = {p.stem: p for p in sorted(folder.glob("*.gm"))}
    if not names:
        return every
    missing = [n for n in names if n not in every]
    if missing:
        sys.exit(f"pdm_chars_blender: no character {', '.join(missing)} (list shows the names)")
    return {n: every[n] for n in names}


def orig_tex(game: Path, tx: Path) -> Path:
    return game / "data" / "ai_models" / "orig_tex" / tx.relative_to(game / "resource" / "textures")


def export(game: Path, folder: Path, names):
    index = texture_index(game)
    (folder / "models").mkdir(parents=True, exist_ok=True)
    (folder / "textures").mkdir(parents=True, exist_ok=True)
    manifest = {"models": {}, "textures": {}}
    for name, path in models_of(game, names).items():
        # a replaced model is exported from its original, so the folder always holds the game's own models
        orig = game / "data" / "ai_models" / "orig" / path.relative_to(game / "resource" / "models")
        gm = read_gm(orig if orig.exists() else path)
        out = folder / "models" / f"{name}.glb"
        out.write_bytes(build(gm, index))
        manifest["models"][name] = md5(out)
        for tex in {o[1] for o in gm["objects"] if o[1]}:
            tx = texture_of(index, tex)
            if tx is None:
                continue
            png = folder / "textures" / (tx.name[:-3].rsplit(".", 1)[0] + ".png")
            src = orig_tex(game, tx)
            Image.fromarray(np.asarray(read_tx(src if src.exists() else tx), np.uint8)).convert("RGBA").save(png)
            manifest["textures"][png.name] = md5(png)
        print(f"{name}: {out}", flush=True)
    old = folder / MANIFEST
    if old.exists() and names:  # a partial export keeps what the earlier ones wrote
        before = json.loads(old.read_text())
        for kind in manifest:
            before[kind].update(manifest[kind])
        manifest = before
    old.write_text(json.dumps(manifest, indent=1))
    print(f"pdm_chars_blender: {len(manifest['models'])} models, {len(manifest['textures'])} textures in {folder}")


def textures_of(game: Path, names):
    """The png names of the textures of the named characters."""
    index = texture_index(game)
    out = set()
    for path in models_of(game, names).values():
        for o in read_gm(path)["objects"]:
            tx = texture_of(index, o[1])
            if tx is not None:
                out.add(tx.name[:-3].rsplit(".", 1)[0] + ".png")
    return out


def changed(folder: Path, kind: str, ext: str, names, force):
    seen = json.loads((folder / MANIFEST).read_text())[kind] if (folder / MANIFEST).exists() else {}
    out = []
    for path in sorted((folder / kind).glob(f"*{ext}")):
        if names and (path.stem if kind == "models" else path.name) not in names:
            continue
        key = path.stem if kind == "models" else path.name
        if force or seen.get(key) != md5(path):
            out.append(path)
    return out


def apply(game: Path, folder: Path, names, force, tex):
    models = changed(folder, "models", ".glb", names, force)
    wanted = textures_of(game, names) if names else None  # before the models: a replaced one names another texture
    known = models_of(game, None)
    for path in models:
        if path.stem not in known:
            sys.exit(f"pdm_chars_blender: {path.name} is no character of the game (list)")
    if models:
        r = subprocess.run([sys.executable, TOOLS / "pdm_glb2gm.py", game, *[p.stem for p in models],
                            "--glb", folder / "models", "--tex", str(tex)])
        if r.returncode:
            sys.exit("pdm_chars_blender: pdm_glb2gm.py failed")
    index = texture_index(game)
    done = 0
    for png in changed(folder, "textures", ".png", wanted, force):
        tx = index.get(png.stem.lower() + ".tga")
        if tx is None:
            print(f"{png.name}: no such texture in the game, left alone")
            continue
        image = Image.open(png).convert("RGBA")
        if image.width & (image.width - 1) or image.height & (image.height - 1):
            sys.exit(f"pdm_chars_blender: {png.name} is {image.width}x{image.height}, the sides must be powers of two")
        keep = orig_tex(game, tx)
        if not keep.exists():
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tx, keep)
        write_tx(image, tx)
        print(f"{png.name}: {tx.name} replaced ({image.width}x{image.height})")
        done += 1
    print(f"pdm_chars_blender: {len(models)} models, {done} textures put into {game}")


def restore(game: Path, names):
    for name in names or models_of(game, None):
        subprocess.run([sys.executable, TOOLS / "pdm_glb2gm.py", game, name, "--restore"], check=True)
    keep = game / "data" / "ai_models" / "orig_tex"
    for orig in sorted(keep.rglob("*.tx")) if keep.exists() else []:
        shutil.copy2(orig, game / "resource" / "textures" / orig.relative_to(keep))
        print(f"{orig.name}: the original is back")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("command", choices=("export", "apply", "restore", "list"))
    ap.add_argument("game", type=Path)
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tex", type=int, default=1024)
    a = ap.parse_args()
    if a.command == "list":
        print("\n".join(models_of(a.game, None)))
    elif a.command == "restore":
        restore(a.game, a.rest)
    else:
        if not a.rest:
            sys.exit("pdm_chars_blender: the folder is missing")
        folder, names = Path(a.rest[0]), a.rest[1:]
        export(a.game, folder, names) if a.command == "export" else apply(a.game, folder, names, a.force, a.tex)


if __name__ == "__main__":
    main()
