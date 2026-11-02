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
WHAT = {"head": "head", "torso": "torso", "arm_l": "left arm with the hand", "arm_r": "right arm with the hand",
        "sword": "thin sabre", "legs": "legs with the boots"}
EXTRA = {"head": " Keep the eyes exactly as in the picture: open, white eyeballs, dark irises, round pupils, eyelids. Keep both ears visible and uncovered, the hair goes behind the ears, never over them. Keep the hair exactly as in the picture, including a ponytail or long strands at the back: do not shorten or remove them. Soft even matte lighting, no glossy highlights or shine on the skin, no reflections. Keep the closed mouth as in the picture: one clean line between the lips, no teeth, no second lip line.",
         "arm_l": " A clean hand with five separate fingers.", "arm_r": " A clean hand with five separate fingers.",
         "legs": "", "torso": "", "sword": ""}
OUTLINE = {"head": "The outline must be smooth and organic like a real person: a round skull, a natural jaw and chin, natural hair, a round neck, no angular polygon silhouette. Keep the skin as in the picture with natural pores."}
OUTLINE = {p: OUTLINE.get(p, "The outline must be smooth and natural, no angular polygon silhouette.") for p in PARTS}
BACK = " This is the view from behind: the face is NOT visible, draw only the back of the head, the hair and the ears."
CUT = {"head": " The neck is cut off flat at the bottom: keep that cut in the skin colour, never grey and never the colour of the background.",
       "torso": "", "arm_l": "", "arm_r": "", "legs": "", "sword": ""}
SIDE = {"front": "seen from the front", "left": "seen from the left side", "back": "seen from the back",
        "right": "seen from the right side"}
VIEW_ORDER = ("front", "left", "back", "right")  # the order of the outputs
STATE = {"start": 0.0}


def prompt_of(part, view):
    """Nothing is invented: only what the picture shows (the first version said "with the hat" and Qwen drew one)."""
    ref = ("" if view in ("front", "back") else " <image2> is the same part seen from the front: take the identity, hair, "
           "colours and details from it, so that all views show one and the same object.")
    return (f"Redraw <image1>, the {WHAT[part]} {SIDE[view]}, as a clean high-detail realistic render. Keep exactly "
            "the same camera view, pose, proportions, colours and every detail that <image1> shows. Do not add "
            "anything that is not in <image1>: no hat, no clothes, no mask, no accessories. Smooth surfaces "
            f"without polygon edges, realistic skin and fabric. {OUTLINE[part]}{'' if view == 'back' else EXTRA[part]}{ref}{BACK if view == 'back' else ''}{CUT[part]} "
            "A flat bright green background.")


def sheet_prompt(part):
    """One prompt for the 2x2 sheet: Qwen draws the four views in one pass, so they agree with each other."""
    return (f"<image1> is a 2x2 contact sheet: four views of the same {WHAT[part]} on a flat bright green background. "
            "Top left: from the front. Top right: from the left side. Bottom left: from the back. Bottom right: from the "
            "right side. Redraw the whole sheet as clean high-detail realistic renders. Keep the grid, the position of "
            "every view, its camera, pose and proportions exactly. All four views must show one and the same real "
            "object with the same colours, the same hair and the same details. Do not add anything that is not in "
            f"<image1>: no hat, no clothes, no mask. {OUTLINE[part]}{EXTRA[part]}{CUT[part]} In the view from the back "
            "the face is not visible. A flat bright green background in all four cells.")


PIP = ["numpy", "Pillow", "scipy", "trimesh", "rtree", "fast-simplification"]


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


def sheet(pics, cell):
    """The four views as a 2x2 sheet: front, left / back, right."""
    from PIL import Image
    sh = Image.new("RGB", (2 * cell, 2 * cell))
    for k, im in enumerate(pics):
        sh.paste(im.resize((cell, cell), Image.LANCZOS), ((k % 2) * cell, (k // 2) * cell))
    return sh


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
            "sheet_cell": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64}),
        }}

    RETURN_TYPES = ("IMAGE",) * 4 + ("STRING",) * 7 + ("IMAGE", "STRING")
    RETURN_NAMES = ("front", "left", "back", "right", "prompt_front", "prompt_left", "prompt_back", "prompt_right",
                    "part", "model", "info", "sheet", "prompt_sheet")
    OUTPUT_NODE = True
    FUNCTION = "go"
    CATEGORY = "pdm"

    @classmethod
    def IS_CHANGED(cls, **kw):
        return float("nan")

    def go(self, repo, game, model, part_index, tpose, margin, rerender, python, sheet_cell=1024):
        STATE["start"] = time.time()
        part = PARTS[part_index % len(PARTS)]
        m = CFG[part][0] if margin < 0 else margin
        log = [f"part {part_index % len(PARTS) + 1}/{len(PARTS)}: {part} of {model}"]
        gamedir = Path(repo) / game
        views = gamedir / "data" / "ai_models" / ("views_tpose_green" if tpose else "views_green")
        files = [views / f"{model}_{part}_{v}.png" for v in VIEW_ORDER]
        if rerender or not all(f.exists() for f in files):
            run([python, Path(repo) / "tools" / "pdm_model_views.py", gamedir, model, "--parts", "--size", 1024,
                 "--bg", "0,255,0", "--out", views] + (["--tpose"] if tpose else []), repo, log)
        else:
            log.append(f"views exist: {views}")
        pics, side = crop(files, m)
        log.append(f"cropped to {side} px (margin {m}), prompts for the Qwen refine nodes made")
        text = "\n".join(log)
        return {"ui": {"text": [text]},
                "result": tuple(tensor(p) for p in pics) + tuple(prompt_of(part, v) for v in VIEW_ORDER)
                + (part, model, text, tensor(sheet(pics, sheet_cell)), sheet_prompt(part))}


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


def despill(img):
    """The green background leaks into the edge pixels of the figure (olive rim on the hair): clamp green to the
    larger of red and blue; the pure background (green, nothing else) stays for the background removal."""
    import torch
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    bg = (g > 0.75) & (r < 0.35) & (b < 0.35)
    return torch.stack([r, torch.where(bg, g, torch.minimum(g, torch.maximum(r, b))), b], dim=-1)


class PDMSheetSplit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"sheet": ("IMAGE",)}}

    RETURN_TYPES = ("IMAGE",) * 4
    RETURN_NAMES = VIEW_ORDER
    FUNCTION = "go"
    CATEGORY = "pdm"

    def go(self, sheet):
        """The 2x2 sheet (front, left / back, right) back into four views of 1024 px."""
        import torch
        h, w = sheet.shape[1] // 2, sheet.shape[2] // 2
        cells = [sheet[:, (k // 2) * h:(k // 2 + 1) * h, (k % 2) * w:(k % 2 + 1) * w, :] for k in range(4)]
        if h != 1024:
            cells = [torch.nn.functional.interpolate(c.permute(0, 3, 1, 2), size=(1024, 1024), mode="bicubic",
                                                     align_corners=False).permute(0, 2, 3, 1).clamp(0, 1) for c in cells]
        return tuple(despill(c) for c in cells)


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
        }, "optional": {"front": ("IMAGE",), "left": ("IMAGE",), "back": ("IMAGE",), "right": ("IMAGE",)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    OUTPUT_NODE = True
    FUNCTION = "go"
    CATEGORY = "pdm"

    @classmethod
    def IS_CHANGED(cls, **kw):
        return float("nan")

    def go(self, mesh, part, model, repo, game, faces, tex, optimize, python, front=None, left=None, back=None, right=None):
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
        if front is not None and left is not None and back is not None and right is not None:
            # the generated texture smears eyes and brows: paint it from the four (sharp) views the mesh was made from
            vdir = gamedir / "data" / "ai_models" / "views" / name
            vdir.mkdir(parents=True, exist_ok=True)
            paths = []
            for vname, t in zip(VIEW_ORDER, (front, left, back, right)):
                from PIL import Image
                pth = vdir / f"{vname}.png"
                Image.fromarray((t[0].cpu().numpy() * 255).clip(0, 255).astype("uint8")).save(pth)
                paths.append(pth)
            try:
                run([python, Path(repo) / "tools" / "pdm_project_views.py", src, glb / f"{name}.glb", *paths], repo, log)
            except RuntimeError as e:
                log.append("PROJECTION FAILED, the generated texture stays: " + str(e)[-300:])
        log.append(f"{src} -> {glb / (name + '.glb')} ({os.path.getsize(src) // 1024} KB)")
        _, f0, t0 = CFG[part]
        if optimize:
            cmd = [python, Path(repo) / "tools" / "pdm_glb_optimize.py", gamedir, name, "--faces", faces or f0,
                   "--tex", tex or t0]
            try:
                try:
                    run(cmd, repo, log)
                except RuntimeError as e:
                    if "No module named" not in str(e):
                        raise
                    log.append("a module is missing: installing the packages of the optimizer")
                    run([python, "-m", "pip", "install", "--user", *PIP], repo, log)
                    run(cmd, repo, log)
            except RuntimeError as e:
                log.append(f"OPTIMIZE FAILED, the GLB is saved, the run goes on. If a module is missing: "
                           f"{python} -m pip install --user numpy Pillow scipy trimesh rtree fast-simplification, "
                           f"then: {python} tools\\pdm_glb_optimize.py {game} {name} --faces {faces or f0} --tex {tex or t0}")
        done = [p for p in PARTS if (glb / f"{model}_{p}.glb").exists()]
        log.append(f"parts ready: {', '.join(done)} ({len(done)}/{len(PARTS)})")
        if len(done) == len(PARTS):
            log.append(f"all parts done. Put them into the game:\n  python tools\\pdm_models_all.py {game} {model} "
                       f"--parts --steps optimize --faces 20000 --tex 2048 --install   (--restore brings the originals back)")
        text = "\n".join(log)
        print(text, flush=True)
        return {"ui": {"text": [text]}, "result": (text,)}


def _patch_flash_decode():
    """TextGenerate (Qwen3.5 describes the view) crashed in comfy_kitchen.flash_attention_decode_gqa:
    "Unsupported Flash Attention tensor strides" - the CUDA kernel wants contiguous q/k/v, the KV cache gives views.
    Make them contiguous; if the kernel still refuses, use the torch version of the same computation."""
    try:
        import comfy_kitchen
        from comfy_kitchen import flash_attention as fa
    except Exception:
        return
    orig = fa.flash_attention_decode_gqa
    if getattr(orig, "_pdm", False):
        return

    def safe(q, k, v, kv_lengths, return_lse=False, causal=True):
        q, k, v = q.contiguous(), k.contiguous(), v.contiguous()
        try:
            return orig(q, k, v, kv_lengths, return_lse=return_lse, causal=causal)
        except RuntimeError:
            out, lse = fa._decode_gqa_torch(q, k, v, kv_lengths, causal)
            return (out, lse) if return_lse else out
    safe._pdm = True
    fa.flash_attention_decode_gqa = safe
    if getattr(comfy_kitchen, "flash_attention_decode_gqa", None) is orig:
        comfy_kitchen.flash_attention_decode_gqa = safe


_patch_flash_decode()


NODE_CLASS_MAPPINGS = {"PDMPartViews": PDMPartViews, "PDMPartSave": PDMPartSave, "PDMSheetSplit": PDMSheetSplit}
NODE_DISPLAY_NAME_MAPPINGS = {"PDMPartViews": "PDM Part Views (splits the character)",
                              "PDMPartSave": "PDM Part Save (GLB + optimize)",
                              "PDMSheetSplit": "PDM Sheet Split (2x2 -> 4 views)"}
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
