#!/usr/bin/env python3
"""Makes pixal3d_parts_auto.json out of pixal3d_4views_refine.json (ours): the same graph (Qwen refine of the four
views -> Pixal3D Multi Views -> shape -> texture -> GLB), but the four Load Image nodes are replaced by the node
PDMPartViews (comfy_nodes/pdm_parts) that cuts the character into parts itself, the prompts of the refine nodes
come from it, and after Save 3D the node PDMPartSave puts the GLB of the part into the game folder and optimizes it.

usage: python make_parts_workflow.py     (run again after the source graph or the nodes change)
"""
import copy
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOADERS = {1140: 0, 1143: 1, 1144: 2, 1147: 3}  # LoadImage -> output of PDMPartViews: front, left, back, right
REFINE = {1140: 2000, 1143: 2001, 1144: 2002, 1147: 2003}  # LoadImage -> its Refine subgraph node


def main():
    g = json.load(open(HERE / "pixal3d_4views_refine.json", encoding="utf-8"))
    nodes = {n["id"]: n for n in g["nodes"]}
    links = {l[0]: l for l in g["links"]}
    nid, lid = g["last_node_id"], g["last_link_id"]

    def new_node():
        nonlocal nid
        nid += 1
        return nid

    def new_link(a, sa, b, sb, typ):
        nonlocal lid
        lid += 1
        links[lid] = [lid, a, sa, b, sb, typ]
        return lid

    views = new_node()
    outs = [("front", "IMAGE"), ("left", "IMAGE"), ("back", "IMAGE"), ("right", "IMAGE"),
            ("prompt_front", "STRING"), ("prompt_left", "STRING"), ("prompt_back", "STRING"), ("prompt_right", "STRING"),
            ("part", "STRING"), ("model", "STRING"), ("info", "STRING")]
    node_views = {"id": views, "type": "PDMPartViews", "pos": [-3900, 300], "size": [470, 520], "flags": {},
                  "order": 0, "mode": 0, "inputs": [],
                  "outputs": [{"name": n, "type": t, "links": []} for n, t in outs],
                  "title": "PDM Part Views: the part comes by itself (Batch count 6)",
                  "properties": {"Node name for S&R": "PDMPartViews"},
                  "widgets_values": [r"C:\corsairs-remake", "pdm-game", "hero1", 0, "increment", True, -1.0, False, "python"]}
    # the old loaders go, their links move to the new node
    for old, slot in LOADERS.items():
        for l in list(links.values()):
            if l[1] == old:
                l[1], l[2] = views, slot
                node_views["outputs"][slot]["links"].append(l[0])
        del nodes[old]
    # prompts of the refine nodes come from the part
    for old, ref in REFINE.items():
        slot = 4 + LOADERS[old]
        n = nodes[ref]
        inp = next(i for i in n["inputs"] if i["name"] == "prompt")
        inp["link"] = new_link(views, slot, ref, n["inputs"].index(inp), "STRING")
        node_views["outputs"][slot]["links"].append(inp["link"])
    # previews of the raw views of the part
    prev_ids = []
    for i, v in enumerate(("front", "left", "back", "right")):
        p = new_node()
        prev_ids.append(p)
        l = new_link(views, i, p, 0, "IMAGE")
        node_views["outputs"][i]["links"].append(l)
        nodes[p] = {"id": p, "type": "PreviewImage", "pos": [-5000 + i * 250, 300], "size": [240, 280], "flags": {},
                    "order": 1, "mode": 0, "inputs": [{"name": "images", "type": "IMAGE", "link": l}], "outputs": [],
                    "title": f"raw {v} view of the part", "properties": {"Node name for S&R": "PreviewImage"},
                    "widgets_values": []}
    nodes[views] = node_views
    # after Save 3D: GLB of the part into the game
    save = new_node()
    s3d = nodes[701]
    mesh_l = new_link(701, 0, save, 0, "FILE_3D")
    s3d["outputs"][0].setdefault("links", [])
    s3d["outputs"][0]["links"] = (s3d["outputs"][0]["links"] or []) + [mesh_l]
    lp = new_link(views, 8, save, 1, "STRING")
    lm = new_link(views, 9, save, 2, "STRING")
    node_views["outputs"][8]["links"].append(lp)
    node_views["outputs"][9]["links"].append(lm)
    nodes[save] = {"id": save, "type": "PDMPartSave", "pos": [4900, 1287], "size": [470, 420], "flags": {},
                   "order": 99, "mode": 0,
                   "inputs": [{"name": "mesh", "type": "FILE_3D", "link": mesh_l},
                              {"name": "part", "type": "STRING", "link": lp},
                              {"name": "model", "type": "STRING", "link": lm}],
                   "outputs": [{"name": "info", "type": "STRING", "links": []}],
                   "title": "PDM Part Save: GLB into the game + optimize",
                   "properties": {"Node name for S&R": "PDMPartSave"},
                   "widgets_values": [r"C:\corsairs-remake", "pdm-game", 0, 0, True, "python"]}
    note = new_node()
    nodes[note] = {"id": note, "type": "Note", "pos": [-3900, -60], "size": [900, 300], "flags": {}, "order": 0,
                   "mode": 0, "inputs": [], "outputs": [], "title": "How to run (parts, automatic)",
                   "properties": {}, "widgets_values": [
                       "Once: copy tools/model3d/comfy_nodes/pdm_parts to ComfyUI/custom_nodes/ and restart ComfyUI "
                       "(install_parts.ps1 does it).\n"
                       "Run: close ENGINE.exe, press Run with Batch count = 6. Every run takes the next part "
                       "(head, torso, arm_l, arm_r, sword, legs): PDM Part Views makes the views with "
                       "tools/pdm_model_views.py, crops them, the prompts go to the Qwen refine nodes, Pixal3D makes "
                       "the 3D, PDM Part Save puts <model>_<part>.glb into data/ai_models/glb and runs "
                       "pdm_glb_optimize.py.\n"
                       "The text fields of the two PDM nodes show every step; the groups STEP 0..5 show where "
                       "the run is. The last run prints the command that installs the parts into the game.\n"
                       "To redo one part: set part_index (0..5) and Batch count 1; rerender = redraw its views."]}
    g["nodes"] = sorted(nodes.values(), key=lambda n: n["id"])
    g["links"] = sorted(links.values())
    g["last_node_id"], g["last_link_id"] = nid, lid
    g["id"] = str(uuid.uuid4())
    g["revision"] = 0
    g["groups"].append({"id": max(x["id"] for x in g["groups"]) + 1, "title": "STEP -1 · PDM: the character is cut into parts",
                        "bounding": [-5020, 240, 1180, 640], "color": "#3f789e", "font_size": 24, "flags": {}})
    json.dump(g, open(HERE / "pixal3d_parts_auto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"pixal3d_parts_auto.json: {len(g['nodes'])} nodes, {len(g['links'])} links")


if __name__ == "__main__":
    main()
