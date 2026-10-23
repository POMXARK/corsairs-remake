#!/usr/bin/env python3
"""Voices every speech of data/voice/lines.jsonl with Fun-CosyVoice3 straight from Python, without ComfyUI
(docs/voice-over.md, step 4b, ours).

The same files and rules as comfy_voice_batch.py: a speech with its file is skipped, --redo <list> voices those
again with the next seed (data/voice/tries.json), the chunks are joined by its join() into 22050 Hz mono 16 bit,
the run ends with pdm_voice_lines.py --bind. So the two scripts may voice one game in turns.

Modes of CosyVoice3, chosen per speech:
  zero_shot      the sample and its text (data/voice/refs.tsv): the closest clone;
  cross_lingual  the sample alone, when refs.tsv has no text for it;
  --instruct     inference_instruct2 with the voice of tools/voice/instruct_prompt.txt (manner, not timbre).
The "+" stress marks of tools/voice/replace.tsv are for Qwen3-TTS and ESpeech; CosyVoice reads them aloud,
so they are dropped from the text.

Runs in the environment of the CosyVoice repository (git clone --recursive FunAudioLLM/CosyVoice, its
requirements.txt), with the weights in <repo>/pretrained_models/Fun-CosyVoice3-0.5B.

usage: cosyvoice_batch.py <game dir> --repo <CosyVoice dir> [--model <weights dir>] [--only <dialog or speaker>]
         [--limit N] [--redo data/voice/redo.txt] [--instruct] [--seed 1] [--shard K/N] [--fp16]

--fp16 (ours): the model computes in half precision, usually faster on a modern GPU; listen to a sample first
(--limit 10) and compare the rtf of the log with the full precision run.

--shard K/N (ours): this process voices every N-th speech starting from K (K = 0..N-1), so N processes run side by
side on one GPU (each ~4 GB of video memory, ~6 GB of RAM). A shard skips a file that appeared meanwhile and does
not bind at the end: after all the shards are done, run pdm_voice_lines.py <game dir> --bind once.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from comfy_voice_batch import instruct_of, join, read_tsv  # noqa: E402

PROMPT = "You are a helpful assistant.<|endofprompt|>"


def seed_all(seed):
    import numpy
    import torch
    random.seed(seed)
    numpy.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--model", type=Path)
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", type=Path)
    ap.add_argument("--instruct", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--fp16", action="store_true")
    ap.add_argument("--shard", help="K/N: this process takes every N-th speech starting from K")
    a = ap.parse_args()

    voice = a.game / "data" / "voice"
    sounds = a.game / "resource" / "sounds"
    lines = [json.loads(s) for s in (voice / "lines.jsonl").read_text(encoding="utf-8").splitlines()]
    refs = read_tsv(voice / "refs.tsv")
    instruct = (TOOLS / "voice" / "instruct_prompt.txt").read_text(encoding="utf-8") if a.instruct else ""

    tries_path = voice / "tries.json"
    tries = json.loads(tries_path.read_text()) if tries_path.exists() else {}
    if a.redo:
        for out in a.redo.read_text(encoding="utf-8").split():
            (sounds / out).unlink(missing_ok=True)
            tries[out] = tries.get(out, 0) + 1
        tries_path.write_text(json.dumps(tries, indent=0, sort_keys=True))

    todo = [r for r in lines if not (sounds / r["out"]).exists()
            and (not a.only or a.only.lower() in (r["dialog"].lower(), r["speaker"].lower()))]
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        if not 0 <= k < n:
            ap.error(f"--shard {a.shard}: K counts from 0, so N shards are 0/{n} .. {n - 1}/{n}")
        todo = todo[k::n]
    if a.limit:
        todo = todo[:a.limit]
    print(f"cosyvoice_batch: {len(todo)} speeches to voice, {sum(len(r['chunks']) for r in todo)} chunks")
    if not todo:
        return

    # the package and its Matcha-TTS submodule are imported from the repository, as its example.py does
    sys.path[:0] = [str(a.repo), str(a.repo / "third_party" / "Matcha-TTS")]
    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import AutoModel
    tts = AutoModel(model_dir=str(a.model or a.repo / "pretrained_models" / "Fun-CosyVoice3-0.5B"), fp16=a.fp16)

    tmp = Path(tempfile.mkdtemp(prefix="pdm_cosy_"))
    t0 = time.time()
    for done, r in enumerate(todo, 1):
        if (sounds / r["out"]).exists():
            continue
        ref = str(sounds / r["ref"])
        parts = []
        for i, chunk in enumerate(r["chunks"]):
            text = re.sub(r"\+(?=\w)", "", chunk)
            seed_all(a.seed + tries.get(r["out"], 0) + i)
            if a.instruct:
                it = tts.inference_instruct2(text, f"You are a helpful assistant. {instruct_of(instruct, r)}"
                                             "<|endofprompt|>", ref, stream=False)
            elif refs.get(r["ref"]):
                it = tts.inference_zero_shot(text, PROMPT + refs[r["ref"]], ref, stream=False)
            else:
                it = tts.inference_cross_lingual(PROMPT + text, ref, stream=False)
            p = tmp / f"{i}.wav"
            torchaudio.save(str(p), torch.cat([j["tts_speech"] for j in it], dim=1), tts.sample_rate)
            parts.append(p)
        join(parts, sounds / r["out"])
        for p in parts:
            p.unlink()
        left = (time.time() - t0) / done * (len(todo) - done)
        print(f"{done}/{len(todo)} {r['out']}  ~{left / 60:.0f} min left", flush=True)
    if not a.shard:
        subprocess.run([sys.executable, "-I", str(TOOLS / "pdm_voice_lines.py"), str(a.game), "--bind"], check=True)


if __name__ == "__main__":
    sys.exit(main())
