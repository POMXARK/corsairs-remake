#!/usr/bin/env python3
"""Convert the whole RESOURCE folder of the original Sea Dogs / «Корсары» (PDM 1.061, Storm 1) for Storm Engine.

usage: pdm2storm.py <PDM_dir | PDM/RESOURCE> <out_dir> [--only stage,...] [-j N]

Stages (all by default):
  textures  .tf -> .tx, .tga without a .tf twin -> .tx          (out/resource/...)
  models    .cff -> .gm                                          (out/resource/...)
  copy      every other file as-is (sounds, ini, texts, ...)     (out/resource/...)
  actions   .a -> decoded text + parsed commands                 (out/data/actions/*.json)
  dialogs   .d -> nodes/links/actions                            (out/data/dialogs/*.json)
  tables    .idf -> objects with name/value fields               (out/data/tables/*.json)
  desc      .def -> ship part locators                           (out/data/desc/*.json)
  characters .mtx -> character cards                             (out/data/characters/*.json)
  ships     .shp -> ship profiles: class, crew, HP, skills, cargo  (out/data/ships/*.json)
  quests    .ql -> story line: quests with condition and action  (out/data/quests/*.json)

The engine reads out/resource; out/data is UTF-8 JSON for the game scripts and for people.
.ani, .sls, .dlm, .dlt are copied raw until their layouts are known (see docs/pdm-formats.md).
A summary goes to stdout and out/convert-report.json.
"""
import argparse
import json
import os
import re
import shlex
import struct
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tf2tx  # noqa: E402
from a_decode import decode as a_decode  # noqa: E402

TEXTURE_EXT = {".tf", ".tga"}
MODEL_EXT = {".cff"}
# converted files do not go to out/resource; everything else is copied for the engine and the scripts
CONVERTED_EXT = TEXTURE_EXT | MODEL_EXT | {".a"}
STAGES = ["textures", "models", "copy", "actions", "dialogs", "tables", "desc", "characters", "ships", "quests"]


# ---------- textures ----------

def tga_to_tx(src: Path, dst: Path):
    """Uncompressed true-colour TGA (16-bit A1R5G5B5 or 32-bit BGRA) -> .tx A8R8G8B8, one mip."""
    data = src.read_bytes()
    id_len, cmap_type, img_type = data[0], data[1], data[2]
    w, h, bpp, desc = struct.unpack_from("<HHBB", data, 12)
    if img_type != 2 or cmap_type != 0:
        raise ValueError(f"TGA type {img_type}/{cmap_type} is not supported")
    off = 18 + id_len
    alpha_bits = desc & 0x0F
    if bpp == 16:
        raw = data[off:off + w * h * 2]
        px = bytearray()
        for i in range(0, len(raw), 2):
            v = raw[i] | raw[i + 1] << 8
            r, g, b = (v >> 10) & 31, (v >> 5) & 31, v & 31
            # as in .tf the bit means transparent: it is clear in all 305 16-bit TGA of PDM, which are opaque UI
            a = 0 if alpha_bits and v & 0x8000 else 255
            px += bytes([b << 3 | b >> 2, g << 3 | g >> 2, r << 3 | r >> 2, a])
    elif bpp == 32:
        px = bytearray(data[off:off + w * h * 4])
        if not alpha_bits:
            px[3::4] = b"\xff" * (w * h)
    elif bpp == 24:
        raw = data[off:off + w * h * 3]
        px = bytearray(w * h * 4)
        px[0::4], px[1::4], px[2::4], px[3::4] = raw[0::3], raw[1::3], raw[2::3], b"\xff" * (w * h)
    else:
        raise ValueError(f"TGA {bpp} bpp is not supported")
    if len(px) != w * h * 4:
        raise ValueError("TGA pixel data is truncated")
    if not desc & 0x20:  # bottom-up rows, .tx is top-down
        row = w * 4
        px = b"".join(px[y * row:(y + 1) * row] for y in range(h - 1, -1, -1))
    dst.write_bytes(struct.pack("<6i", 0, w, h, 1, 21, w * h * 4) + bytes(px))


def convert_texture(src: Path, dst: Path):
    if src.suffix.lower() == ".tf":
        ok, err = tf2tx.convert_tf_to_tx(str(src), str(dst))
        if not ok:
            raise ValueError(err)
    else:
        tga_to_tx(src, dst)


def convert_model(src: Path, dst: Path):
    import cff2gm  # pulls engine/demos/common/storm_formats, only needed here
    if not cff2gm.cff_to_gm(src, dst):
        raise ValueError("no meshes")


def _job(args):
    kind, src, dst = args
    try:
        (convert_texture if kind == "textures" else convert_model)(Path(src), Path(dst))
        return kind, src, None
    except Exception as e:  # noqa: BLE001 - report every broken file and go on
        return kind, src, f"{type(e).__name__}: {e}"


# ---------- game data ----------

def text(data: bytes) -> str:
    return data.decode("cp1251").replace("\r\n", "\n")


def parse_actions(src: Path):
    """Decoded .a: one command per line, '/' starts a comment (CORE.dll skips such lines)."""
    body = text(a_decode(src.read_bytes()))
    commands = []
    for line in body.splitlines():
        line = line.strip().rstrip("\x00")
        if not line or line.startswith("/"):
            continue
        try:
            words = shlex.split(line, posix=True)
        except ValueError:
            words = line.split()
        commands.append({"op": words[0].upper(), "args": words[1:], "line": line})
    return {"source": src.name, "commands": commands}


TAG = re.compile(r"<([NLAT]) (.*?)>", re.S)


def parse_dialog(src: Path):
    """.d: <N node>, then <T text>; links <L id,a,b,target> with optional <A action> and <T text>."""
    nodes, node, link = [], None, None
    for tag, value in TAG.findall(text(src.read_bytes())):
        value = value.strip()
        if tag == "N":
            node, link = {"id": value, "text": "", "links": []}, None
            nodes.append(node)
        elif node is None:
            continue
        elif tag == "L":
            lid, *flags, target = [p.strip() for p in value.split(",")]
            link = {"id": lid, "flags": [int(f) if f.isdigit() else f for f in flags], "to": target,
                    "action": None, "text": ""}
            node["links"].append(link)
        elif tag == "A":
            (link if link else node)["action"] = value
        elif tag == "T":
            (link if link else node)["text"] = value
    return {"source": src.name, "nodes": nodes}


def cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("cp1251", "replace")


def parse_idf(src: Path):
    """.idf: u32, u32 count, u32; per object u32 n + n x (u32 heap junk, name[64], value[64])."""
    data = src.read_bytes()
    _, count, _ = struct.unpack_from("<3I", data, 0)
    off, objects = 12, []
    for _ in range(count):
        (n,) = struct.unpack_from("<I", data, off)
        off += 4
        fields = []
        for _ in range(n):
            fields.append([cstr(data[off + 4:off + 68]), cstr(data[off + 68:off + 132])])
            off += 132
        objects.append(fields)
    if off != len(data):
        raise ValueError(f"{len(data) - off} bytes left after {count} objects")
    return {"source": src.name, "objects": objects}


DEF_CLASS = {200: "Model", 201: "Rey", 202: "Sail", 203: "Cannon", 204: "Flag", 205: "Waterline",
             206: "Patch", 207: "CannonSet", 208: "AllCannons", 209: "ShipTrace"}


def parse_def(src: Path):
    """.def (ship description): u32 count + count x 296-byte items (DEF.bt of seadogs-file-formats)."""
    data = src.read_bytes()
    (count,) = struct.unpack_from("<I", data, 0)
    if 4 + count * 296 != len(data):
        raise ValueError(f"size {len(data)} != 4 + {count}*296")
    items = []
    for i in range(count):
        o = 4 + i * 296
        idx, cls, idx2 = struct.unpack_from("<3I", data, o)
        pos = struct.unpack_from("<3f", data, o + 268)
        rot = struct.unpack_from("<3f", data, o + 280)
        (link,) = struct.unpack_from("<i", data, o + 292)
        items.append({"index": idx, "class": DEF_CLASS.get(cls, cls), "sub": idx2, "file": cstr(data[o + 12:o + 268]),
                      "pos": [round(v, 5) for v in pos], "rot": [round(v, 5) for v in rot], "link": link})
    return {"source": src.name, "items": items}


def _unknown(data: bytes, known):
    """Non-empty dwords outside the known fields, kept for further reverse engineering (0xCCCCCCCC = MSVC fill)."""
    out = {}
    for off in range(0, len(data), 4):
        if any(o <= off < o + n for o, n in known):
            continue
        (v,) = struct.unpack_from("<i", data, off)
        if v not in (0, -0x33333334):
            out[f"0x{off:03x}"] = v
    return out


# label order of the CHARACTER_EDITOR form; the 9 ints follow it
SKILLS = ["sailing", "repair", "commerce", "accuracy", "reload", "coordination", "combat", "defence", "board_range"]
OFFICER_RANKS = ["FIRST_MATE", "BOATSWAIN", "MASTER_PURSER", "MASTER_GUNNER", "SURGEON", "CARPENTER"]


def parse_mtx(src: Path):
    """.mtx: 2384-byte dump that CHARACTER_EDITOR builds field by field (FUN_10003dc0); u32 0 is the size."""
    d = src.read_bytes()
    i = lambda o: struct.unpack_from("<i", d, o)[0]  # noqa: E731
    if len(d) != 0x950 or i(0) != 0x950:
        raise ValueError("not a 2384-byte character card")
    rank = i(0x934)
    known = [(0, 12), (0x58, 32), (0x78, 32), (0xa8, 8), (0x2b4, 4), (0x2c8, 32), (0x2e8, 32), (0x308, 64),
             (0x348, 64), (0x388, 4), (0x734, 36), (0x934, 4)]
    return {"source": src.name, "name": cstr(d[0x58:0x78]), "id": cstr(d[0x78:0x98]),
            "nation": i(0xa8),  # index in WORLDS/nations.idf
            "relation": i(0xac),  # index in WORLDS/relations.idf
            "kind": i(0x2b4),  # "character is": 0 most NPC, 2 captains with a ship, 1 three quest NPC
            "model": cstr(d[0x2c8:0x2e8]), "ship": cstr(d[0x2e8:0x308]), "dialog": cstr(d[0x308:0x348]),
            "address": {"island": cstr(d[0x348:0x388]), "location": i(0x388)},
            "skills": dict(zip(SKILLS, struct.unpack_from("<9i", d, 0x734))),
            "officer_rank": OFFICER_RANKS[rank] if 0 <= rank < len(OFFICER_RANKS) else None,
            "unknown": _unknown(d, known)}


def parse_shp(src: Path):
    """.shp: u32 player skill + 0x2f0-byte profile + 0x24-byte crew block, written by TOOLS_SHIPEDITOR (FUN_10004ad0)."""
    d = src.read_bytes()
    i = lambda o: struct.unpack_from("<i", d, o)[0]  # noqa: E731
    if len(d) != 792:  # reserved/empty.shp is a 740-byte template of an older editor (April 2000)
        raise ValueError(f"{len(d)} bytes, a ship profile is 792")
    cargo = struct.unpack_from("<128i", d, 0x90)  # indices of WORLDS/Goods.idf
    known = [(0, 4), (0x08, 32), (0x28, 32), (0x4c, 4), (0x5c, 4), (0x84, 4), (0x90, 512), (0x300, 12)]
    return {"source": src.name, "name": cstr(d[0x08:0x28]), "class": cstr(d[0x28:0x48]),  # class of WORLDS/Ships.idf
            "player_skill": i(0), "crew": i(0x5c), "hull_hp": i(0x4c),
            "weapon_type": i(0x84),  # 0 Demi-culverins, 1 Culverins, 2 Demi-cannons (Goods.idf order)
            "skills": {"cannoneer": i(0x304), "soldier": i(0x300), "sailor": i(0x308)},
            "cargo": {str(n): v for n, v in enumerate(cargo) if v},
            "unknown": _unknown(d, known)}


# pointer tables of QUEST_EDITOR.dll .data (0x1000b5a0, 0x1000b068)
QL_CONDITIONS = ["NO CONDITION", "OBTAIN", "KILL", "ESCORT", "MATCH"]
QL_TYPES = ["Person", "Game", "Ship", "Item", "Goods", "Record", "Quest", "Location", "Expirience", "Module",
            "Characteristics", "File", "Rank", "Dialog", "DLink", "Story line", "String", "Interface", "Playside",
            "Model", "Reputation", "DNode", "State", "Officer", "Officer Rank", "Engine movie"]


def _ql_condition(b: bytes):
    """u8 condition, u8 object type, then u32 len + string and/or i32 value; ESCORT adds a Location target."""
    if len(b) < 2 or b[0] == 0:
        return None
    name = lambda i: QL_TYPES[i] if i < len(QL_TYPES) else i  # noqa: E731
    cond = {"type": QL_CONDITIONS[b[0]] if b[0] < len(QL_CONDITIONS) else b[0], "object": name(b[1])}
    p = 2
    if len(b) - p == 4:
        cond["value"] = struct.unpack_from("<i", b, p)[0]
        return cond
    (n,) = struct.unpack_from("<I", b, p)
    cond["name"] = cstr(b[p + 4:p + 4 + n])
    p += 4 + n
    if len(b) - p == 4:
        cond["value"] = struct.unpack_from("<i", b, p)[0]
    elif len(b) - p > 4:  # ESCORT: u8 type (Location), u32 72, name[64], i32, i32
        (n,) = struct.unpack_from("<I", b, p + 1)
        cond["to"] = {"object": name(b[p]), "name": cstr(b[p + 5:p + 69]),
                      "params": list(struct.unpack_from("<2i", b, p + 69)) if n == 72 else b[p + 69:p + 5 + n].hex()}
    return cond


def parse_ql(src: Path):
    """.ql story line: u32, u32 count, u32; per quest a 0x10c header (u32 0, u32 data len, u32 heap pointer,
    name[64], action[64], action[64], [64]) + data len bytes of condition (QUEST_EDITOR FUN_10004570 appends one quest).
    The third string is the ACTIONS/*.a run when the condition is met (106 of 106 exist), "void" is the idle quest."""
    d = src.read_bytes()
    _, count, _ = struct.unpack_from("<3I", d, 0)
    off, quests = 12, []
    for _ in range(count):
        (n,) = struct.unpack_from("<I", d, off + 4)
        names = [cstr(d[off + 12 + 64 * k:off + 76 + 64 * k]) for k in range(4)]
        quests.append({"name": names[0], "action_alt": names[1] or None, "action": names[2] or None,
                       "extra": names[3] or None, "condition": _ql_condition(d[off + 0x10c:off + 0x10c + n])})
        off += 0x10c + n
    if off != len(d):
        raise ValueError(f"{len(d) - off} bytes left after {count} quests")
    return {"source": src.name, "story_line": src.stem, "quests": quests}


DATA_STAGES = {"actions": (".a", parse_actions), "dialogs": (".d", parse_dialog),
               "tables": (".idf", parse_idf), "desc": (".def", parse_def),
               "characters": (".mtx", parse_mtx), "ships": (".shp", parse_shp),
               "quests": (".ql", parse_ql)}


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdm", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--only", default=",".join(STAGES), help="comma-separated stages")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()

    res = a.pdm / "RESOURCE" if (a.pdm / "RESOURCE").is_dir() else a.pdm
    if not res.is_dir():
        sys.exit(f"no RESOURCE in {a.pdm}")
    stages = [s.strip() for s in a.only.split(",") if s.strip()]
    if bad := set(stages) - set(STAGES):
        sys.exit(f"unknown stages: {', '.join(sorted(bad))}")
    out_res, out_data = a.out / "resource", a.out / "data"
    files = sorted(p for p in res.rglob("*") if p.is_file())
    report_path = a.out / "convert-report.json"
    report = {"source": str(res), "stages": {}}
    if report_path.exists():  # --only reruns update their stages and keep the others
        report["stages"] = json.loads(report_path.read_text(encoding="utf-8")).get("stages", {})
    t0 = time.time()

    def stage(name, ok, failed, extra=None):
        report["stages"][name] = {"ok": ok, "failed": len(failed), "errors": failed, **(extra or {})}
        print(f"  {name:9} {ok:5} ok, {len(failed)} failed  ({time.time() - t0:.0f}s)")
        for f, e in failed[:20]:
            print(f"      {f}: {e}")

    # textures + models: CPU-heavy, run in parallel
    tf_stems = {p.with_suffix("").as_posix().lower() for p in files if p.suffix.lower() == ".tf"}
    jobs = []
    for p in files:
        ext, rel = p.suffix.lower(), p.relative_to(res)
        if "textures" in stages and ext in TEXTURE_EXT:
            if ext == ".tga" and p.with_suffix("").as_posix().lower() in tf_stems:
                continue  # the .tf twin is the texture the game used
            jobs.append(("textures", str(p), str(out_res / rel.with_suffix(".tx"))))
        elif "models" in stages and ext in MODEL_EXT:
            jobs.append(("models", str(p), str(out_res / rel.with_suffix(".gm"))))
    for _, _, dst in jobs:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
    if jobs:
        print(f"[textures/models] {len(jobs)} files, {a.jobs} jobs")
        results = Counter()
        failed = {"textures": [], "models": []}
        with ProcessPoolExecutor(a.jobs) as pool:
            for kind, src, err in pool.map(_job, jobs, chunksize=4):
                if err:
                    failed[kind].append([str(Path(src).relative_to(res)), err])
                else:
                    results[kind] += 1
        for kind in ("textures", "models"):
            if kind in stages:
                stage(kind, results[kind], failed[kind])

    if "copy" in stages:
        print("[copy]")
        n, by_ext = 0, Counter()
        for p in files:
            if p.suffix.lower() in CONVERTED_EXT:
                continue
            dst = out_res / p.relative_to(res)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.stat().st_size != p.stat().st_size:
                dst.write_bytes(p.read_bytes())
            n += 1
            by_ext[p.suffix.lower() or "(none)"] += 1
        stage("copy", n, [], {"by_ext": dict(by_ext.most_common())})

    for name, (ext, parse) in DATA_STAGES.items():
        if name not in stages:
            continue
        print(f"[{name}]")
        ok, failed = 0, []
        for p in files:
            if p.suffix.lower() != ext:
                continue
            rel = p.relative_to(res)
            try:
                obj = parse(p)
            except Exception as e:  # noqa: BLE001
                failed.append([str(rel), f"{type(e).__name__}: {e}"])
                continue
            dst = out_data / name / rel.parent / (p.stem + ".json")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
            ok += 1
        stage(name, ok, failed)

    a.out.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total_fail = sum(s["failed"] for s in report["stages"].values())
    print(f"done in {time.time() - t0:.0f}s, {total_fail} failed, report: {report_path}")


if __name__ == "__main__":
    main()
