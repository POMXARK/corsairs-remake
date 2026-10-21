#!/usr/bin/env python3
"""Checks the voiced speeches against their text (docs/voice-over.md, step 5, ours).

Every file of data/voice/lines.jsonl that exists is heard by Whisper and compared with what it has to say:
the share of wrong letters (CER, punctuation and case left out), and the seconds per letter (too few: the
model dropped words, too many: it got stuck or mumbles). Writes
- data/voice/report.tsv: out, CER, seconds, seconds per letter, tries, what Whisper heard;
- data/voice/redo.txt: the speeches to voice again: comfy_voice_batch.py --redo takes it, with the next seed;
  after --max-tries a speech goes to data/voice/listen.txt for the ear instead.
A file already in report.tsv and not newer is not heard again.

usage: pdm_voice_check.py <game dir> [--cer 0.15] [--max-tries 3] [--model large-v3] [--device cuda|cpu]
"""
import argparse
import json
import re
import sys
import wave
from pathlib import Path

FAST, SLOW = 0.04, 0.15


def letters(t: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]", "", t.lower().replace("ё", "е"))


def cer(want: str, got: str) -> float:
    a, b = letters(want), letters(got)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--cer", type=float, default=0.15)
    ap.add_argument("--max-tries", type=int, default=3)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()

    voice = a.game / "data" / "voice"
    sounds = a.game / "resource" / "sounds"
    lines = [json.loads(s) for s in (voice / "lines.jsonl").read_text(encoding="utf-8").splitlines()]
    tries = json.loads((voice / "tries.json").read_text()) if (voice / "tries.json").exists() else {}
    report_path = voice / "report.tsv"
    old = {}
    if report_path.exists():
        for row in report_path.read_text(encoding="utf-8").splitlines()[1:]:
            f = row.split("\t")
            old[f[0]] = f
    model = None
    rows, redo, listen = [], [], []
    for r in lines:
        path = sounds / r["out"]
        if not path.exists():
            continue
        f = old.get(r["out"])
        if f is None or path.stat().st_mtime > report_path.stat().st_mtime:
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel(a.model, device=a.device,
                                     compute_type="float16" if a.device == "cuda" else "int8")
            segments, _ = model.transcribe(str(path), language="ru", beam_size=5)
            heard = " ".join(s.text.strip() for s in segments).strip()
            sec = seconds(path)
            want = " ".join(r["chunks"]).replace("+", "")
            f = [r["out"], f"{cer(want, heard):.3f}", f"{sec:.2f}", f"{sec / max(len(letters(want)), 1):.3f}",
                 str(tries.get(r["out"], 0)), heard]
            print(f"{f[1]}  {r['out']}", flush=True)
        f[4] = str(tries.get(r["out"], 0))
        rows.append(f)
        bad = float(f[1]) > a.cer or not FAST <= float(f[3]) <= SLOW
        if bad:
            (redo if int(f[4]) + 1 < a.max_tries else listen).append(r["out"])
    report_path.write_text("out\tcer\tseconds\tsec_per_letter\ttries\theard\n" +
                           "".join("\t".join(f) + "\n" for f in rows), encoding="utf-8")
    (voice / "redo.txt").write_text("".join(o + "\n" for o in redo), encoding="utf-8")
    (voice / "listen.txt").write_text("".join(o + "\n" for o in listen), encoding="utf-8")
    print(f"pdm_voice_check: {len(rows)} heard, {len(redo)} to voice again (redo.txt), "
          f"{len(listen)} for the ear (listen.txt)")


if __name__ == "__main__":
    sys.exit(main())
