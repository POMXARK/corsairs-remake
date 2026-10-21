#!/usr/bin/env python3
"""A zip of the working copy to unpack and run without git (ours): corsairs-remake with the engine in engine/.

Takes the files git knows and the new ones it does not ignore, with the changes not committed yet, from
corsairs-remake and from the engine (its submodules too, src/libs/editor_tools). The engine is taken from
--engine, the working tree of storm-engine next to the repository by default, else the submodule engine/:
the work of the engine is there before it is committed and bumped. What git ignores stays out: the build,
the data of the original and what run.sh converts from it (pdm-game/resource, data, program/data), as
the original is not ours to give; the one who unpacks it runs game.bat with an installed copy of PDM 1.061.
Also left out: __pycache__, imgui.ini and the logs. Needs git on the machine that packs, not on the one
that unpacks. Prints the size and the number of files; a repeated run gives the same zip (fixed dates).

usage: make_archive.py [--engine ../storm-engine] [--out ../dist/corsairs-remake-<date>.zip]
"""
import argparse
import datetime
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"__pycache__", ".git"}
SKIP_NAMES = {"imgui.ini"}
SKIP_SUFFIXES = (".pyc", ".log", ".dxvk-cache")
DATE = (2026, 1, 1, 0, 0, 0)


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
                print(f"make_archive: {repo.name}/{path}: the submodule is not checked out, left out", file=sys.stderr)
            continue
        result.append(path)
    return sorted(set(result))


def wanted(path: str):
    parts = path.split("/")
    return not (SKIP_PARTS & set(parts) or parts[-1] in SKIP_NAMES or parts[-1].endswith(SKIP_SUFFIXES))


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("--engine", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    engine = a.engine or (ROOT.parent / "storm-engine" if (ROOT.parent / "storm-engine" / ".git").exists() else ROOT / "engine")
    out = a.out or ROOT.parent / "dist" / f"corsairs-remake-{datetime.date.today():%Y%m%d}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = [(ROOT / p, f"corsairs-remake/{p}") for p in files(ROOT) if p.split("/")[0] != "engine" and wanted(p)]
    entries += [(engine / p, f"corsairs-remake/engine/{p}") for p in files(engine) if wanted(p)]
    size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, name in sorted(entries, key=lambda e: e[1]):
            if not src.is_file():
                continue  # deleted in the working tree, not committed yet
            info = zipfile.ZipInfo(name, DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (src.stat().st_mode & 0o777 | 0o100000) << 16  # run.sh stays executable
            data = src.read_bytes()
            size += len(data)
            z.writestr(info, data)
    print(f"{out}: {len(entries)} files, {size / 2**20:.0f} MB unpacked, {out.stat().st_size / 2**20:.0f} MB zip; "
          f"the engine from {engine}")


if __name__ == "__main__":
    main()
