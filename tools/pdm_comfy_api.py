#!/usr/bin/env python3
"""Turns the template "Pixal3D: Multi Views to 3D" (a workflow saved from ComfyUI, 3d_pixal3d_multi_views.json)
into the API graph that comfy_model_batch.py queues: tools/model3d/image_to_model_api.json.

The turnaround sheet and its four crops are replaced by four Load Image nodes titled IMAGE, IMAGE_LEFT,
IMAGE_BACK, IMAGE_RIGHT (the views of pdm_model_views.py); the background removal that follows them stays.
The sparse-structure sampler becomes SEED, the Save 3D node SAVE. Notes and previews that nothing reads are dropped.

The template "Pixal3D & TRELLIS.2: Image to Model" (3d_pixal3d_trellis2_image_to_model.json) is taken too: its
single image becomes IMAGE (the front view), --trellis turns its switch to TRELLIS.2 (Pixal3D otherwise).

The workflows of PixelArtistry (github.com/pixelartistry/PixelArtistry-Watertight-Meshes, MIT) are built on that
template and go through the same way: --save is the Save 3D node that gives the model (01 and 01b: 331, 02: 343,
03: 341), --comfy gives the names of the widgets of the custom nodes (WTiVo, LODTailor: the file keeps only
their values), --blender is the path of Blender that the nodes of LODTailor run. A bypassed node is stepped over.

usage: pdm_comfy_api.py <template.json> [--trellis] [--save ID] [--comfy URL] [--blender PATH]
                        [--out tools/model3d/image_to_model_api.json]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

SKIP = {"Note", "MarkdownNote", "Preview3DAdvanced"}
NOT_INPUTS = {"control_after_generate", "fixed", "upload"}
CROPS = {338: "IMAGE", 341: "IMAGE_LEFT", 342: "IMAGE_BACK", 345: "IMAGE_RIGHT"}  # ImageCropV2 of the sheet
SEED_NODE, SAVE_NODE, SHEET_NODE = 3, 372, 364
# the template "Pixal3D & TRELLIS.2: Image to Model": one image, a switch between the two models
SINGLE = {"image": 122, "switch": 316, "save": 322}


WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def widget_names(info):
    """The widgets of a node class in the order of widgets_values (a seed has the extra control_after_generate)."""
    names = []
    for part in ("required", "optional"):
        for name in (info.get("input_order") or {}).get(part) or info.get("input", {}).get(part, {}):
            spec = info["input"][part][name]
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(kind, list) or kind in WIDGET_TYPES:
                names.append(name)
                if opts.get("control_after_generate"):
                    names.append("control_after_generate")
    return names


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("workflow", type=Path)
    ap.add_argument("--trellis", action="store_true", help="the single-image template: TRELLIS.2 instead of Pixal3D")
    ap.add_argument("--save", type=int, help="id of the Save 3D node that becomes SAVE")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188", help="a running ComfyUI: /object_info names the widgets")
    ap.add_argument("--blender", help="path of blender.exe for the nodes that run Blender")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "model3d" / "image_to_model_api.json")
    a = ap.parse_args()
    ui = json.loads(a.workflow.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in ui["nodes"]}
    single = SINGLE["switch"] in nodes
    crops, save = ({}, SINGLE["save"]) if single else (CROPS, SAVE_NODE)
    save = a.save or save
    sheet = SINGLE["image"] if single else SHEET_NODE
    for need in (*crops, SEED_NODE, save, sheet):
        if need not in nodes:
            sys.exit(f"pdm_comfy_api: no node {need}: this is not a template of Pixal3D (multi views, image to model)")
    source = {}  # link id -> (node, slot)
    for lid, src, slot, *_ in ui["links"]:
        source[lid] = (src, slot)

    def origin(src, slot):
        """The node that really gives the value: a bypassed node passes on its input of the same type."""
        while nodes[src].get("mode") == 4:
            kind = nodes[src]["outputs"][slot]["type"]
            link = next((i["link"] for i in nodes[src].get("inputs", [])
                         if i["type"] == kind and i.get("link") is not None), None)
            if link is None:
                sys.exit(f"pdm_comfy_api: the bypassed node {src} has no input of the type {kind}")
            src, slot = source[link]
        return src, slot

    object_info = None
    graph = {}
    for nid, n in nodes.items():
        if n["type"] in SKIP or n.get("mode") == 4:
            continue
        inputs = {}
        if nid == SINGLE["image"] and single:
            graph[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": "view.png"},
                               "_meta": {"title": "IMAGE"}}
            continue
        if nid == SHEET_NODE and not single:
            continue
        if nid in crops:
            graph[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": "view.png"},
                               "_meta": {"title": crops[nid]}}
            continue
        linked = set()
        for i in n.get("inputs", []):
            if i.get("link") is not None:
                src, slot = origin(*source[i["link"]])
                if nodes[src]["type"] in SKIP:
                    continue
                inputs[i["name"]] = [str(src), slot]
                linked.add(i["name"])
        named = n.get("widgets_values_named")
        if object_info is None and n["type"] not in SKIP:
            try:
                with urllib.request.urlopen(a.comfy + "/object_info", timeout=60) as r:
                    object_info = json.load(r)
            except OSError:
                pass
        if named is None and n.get("widgets_values") and n["type"] not in SKIP:
            if object_info is None:
                try:
                    with urllib.request.urlopen(a.comfy + "/object_info", timeout=60) as r:
                        object_info = json.load(r)
                except OSError as e:
                    sys.exit(f"pdm_comfy_api: node {nid} {n['type']} has no named widgets and {a.comfy} does not "
                             f"answer ({e}): start ComfyUI with the node packs of PixelArtistry")
            if n["type"] not in object_info:
                sys.exit(f"pdm_comfy_api: ComfyUI does not know the node {n['type']} (the node pack is not installed)")
            info = object_info[n["type"]]
            names = widget_names(info)
            if n["type"] == "Save3DAdvanced":
                # the viewer state is a widget of the frontend, /object_info lists it elsewhere: prefix, state, size
                names = [names[0], "viewport_state", "width", "height"]
            named = dict(zip(names, n["widgets_values"]))
        if object_info is not None and n["type"] in object_info and n["type"] not in SKIP:
            info, named = object_info[n["type"]], dict(named or {})
            # a widget that the saved workflow does not hold (a newer version of the node) takes the node default
            for k, spec in info["input"].get("required", {}).items():
                if k in named or k in linked or not (isinstance(spec[0], list) or spec[0] in WIDGET_TYPES):
                    continue
                opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                named[k] = opts["default"] if "default" in opts else spec[0][0] if isinstance(spec[0], list) else ""
                print(f"pdm_comfy_api: node {nid} {n['type']}: {k} is not in the workflow, default {named[k]!r}",
                      file=sys.stderr)
        for k, v in (named or {}).items():
            if k not in NOT_INPUTS and k not in linked:
                inputs[k] = v
        if n["type"] == "PrimitiveInt":
            inputs.pop("fixed", None)
        meta = n.get("title") or n["type"]
        if nid == SEED_NODE:
            meta = "SEED"
        elif nid == save:
            meta = "SAVE"
            inputs["filename_prefix"] = "pdm_models/model"
        if a.blender and n["type"] == "PrimitiveString" and "Blender" in (n.get("title") or ""):
            inputs["value"] = a.blender
        if single and nid == SINGLE["switch"]:
            inputs["value"] = a.trellis
        graph[str(nid)] = {"class_type": n["type"], "inputs": inputs, "_meta": {"title": meta}}

    # a node nobody reads and that saves nothing is dropped: its inputs would be queued for nothing
    outputs = {"SaveImageAdvanced", "Save3DAdvanced", "PreviewImage"}
    while True:
        used = {r[0] for g in graph.values() for r in g["inputs"].values() if isinstance(r, list)}
        dead = [k for k, g in graph.items() if k not in used and g["class_type"] not in outputs]
        if not dead:
            break
        for k in dead:
            del graph[k]
    for g in graph.values():  # links to the dropped nodes
        g["inputs"] = {k: v for k, v in g["inputs"].items() if not isinstance(v, list) or v[0] in graph}
    a.out.write_text(json.dumps(graph, indent=1), encoding="utf-8")
    print(f"pdm_comfy_api: {len(graph)} nodes -> {a.out}")


if __name__ == "__main__":
    main()
