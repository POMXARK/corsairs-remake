#!/usr/bin/env python3
"""The whole chain of docs/ai-models.md for many models in one run: views of the game models -> redrawn views
(Qwen-Image through ComfyUI) -> 3D models (Pixal3D / TRELLIS.2) -> light GLB for the game -> .gm in the game.

Every step is the tool of its own (pdm_model_views.py, comfy_view_refine.py, comfy_model_batch.py,
pdm_glb_optimize.py, pdm_glb2gm.py) and skips what it has made already, so the run can be stopped and
started again; --redo makes the models again with the next seed. The last step (--install) puts the models into
the game in place of the originals (pdm_glb2gm.py --restore brings the originals back), it is not a default.

usage: pdm_models_all.py <game dir> [<model> ...] [--steps views,refine,model,optimize] [--install] [--redo]
         [--quality normal] [--crop 0.05] [--faces 12000] [--tex 1024] [--comfy URL] [--workflow API.json] [--set Class.input=value ...]
  <model>: characters/hero1 or hero1; none given: the models that have views already (the views step is skipped)
"""
import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
STEPS = ("views", "refine", "model", "optimize")


def run(*cmd):
    print("\n> " + " ".join(map(str, cmd)), flush=True)
    if subprocess.run([sys.executable, *map(str, cmd)]).returncode != 0:
        sys.exit(f"pdm_models_all: {Path(cmd[0]).name} failed")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("models", nargs="*")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--parts", action="store_true", help="a character part by part (pdm_model_views.PARTS)")
    ap.add_argument("--only-parts", help="with --parts: the groups taken from the networks (head,torso,...), the rest stays original")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--quality", default="normal")
    ap.add_argument("--crop", type=float, default=0.05)
    ap.add_argument("--faces", type=int, default=12000)
    ap.add_argument("--tex", type=int, default=1024)
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--workflow", type=Path, help="the API graph of the model step (default: image_to_model_api.json)")
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args()
    steps = a.steps.split(",")
    for s in steps:
        if s not in STEPS:
            sys.exit(f"pdm_models_all: no step {s} (views, refine, model, optimize)")
    ai = a.game / "data" / "ai_models"
    if "views" in steps and a.models:  # without names the views that are there are taken
        run(TOOLS / "pdm_model_views.py", a.game, *a.models, *(["--parts"] if a.parts else []))
    models = [m.split("/")[-1] for m in a.models]
    if a.parts:
        sys.path.insert(0, str(TOOLS))
        from pdm_model_views import PARTS  # noqa: E402
    names = [f"{m}_{part}" for m in models for part in PARTS if not a.only_parts or part in a.only_parts.split(",")
             ] if a.parts else models or sorted(
        p.name[:-len("_front.png")] for p in (ai / "views").glob("*_front.png"))
    if not names:
        sys.exit(f"pdm_models_all: no views in {ai / 'views'}")
    print(f"pdm_models_all: {len(names)} models: {', '.join(names)}")
    redo = ["--redo", *names] if a.redo else []
    if "refine" in steps:
        run(TOOLS / "comfy_view_refine.py", a.game, "--comfy", a.comfy, "--only", *names, *redo)
    if "model" in steps:
        # redrawn views are taken where they exist for these names (a folder of another run does not count)
        views = ai / ("views_refined" if "refine" in steps or (ai / "views_refined" / f"{names[0]}_front.png").exists()
                      else "views")
        extra = ["--set", *a.set] if a.set else []
        run(TOOLS / "comfy_model_batch.py", a.game, "--comfy", a.comfy, "--views", views, "--only", *names,
            "--quality", a.quality, "--crop", a.crop, *redo,
            *(["--workflow", a.workflow] if a.workflow else []), *extra)
    if "optimize" in steps:
        run(TOOLS / "pdm_glb_optimize.py", a.game, *names, "--faces", a.faces, "--tex", a.tex)
    if a.install:
        run(TOOLS / "pdm_glb2gm.py", a.game, *(models if a.parts else names), "--glb", ai / "glb_opt", "--tex", a.tex,
            *(["--parts"] if a.parts else []), *(["--only-parts", a.only_parts] if a.only_parts else []))
    print("\npdm_models_all: done")


if __name__ == "__main__":
    main()
