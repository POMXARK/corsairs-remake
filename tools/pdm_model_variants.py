#!/usr/bin/env python3
"""Makes several variants of one model with comfy_model_batch.py and a picture to compare them by
(docs/ai-models.md, ours): different seeds, qualities and workflows (Pixal3D, TRELLIS.2, Hunyuan3D, ...).

A variant is TAG=WORKFLOW[,QUALITY[,SEED]], the GLB is data/ai_models/glb/<name>_<TAG>.glb. A variant that
exists is skipped, so the run goes on after a stop. Without --variant the matrix is: seeds 1-3 of the workflow
tools/model3d/image_to_model_api.json, and TRELLIS.2 (tools/model3d/image_to_model_trellis_api.json, made by
`pdm_comfy_api.py <single-image template> --trellis --out ...`) if that file is there.
When Blender is found (--blender, or `blender` in PATH) pdm_glb_preview.py draws every variant into
data/ai_models/compare/<name>.png.

usage: pdm_model_variants.py <game dir> <name> [--variant TAG=WORKFLOW[,QUALITY[,SEED]] ...] [--views DIR]
         [--comfy URL] [--blender PATH] [--no-preview]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MODEL3D = TOOLS / "model3d"


def default_variants():
    main = MODEL3D / "image_to_model_api.json"
    out = [(f"seed{s}", main, "normal", s) for s in (1, 2, 3)]
    trellis = MODEL3D / "image_to_model_trellis_api.json"
    if trellis.exists():
        out.append(("trellis", trellis, "normal", 1))
    return out


def parse(item):
    try:
        tag, rest = item.split("=", 1)
        wf, *more = rest.split(",")
        return tag, Path(wf), more[0] if more else "normal", int(more[1]) if len(more) > 1 else 1
    except ValueError:
        sys.exit(f"pdm_model_variants: a variant is TAG=WORKFLOW[,QUALITY[,SEED]], not {item}")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("name")
    ap.add_argument("--variant", action="append", default=[])
    ap.add_argument("--views", type=Path)
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--blender", default=shutil.which("blender"))
    ap.add_argument("--no-preview", action="store_true")
    a = ap.parse_args()
    variants = [parse(v) for v in a.variant] or default_variants()
    glb = a.game / "data" / "ai_models" / "glb"
    for tag, wf, quality, seed in variants:
        if not wf.exists():
            print(f"pdm_model_variants: {tag}: no {wf}, skipped")
            continue
        cmd = [sys.executable, str(TOOLS / "comfy_model_batch.py"), str(a.game), "--only", a.name, "--workflow",
               str(wf), "--quality", quality, "--seed", str(seed), "--tag", tag, "--comfy", a.comfy]
        if a.views:
            cmd += ["--views", str(a.views)]
        print(f"pdm_model_variants: {tag} ({wf.name}, {quality}, seed {seed})", flush=True)
        if subprocess.run(cmd).returncode != 0:
            print(f"pdm_model_variants: {tag} failed, going on", flush=True)
    files = sorted(glb.glob(f"{a.name}_*.glb"))
    print("pdm_model_variants: " + (", ".join(f.name for f in files) or "no GLB"))
    if a.no_preview or not files:
        return
    if not a.blender:
        print("pdm_model_variants: no Blender (--blender C:\\...\\blender.exe): the picture is not made")
        return
    sheet = a.game / "data" / "ai_models" / "compare" / f"{a.name}.png"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([a.blender, "-b", "-P", str(TOOLS / "pdm_glb_preview.py"), "--", "--out", str(sheet),
                    *map(str, files)])
    print(f"pdm_model_variants: {sheet}")


if __name__ == "__main__":
    main()
