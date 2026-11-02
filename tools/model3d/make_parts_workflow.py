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
            ("part", "STRING"), ("model", "STRING"), ("info", "STRING"),
            ("sheet", "IMAGE"), ("prompt_sheet", "STRING")]
    node_views = {"id": views, "type": "PDMPartViews", "pos": [-3900, 300], "size": [470, 520], "flags": {},
                  "order": 0, "mode": 0, "inputs": [],
                  "outputs": [{"name": n, "type": t, "links": []} for n, t in outs],
                  "title": "PDM Part Views: the part comes by itself (Batch count 6)",
                  "properties": {"Node name for S&R": "PDMPartViews"},
                  "widgets_values": [r"C:\corsairs-remake", "pdm-game", "hero1", 0, "increment", True, -1.0, False, "python", 1024]}
    # the old loaders go, their links move to the new node
    for old, slot in LOADERS.items():
        for l in list(links.values()):
            if l[1] == old:
                l[1], l[2] = views, slot
                node_views["outputs"][slot]["links"].append(l[0])
        del nodes[old]
    # ONE Qwen pass on a 2x2 sheet of the four views (front, left / back, right), then the sheet is cut back: the four
    # views agree with each other (the independent redraws of ComfyUI_00007 hid the ears under hair, doubled the lips)
    main = REFINE[1140]
    n = nodes[main]
    i_prompt = next(i for i in n["inputs"] if i["name"] == "prompt")
    i_img = next(i for i in n["inputs"] if i["name"] == "images.image_1")
    links.pop(i_prompt["link"], None)
    links.pop(i_img["link"], None)
    i_prompt["link"] = new_link(views, 12, main, n["inputs"].index(i_prompt), "STRING")
    i_img["link"] = new_link(views, 11, main, n["inputs"].index(i_img), "IMAGE")
    node_views["outputs"][12]["links"].append(i_prompt["link"])
    node_views["outputs"][11]["links"].append(i_img["link"])
    n["widgets_values"][7] = n["widgets_values"][8] = 2048  # width, height of the sheet (sheet_cell 1024 x 2)
    n["title"] = "Refine the 2x2 sheet of the part (Qwen Image 2.1 Edit)"
    split = new_node()
    nodes[split] = {"id": split, "type": "PDMSheetSplit", "pos": [n["pos"][0] + 500, n["pos"][1]], "size": [260, 120],
                    "flags": {}, "order": 5, "mode": 0, "inputs": [{"name": "sheet", "type": "IMAGE", "link": None}],
                    "outputs": [{"name": v, "type": "IMAGE", "links": []} for v in ("front", "left", "back", "right")],
                    "title": "PDM Sheet Split (2x2 -> 4 views)", "properties": {"Node name for S&R": "PDMSheetSplit"},
                    "widgets_values": []}
    nodes[split]["inputs"][0]["link"] = new_link(main, 0, split, 0, "IMAGE")
    n["outputs"][0]["links"] = [nodes[split]["inputs"][0]["link"]]
    # the consumers of the four old refine nodes now take the views of the split node
    for old, ref in REFINE.items():
        for l in list(links.values()):
            if l[1] == ref and l[3] != split and l[3] not in REFINE.values():
                l[1], l[2] = split, LOADERS[old]
                nodes[split]["outputs"][LOADERS[old]]["links"].append(l[0])
    for ref in list(REFINE.values())[1:]:  # the other three refine nodes are not needed
        for l in list(links.values()):
            if l[3] == ref or l[1] == ref:
                links.pop(l[0], None)
        del nodes[ref]
    for o in node_views["outputs"]:
        o["links"] = [x for x in o["links"] if x in links]
    # refine_prompt (widget 2): the VLM of the subgraph (Qwen3.5 PE) looks at the view and rewrites our prompt by what it shows
    # pdm_parts patches flash_attention_decode_gqa (contiguous q/k/v, torch fallback), so the VLM can run again
    for ref in [REFINE[1140]]:
        nodes[ref]["widgets_values"][2] = True
    # TextGenerate wrote up to 16256 tokens (9 minutes at 5 tokens/s in ComfyUI_00009); the description took 2916 tokens, cut at 400 the sheet came out as a collage of tiny heads
    for sg in g["definitions"]["subgraphs"]:
        for n in sg["nodes"]:
            if n["type"] == "TextGenerate":
                n["widgets_values"][1] = 4096
    # DecimateMesh (186) 700000 faces -> UnwrapMesh cut them into 10 358 tiny charts, the 4096 atlas was confetti
    # (the log of the first run). 60000 faces unwrap into big charts; the detail comes from reference_mesh / normal map.
    nodes[186]["widgets_values"][0] = 60000
    # UnwrapMesh (196): "pec" cuts the dense voxel-born mesh into hundreds of small charts (the atlas of ComfyUI_00007 is
    # confetti); "adaptive" (CPU) is slower and should give fewer, bigger charts. Not checked in ComfyUI yet.
    nodes[196]["widgets_values"][0] = "adaptive"
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
    # the four views that go into Pixal3D (cropped, background removed) also go to the save node: it paints the texture
    save_inputs = []
    upl = new_node()
    nodes[upl] = {"id": upl, "type": "UpscaleModelLoader", "pos": [4000, 1500], "size": [270, 60], "flags": {}, "order": 0,
                  "mode": 0, "inputs": [], "outputs": [{"name": "UPSCALE_MODEL", "type": "UPSCALE_MODEL", "links": []}],
                  "title": "upscale model", "properties": {"Node name for S&R": "UpscaleModelLoader"},
                  "widgets_values": ["4x-UltraSharp.pth"]}
    for inp in nodes[324]["inputs"]:
        if inp["name"] in ("front", "left", "back", "right"):
            src_link = links[inp["link"]]
            # 4x-UltraSharp: the views are 1024 px, a pore is about one pixel; the texture is painted from the 4096 px versions
            up = new_node()
            l_in = new_link(src_link[1], src_link[2], up, 1, "IMAGE")
            nodes[src_link[1]]["outputs"][src_link[2]]["links"].append(l_in)
            l_mod = new_link(upl, 0, up, 0, "UPSCALE_MODEL")
            nodes[upl]["outputs"][0]["links"].append(l_mod)
            nodes[up] = {"id": up, "type": "ImageUpscaleWithModel", "pos": [4300, 1300 + 120 * len(save_inputs)], "size": [250, 50],
                         "flags": {}, "order": 98, "mode": 0,
                         "inputs": [{"name": "upscale_model", "type": "UPSCALE_MODEL", "link": l_mod},
                                    {"name": "image", "type": "IMAGE", "link": l_in}],
                         "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": []}],
                         "title": f"4x {inp['name']} for the texture", "properties": {"Node name for S&R": "ImageUpscaleWithModel"},
                         "widgets_values": []}
            lk = new_link(up, 0, save, 3 + len(save_inputs), "IMAGE")
            nodes[up]["outputs"][0]["links"].append(lk)
            save_inputs.append({"name": inp["name"], "type": "IMAGE", "link": lk})
    nodes[save] = {"id": save, "type": "PDMPartSave", "pos": [4900, 1287], "size": [470, 420], "flags": {},
                   "order": 99, "mode": 0,
                   "inputs": [{"name": "mesh", "type": "FILE_3D", "link": mesh_l},
                              {"name": "part", "type": "STRING", "link": lp},
                              {"name": "model", "type": "STRING", "link": lm}] + save_inputs,
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
