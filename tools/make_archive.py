#!/usr/bin/env python3
"""A zip of the working copy to unpack and build without git (ours): corsairs-remake with the engine in engine/.

Takes the files git knows and the new ones it does not ignore, with the changes not committed yet, from
corsairs-remake and from the engine (its submodules too, src/libs/editor_tools). The engine is taken from
--engine, the working tree of storm-engine next to the repository by default, else the submodule engine/:
the work of the engine is there before it is committed and bumped. What git ignores stays out: the build,
the data of the original and what run.sh converts from it (pdm-game/resource, data, program/data), as
the original is not ours to give; the one who unpacks it runs game.bat with an installed copy of PDM 1.061.

The archive is tied to no repository: the files of git (.git*, .github), of the IDE (.idea) and the
agents (AGENTS.md, GEMINI.md, opencode.json, .opencode) are left out, the links to the repositories of the fork and
the local paths in the texts are replaced (SCRUB), and a marker of them left in a text stops the packing.
The build still downloads from the net what any build does: Conan packages, pip packages.

By default only what pdm-game needs (under --limit MB, 100): the first remake (game/, assets/, the run
scripts of the root), the videos, pdm-sea, the engine tools but gltf2gm and the demos other than KEEP_DEMOS are left
out, the kept demos without their resource/ and media/ (run.ps1 builds from their make_*.py and fonts).
--full packs everything. Also left out: __pycache__, imgui.ini and the logs. docs/archive.md goes to the
root as ARCHIVE.md: how to build from the archive. Needs git on the machine that packs, not on the one
that unpacks. A repeated run gives the same zip (fixed dates).

usage: make_archive.py [--engine ../storm-engine] [--out ../dist/corsairs-remake-<date>.zip] [--full] [--limit 100]
"""
import argparse
import base64
import datetime
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"__pycache__", ".git", ".github", ".idea", ".vscode", ".opencode", ".claude"}
SKIP_NAMES = {"imgui.ini", ".gitmodules", ".gitattributes", ".gitignore", "AGENTS.md", "GEMINI.md", "opencode.json",
              ".opencodeignore"}
SKIP_SUFFIXES = (".pyc", ".log", ".dxvk-cache")
DATE = (2026, 1, 1, 0, 0, 0)

# what pdm-game does not use: the first remake on free assets, the gallery videos, the second game
GAME_SKIP = ("game/", "assets/", "media/", "pdm-game/media/", "pdm-sea/", "run.sh", "run.ps1", "run.bat")
# the demos run.ps1 and the tools import or take fonts from: common (storm_formats, demo.ps1), sea and
# ship (make_sea.py, make_ship.py), dialog (make_dialog.py, PT Serif), interface (Old Standard), particles
# and battle with sound (make_particles.py, make_battle.py imports make_sound.py)
KEEP_DEMOS = {"common", "sea", "ship", "dialog", "interface", "particles", "battle", "sound"}
ENGINE_SKIP = ("tools/",)
# but the build of the engine copies gltf2gm.py next to engine.exe (src/apps/engine/CMakeLists.txt)
ENGINE_KEEP = ("tools/gltf2gm/",)
TEXT_SUFFIXES = {".md", ".txt", ".py", ".ps1", ".sh", ".bat", ".json", ".yml", ".yaml", ".ini", ".c", ".h",
                 ".cpp", ".hpp", ".cmake", ".toml", ".cfg", ".tsv", ".csv", ".htm", ".html", ".xml"}

# the account of the one who packs, base64 so that this file carries none of it in the archive (ours):
# the GitHub user, the user of the machine, the disk, the name and the mail domains
FORK, USER, DISK, *OTHERS = [base64.b64decode(s).decode() for s in (
    "UE9NWEFSSw==", "cm9tYW4=", "MzgzYmU5ZWU=", "YnVzaHVldg==", "YmVuZWZpdHR5", "Z291dHBha2Fk", "0JHRg9GI0YPQtdCy")]
# the links to the repositories of the fork and the paths of the machine that packs
SCRUB = [
    (re.compile(rf"https?://github\.com/{FORK}/([\w.-]+?)(?:\.git)?(?=[\s)\]`'\"/#]|$)", re.M), r"<\1 repository>"),
    (re.compile(FORK), "the fork"),
    (re.compile(rf"/media/{USER}/[\w-]+/home\b"), "/path/to"),
    (re.compile(rf"/home/{USER}\b"), "~"),
]
# a text with one of these after SCRUB stops the packing: a trace of the account that packs
MARKERS = re.compile("|".join(re.escape(m) for m in [FORK, f"/home/{USER}", f"/media/{USER}", DISK, *OTHERS]).encode(), re.I)


def files(repo: Path):
    """The files of a working tree git keeps or would keep, the submodules opened, relative to it."""
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                          "--stage"], capture_output=True, check=True).stdout
    # --stage marks a submodule with the mode 160000; the untracked files come without a stage
    result = []
    for entry in out.decode("utf-8").split("\0"):
        if not entry:
            continue
        if "\t" in entry:
            mode, path = entry.split(" ", 1)[0], entry.split("\t", 1)[1]
        else:
            mode, path = "", entry
        if mode == "160000":
            sub = repo / path
            if (sub / ".git").exists():
                result += [f"{path}/{p}" for p in files(sub)]
            else:
                sys.exit(f"make_archive: {repo.name}/{path}: the submodule is not checked out "
                         f"(git submodule update --init --recursive), the build needs it")
            continue
        result.append(path)
    return sorted(set(result))


def wanted(path: str):
    parts = path.split("/")
    return not (SKIP_PARTS & set(parts) or parts[-1] in SKIP_NAMES or parts[-1].endswith(SKIP_SUFFIXES))


def game_wanted(path: str, full: bool):
    return path.split("/")[0] != "engine" and wanted(path) and (full or not path.startswith(GAME_SKIP))


def engine_wanted(path: str, full: bool):
    if not wanted(path):
        return False
    if full:
        return True
    parts = path.split("/")
    if path.startswith(ENGINE_SKIP) and not path.startswith(ENGINE_KEEP):
        return False
    if parts[0] == "demos" and len(parts) > 2:
        return parts[1] in KEEP_DEMOS and parts[2] not in ("resource", "media")
    if parts[0] == "docs":
        return Path(path).suffix.lower() in TEXT_SUFFIXES  # the pictures and the scans of the old docs stay out
    return True


def scrub(name: str, data: bytes):
    """The text with the links and paths of SCRUB replaced; a binary file as it is."""
    if Path(name).suffix.lower() not in TEXT_SUFFIXES and Path(name).name != "CMakeLists.txt":
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    for pattern, repl in SCRUB:
        text = pattern.sub(repl, text)
    return text.encode("utf-8")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("--engine", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--limit", type=float, default=100.0, help="MB of the zip, 0: no limit")
    a = ap.parse_args()
    engine = a.engine or (ROOT.parent / "storm-engine" if (ROOT.parent / "storm-engine" / ".git").exists() else ROOT / "engine")
    out = a.out or ROOT.parent / "dist" / f"corsairs-remake-{datetime.date.today():%Y%m%d}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = [(ROOT / p, f"corsairs-remake/{p}") for p in files(ROOT) if game_wanted(p, a.full)]
    entries += [(engine / p, f"corsairs-remake/engine/{p}") for p in files(engine) if engine_wanted(p, a.full)]
    entries.append((ROOT / "docs/archive.md", "corsairs-remake/ARCHIVE.md"))
    size, count, traces = 0, 0, []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, name in sorted(entries, key=lambda e: e[1]):
            if not src.is_file():
                continue  # deleted in the working tree, not committed yet
            info = zipfile.ZipInfo(name, DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (src.stat().st_mode & 0o777 | 0o100000) << 16  # run.sh stays executable
            data = scrub(name, src.read_bytes())
            if Path(name).suffix.lower() in TEXT_SUFFIXES and MARKERS.search(data):
                traces.append(name)
            size += len(data)
            count += 1
            z.writestr(info, data)
    zip_mb = out.stat().st_size / 2**20
    print(f"{out}: {count} files, {size / 2**20:.0f} MB unpacked, {zip_mb:.0f} MB zip; the engine from {engine}")
    if traces:
        out.unlink()
        sys.exit("make_archive: traces of the account in " + ", ".join(traces) + " — add them to SCRUB; no zip")
    if a.limit and zip_mb > a.limit:
        out.unlink()
        sys.exit(f"make_archive: {zip_mb:.0f} MB is over --limit {a.limit:.0f} MB; no zip")


if __name__ == "__main__":
    main()
