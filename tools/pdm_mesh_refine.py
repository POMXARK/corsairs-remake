#!/usr/bin/env python3
"""Refines the mesh of the original model with UltraShape in ComfyUI: the shape grows detail on the geometry that
is there (docs/ai-models-refine.md, ours).

The original .gm of pdm-game/resource is written as a GLB (pdm_gm2glb.py), uploaded to ComfyUI with the front view
of the model (the picture the refinement is guided by), and the graph
  Load Image + Load Model -> Load Coarse Mesh -> Refine -> Convert To GLB -> Save 3D
is run through the API. The result is data/ai_models/glb_refined/<name>.glb: a new, closed mesh without UVs, bones
and texture. It is a source for baking (the maps go to the original mesh) and for pdm_model_check.py, not the
model of the game by itself.

usage: pdm_mesh_refine.py <game dir> <model> [<model> ...] [--comfy http://127.0.0.1:8188] [--image <png>]
         [--checkpoint ultrashape_v1.pt] [--config infer_dit_refine.yaml] [--dtype bfloat16] [--low-vram]
         [--steps 50] [--guidance 5.0] [--octree 384] [--chunks 8000] [--latents 0] [--seed 42]
         [--remove-bg] [--mc-level 0.0] [--box 1.0] [--redo] [--out data/ai_models/glb_refined]
  <model>: a name found under resource/models (hero1); for --parts names of the parts: hero1_head ...
  --image: the picture of the guidance, default data/ai_models/views_refined/<model>_front.png, else views/
"""
import argparse
import copy
import json
import sys
import time
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from comfy_model_batch import POLL, Comfy3D, Progress  # noqa: E402
from pdm_gm2glb import build  # noqa: E402
from pdm_model_views import find_model, read_gm, texture_index  # noqa: E402

REQUIRED_NODES = ("UltraShapeLoadModel", "UltraShapeLoadCoarseMesh", "UltraShapeRefine", "UltraShapeConvertToGLB")


def graph_of(a, image: str, mesh: str, seed: int, prefix: str, info: dict) -> dict:
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": image}},
        "2": {"class_type": "UltraShapeLoadModel", "inputs": {
            "checkpoint": a.checkpoint, "config": a.config, "dtype": a.dtype, "low_vram": a.low_vram}},
        "3": {"class_type": "UltraShapeLoadCoarseMesh", "inputs": {
            "model": ["2", 0], "mesh_path": mesh, "num_latents": a.latents}},
        "4": {"class_type": "UltraShapeRefine", "inputs": {
            "model": ["2", 0], "coarse_mesh": ["3", 0], "image": ["1", 0], "steps": a.steps,
            "guidance_scale": a.guidance, "octree_resolution": a.octree, "num_chunks": a.chunks,
            "mc_level": a.mc_level, "box_v": a.box, "seed": seed, "remove_bg": a.remove_bg}},
        "5": {"class_type": "UltraShapeConvertToGLB", "inputs": {"refined_mesh": ["4", 0], "file_format": "glb"}},
    }
    # Save 3D: the first input of a node type takes the mesh, every other required input its default of /object_info
    save = {"class_type": "Save3DAdvanced", "inputs": {}}
    linked = False
    for name, spec in info["Save3DAdvanced"]["input"]["required"].items():
        kind = spec[0]
        if isinstance(kind, str) and kind not in ("STRING", "INT", "FLOAT", "BOOLEAN") and not linked:
            save["inputs"][name] = ["5", 0]  # the 3D file (FILE_3D)
            linked = True
        elif isinstance(kind, list):
            save["inputs"][name] = spec[1].get("default", kind[0]) if len(spec) > 1 else kind[0]
        elif len(spec) > 1 and "default" in spec[1]:
            save["inputs"][name] = spec[1]["default"]
        elif kind == "STRING":
            save["inputs"][name] = prefix
    for name in save["inputs"]:  # the file name prefix is the one string that is not the mesh
        if "prefix" in name:
            save["inputs"][name] = prefix
    g["6"] = save
    return g


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--image", type=Path)
    ap.add_argument("--checkpoint", default="ultrashape_v1.pt")
    ap.add_argument("--config", default="infer_dit_refine.yaml")
    ap.add_argument("--dtype", default="bfloat16", choices=("float16", "bfloat16", "float32"))
    ap.add_argument("--low-vram", action="store_true")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--octree", type=int, default=384)
    ap.add_argument("--chunks", type=int, default=8000)
    ap.add_argument("--latents", type=int, default=0, help="0: the default of the config")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mc-level", type=float, default=0.0)
    ap.add_argument("--box", type=float, default=1.0)
    ap.add_argument("--remove-bg", action="store_true")
    ap.add_argument("--redo", action="store_true", help="make again what is there, with the next seed")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    ai = a.game / "data" / "ai_models"
    out = a.out or ai / "glb_refined"
    comfy = Comfy3D(a.comfy)
    with urllib.request.urlopen(a.comfy + "/object_info", timeout=60) as r:
        info = json.load(r)
    missing = [n for n in REQUIRED_NODES + ("Save3DAdvanced",) if n not in info]
    if missing:
        sys.exit(f"pdm_mesh_refine: ComfyUI has no node {', '.join(missing)}: install ComfyUI-UltraShape1 "
                 f"(docs/ai-models-refine.md, step 2) and restart it")
    seeds = json.loads((out / "seeds.json").read_text()) if (out / "seeds.json").exists() else {}
    textures = None
    for name in a.models:
        target = out / f"{name}.glb"
        if target.exists() and not a.redo:
            print(f"pdm_mesh_refine: {target} is there, --redo makes it again")
            continue
        image = a.image
        for d in ("views_refined", "views"):
            if image is None and (ai / d / f"{name}_front.png").exists():
                image = ai / d / f"{name}_front.png"
        if image is None:
            sys.exit(f"pdm_mesh_refine: no {name}_front.png in {ai}/views: run pdm_model_views.py first")
        orig = ai / "glb" / f"{name}_orig.glb"
        if not orig.exists():
            textures = textures or texture_index(a.game)
            orig.parent.mkdir(parents=True, exist_ok=True)
            orig.write_bytes(build(read_gm(find_model(a.game, name)), textures))
            print(f"pdm_mesh_refine: {orig} written from the .gm")
        comfy.upload(image, "pdm_models")
        comfy.upload(orig, "pdm_models")
        tries = seeds.get(name, 0) + (1 if a.redo else 0)
        g = graph_of(a, f"pdm_models/{image.name}", f"pdm_models/{orig.name}", a.seed + tries,
                     f"3d/pdm_refined_{name}", info)
        progress = Progress(a.comfy, "pdm-voice")
        pid = comfy.queue(copy.deepcopy(g))
        t0 = time.time()
        while (f := comfy.result(pid)) is None:
            progress.poll(POLL)
            node = g.get(str(progress.node), {})
            step = f" {progress.step}/{progress.steps}" if progress.steps else ""
            print(f"\r{name}: {node.get('class_type', '...')}{step}, {(time.time() - t0) / 60:.1f} min".ljust(90),
                  end="", flush=True)
        print()
        comfy.fetch(f, target)
        seeds[name] = tries
        (out / "seeds.json").write_text(json.dumps(seeds, indent=1, sort_keys=True))
        print(f"pdm_mesh_refine: {target}, seed {a.seed + tries}, {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
