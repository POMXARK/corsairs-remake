#!/usr/bin/env python3
"""Makes 3D models of the views of pdm_model_views.py through the HTTP API of ComfyUI (docs/ai-models.md, ours).

The workflow is the template "Pixal3D & TRELLIS.2: Image to Model" or "Pixal3D: Multi Views to 3D"
exported by Workflow -> Export (API) into tools/model3d/. The script finds its nodes by their titles:
  IMAGE        Load Image, the front view;
  IMAGE_RIGHT, IMAGE_BACK, IMAGE_LEFT   Load Image, the other views (optional, a multi-view workflow);
  SEED         a node with a seed input (optional; fixed, a run repeats);
  FACES        the number of faces the mesh is decimated to (optional);
  SAVE         Save 3D, the GLB.
The input each of them takes is --seed-input / --faces-input; a node with a single number input takes
the number there whatever its name.

For every model with a <name>_front.png in the views and no <name>.glb yet: the views are uploaded to
input/pdm_models, the graph is queued, the file it saves is fetched by /view (ComfyUI may run on another
machine, `--listen`) to data/ai_models/glb/<name>.glb. A file that exists is skipped, so a run stops and
goes on; --redo <name> makes it again with the next seed. Then pdm_glb2gm.py puts it into the game.

usage: comfy_model_batch.py <game dir> [--workflow tools/model3d/image_to_model_api.json]
         [--comfy http://127.0.0.1:8188] [--only <name> ...] [--redo <name> ...] [--faces 20000] [--seed 1]
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
from comfy_voice_batch import Comfy  # noqa: E402

VIEWS = {"IMAGE": "front", "IMAGE_RIGHT": "right", "IMAGE_BACK": "back", "IMAGE_LEFT": "left"}
MODEL_EXT = (".glb", ".gltf", ".obj", ".fbx", ".ply")
POLL = 2.0


class Comfy3D(Comfy):
    def result(self, pid):
        """The 3D file of a finished prompt, None while it runs; an error of the graph stops the run."""
        h = self.call(f"/history/{pid}")
        if pid not in h:
            return None
        status = h[pid].get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI: {json.dumps(status.get('messages', []), ensure_ascii=False)[:800]}")
        # Save 3D lists its file under a key of its own (3d, result, ...): any file of a 3D format
        for out in h[pid]["outputs"].values():
            for files in out.values():
                for f in files if isinstance(files, list) else ():
                    if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(MODEL_EXT):
                        return f
        raise RuntimeError(f"ComfyUI: no 3D file in the outputs of {pid}: is the SAVE node a Save 3D?")

    def fetch(self, a, to: Path):
        q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""),
                                    "type": a.get("type", "output")})
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_bytes(urllib.request.urlopen(f"{self.url}/view?{q}", timeout=600).read())


def titled(graph, title):
    return next((n for n in graph.values() if n.get("_meta", {}).get("title") == title), None)


def set_number(node, name, value, title):
    """The input `name` of the node; a node with one number input takes it there whatever its name."""
    inputs = node["inputs"]
    if name not in inputs:
        numbers = [k for k, v in inputs.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(numbers) != 1:
            sys.exit(f"comfy_model_batch: node {title} has no input {name} (inputs: {', '.join(inputs)})")
        name = numbers[0]
    inputs[name] = value


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--workflow", type=Path, default=TOOLS / "model3d" / "image_to_model_api.json")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--views", type=Path)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--redo", nargs="*", default=[])
    ap.add_argument("--faces", type=int, default=20000, help="a skinned model holds 65536 vertices at most")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seed-input", default="seed")
    ap.add_argument("--faces-input", default="value")
    a = ap.parse_args()
    if not a.workflow.exists():
        sys.exit(f"comfy_model_batch: no {a.workflow}: export the template as API (docs/ai-models.md, step 3)")
    graph = json.loads(a.workflow.read_text(encoding="utf-8"))
    for title in ("IMAGE", "SAVE"):
        if titled(graph, title) is None:
            sys.exit(f"comfy_model_batch: no node titled {title} in the workflow (docs/ai-models.md, step 3)")
    views = a.views or a.game / "data" / "ai_models" / "views"
    out = a.game / "data" / "ai_models" / "glb"
    names = sorted(p.name[:-len("_front.png")] for p in views.glob("*_front.png"))
    names = [n for n in names if not a.only or n in a.only]
    todo = [n for n in names if n in a.redo or not (out / f"{n}.glb").exists()]
    print(f"comfy_model_batch: {len(todo)} of {len(names)} models to make")
    comfy = Comfy3D(a.comfy)
    tries = {}
    if (out / "seeds.json").exists():
        tries = json.loads((out / "seeds.json").read_text())
    started = time.time()
    for k, name in enumerate(todo):
        g = copy.deepcopy(graph)
        for title, view in VIEWS.items():
            node = titled(g, title)
            if node is None:
                continue
            png = views / f"{name}_{view}.png"
            if not png.exists():
                sys.exit(f"comfy_model_batch: the workflow takes {title}, there is no {png}")
            comfy.upload(png, "pdm_models")
            node["inputs"]["image"] = f"pdm_models/{png.name}"
        seed = a.seed + tries.get(name, 0) + (1 if name in a.redo else 0)
        if (node := titled(g, "SEED")) is not None:
            set_number(node, a.seed_input, seed, "SEED")
        if (node := titled(g, "FACES")) is not None:
            set_number(node, a.faces_input, a.faces, "FACES")
        pid = comfy.queue(g)
        while (f := comfy.result(pid)) is None:
            time.sleep(POLL)
        suffix = Path(f["filename"]).suffix.lower()
        comfy.fetch(f, out / f"{name}{suffix}")
        tries[name] = seed - a.seed
        (out / "seeds.json").write_text(json.dumps(tries, indent=1, sort_keys=True))
        left = (time.time() - started) / (k + 1) * (len(todo) - k - 1)
        print(f"{name}{suffix}: seed {seed}, {left / 60:.0f} min left", flush=True)


if __name__ == "__main__":
    main()
