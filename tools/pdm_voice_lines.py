#!/usr/bin/env python3
"""The speech of the NPCs for a neural voice-over (docs/voice-over.md, ours).

Reads what the converters wrote, so every key is the one the game uses:
- program/data/pdm_logic.c: PdmDialogs.<dialog>.<node>.text, Pdm_SetDialog("<character>", "<dialog>");
- program/data/pdm_data.c: PdmCharacters.<character>.id / .model / .dialog;
- program/data/pdm_voices.c: PdmCharacters.<character>.greeting, the sample of the voice (SOUNDS/<id>.wav).

Writes
- data/voice/lines.jsonl: a line per speech of a node: dialog, node, speaker, ref (the greeting), the text
  as the dialog shows it, the chunks to voice (the text made speakable, long speech cut by sentences), out;
- program/data/pdm_voice_lines.c: PdmVoiceLines.<dialog>.<node> = "voices\\lines\\..." for the files
  that exist in resource/sounds, so a speech without its file stays silent;
- data/voice/lines_report.txt: the speakers found by the file name and the borrowed samples.

The speaker of a dialog: Pdm_SetDialog, else the character whose id starts the name of the .d file
(DIALOGS/<id>_<dialog>.d). The sample: its greeting, else the greeting of a character of the same model.

Optional: --llm <ollama url> makes the chunks speakable with a local model (tools/voice/llm_prep_prompt.txt);
the answers are kept in data/voice/llm_cache.jsonl, so a second run asks nothing and writes the same files.

usage: pdm_voice_lines.py <game dir> [--bind] [--llm http://127.0.0.1:11434] [--llm-model qwen3:14b]
  --bind  only rewrites program/data/pdm_voice_lines.c (after new voice files came)
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
# a chunk longer than this is cut by sentences: a long one makes the models lose the pace and drop words
CHUNK = 250

UNITS = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять",
         "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
         "семнадцать", "восемнадцать", "девятнадцать"]
TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят",
        "девяносто"]
HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот",
            "девятьсот"]


def words_999(n: int, female=False) -> list:
    out = [HUNDREDS[n // 100]]
    n %= 100
    if n < 20:
        out.append(UNITS[n])
    else:
        out += [TENS[n // 10], UNITS[n % 10]]
    if female and out[-1] in ("один", "два"):
        out[-1] = {"один": "одна", "два": "две"}[out[-1]]
    return [w for w in out if w]


def number_words(n: int) -> str:
    """A whole number in words, nominative (enough for the sums and counts of the dialogs)."""
    if n == 0:
        return "ноль"
    out = []
    for size, forms, female in ((10 ** 6, ("миллион", "миллиона", "миллионов"), False),
                                (1000, ("тысяча", "тысячи", "тысяч"), True)):
        if n >= size:
            k = n // size
            n %= size
            last = k % 100
            form = forms[2] if 11 <= last <= 14 else forms[0] if k % 10 == 1 else \
                forms[1] if 2 <= k % 10 <= 4 else forms[2]
            out += words_999(k, female) + [form]
    out += words_999(n)
    return " ".join(out)


def stress_table() -> list:
    """tools/voice/replace.tsv: <what>\\t<how to say it>, e.g. names with a stress mark."""
    path = TOOLS / "voice" / "replace.tsv"
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "\t" in line:
                rows.append(tuple(line.split("\t", 1)))
    return rows


def speakable(text: str, replace: list) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s-{1,2}\s", " — ", t)
    t = re.sub(r"\d+", lambda m: number_words(int(m.group())), t)
    for what, how in replace:
        t = t.replace(what, how)
    return t


def chunks(text: str) -> list:
    if len(text) <= CHUNK:
        return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if cur and len(cur) + 1 + len(s) > CHUNK:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    return out + [cur] if cur else out


class Llm:
    """The chunks made speakable by a local model over the Ollama API, cached by the text."""

    def __init__(self, url, model, cache: Path):
        self.url, self.model, self.cache = url, model, cache
        self.prompt = (TOOLS / "voice" / "llm_prep_prompt.txt").read_text(encoding="utf-8")
        self.known = {}
        if cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                self.known[r["md5"]] = r["out"]

    def __call__(self, text: str) -> str:
        h = hashlib.md5(text.encode()).hexdigest()
        if h not in self.known:
            body = {"model": self.model, "system": self.prompt, "prompt": text, "stream": False,
                    "options": {"temperature": 0, "seed": 1}}
            req = urllib.request.Request(self.url + "/api/generate", json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
            out = json.load(urllib.request.urlopen(req, timeout=300))["response"].strip()
            # a model that thinks aloud or answers too much is not trusted: the text stays as it was
            out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
            if not out or abs(len(out) - len(text)) > len(text) * 0.6 + 20:
                out = text
            self.known[h] = out
            with self.cache.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"md5": h, "in": text, "out": out}, ensure_ascii=False) + "\n")
        return self.known[h]


def attrs(path: Path, pattern: str):
    return re.findall(pattern, path.read_text(encoding="utf-8"))


def read_game(game: Path):
    data = game / "program" / "data"
    logic = data / "pdm_logic.c"
    dialogs, source, order = {}, {}, []
    current = None
    for line in logic.read_text(encoding="utf-8").splitlines():
        m = re.match(r"// DIALOGS/(.+)\.d$", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r'\tPdmDialogs\.(\w+)\.(\w+)\.text = "(.*)";$', line)
        if m:
            dk, node, text = m.groups()
            if dk not in dialogs:
                dialogs[dk] = {}
                source[dk] = current
                order.append(dk)
            dialogs[dk][node] = text
    speaker = {}
    for ck, dk in attrs(logic, r'Pdm_SetDialog\("(\w+)", "(\w+)"\)'):
        speaker.setdefault(dk, ck)
    ids = dict((k, v) for k, v in attrs(data / "pdm_data.c", r'\tPdmCharacters\.(\w+)\.id = "(.*)";'))
    models = dict(attrs(data / "pdm_data.c", r'\tPdmCharacters\.(\w+)\.model = "(.*)";'))
    greeting = dict(attrs(data / "pdm_voices.c", r'\tPdmCharacters\.(\w+)\.greeting = "(.*)";'))
    return dialogs, source, order, speaker, ids, models, greeting


def by_file_name(src: str, ids: dict):
    """DIALOGS/<id>_<dialog>.d: the longest id of a character the name starts with."""
    best = None
    for ck, cid in ids.items():
        if src.lower().startswith(cid.lower() + "_") and (best is None or len(cid) > len(ids[best])):
            best = ck
    return best


def model_class(model: str) -> str:
    """CHARACTERS\\Citizen6.cff, negotiant4_dr.cff -> citizen, negotiant: one class, one kind of voice."""
    return re.match(r"[a-z]*", Path(model.replace("\\", "/")).stem.lower()).group()


def bind(game: Path, lines: list):
    sounds = game / "resource" / "sounds"
    out = ["// Generated by tools/pdm_voice_lines.py: the voice of the speech of a node of a dialog, said",
           "// after the greeting (docs/voice-over.md); only the files that exist", "object PdmVoiceLines;", "",
           "void PdmVoiceLines_Init()", "{"]
    n = 0
    for r in lines:
        if (sounds / r["out"]).exists():
            out.append(f'\tPdmVoiceLines.{r["dialog"]}.{r["node"]} = "{r["out"].replace("/", chr(92))}";')
            n += 1
    out += ["}", ""]
    path = game / "program" / "data" / "pdm_voice_lines.c"
    text = "\n".join(out)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--bind", action="store_true")
    ap.add_argument("--llm")
    ap.add_argument("--llm-model", default="qwen3:14b")
    a = ap.parse_args()
    voice = a.game / "data" / "voice"
    voice.mkdir(parents=True, exist_ok=True)
    jsonl = voice / "lines.jsonl"

    if a.bind:
        lines = [json.loads(s) for s in jsonl.read_text(encoding="utf-8").splitlines()]
        print(f"pdm_voice_lines: {bind(a.game, lines)} of {len(lines)} speeches have a voice")
        return

    dialogs, source, order, speaker, ids, models, greeting = read_game(a.game)
    # a sample of every class of model, for the characters without a greeting: the first by key
    class_ref = {}
    for ck in sorted(greeting):
        class_ref.setdefault(model_class(models.get(ck, "")), ck)
    replace = stress_table()
    llm = Llm(a.llm, a.llm_model, voice / "llm_cache.jsonl") if a.llm else None
    report, lines = [], []
    for dk in order:
        ck = speaker.get(dk)
        if ck is None:
            ck = by_file_name(source[dk] or "", ids)
            report.append(f"speaker by the file name: {dk} -> {ck}")
        if ck is None:
            report.append(f"no speaker: {dk}")
            continue
        ref_ck = ck if ck in greeting else class_ref.get(model_class(models.get(ck, "")))
        if ref_ck is None:
            report.append(f"no sample: {dk} ({ck}, {models.get(ck)})")
            continue
        if ref_ck != ck:
            report.append(f"borrowed sample: {ck} speaks with the voice of {ref_ck}")
        for node, text in dialogs[dk].items():
            if not text.strip():
                continue
            parts = chunks(speakable(text, replace))
            if llm:
                parts = [llm(p) for p in parts]
            lines.append({"dialog": dk, "node": node, "speaker": ck, "class": model_class(models.get(ck, "")),
                          "ref": greeting[ref_ck].replace("\\", "/"), "text": text, "chunks": parts,
                          "out": f"voices/lines/{dk.lower()}/{node.lower()}.wav"})
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines)
    if not jsonl.exists() or jsonl.read_text(encoding="utf-8") != text:
        jsonl.write_text(text, encoding="utf-8")
    report = list(dict.fromkeys(report))
    (voice / "lines_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    n = bind(a.game, lines)
    speakers = len({r["speaker"] for r in lines})
    print(f"pdm_voice_lines: {len(lines)} speeches of {speakers} speakers, "
          f"{sum(len(r['chunks']) for r in lines)} chunks, {n} voiced, {len(report)} notes in lines_report.txt")


if __name__ == "__main__":
    sys.exit(main())
