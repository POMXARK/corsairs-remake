#!/usr/bin/env python3
"""The text of every voice sample (the greetings, resource/sounds/voices/*.wav) by Whisper (ours).

The cloning models (Qwen3-TTS, F5-TTS) copy a voice closer when they know what the sample says. Writes
data/voice/refs.tsv: <ref>\\t<text>. A row already in the file is kept: correct it by ear once, a second run
does not overwrite it. Needs faster-whisper (pip install faster-whisper), a GPU makes it minutes.

usage: pdm_voice_refs.py <game dir> [--model large-v3] [--device cuda|cpu]
"""
import argparse
import sys
from pathlib import Path


def read_tsv(path: Path) -> dict:
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                k, v = line.split("\t", 1)
                rows[k] = v
    return rows


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    from faster_whisper import WhisperModel

    out = a.game / "data" / "voice" / "refs.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = read_tsv(out)
    wavs = sorted((a.game / "resource" / "sounds" / "voices").glob("*.wav"))
    todo = [w for w in wavs if f"voices/{w.name}" not in rows]
    if todo:
        model = WhisperModel(a.model, device=a.device, compute_type="float16" if a.device == "cuda" else "int8")
        for w in todo:
            segments, _ = model.transcribe(str(w), language="ru", beam_size=5, vad_filter=False)
            rows[f"voices/{w.name}"] = " ".join(s.text.strip() for s in segments).strip()
            print(f"{w.name}\t{rows[f'voices/{w.name}']}")
    out.write_text("".join(f"{k}\t{rows[k]}\n" for k in sorted(rows)), encoding="utf-8")
    print(f"pdm_voice_refs: {len(rows)} samples, {len(todo)} new")


if __name__ == "__main__":
    sys.exit(main())
