#!/usr/bin/env python3
"""The faces of the original (seadogs10..13.ttf of Windows\\Fonts: Interface, SeaWolf, Log-Russ, Log-russ-Italic) for
pdm_ui.py: SeaWolf and Log-Russ keep their Russian letters under the codes of Windows-1251 (the game prints bytes), not
under Unicode, so a converter that asks for "А" finds a hole. This writes a copy of every such face with a Unicode
table made from the byte table (the glyphs are not touched). The fonts are the original's and are not free: the copies
stay outside git, next to the originals; run pdm_ui.py with PDM_FONTS=<out>.

Needs fontTools (pip install --user fonttools), so run it WITHOUT -I:
    python3 tools/pdm_fonts.py <folder with seadogs*.ttf> <out folder>
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable


def byte_table(font):
    """{byte: glyph name} of the table of Macintosh (1, 0): the original is addressed by bytes."""
    for table in font["cmap"].tables:
        if (table.platformID, table.platEncID) == (1, 0):
            return table.cmap
    return {}


def unicode_has_cyrillic(font):
    best = font.getBestCmap() or {}
    return all(c in best for c in range(0x410, 0x450))


def convert(src, dst):
    font = TTFont(src)
    if unicode_has_cyrillic(font):
        font.save(dst)
        return "kept (Cyrillic in Unicode)"
    table = byte_table(font)
    cmap = {}
    for byte in range(32, 256):
        if byte not in table:
            continue
        char = bytes([byte]).decode("cp1251", errors="ignore")
        if char:
            cmap[ord(char)] = table[byte]
    if not all(c in cmap for c in range(0x410, 0x450)):
        return "skipped (no Cyrillic under the bytes either)"
    unicode = CmapSubtable.newSubtable(4)
    unicode.platformID, unicode.platEncID, unicode.language = 3, 1, 0
    unicode.cmap = {c: g for c, g in cmap.items() if c < 0x10000}
    font["cmap"].tables = [unicode]
    font.save(dst)
    return f"{len(unicode.cmap)} signs, Cyrillic from the bytes of Windows-1251"


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for ttf in sorted(src.glob("seadogs*.ttf")):
        print(ttf.name, convert(ttf, out / ttf.name))


if __name__ == "__main__":
    main()
