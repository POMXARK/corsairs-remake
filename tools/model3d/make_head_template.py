#!/usr/bin/env python3
"""Makes pixal3d_head_template.json out of the official ComfyUI template 3d_pixal3d_trellis2_image_to_model
(comfy_template_pixal3d_trellis2.json, from github.com/Comfy-Org/workflow_templates, see
blog.comfy.org/p/trellis2-and-pixal3d-are-now-native): the graph and its settings untouched (Pixal3D on one image,
remesh solid fill 20 smooth 20, 700k faces, pec unwrap, its own texture, normal and AO baked from the high mesh),
only the input picture is the front view of hero1 and the GLB goes to 3d/hero1_head_tpl.

usage: python make_head_template.py     then put views/hero1_head/front.png into ComfyUI/input as hero1_head_front.png
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    g = json.load(open(HERE / "comfy_template_pixal3d_trellis2.json", encoding="utf-8"))
    nodes = {n["id"]: n for n in g["nodes"]}
    nodes[122]["widgets_values"][0] = "hero1_head_front.png"  # LoadImage
    nodes[322]["widgets_values"][0] = "3d/hero1_head_tpl"  # Save3DAdvanced
    json.dump(g, open(HERE / "pixal3d_head_template.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
