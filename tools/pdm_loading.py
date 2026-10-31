#!/usr/bin/env python3
"""The "Loading" banner of the original: RESOURCE/IMAGES/loading0..2.tga (322x50), which CORE.dll blits at (5,5) of
the frozen frame while a location loads, one frame per >=30 ms in turn.
The engine draws it with its progress view (ReloadProgressStart): an atlas Loading\\progress.tga of a square 3x3 grid
(the engine takes the row as frame / rows, so the grid is square) whose cells repeat the three frames in turn.
usage: pdm_loading.py <original game dir> <resource dir>; writes textures/loading/progress.tga.tx"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "common"))
from storm_formats import write_tx  # noqa: E402

CELL_W, CELL_H = 512, 64  # the cell is wider than the picture; the banner keeps its 322x50 at the top left
GRID = 3

src = Path(sys.argv[1])
frames = [Image.open(next(src.rglob(f"loading{i}.tga"))).convert("RGBA") for i in range(3)]
atlas = Image.new("RGBA", (CELL_W * GRID, CELL_H * GRID), (0, 0, 0, 0))
for cell in range(GRID * GRID):
    atlas.paste(frames[cell % 3], ((cell % GRID) * CELL_W, (cell // GRID) * CELL_H))
write_tx(atlas, Path(sys.argv[2]) / "textures" / "loading" / "progress.tga.tx", mip_chain=False)
