"""Nodes of ComfyUI that cut a game character into parts and hand every part to Pixal3D (ours).

PDMPartViews  runs tools/pdm_model_views.py (--parts) when the views of the part are not there yet, crops the four
              views to the figure, gives them out with a prompt of every view for the Qwen refine nodes. The
              part_index input counts up by itself after each run (control_after_generate = increment), so
              "Batch count 6" in the Run menu goes through head, torso, arm_l, arm_r, sword, legs one by one.
PDMPartSave   takes the GLB of the part from the output folder of ComfyUI, puts it to <game>/data/ai_models/glb/
              <model>_<part>.glb and runs tools/pdm_glb_optimize.py (faces and texture of the part).
Both nodes show what they did in a text field of the node (js/pdm_parts.js), the same text goes to the console.
Install: copy this folder to ComfyUI/custom_nodes/ (tools/model3d/install_parts.ps1 does it), restart ComfyUI.
"""
import glob
import os
import subprocess
import time
from pathlib import Path

PARTS = ("head", "torso", "arm_l", "arm_r", "sword", "legs")  # tools/pdm_model_views.py PARTS
# margin of the crop, faces, texture of the part: a face needs the most pixels, a sword the fewest
CFG = {"head": (0.02, 15000, 2048), "torso": (0.04, 20000, 2048), "arm_l": (0.05, 8000, 1024),
       "arm_r": (0.05, 8000, 1024), "sword": (0.05, 4000, 1024), "legs": (0.04, 15000, 2048)}
WHAT = {"head": "head of the character with the hat, hair and face",
        "torso": "torso of the character with the coat, collar and belt",
        "arm_l": "left arm of the character with the sleeve and the hand", 
        "arm_r": "right arm of the character with the sleeve and the hand",
        "sword": "thin sabre",
        "legs": "legs of the character with the trousers and boots"}
EXTRA = {"head": " Open eyes with white eyeballs, dark irises and round pupils, eyelids and eyebrows, a detailed face.",
         "arm_l": " Clean hand with five separate fingers.", "arm_r": " Clean hand with five separate fingers.",
         "legs": " Sharp leather boots.", "torso": " Gold embroidery, a lace collar.", "sword": ""}
SIDE = {"front": "seen from the front", "left": "seen from the left side", "back": "seen from the back",
        "right": "seen from the right side"}
VIEW_ORDER = ("front", "left", "back", "right")  # the order of the outputs
STATE = {"start": 0.0}


def prompt_of(part, view):
    return (f"The same {WHAT[part]} {SIDE[view]}, the same pose, the same costume, the same colours and the same "
            f"gold embroidery. Realistic detailed fabric.{EXTRA[part]} Orthographic view, a flat grey background. "
            "Keep exactly the same camera view and proportions.")


def run(cmd, cwd, log):
    log.append("> " + " ".join(map(str, cmd)))
    print(log[-1], flush=True)
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, errors="replace")
    tail = (p.stdout + p.stderr).strip().splitlines()[-12:]
    log.extend(tail)
    print("\n".join(tail), flush=True)
    if p.returncode:
        raise RuntimeError("\n".join(log[-14:]))


def crop(paths, margin, size=1024):
    """The four views into squares that hold the figure of each of them (as comfy_model_batch.crop_views)."""
    import numpy as np
    from PIL import Image
    pics = [Image.open(p).convert("RGB") for p in paths]
    lo, hi = [10 ** 9, 10 ** 9], [-1, -1]
    for im in pics:
        a = np.asarray(im).astype(int)
        ys, xs = np.nonzero(np.abs(a - a[0, 0]).sum(axis=2) > 36)  # the grey of the corner is the background
        if len(xs):
            lo = [min(lo[0], xs.min()), min(lo[1], ys.min())]
            hi = [max(hi[0], xs.max()), max(hi[1], ys.max())]
    side = max(hi[0] - lo[0], hi[1] - lo[1], 8) * (1 + 2 * margin)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    out = []
    for im in pics:
        canvas = Image.new("RGB", (int(side) + 1, int(side) + 1), tuple(np.asarray(im)[0, 0]))
        canvas.paste(im, (-int(cx - side / 2), -int(cy - side / 2)))
        out.append(canvas.resize((size, size), Image.LANCZOS))
    return out, int(side)


def tensor(im):
    import numpy as np
    import torch
    return torch.from_numpy(np.asarray(im).astype("float32") / 255.0)[None,]


class PDMPartViews:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "repo": ("STRING", {"default": r"C:\corsairs-remake"}),
            "game": ("STRING", {"default": "pdm-game"}),
            "model": ("STRING", {"default": "hero1"}),
            "part_index": ("INT", {"default": 0, "min": 0, "max": 9999, "control_after_generate": True}),
            "tpose": ("BOOLEAN", {"default": True}),
            "margin": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 0.5, "step": 0.01}),
            "rerender": ("BOOLEAN", {"default": False}),
            "python": ("STRING", {"default": "python"}),
        }}

    RETURN_TYPES = ("IMAGE",) * 4 + ("STRING",) * 7
    RETURN_NAMES = ("front", "left", "back", "right", "prompt_front", "prompt_left", "prompt_back", "prompt_right",
                    "part", "model", "info")
    OUTPUT_NODE = True
    FUNCTION = "go"
    CATEGORY = "pdm"

    @classmethod
    def IS_CHANGED(cls, **kw):
        return float("nan")

    def go(self, repo, game, model, part_index, tpose, margin, rerender, python):
        STATE["start"] = time.time()
        part = PARTS[part_index % len(PARTS)]
        m = CFG[part][0] if margin < 0 else margin
        log = [f"part {part_index % len(PARTS) + 1}/{len(PARTS)}: {part} of {model}"]
        gamedir = Path(repo) / game
        views = gamedir / "data" / "ai_models" / ("views_tpose" if tpose else "views")
        files = [views / f"{model}_{part}_{v}.png" for v in VIEW_ORDER]
        if rerender or not all(f.exists() for f in files):
            run([python, Path(repo) / "tools" / "pdm_model_views.py", gamedir, model, "--parts", "--size", 1024,
                 "--out", views] + (["--tpose"] if tpose else []), repo, log)
        else:
            log.append(f"views exist: {views}")
        pics, side = crop(files, m)
        log.append(f"cropped to {side} px (margin {m}), prompts for the Qwen refine nodes made")
        text = "\n".join(log)
        return {"ui": {"text": [text]},
                "result": tuple(tensor(p) for p in pics) + tuple(prompt_of(part, v) for v in VIEW_ORDER)
                + (part, model, text)}


def find_glb(mesh):
    """The GLB the Save 3D node wrote: its output as a path, a dict or an object, else the newest file since start."""
    cands = [mesh] if isinstance(mesh, str) else []
    if isinstance(mesh, dict):
        cands += [mesh.get(k) for k in ("path", "file", "filename", "source")]
    for k in ("path", "file", "filename", "source", "save_path"):
        cands.append(getattr(mesh, k, None))
    try:
        import folder_paths
        out = folder_paths.get_output_directory()
    except Exception:
        out = "."
    for c in cands:
        if isinstance(c, str):
            for p in (c, os.path.join(out, c), os.path.join(out, "3d", c)):
                if os.path.isfile(p):
                    return p
    new = [p for p in glob.glob(os.path.join(out, "**", "*.glb"), recursive=True)
           if os.path.getmtime(p) >= STATE["start"] - 5]
    return max(new, key=os.path.getmtime) if new else None


class PDMPartSave:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "mesh": ("FILE_3D",),
            "part": ("STRING", {"forceInput": True}),
            "model": ("STRING", {"forceInput": True}),
            "repo": ("STRING", {"default": r"C:\corsairs-remake"}),
            "game": ("STRING", {"default": "pdm-game"}),
            "faces": ("INT", {"default": 0, "min": 0, "max": 65000}),
            "tex": ("INT", {"default": 0, "min": 0, "max": 4096}),
            "optimize": ("BOOLEAN", {"default": True}),
            "python": ("STRING", {"default": "python"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    OUTPUT_NODE = True
    FUNCTION = "go"
    CATEGORY = "pdm"

    @classmethod
    def IS_CHANGED(cls, **kw):
        return float("nan")

    def go(self, mesh, part, model, repo, game, faces, tex, optimize, python):
        import shutil
        log = [f"saving {model}_{part}"]
        src = find_glb(mesh)
        if not src:
            raise RuntimeError("PDMPartSave: no GLB found in the output folder of ComfyUI")
        gamedir = Path(repo) / game
        glb = gamedir / "data" / "ai_models" / "glb"
        glb.mkdir(parents=True, exist_ok=True)
        name = f"{model}_{part}"
        shutil.copyfile(src, glb / f"{name}.glb")
        log.append(f"{src} -> {glb / (name + '.glb')} ({os.path.getsize(src) // 1024} KB)")
        _, f0, t0 = CFG[part]
        if optimize:
            run([python, Path(repo) / "tools" / "pdm_glb_optimize.py", gamedir, name, "--faces", faces or f0,
                 "--tex", tex or t0], repo, log)
        done = [p for p in PARTS if (glb / f"{model}_{p}.glb").exists()]
        log.append(f"parts ready: {', '.join(done)} ({len(done)}/{len(PARTS)})")
        if len(done) == len(PARTS):
            log.append(f"all parts done. Put them into the game:\n  python tools\\pdm_models_all.py {game} {model} "
                       f"--parts --steps optimize --faces 20000 --tex 2048 --install   (--restore brings the originals back)")
        text = "\n".join(log)
        print(text, flush=True)
        return {"ui": {"text": [text]}, "result": (text,)}


NODE_CLASS_MAPPINGS = {"PDMPartViews": PDMPartViews, "PDMPartSave": PDMPartSave}
NODE_DISPLAY_NAME_MAPPINGS = {"PDMPartViews": "PDM Part Views (splits the character)",
                              "PDMPartSave": "PDM Part Save (GLB + optimize)"}
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
