"""Converts the sea toolbar (SQUAD_CONTROL.dll) and the navigator (NAVIGATOR.dll) of the original Sea Dogs on
TEXTURES/toolbar and the action icon of the land for BATTLE_INTERFACE and ILogAndActions of Storm Engine.

Usage: pdm_hud.py <Sea Dogs install dir with RESOURCE> <game dir>
Writes into <game dir>/resource/textures/battle_interface/pdm:
  commands.tga.tx  the icons of the commands, <cmd>_n.tga and <cmd>_a.tga (64x64) side by side in a grid of
                   8x4: the normal one of the command i in the cell 2i, the active one in 2i+1
  ships.tga.tx     the pictures of the ships, <icon>1.tga (a dark plate in the corner) and <icon>2.tga (the
                   plate lit, the ship chosen), with the flag of the nation (tflag0..3.tga, its blue keyed out)
                   in the top left corner and the class of the ship on the plate, in a grid of 16x16: the cell
                   ((icon * 4 + flag) * 2 + lit)
  status.tga.tx    ship_status.tga: the bars of the sails, the crew and the hull, empty on the top, full below
  back.tga.tx      the empty bars with the crew full (ours: the engine draws two gauges, the crew stays full)
  info.tga.tx      ship_info.tga, the panel of the charges bottom right: its 4 rows of 50 (the balls, the grapes,
                   the knippels, the bombs lit) in rows of 64 and an empty fifth row, 8 rows in all
  nav_frame.tga.tx    the frame of the navigator (obrooch4: a ring with a plate below for the speeds)
  nav_compass.tga.tx  the letters of the compass (compas-new), turned with the heading
  nav_cannons.tga.tx  a white band round the frame: the navigator cuts the arcs of the broadsides out of it and
                      tints them by their reload (ours: NAVIGATOR.dll shows the guns on a panel of their own)
  nav_wind.tga.tx     the wind arrow across the map (wind.tf, its black background made transparent)
and <game dir>/program/data/pdm_hud.c: the cells of the commands, the icons and the flags, the notes of the
commands and the names of the exits ([main] of TEXTS/RUSSIAN/INI/interface.ini).
The engine reads a picture grid with as many rows as columns (BIShipIcon::GetShipUVFromPictureIndex
takes the rows for the columns), so the grids of the ships are square.
The navigator draws its square textures on one square round the map: the frame and the compass take the middle
NAV_FRAME of NAV texels (scaled 1.5 from 128), the band of the guns the ring outside the frame.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent / "engine/demos/common"))
from storm_formats import write_tx  # noqa: E402
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))
from pdm_ui import LANGUAGE, Original  # noqa: E402
from tf2tx import tf_image  # noqa: E402

# the icons of the toolbar; SQUAD_CONTROL.dll gives follow_me followme, capture and boarding board,
# sail_to chase, sea_map map2, land town, skip_time time
COMMANDS = ["assault", "board", "cancel", "chase", "destroy", "followme", "map", "map2", "ocean", "runaway", "time",
            "town"]
COMMAND_COLS = 8
SHIP_COLS = 16
CELL = 64
# the nations of WORLDS/nations.idf -> tflag<n>.tga; the Americans sail under the pirate flag (their flag of
# nations.idf is flag-pirat.tf)
FLAGS = {"england": 0, "pirate": 1, "france": 2, "spain": 3, "America": 1}
FLAG_COUNT = 4
FLAG_KEY = (104, 176, 216)
# the toolbar draws pure black as transparent (a colour key): the pictures take the top 50 rows of their 64,
# the rest is black, so is the gap between the empty and the full bars of ship_status
BLACK_KEY = (0, 0, 0)
# the flag (its 19x17 at the top left of tflag) in the top left corner of the picture, the class of the ship on
# its dark plate, white on the lit picture and grey on the other (FUN_100030a0 of SQUAD_CONTROL.dll; ours: the
# original prints it with arial 10, the converter bakes it in with the font of Pillow)
FLAG_BOX = (0, 0, 19, 17)
FLAG_AT = (2, 2)
CLASS_AT = (6, 27)
CLASS_COLOURS = ((143, 143, 143, 255), (255, 255, 255, 255))
# ship_info.tga: the panel of 256x50, the rows of the charges one under another; the rows of the grid of the
# navigator are of 64, the fifth empty one hides the panel
INFO_W = 256
INFO_ROW = 50
INFO_CHARGES = 4
INFO_ROWS = 8
# ship_status.tga: the empty bars at the top, the full ones below; the stripes of the full ones
STATUS_EMPTY = (0, 0, 64, 20)
STATUS_FULL = (0, 20, 64, 40)
CREW_ROWS = (27, 33)
# the navigator: its textures are NAV texels square, the pictures of 128 (frame and compass) take NAV_FRAME of them;
# the band of the guns from just outside the ring of the frame (its radius 64 of 128), in texels of NAV
NAV = 256
NAV_FRAME = 192
CANNON_BAND = (98, 110)
SUPERSAMPLE = 4
# the notes of the commands and the names of the exits of the land, keys of [main]
NOTES = ["follow_me", "destroy", "capture", "run_away", "sea_map", "land", "boarding", "sail_to", "assault",
         "info_bar", "open_sea", "street", "tavern", "store", "shipyard", "townhall", "fort", "sea",
         "ControlTurboMode", "ControlExecuteFastAction"]


def picture(pdm, name, key=BLACK_KEY):
    path = pdm.find("TEXTURES/toolbar/" + name)
    if path is None:
        raise SystemExit(f"pdm_hud: no TEXTURES/toolbar/{name}")
    return keyed(Image.open(path).convert("RGBA"), key)


def keyed(image, key):
    image = image.copy()
    image.putdata([(r, g, b, 0) if (r, g, b) == key else (r, g, b, a) for r, g, b, a in image.getdata()])
    return image


def commands(pdm):
    rows = -(-len(COMMANDS) * 2 // COMMAND_COLS)
    atlas = Image.new("RGBA", (COMMAND_COLS * CELL, rows * CELL))
    for i, name in enumerate(COMMANDS):
        for lit, suffix in enumerate(("n", "a")):
            cell = 2 * i + lit
            atlas.paste(picture(pdm, f"{name}_{suffix}.tga"), (cell % COMMAND_COLS * CELL, cell // COMMAND_COLS * CELL))
    return atlas


def ship_icons(pdm):
    """The stems with both pictures, in the order of their names."""
    folder = pdm.find("TEXTURES/toolbar")
    stems = {p.name[:-5].lower() for p in folder.iterdir() if p.name.lower().endswith("1.tga")}
    return sorted(s for s in stems if pdm.find(f"TEXTURES/toolbar/{s}2.tga") and not s.startswith(("it_", "tflag")))


def ship_classes(game):
    """The class of the ship of each icon (WORLDS/Ships.idf, one class an icon)."""
    table = json.loads((game / "data/tables/WORLDS/Ships.json").read_text(encoding="utf-8"))
    return {o["icon"].lower(): o["class"] for o in map(dict, table["objects"]) if o.get("icon")}


def ships(pdm, icons, classes):
    cells = len(icons) * FLAG_COUNT * 2
    if cells > SHIP_COLS * SHIP_COLS:
        raise SystemExit(f"pdm_hud: {cells} ship pictures do not fit the grid of {SHIP_COLS}")
    atlas = Image.new("RGBA", (SHIP_COLS * CELL, SHIP_COLS * CELL))
    flags = [picture(pdm, f"tflag{f}.tga", FLAG_KEY).crop(FLAG_BOX) for f in range(FLAG_COUNT)]
    font = ImageFont.load_default()
    for i, icon in enumerate(icons):
        for f, flag in enumerate(flags):
            for lit in range(2):
                image = picture(pdm, f"{icon}{lit + 1}.tga")
                image.alpha_composite(flag, FLAG_AT)
                if icon in classes:
                    ImageDraw.Draw(image).text(CLASS_AT, classes[icon], font=font, fill=CLASS_COLOURS[lit])
                cell = (i * FLAG_COUNT + f) * 2 + lit
                atlas.paste(image, (cell % SHIP_COLS * CELL, cell // SHIP_COLS * CELL))
    return atlas


def back(status):
    empty = status.crop(STATUS_EMPTY)
    full = status.crop(STATUS_FULL)
    y0, y1 = CREW_ROWS
    top = STATUS_FULL[1]
    empty.paste(full.crop((0, y0 - top, 64, y1 - top)), (0, y0 - top))
    return empty


def info(pdm):
    panel = picture(pdm, "ship_info.tga")
    image = Image.new("RGBA", (INFO_W, CELL * INFO_ROWS))
    for row in range(INFO_CHARGES):
        image.paste(panel.crop((0, row * INFO_ROW, INFO_W, (row + 1) * INFO_ROW)), (0, row * CELL))
    return image


def toolbar(pdm, name):
    path = pdm.find("TEXTURES/toolbar/" + name)
    if path is None:
        raise SystemExit(f"pdm_hud: no TEXTURES/toolbar/{name}")
    return tf_image(path) if name.lower().endswith(".tf") else Image.open(path).convert("RGBA")


def nav_square(image):
    """A picture of 128 in the middle of the square of the navigator."""
    canvas = Image.new("RGBA", (NAV, NAV))
    offset = (NAV - NAV_FRAME) // 2
    canvas.alpha_composite(image.resize((NAV_FRAME, NAV_FRAME), Image.LANCZOS), (offset, offset))
    return canvas


def nav_cannons():
    big = NAV * SUPERSAMPLE
    image = Image.new("RGBA", (big, big))
    draw = ImageDraw.Draw(image)
    c = big / 2
    r_in, r_out = (r * SUPERSAMPLE for r in CANNON_BAND)
    draw.ellipse((c - r_out, c - r_out, c + r_out, c + r_out), fill=(255, 255, 255, 230))
    draw.ellipse((c - r_in, c - r_in, c + r_in, c + r_in), fill=(0, 0, 0, 0))
    return image.resize((NAV, NAV), Image.LANCZOS)


def nav_wind(pdm):
    # black is the background; the arrow fades into it in the middle, so its brightness (tripled: the dark middle
    # still shows on the map) is its alpha
    image = toolbar(pdm, "wind.tf")
    image.putdata([(r, g, b, min(255, 3 * max(r, g, b))) for r, g, b, _ in image.getdata()])
    return image


def strings(pdm):
    path = pdm.find(f"TEXTS/{LANGUAGE}/INI/interface.ini")
    found = {}
    for line in path.read_bytes().decode("cp1251").splitlines():
        if "=" in line and not line.lstrip().startswith(("//", "[")):
            k, v = line.split("=", 1)
            found.setdefault(k.strip(), v.strip().replace('"', "'"))
    return found


def main():
    pdm, game = Original(sys.argv[1]), Path(sys.argv[2])
    out = game / "resource/textures/battle_interface/pdm"
    write_tx(commands(pdm), out / "commands.tga.tx", mip_chain=False)
    icons = ship_icons(pdm)
    write_tx(ships(pdm, icons, ship_classes(game)), out / "ships.tga.tx", mip_chain=False)
    status = picture(pdm, "ship_status.tga")
    write_tx(status, out / "status.tga.tx", mip_chain=False)
    write_tx(back(status), out / "back.tga.tx", mip_chain=False)
    write_tx(info(pdm), out / "info.tga.tx", mip_chain=False)
    write_tx(nav_square(toolbar(pdm, "obrooch4.tga")), out / "nav_frame.tga.tx", mip_chain=False)
    write_tx(nav_square(toolbar(pdm, "compas-new.tf")), out / "nav_compass.tga.tx", mip_chain=False)
    write_tx(nav_cannons(), out / "nav_cannons.tga.tx", mip_chain=False)
    write_tx(nav_wind(pdm), out / "nav_wind.tga.tx", mip_chain=False)

    texts = strings(pdm)
    lines = [f"\tPdmHud.command_cols = {COMMAND_COLS};",
             f"\tPdmHud.command_rows = {-(-len(COMMANDS) * 2 // COMMAND_COLS)};",
             f"\tPdmHud.ship_cols = {SHIP_COLS};",
             f"\tPdmHud.flag_count = {FLAG_COUNT};",
             f"\tPdmHud.info_rows = {INFO_ROWS};",
             f"\tPdmHud.info_empty = {INFO_CHARGES};",
             f"\tPdmHud.nav_scale = {NAV / NAV_FRAME:.6f};"]
    lines += [f"\tPdmHud.command.{name} = {i * 2};" for i, name in enumerate(COMMANDS)]
    lines += [f"\tPdmHud.icon.{icon} = {i};" for i, icon in enumerate(icons)]
    lines += [f"\tPdmHud.flag.{nation} = {f};" for nation, f in FLAGS.items()]
    missing = [k for k in NOTES if k not in texts]
    if missing:
        raise SystemExit("pdm_hud: no " + ", ".join(missing) + " in interface.ini")
    lines += [f'\tPdmHud.note.{k} = "{texts[k]}";' for k in NOTES]
    (game / "program/data").mkdir(parents=True, exist_ok=True)
    (game / "program/data/pdm_hud.c").write_text(
        "// Generated by tools/pdm_hud.py: the cells of the pictures of the toolbar (resource/textures/battle_interface/pdm)\n"
        "// and the notes of its commands\nobject PdmHud;\n\nvoid PdmHud_Init()\n{\n" + "\n".join(lines) + "\n}\n",
        encoding="utf-8")
    print(f"pdm_hud: {len(COMMANDS)} commands, {len(icons)} ship pictures x {FLAG_COUNT} flags, {len(NOTES)} notes")


if __name__ == "__main__":
    main()
