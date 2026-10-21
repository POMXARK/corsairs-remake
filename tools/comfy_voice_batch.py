#!/usr/bin/env python3
"""Voices every speech of data/voice/lines.jsonl through the HTTP API of ComfyUI (docs/voice-over.md, ours).

The workflow is any graph of a cloning TTS exported by Workflow -> Export (API). The script finds its nodes
by their titles, so the nodes inside may be of any pack:
  REF_AUDIO  Load Audio, the sample;            REF_TEXT  the text of the sample (optional);
  TEXT       the text to say;                   SAVE      Save Audio;
  SEED       a node with a seed input (optional; the seed of every try is fixed, a run repeats);
  INSTRUCT   the description of the voice (optional, models with an instruct: tools/voice/instruct_prompt.txt).
The input each of them takes is --text-input / --seed-input (the name of the input in voice_api.json).

For every speech without its file: the samples are uploaded once to input/pdm_voices, every chunk is queued,
its audio is fetched by /view (ComfyUI may run on another machine, `--listen`), and ffmpeg makes the chunks
one file as the original sounds are: 22050 Hz mono 16 bit, a pause between chunks, the loudness levelled.
A file that exists is skipped, so a run stops and goes on; --redo <list> voices those again with the next
seed (data/voice/redo.txt of pdm_voice_check.py). Ends with pdm_voice_lines.py --bind.

usage: comfy_voice_batch.py <game dir> [--workflow tools/voice/voice_api.json] [--comfy http://127.0.0.1:8188]
         [--only <dialog or speaker>] [--limit N] [--redo data/voice/redo.txt] [--inflight 2]
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PAUSE = 0.25
RATE = 22050


class Comfy:
    def __init__(self, url):
        self.url = url.rstrip("/")

    def call(self, path, data=None):
        req = urllib.request.Request(self.url + path, json.dumps(data).encode() if data is not None else None,
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=60))

    def upload(self, path: Path, subfolder: str):
        """/upload/image takes any file into input/<subfolder>, as the Load Audio node of the UI does."""
        boundary = uuid.uuid4().hex
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
                f"Content-Type: audio/wav\r\n\r\n").encode()
        tail = (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="subfolder"\r\n\r\n{subfolder}'
                f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
                f"\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.url + "/upload/image", head + path.read_bytes() + tail,
                                     {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        urllib.request.urlopen(req, timeout=60).read()

    def queue(self, graph) -> str:
        return self.call("/prompt", {"prompt": graph, "client_id": "pdm-voice"})["prompt_id"]

    def result(self, pid):
        """The audio file of a finished prompt, None while it runs; an error of the graph stops the run."""
        h = self.call(f"/history/{pid}")
        if pid not in h:
            return None
        status = h[pid].get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI: {json.dumps(status.get('messages', []), ensure_ascii=False)[:800]}")
        for out in h[pid]["outputs"].values():
            for a in out.get("audio", []):
                return a
        raise RuntimeError(f"ComfyUI: no audio in the outputs of {pid}: is the SAVE node a Save Audio?")

    def fetch(self, a, to: Path):
        q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""),
                                    "type": a.get("type", "output")})
        to.write_bytes(urllib.request.urlopen(f"{self.url}/view?{q}", timeout=120).read())


def node(graph, title, need=True):
    for n in graph.values():
        if n.get("_meta", {}).get("title") == title:
            return n
    if need:
        sys.exit(f"comfy_voice_batch: no node titled {title} in the workflow (docs/voice-over.md, step 4)")
    return None


def read_tsv(path: Path) -> dict:
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                k, v = line.split("\t", 1)
                rows[k] = v
    return rows


def instruct_of(prompt: str, line: dict) -> str:
    """tools/voice/instruct_prompt.txt: "template: ... {voice} ...", then "<class of the model>: <the voice>"."""
    rows = dict(l.split(":", 1) for l in prompt.splitlines() if ":" in l and not l.startswith("#"))
    rows = {k.strip(): v.strip() for k, v in rows.items()}
    voice = rows.get(line.get("class", ""), rows.get("default", ""))
    return rows["template"].replace("{voice}", voice).replace("{speaker}", line["speaker"].replace("_", " "))


def join(parts, out: Path):
    """The chunks one after another with a pause, 22050 Hz mono 16 bit, the loudness levelled."""
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs, filters = [], []
    for i, p in enumerate(parts):
        inputs += ["-i", str(p)]
        pad = f",apad=pad_dur={PAUSE}" if i < len(parts) - 1 else ""
        filters.append(f"[{i}:a]aresample={RATE},aformat=channel_layouts=mono,"
                       f"silenceremove=start_periods=1:start_threshold=-50dB{pad}[a{i}]")
    chain = "".join(f"[a{i}]" for i in range(len(parts)))
    filters.append(f"{chain}concat=n={len(parts)}:v=0:a=1,loudnorm=I=-18:TP=-2,aresample={RATE}[o]")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[o]", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(out)], check=True)


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--workflow", type=Path, default=TOOLS / "voice" / "voice_api.json")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", type=Path)
    ap.add_argument("--inflight", type=int, default=2)
    ap.add_argument("--text-input", default="text")
    ap.add_argument("--seed-input", default="seed")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    voice = a.game / "data" / "voice"
    sounds = a.game / "resource" / "sounds"
    lines = [json.loads(s) for s in (voice / "lines.jsonl").read_text(encoding="utf-8").splitlines()]
    refs = read_tsv(voice / "refs.tsv")
    template = a.workflow.read_text(encoding="utf-8")
    graph0 = json.loads(template)
    for t in ("REF_AUDIO", "TEXT", "SAVE"):
        node(graph0, t)
    has_ref_text = node(graph0, "REF_TEXT", False) is not None
    has_seed = node(graph0, "SEED", False) is not None
    has_instruct = node(graph0, "INSTRUCT", False) is not None
    instruct = (TOOLS / "voice" / "instruct_prompt.txt").read_text(encoding="utf-8") if has_instruct else ""
    if has_ref_text and not refs:
        sys.exit("comfy_voice_batch: the workflow has REF_TEXT but data/voice/refs.tsv is empty: run pdm_voice_refs.py")

    # tries of a speech: its seed is --seed + the tries, so a redo gives another take and a rerun the same one
    tries_path = voice / "tries.json"
    tries = json.loads(tries_path.read_text()) if tries_path.exists() else {}
    if a.redo:
        for out in a.redo.read_text(encoding="utf-8").split():
            (sounds / out).unlink(missing_ok=True)
            tries[out] = tries.get(out, 0) + 1
        tries_path.write_text(json.dumps(tries, indent=0, sort_keys=True))

    todo = [r for r in lines if not (sounds / r["out"]).exists()
            and (not a.only or a.only.lower() in (r["dialog"].lower(), r["speaker"].lower()))]
    if a.limit:
        todo = todo[:a.limit]
    print(f"comfy_voice_batch: {len(todo)} speeches to voice, {sum(len(r['chunks']) for r in todo)} chunks")
    if not todo:
        return

    comfy = Comfy(a.comfy)
    for ref in sorted({r["ref"] for r in todo}):
        comfy.upload(sounds / ref, "pdm_voices")

    jobs = [(r, i, c) for r in todo for i, c in enumerate(r["chunks"])]
    tmp = Path(tempfile.mkdtemp(prefix="pdm_voice_"))
    parts, running, done, t0 = {}, {}, 0, time.time()
    while jobs or running:
        while jobs and len(running) < a.inflight:
            r, i, text = jobs.pop(0)
            g = json.loads(template)
            node(g, "REF_AUDIO")["inputs"]["audio"] = "pdm_voices/" + Path(r["ref"]).name
            node(g, "TEXT")["inputs"][a.text_input] = text
            node(g, "SAVE")["inputs"]["filename_prefix"] = f"pdm_voice/{r['dialog'].lower()}_{r['node']}_{i}"
            if has_ref_text:
                node(g, "REF_TEXT")["inputs"][a.text_input] = refs.get(r["ref"], "")
            if has_seed:
                node(g, "SEED")["inputs"][a.seed_input] = a.seed + tries.get(r["out"], 0)
            if has_instruct:
                node(g, "INSTRUCT")["inputs"][a.text_input] = instruct_of(instruct, r)
            running[comfy.queue(g)] = (r, i)
        time.sleep(0.3)
        for pid in list(running):
            audio = comfy.result(pid)
            if audio is None:
                continue
            r, i = running.pop(pid)
            p = tmp / f"{r['dialog']}_{r['node']}_{i}{Path(audio['filename']).suffix}"
            comfy.fetch(audio, p)
            got = parts.setdefault(r["out"], {})
            got[i] = p
            if len(got) == len(r["chunks"]):
                join([got[k] for k in range(len(r["chunks"]))], sounds / r["out"])
                for f in got.values():
                    f.unlink()
                del parts[r["out"]]
                done += 1
                left = (time.time() - t0) / done * (len(todo) - done)
                print(f"{done}/{len(todo)} {r['out']}  ~{left / 60:.0f} min left", flush=True)
    subprocess.run([sys.executable, "-I", str(TOOLS / "pdm_voice_lines.py"), str(a.game), "--bind"], check=True)


if __name__ == "__main__":
    sys.exit(main())
