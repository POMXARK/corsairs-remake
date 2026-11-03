#!/usr/bin/env python3
"""Makes pixal3d_head_template.json out of the official ComfyUI template 3d_pixal3d_trellis2_image_to_model
(comfy_template_pixal3d_trellis2.json, from github.com/Comfy-Org/workflow_templates, see
blog.comfy.org/p/trellis2-and-pixal3d-are-now-native): the graph and its settings untouched (Pixal3D on one image,
remesh solid fill 20 smooth 20, 700k faces, pec unwrap, its own texture, normal and AO baked from the high mesh),
only the input picture is the front view of hero1 and the GLB goes to 3d/hero1_head_tpl.

*_bf16.json: the same graphs on the unquantized weights pixal3d(_multiview)_bf16.safetensors, for an A/B with int8.

pixal3d_head_4views.json: the same graph, but Pixal3D Multi-View Conditioning (multiview weights, FOV 20) gets the four
views front / left / back / right (the back gives the ponytail and the nape, that one front view does not show).
The node takes any subset at fixed 90 degree steps (no 3/4 view), but front + back alone is no use: the two cameras
look along the same rays, the model cannot tell the depth and grew a second face on the nape; the sides give the depth.

usage: python make_head_template.py     then put despill_view.py of views/hero1_head/{front,left,back,right}.png into
       ComfyUI/input as hero1_head_{front,left,back,right}.png
"""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    g = json.load(open(HERE / "comfy_template_pixal3d_trellis2.json", encoding="utf-8"))
    nodes = {n["id"]: n for n in g["nodes"]}
    nodes[122]["widgets_values"][0] = "hero1_head_front.png"  # LoadImage
    nodes[322]["widgets_values"][0] = "3d/hero1_head_tpl"  # Save3DAdvanced
    json.dump(g, open(HERE / "pixal3d_head_template.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bf16(g, "pixal3d_bf16.safetensors", "pixal3d_head_template_bf16.json")
    four_views(g)


def four_views(g):
    g = copy.deepcopy(g)
    nodes = {n["id"]: n for n in g["nodes"]}
    links = {l[0]: l for l in g["links"]}
    nid, lid = g["last_node_id"], g["last_link_id"]

    def node(typ, pos, inputs, outputs, widgets):
        nonlocal nid
        nid += 1
        n = {"id": nid, "type": typ, "pos": pos, "size": [300, 120], "flags": {}, "order": 0, "mode": 0,
             "inputs": [{"name": k, "type": t, "link": None} for k, t in inputs],
             "outputs": [{"name": k, "type": t, "links": []} for k, t in outputs],
             "properties": {"Node name for S&R": typ}, "widgets_values": widgets}
        g["nodes"].append(n)
        nodes[nid] = n
        return n

    def link(src, so, dst, di):
        nonlocal lid
        lid += 1
        t = src["outputs"][so]["type"]
        g["links"].append([lid, src["id"], so, dst["id"], di, t])
        src["outputs"][so]["links"].append(lid)
        dst["inputs"][di]["link"] = lid

    def unlink(k):
        l = links.pop(k)
        g["links"].remove(l)
        nodes[l[1]]["outputs"][l[2]]["links"].remove(k)

    x, y = nodes[122]["pos"]
    mv = node("Pixal3DMultiViewConditioning", [x + 1200, y + 700],
              [("clip_vision_model", "CLIP_VISION"), ("front", "IMAGE"), ("left", "IMAGE"), ("back", "IMAGE"), ("right", "IMAGE")],
              [("positive", "CONDITIONING"), ("negative", "CONDITIONING")], [20.0])
    link(nodes[15], 0, mv, 0)
    link(nodes[302], 0, mv, 1)  # the front view after background removal and crop
    for i, side in enumerate(("left", "back", "right")):
        dy = y + 700 + 400 * i
        load = node("LoadImage", [x, dy], [], [("IMAGE", "IMAGE"), ("MASK", "MASK")], [f"hero1_head_{side}.png", "image"])
        rmbg = node("RemoveBackground", [x + 400, dy], [("bg_removal_model", nodes[192]["inputs"][0]["type"]), ("image", "IMAGE")],
                    [("mask", "MASK")], [])
        crop = node("ImageCropToMask", [x + 800, dy], [("images", "IMAGE"), ("masks", "MASK")], [("images", "IMAGE")],
                    list(nodes[312]["widgets_values"]))
        link(nodes[193], 0, rmbg, 0)
        link(load, 0, rmbg, 1)
        link(load, 0, crop, 0)
        link(rmbg, 0, crop, 1)
        link(crop, 0, mv, 2 + i)
    for k, out, sw in ((1277, 0, 314), (1280, 1, 315)):  # Pixal3D conditioning -> the Pixal3D / TRELLIS.2 switches
        unlink(k)
        link(mv, out, nodes[sw], 0)
    nodes[319]["widgets_values"][0] = "pixal3d_multiview_int8_convrot.safetensors"
    nodes[322]["widgets_values"][0] = "3d/hero1_head_4v"
    g["last_node_id"], g["last_link_id"] = nid, lid
    json.dump(g, open(HERE / "pixal3d_head_4views.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bf16(g, "pixal3d_multiview_bf16.safetensors", "pixal3d_head_4views_bf16.json")


def bf16(g, weights, name):
    """The same graph on the unquantized Pixal3D weights (11 GB): A/B against int8 with the same seeds."""
    g = copy.deepcopy(g)
    nodes = {n["id"]: n for n in g["nodes"]}
    nodes[319]["widgets_values"][0] = weights
    nodes[322]["widgets_values"][0] += "_bf16"
    json.dump(g, open(HERE / name, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
