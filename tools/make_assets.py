"""Builds the game textures (.tx) and the font ini from downloaded free assets.

Usage: make_assets.py <assets dir> <output resource dir>
<assets dir> must contain OldStandard-Bold.ttf and ninth_wave.jpg (see fetch_assets.sh) and
ptserif/PT_Serif-Web-{Regular,Bold}.ttf (engine/demos/dialog/fetch_assets.sh).
"""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TXF_A8R8G8B8 = 21

FONTS = {
    # name: (TrueType file in the assets dir, pixel size, outline)
    "interface_title": ("OldStandard-Bold.ttf", 72, 3),
    "interface_button": ("OldStandard-Bold.ttf", 30, 2),
    "interface_normal": ("OldStandard-Bold.ttf", 20, 1),
    # the dialog window (dialog.ini from make_port.py); the dialog scales them by the window height / 600
    "dialog_text": ("ptserif/PT_Serif-Web-Regular.ttf", 19, 1),
    "dialog_links": ("ptserif/PT_Serif-Web-Regular.ttf", 18, 1),
    "dialog_name": ("ptserif/PT_Serif-Web-Bold.ttf", 18, 1),
    # the world map (map.c): the island names and the date under the clock
    "wdm_label": ("ptserif/PT_Serif-Web-Bold.ttf", 20, 2),
    "wdm_date": ("ptserif/PT_Serif-Web-Bold.ttf", 15, 1),
}
CHARS = [chr(c) for c in range(33, 127)] + [chr(c) for c in range(0x410, 0x450)] + ["Ё", "ё", "—", "«", "»", "·"]
SKIP_KEYS = {";", "[", "]"}  # would break the ini syntax


def write_tx(image, path):
    """Writes a single mip A8R8G8B8 texture, the engine's native format (raw TGA is Windows only)."""
    image = image.convert("RGBA")
    r, g, b, a = image.split()
    pixels = Image.merge("RGBA", (b, g, r, a)).tobytes()  # D3DFMT_A8R8G8B8 is BGRA in memory
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as out:
        out.write(struct.pack("<6i", 0, image.width, image.height, 1, TXF_A8R8G8B8, len(pixels)))
        out.write(pixels)


def make_background(src, dst):
    painting = Image.open(src).convert("RGB")
    w, h = painting.size
    crop_w = h * 4 // 3
    left = (w - crop_w) // 2
    painting = painting.crop((left, 0, left + crop_w, h)).resize((1024, 768), Image.LANCZOS)
    # darken the left side under the menu panel
    shade = Image.linear_gradient("L").rotate(90).resize((1024, 768))
    painting = Image.composite(painting, Image.new("RGB", painting.size, (8, 10, 16)), shade.point(lambda v: 90 + v * 165 // 255))
    canvas = Image.new("RGB", (1024, 1024))
    canvas.paste(painting, (0, 0))
    write_tx(canvas, dst / "textures/interfaces/menu_back.tga.tx")


def button_piece(width, height, selected, rounded_left):
    piece = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(piece)
    fill = (92, 58, 28, 230) if selected else (28, 22, 18, 200)
    border = (232, 190, 96, 255) if selected else (150, 118, 64, 255)
    radius = 10 if rounded_left else 0
    box = (2, 2, width + (0 if rounded_left else 20), height - 3)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=border, width=2)
    if selected:
        draw.line((box[0] + 6, 6, width + 20, 6), fill=(255, 225, 150, 90), width=2)
    return piece


def make_icons(dst):
    atlas = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
    for row, selected in enumerate((False, True)):
        y = row * 48
        # left (0..16) and middle (16..144) are cut from one image so they join seamlessly;
        # pixels past 144 stay as filtering padding
        atlas.paste(button_piece(160, 48, selected, True), (0, y))
    write_tx(atlas, dst / "textures/interfaces/menu_icons.tga.tx")

    cursor = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cursor)
    arrow = [(16, 16), (16, 31), (20, 27), (24, 31), (26, 30), (22, 26), (28, 26)]
    draw.polygon(arrow, fill=(240, 200, 110, 255), outline=(40, 25, 10, 255))
    write_tx(cursor, dst / "textures/interfaces/cursor32.tga.tx")


def make_fonts(assets, dst):
    sections = []
    for name, (ttf, size, outline) in FONTS.items():
        font = ImageFont.truetype(str(assets / ttf), size)
        ascent, descent = font.getmetrics()
        cell_h = ascent + descent + outline * 2
        atlas_w = 1024
        atlas = Image.new("RGBA", (atlas_w, 1024), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        x, y = 1, 1
        records = []
        for ch in CHARS:
            w = int(font.getlength(ch)) + outline * 2 + 1
            if x + w + 1 > atlas_w:
                x, y = 1, y + cell_h + 2
            # white glyph with a dark outline, tinted by the node color
            draw.text((x + outline, y + outline), ch, font=font, fill=(255, 255, 255, 255),
                      stroke_width=outline, stroke_fill=(0, 0, 0, 255))
            records.append((ch, x, y, w))
            x += w + 2
        atlas_h = 1
        while atlas_h < y + cell_h + 2:
            atlas_h *= 2
        write_tx(atlas.crop((0, 0, atlas_w, atlas_h)), dst / f"textures/fonts/{name}.tga.tx")

        lines = [f"[{name.upper()}]",
                 f"Texture = fonts\\{name}.tga",
                 "Techniques = InterfaceFont",
                 f"Texture_xsize = {atlas_w}",
                 f"Texture_ysize = {atlas_h}",
                 f"Height = {cell_h}",
                 f"Spacebar = {int(font.getlength(' '))}",
                 "Symbol_interval = -1",
                 ""]
        for ch, cx, cy, w in records:
            if ch in SKIP_KEYS:
                continue
            key = "equ" if ch == "=" else (ch + "_" if "a" <= ch <= "z" else ch)
            lines.append(f"char_{key} = {cx},{cy},{w},{cell_h}")
        sections.append("\n".join(lines))
    (dst / "ini").mkdir(parents=True, exist_ok=True)
    header = "; generated by make_assets.py from Old Standard Bold and PT Serif (SIL Open Font License)\n\n"
    (dst / "ini/fonts.ini").write_text(header + "\n\n".join(sections) + "\n", encoding="utf-8")


def main():
    assets, dst = Path(sys.argv[1]), Path(sys.argv[2])
    make_background(assets / "ninth_wave.jpg", dst)
    make_icons(dst)
    make_fonts(assets, dst)


if __name__ == "__main__":
    main()
