#!/usr/bin/env python3
"""Writes tools/model3d/refine_api.json for comfy_view_refine.py: the API graph of the ComfyUI template
"Qwen Image 2.1 image edit" without the prompt enhancer and the custom size (the subgraph of the template is
flattened by hand: a UI export with a subgraph cannot be turned into an API graph by a script that does not
know the nodes inside).

usage: pdm_comfy_refine_graph.py [--out tools/model3d/refine_api.json] [--steps 25] [--resolution 0]
         [--unet ...] [--clip ...] [--vae ...]
The model names are those of the template; the others are taken from Models of the ComfyUI.
"""
import argparse
import json
from pathlib import Path


def node(cls, title, **inputs):
    return {"class_type": cls, "_meta": {"title": title}, "inputs": inputs}


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "model3d" / "refine_api.json")
    ap.add_argument("--steps", type=int, default=25, help="the official pipeline uses 40-50 with euler")
    ap.add_argument("--resolution", type=int, default=0, help="a total pixel budget; 0 keeps the size of the view")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--unet", default="qwen_image_2.1_int8_convrot.safetensors")
    ap.add_argument("--clip", default="qwen3vl_8b_int8_convrot.safetensors")
    ap.add_argument("--vae", default="qwen_image_2.1_vae_bf16.safetensors")
    a = ap.parse_args()
    g = {
        "1": node("LoadImage", "IMAGE", image="example.png"),
        "2": node("UNETLoader", "UNET", unet_name=a.unet, weight_dtype="default"),
        "3": node("CLIPLoader", "CLIP", clip_name=a.clip, type="qwen_image", device="default"),
        "4": node("VAELoader", "VAE", vae_name=a.vae),
        "5": node("QwenImage21Cache", "CACHE", model=["2", 0], device="auto", dtype="default"),
        "6": node("TextEncodeQwenImage21", "PROMPT", clip=["3", 0], vae=["4", 0], prompt="",
                  negative_prompt="", resolution=a.resolution, **{"images.image_1": ["1", 0]}),
        "7": node("KSampler", "SEED", model=["5", 0], positive=["6", 0], negative=["6", 1],
                  latent_image=["6", 2], seed=a.seed, steps=a.steps, cfg=1, sampler_name="euler",
                  scheduler="simple", denoise=1),
        "8": node("VAEDecode", "DECODE", samples=["7", 0], vae=["4", 0]),
        "9": node("SaveImageAdvanced", "SAVE", images=["8", 0], filename_prefix="pdm_models/refined",
                  format="png", **{"format.bit_depth": "8-bit", "format.input_color_space": "sRGB"}),
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(g, indent=1), encoding="utf-8")
    print(f"pdm_comfy_refine_graph: {a.out}")


if __name__ == "__main__":
    main()
