#!/usr/bin/env python3
"""Redraws the views of pdm_model_views.py with an image model of ComfyUI (Qwen-Image edit and the like):
clean hands, fabric, the face, the pose and the colours kept. The result is the input of comfy_model_batch.py
(docs/ai-models.md, ours).

The workflow is an image-to-image or edit template exported by Workflow -> Export (API) into
tools/model3d/refine_api.json. The script finds its nodes by their titles:
  IMAGE   Load Image, the view;
  PROMPT  the node with the text of the task (a text input of its own, whatever its name);
  SEED    a node with a seed input (optional);
  SAVE    Save Image.

Every view of a model gets the same seed: the four of them are drawn alike. The views go to
data/ai_models/views_refined, the originals stay; the models are made of them by
comfy_model_batch.py <game dir> --views <game dir>/data/ai_models/views_refined.

usage: comfy_view_refine.py <game dir> [--workflow tools/model3d/refine_api.json] [--comfy http://127.0.0.1:8188]
         [--only <name> ...] [--redo <name> ...] [--seed 1] [--prompt "..."]
"""
import argparse
import copy
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from comfy_model_batch import POLL, Progress, set_number, titled  # noqa: E402
from comfy_voice_batch import Comfy  # noqa: E402

VIEWS = ("front", "right", "back", "left")
SIDE = {"front": "seen from the front", "right": "seen from the right side", "back": "seen from the back",
        "left": "seen from the left side"}
PROMPT = ("The same character {side}, the same pose, the same costume, the same colours and the same gold "
          "embroidery. Realistic detailed fabric, clean hands with five separate fingers, a detailed face, "
          "sharp leather boots, a thin sword. Orthographic full-body view, a flat grey background.")


class ComfyImage(Comfy):
    def result(self, pid):
        h = self.call(f"/history/{pid}")
        if pid not in h:
            return None
        status = h[pid].get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI: {json.dumps(status.get('messages', []), ensure_ascii=False)[:800]}")
        for out in h[pid]["outputs"].values():
            for im in out.get("images", []):
                if im.get("type") == "output":
                    return im
        raise RuntimeError(f"ComfyUI: no image in the outputs of {pid}: is the SAVE node a Save Image?")

    def fetch(self, a, to: Path):
        q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""),
                                    "type": a.get("type", "output")})
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_bytes(urllib.request.urlopen(f"{self.url}/view?{q}", timeout=120).read())


def set_text(node, text):
    """The string input of the node that holds the text of the task."""
    inputs = node["inputs"]
    keys = [k for k in ("prompt", "text", "positive_prompt") if isinstance(inputs.get(k), str)]
    keys = keys or [k for k, v in inputs.items() if isinstance(v, str)]
    if not keys:
        sys.exit("comfy_view_refine: the PROMPT node has no text input")
    inputs[keys[0]] = text


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--workflow", type=Path, default=TOOLS / "model3d" / "refine_api.json")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--views", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--redo", nargs="*", default=[])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seed-input", default="seed")
    ap.add_argument("--prompt", default=PROMPT, help="{side} becomes the side the view is seen from")
    a = ap.parse_args()
    if not a.workflow.exists():
        sys.exit(f"comfy_view_refine: no {a.workflow}: export the image-to-image workflow as API")
    graph = json.loads(a.workflow.read_text(encoding="utf-8"))
    for title in ("IMAGE", "PROMPT", "SAVE"):
        if titled(graph, title) is None:
            sys.exit(f"comfy_view_refine: no node titled {title} in the workflow")
    views = a.views or a.game / "data" / "ai_models" / "views"
    out = a.out or a.game / "data" / "ai_models" / "views_refined"
    names = sorted(p.name[:-len("_front.png")] for p in views.glob("*_front.png"))
    names = [n for n in names if not a.only or n in a.only]
    todo = [(n, v) for n in names for v in VIEWS
            if (views / f"{n}_{v}.png").exists() and (n in a.redo or not (out / f"{n}_{v}.png").exists())]
    print(f"comfy_view_refine: {len(todo)} views to draw")
    comfy = ComfyImage(a.comfy)
    started = time.time()
    for k, (name, view) in enumerate(todo):
        g = copy.deepcopy(graph)
        png = views / f"{name}_{view}.png"
        comfy.upload(png, "pdm_models")
        titled(g, "IMAGE")["inputs"]["image"] = f"pdm_models/{png.name}"
        set_text(titled(g, "PROMPT"), a.prompt.replace("{side}", SIDE[view]))
        if (node := titled(g, "SEED")) is not None:
            set_number(node, a.seed_input, a.seed + (1 if name in a.redo else 0), "SEED")
        progress = Progress(a.comfy, "pdm-voice")
        pid = comfy.queue(g)
        t0 = time.time()
        while (f := comfy.result(pid)) is None:
            progress.poll(POLL)
            node = g.get(str(progress.node), {})
            title = node.get("_meta", {}).get("title") or node.get("class_type", "...")
            step = f" {progress.step}/{progress.steps}" if progress.steps else ""
            print(f"\r{name}_{view}: node {len(progress.done)}/{len(g)} {title}{step}, "
                  f"{time.time() - t0:.0f} s".ljust(100), end="", flush=True)
        print()
        comfy.fetch(f, out / f"{name}_{view}.png")
        left = (time.time() - started) / (k + 1) * (len(todo) - k - 1)
        print(f"{name}_{view}.png: {left / 60:.0f} min left", flush=True)


if __name__ == "__main__":
    main()
