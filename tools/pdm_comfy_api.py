#!/usr/bin/env python3
"""Turns the template "Pixal3D: Multi Views to 3D" (a workflow saved from ComfyUI, 3d_pixal3d_multi_views.json)
into the API graph that comfy_model_batch.py queues: tools/model3d/image_to_model_api.json.

The turnaround sheet and its four crops are replaced by four Load Image nodes titled IMAGE, IMAGE_LEFT,
IMAGE_BACK, IMAGE_RIGHT (the views of pdm_model_views.py); the background removal that follows them stays.
The sparse-structure sampler becomes SEED, the Save 3D node SAVE. Notes and previews that nothing reads are dropped.

The template "Pixal3D & TRELLIS.2: Image to Model" (3d_pixal3d_trellis2_image_to_model.json) is taken too: its
single image becomes IMAGE (the front view), --trellis turns its switch to TRELLIS.2 (Pixal3D otherwise).

usage: pdm_comfy_api.py <template.json> [--trellis] [--out tools/model3d/image_to_model_api.json]
"""
import argparse
import json
import sys
from pathlib import Path

SKIP = {"Note", "MarkdownNote", "Preview3DAdvanced"}
NOT_INPUTS = {"control_after_generate", "fixed", "upload"}
CROPS = {338: "IMAGE", 341: "IMAGE_LEFT", 342: "IMAGE_BACK", 345: "IMAGE_RIGHT"}  # ImageCropV2 of the sheet
SEED_NODE, SAVE_NODE, SHEET_NODE = 3, 372, 364
# the template "Pixal3D & TRELLIS.2: Image to Model": one image, a switch between the two models
SINGLE = {"image": 122, "switch": 316, "save": 322}


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("workflow", type=Path)
    ap.add_argument("--trellis", action="store_true", help="the single-image template: TRELLIS.2 instead of Pixal3D")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "model3d" / "image_to_model_api.json")
    a = ap.parse_args()
    ui = json.loads(a.workflow.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in ui["nodes"]}
    single = SINGLE["switch"] in nodes
    crops, save = ({}, SINGLE["save"]) if single else (CROPS, SAVE_NODE)
    sheet = SINGLE["image"] if single else SHEET_NODE
    for need in (*crops, SEED_NODE, save, sheet):
        if need not in nodes:
            sys.exit(f"pdm_comfy_api: no node {need}: this is not a template of Pixal3D (multi views, image to model)")
    source = {}  # link id -> (node, slot)
    for lid, src, slot, *_ in ui["links"]:
        source[lid] = (src, slot)

    graph = {}
    for nid, n in nodes.items():
        if n["type"] in SKIP:
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
                src, slot = source[i["link"]]
                if nodes[src]["type"] in SKIP:
                    continue
                inputs[i["name"]] = [str(src), slot]
                linked.add(i["name"])
        for k, v in (n.get("widgets_values_named") or {}).items():
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
