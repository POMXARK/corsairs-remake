r"""Converts the screens of the original Sea Dogs interface (RESOURCE/INI/menu.ini, town.ini, ...)
into XINTERFACE screens of Storm Engine.

Usage: pdm_ui.py <Sea Dogs install dir with RESOURCE> <game dir>
The screens are every section of INI/menu.ini (the menu and its pages), map.ini (the world map),
town.ini (the trade, the shipyard, the crew, the tavern), status.ini (the status of the hero, F1) and
ransack.ini (the captured ship); a name met twice gets the stem of its file (messagebox_town).
Writes into <game dir>/resource:
  ini/interfaces/{interfaces,defaultnode,pictures}.ini and <section>.ini per screen,
  ini/texts/language.ini and texts/russian/common.ini (the strings of TEXTS/RUSSIAN/INI/interface.ini),
  ini/fonts.ini and textures/fonts/*.tx (the fonts of INI/fonts.ini: the original TTF if it is installed,
  in Linux, Wine or Windows, or PDM_FONTS names its folder; else a free font),
  textures/interfaces/pdm/*.tx (the pictures of IMAGES),
  ini/dialog.ini and textures/dialog/dialog.tga.tx (the dialog window: [DialogTerminal] of INI/fonts.ini),
  sounds/voices/<character>.wav (SOUNDS/<id>.wav, the greeting of a character when a dialog opens) and
  <game dir>/program/data/pdm_voices.c, which gives them to the characters, and
  <game dir>/program/data/pdm_screens.c (the titles with %s the scripts fill).

The pattern: every screen of the original is one ini section of one grammar, read by MENU.dll,
TOWN.dll, STATUS.dll ... on an 800x600 virtual screen:
  background = ..\fons\menu-fon-$.tga          a picture under the screen, $ = the language
  ramka      = type,x1,y1,x2,y2               a frame of frames\<type>.tga pieces
  titleN     = txt:"#Key#",font:"name,size,0",xo:..,yo:..,rgb:"r,g,b"
  lb_Name    = txt:"#Key#",file:"..\buttons\mbutton",xo:..,yo:..,font:..,rgbn/rgba/rgbd/rgbi:"r,g,b"
               a button of <file>-{nor,hi,down,dis}.tga with the text colours of the states
  t_Name     = #Key#                           a text the screen shows in a message box
  EditName   = font:..,xl:..,yo:..             a field the DLL fills (the name, the money); [Common] gives
               the fields of every screen of the file
  s_Name     = txt:"... %d",...                a value template of the status
  @rgb_small@                                  a macro of [Common]
A button without a file is a clickable text. The frames, the scrolls and the rows of the lists are drawn
by the C++ of the DLLs: they stay comments in the screen.
The positions: xo/yo the centre, xl/yl the left/top, xr the right edge. A key may be followed by ':'
instead of ',' (xr:585:yo:175 in [Options]). The paths are relative to [Common] path = MENU\ and do
not care about the case of letters.
"""
import math
import os
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageFont

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent / "engine/demos/common"))
from storm_formats import write_fonts, write_tx  # noqa: E402
# the window of the dialog demo; no __pycache__ in the engine submodule
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS.parent / "engine/demos/dialog"))
import make_dialog  # noqa: E402
sys.path.insert(0, str(TOOLS))
from pdm_data2c import key, load  # noqa: E402

LANGUAGE = "russian"
# the faces of INI/fonts.ini (log-russ, seawolf, Interface) are not in the game folder: the installer put
# seadogs10..13.ttf into Windows\Fonts. They are looked for by their family in the folders of PDM_FONTS, the
# game, the fonts of Linux, the Wine prefixes and Windows; without them free fonts stand in (ours)
FREE_FONTS = {
    "seawolf": TOOLS.parent / "engine/demos/interface/assets/OldStandard-Bold.ttf",
    "log-russ": TOOLS.parent / "engine/demos/dialog/assets/PT_Serif-Web-Regular.ttf",
    "log-russ-italic": TOOLS.parent / "engine/demos/dialog/assets/PT_Serif-Web-Regular.ttf",
    # Interface is bold in the original, but a bold serif at 14 px smears on the parchment (ours: regular)
    "interface": TOOLS.parent / "engine/demos/dialog/assets/PT_Serif-Web-Regular.ttf",
}
FREE_FONT = FREE_FONTS["seawolf"]
# the fonts are rendered this many times bigger than the virtual screen asks and scaled down by the node,
# so the text stays sharp in a window bigger than 800x600
FONT_OVERSAMPLE = 1.5
# the width of EditPage1 of the journal, px
PAGE_WIDTH = 280
# the free fonts are wider than log-russ: at the full height "Продолжить игру" does not fit its button
FONT_FIT = 0.85
# the outline of the font of the notes of the toolbar, PDM_HUD_18, in texels
HUD_OUTLINE = 2
# black is the colour key of the pictures of the original (the corners of the buttons, the cursor)
KEY_COLOR = (0, 0, 0)
# how far the blurred background goes beside a 4:3 screen of 800x600: 16:9 (Full HD, 2K) needs 134, 21:9 needs 300
WIDE_BAND = 400
ATTR = re.compile(r'(\w+):(?:"([^"]*)"|([^,:"]+))')


def font_dirs(pdm):
    """Where the fonts of the original may be: PDM_FONTS (folders by os.pathsep), the game, the fonts of the
    user and of Linux, C:\\Windows\\Fonts of the Wine prefixes (~/.wine, ~/Games, ~/.local/share/wineprefixes)
    and of Windows."""
    home = Path.home()
    dirs = [Path(d) for d in os.environ.get("PDM_FONTS", "").split(os.pathsep) if d]
    dirs += [Path(pdm), home / ".local/share/fonts", home / ".fonts", Path("/usr/share/fonts"),
             Path("/usr/local/share/fonts")]
    for prefix in ("*", ".*", ".local/share/wineprefixes/*"):
        dirs += sorted(home.glob(prefix + "/drive_c/windows/Fonts"))
    dirs += [Path(os.environ[v]) / d for v, d in (("WINDIR", "Fonts"), ("LOCALAPPDATA", "Microsoft/Windows/Fonts"))
             if v in os.environ]
    return [d for d in dirs if d.is_dir()]


def face_key(name):
    return "".join(c for c in name.lower() if c.isalnum())


def has_cyrillic(path):
    """Whether the TrueType file draws Russian letters: a glyph it lacks is the empty box of .notdef, the same
    for every missing character (a SeaWolf of a western copy gave squares in the titles)."""
    try:
        font = ImageFont.truetype(str(path), 40)
    except OSError:
        return False
    box = bytes(font.getmask("\U0010ffff"))
    return all(bytes(font.getmask(c)) != box for c in "АБВЖМЯабвеюя")


def find_faces(dirs):
    """{family (+ italic): TrueType file} of the fonts in the folders: "SeaWolf_L" -> seawolfl."""
    faces = {}
    for d in dirs:
        for f in sorted(d.rglob("*")):
            if f.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                family, style = ImageFont.truetype(str(f), 10).getname()
            except OSError:
                continue
            italic = "italic" if "italic" in (style or "").lower() else ""
            faces.setdefault(face_key(family + italic), f)
    return faces


CURSOR_FRAMES = 64      # frames of the turn of the cursor in its strip
CURSOR_FRAME = 64       # one frame, px
CURSOR_TIP = 8          # where the tip of the arrowhead is in a frame (the same in all of them), px


def _cursor_imports():
    import numpy
    import cff2gm
    import tf2tx
    return numpy, cff2gm, tf2tx


def render_cursor_model(cff, tf, frames=CURSOR_FRAMES, size=CURSOR_FRAME, ss=6, tilt=0.3, roll=-0.78):
    """The cursor of the original screens (MODELS/cursor.cff, a four-sided silver arrowhead, textured k_1n.tf) as a
    strip of `frames` pictures of size x size: the arrowhead turns round its axis (the screenshots of the original show
    it flat, wide and thin in turn; it is not the flat IMAGES/cursor.tga that the screen .ini name). The tip stays in
    one place, (CURSOR_TIP, CURSOR_TIP), and the light is fixed to the screen, so the faces flash as it turns."""
    np, cff2gm, tf2tx = _cursor_imports()
    meshes = cff2gm.cff_to_meshes(cff)
    tex = np.asarray(tf2tx.tf_image(tf).convert("RGBA"), dtype=float)
    th, tw = tex.shape[:2]
    tris = []
    for m in meshes:
        for a, b, c in m.triangles[:len(m.triangles) // 2]:    # the second half is the back copy of the faces
            tris.append([(m.vertices[i][0], m.vertices[i][2]) for i in (a, b, c)])
    tip = max((p for t in tris for p, _ in t), key=lambda p: p[2])
    length = tip[2] - min(p[2] for t in tris for p, _ in t)
    k = (size - 2 * CURSOR_TIP) * ss / (length * math.cos(math.pi / 4))   # the length of it along the diagonal
    light = np.array([-0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    big = size * ss

    def turned(p, spin):
        x, y, z = p
        c, s = math.cos(spin), math.sin(spin)
        x, y = x * c - y * s, x * s + y * c             # round the axis of the arrowhead
        x, y, z = x, -z, y                              # the tip goes up the screen (y is down)
        c, s = math.cos(tilt), math.sin(tilt)
        y, z = y * c - z * s, y * s + z * c             # leans to the viewer
        c, s = math.cos(roll), math.sin(roll)
        x, y = x * c - y * s, x * s + y * c             # and to the left
        return x, y, z

    origin = turned(tip, 0.0)
    strip = Image.new("RGBA", (size * frames, size))
    for f in range(frames):
        spin = 2 * math.pi * f / frames
        img = np.zeros((big, big, 4))
        zbuf = np.full((big, big), -1e9)
        for t in tris:
            q = [turned(p, spin) for p, _ in t]
            P = np.array([[(p[0] - origin[0]) * k + CURSOR_TIP * ss, (p[1] - origin[1]) * k + CURSOR_TIP * ss, p[2]]
                          for p in q])
            UV = np.array([uv for _, uv in t])
            normal = np.cross(P[1] - P[0], P[2] - P[0])
            length_n = np.linalg.norm(normal)
            d = (P[1, 0] - P[0, 0]) * (P[2, 1] - P[0, 1]) - (P[2, 0] - P[0, 0]) * (P[1, 1] - P[0, 1])
            if length_n < 1e-9 or abs(d) < 1e-9:
                continue
            normal /= length_n
            if normal[2] < 0:
                normal = -normal                        # both sides of a face are drawn
            shade = 0.55 + 0.6 * max(0.0, float(normal @ light))
            for y in range(max(int(P[:, 1].min()), 0), min(int(P[:, 1].max()) + 1, big)):
                for x in range(max(int(P[:, 0].min()), 0), min(int(P[:, 0].max()) + 1, big)):
                    w1 = ((x + .5 - P[0, 0]) * (P[2, 1] - P[0, 1]) - (P[2, 0] - P[0, 0]) * (y + .5 - P[0, 1])) / d
                    w2 = ((P[1, 0] - P[0, 0]) * (y + .5 - P[0, 1]) - (x + .5 - P[0, 0]) * (P[1, 1] - P[0, 1])) / d
                    w0 = 1 - w1 - w2
                    if min(w0, w1, w2) < 0:
                        continue
                    z = w0 * P[0, 2] + w1 * P[1, 2] + w2 * P[2, 2]
                    if z <= zbuf[y, x]:
                        continue
                    zbuf[y, x] = z
                    u = w0 * UV[0, 0] + w1 * UV[1, 0] + w2 * UV[2, 0]
                    v = w0 * UV[0, 1] + w1 * UV[1, 1] + w2 * UV[2, 1]
                    c = tex[int(v * th) % th, int(u * tw) % tw]
                    img[y, x] = [min(255, c[0] * shade), min(255, c[1] * shade), min(255, c[2] * shade), 255]
        # a box filter down to the frame, the colours weighed by the cover
        cover = img[..., 3:4] / 255
        rgb = (img[..., :3] * cover).reshape(size, ss, size, ss, 3).sum((1, 3))
        al = cover.reshape(size, ss, size, ss, 1).sum((1, 3))
        out = np.zeros((size, size, 4))
        inside = al[..., 0] > 0
        out[inside, :3] = rgb[inside] / al[inside]
        out[..., 3] = al[..., 0] / (ss * ss) * 255
        strip.paste(Image.fromarray(out.astype("uint8"), "RGBA"), (f * size, 0))
    return strip


class Original:
    """The files of an installed Sea Dogs, looked up without caring about the case of letters."""

    def __init__(self, root):
        self.root = Path(root) / "RESOURCE"

    def find(self, relative):
        path = self.root
        for part in re.split(r"[\\/]+", relative):
            if part in ("", "."):
                continue
            if part == "..":
                path = path.parent
                continue
            names = {p.name.lower(): p for p in path.iterdir()} if path.is_dir() else {}
            if part.lower() not in names:
                return None
            path = names[part.lower()]
        return path


def read_ini(path):
    """[Section] key = value, // comments; the order and repeated keys are kept."""
    sections, current = {}, None
    for line in path.read_bytes().decode("cp1251").splitlines():
        line = line.strip()
        if line.startswith("//") or not line:
            continue
        if line.startswith("["):
            current = sections.setdefault(line.strip("[]"), [])
        elif "=" in line and current is not None:
            key, value = line.split("=", 1)
            current.append((key.strip(), value.strip()))
    return sections


def attrs(value):
    return {m.group(1): m.group(2) if m.group(2) is not None else m.group(3).strip() for m in ATTR.finditer(value)}


def text_key(txt):
    return txt.strip("#") if txt.startswith("#") else None


def rgb(value, default):
    return "255," + (value or default)


class Converter:
    def __init__(self, pdm, game):
        self.pdm = Original(pdm)
        self.game = Path(game)
        self.resource = self.game / "resource"
        self.menu = self.read_screens("menu.ini")
        self.strings = self.read_strings()
        self.fonts = {}     # name -> (size, outline, line height on the virtual screen, TrueType file)
        # the fonts of INI/fonts.ini: key -> (face, the scale of its height)
        self.faces = {k: (v.split(",")[3].strip(), float(v.split(",")[0]))
                      for k, v in read_ini(self.pdm.find("INI/fonts.ini"))[LANGUAGE]}
        self.installed = find_faces(font_dirs(pdm))
        self.ttfs = {}      # face -> (TrueType file, is it the original)
        self.pictures = {}  # group -> (texture, width, height, [(name, x1, y1, x2, y2)], size of a button)
        self.plates = {}    # stem -> ((texture, width, height), size of the picture) or None
        self.screens = {}   # the name of a converted screen -> (file, section)
        self.places = {}    # screen -> (the number of its title with %s, the text)
        self.templates = {}  # screen -> {S_XXX: the text of its value}
        self.lists = {}     # screen -> the columns of its list (shiptovarname, shiponboard, ...)
        self.credits = {}  # screen -> the text of its credits, the lines divided by \\n
        self.messages = {}  # screen -> {exit: the text of its t_Exit}
        self.skipped = []
        self.pointers = {}  # the cursors of a screen: name -> a MousePointer line

    def read_screens(self, file):
        """INI/<file>: the screens of one DLL; the paths of their pictures start at [Common] path."""
        self.ini = read_ini(self.pdm.find("INI/" + file))
        self.ini_name = file
        self.base = "IMAGES/" + dict(self.ini["Common"])["path"]
        return self.ini

    # ---------- texts and fonts ----------

    def read_strings(self):
        strings = {}
        path = self.pdm.find(f"TEXTS/{LANGUAGE}/INI/interface.ini")
        for line in path.read_bytes().decode("cp1251").splitlines():
            if "=" in line and not line.lstrip().startswith(("//", "[")):
                key, value = line.split("=", 1)
                strings.setdefault(key.strip(), value.strip().replace('"', "'"))
        # the voices of the characters, a row of [Options] the original has not got (ours)
        strings.setdefault("OptVoices", "Голоса NPC")
        return strings

    def ttf(self, face):
        """The TrueType file of a face of INI/fonts.ini and whether it is the original: the family of the same
        name, else the shortest that starts with it (seawolf -> SeaWolf_L), else a free font."""
        if face not in self.ttfs:
            k = face_key(face)
            found = self.installed.get(k) or next(
                (self.installed[f] for f in sorted(self.installed, key=len) if f.startswith(k)), None)
            if found is not None and not has_cyrillic(found):
                self.skipped.append(f"font {face}: {found.name} has no Cyrillic, "
                                    f"{FREE_FONTS.get(face.lower(), FREE_FONT).stem} stands in")
                found = None
            elif found is None:
                self.skipped.append(f"font {face}: not installed, {FREE_FONTS.get(face.lower(), FREE_FONT).stem} "
                                    "stands in")
            self.ttfs[face] = (found, True) if found else (FREE_FONTS.get(face.lower(), FREE_FONT), False)
        return self.ttfs[face]

    def font(self, spec, face=None):
        """font:"logbook,27,0" -> pdm_logbook_27; the size is the height of a line, as CreateFont takes it.
        The face is the one of logbook in INI/fonts.ini, or the given one."""
        parts = spec.split(",")
        key = parts[0].strip().lower()
        name = f"pdm_{key}_{parts[1].strip()}"
        if name not in self.fonts:
            face, scale = (face, 1.0) if face else self.faces.get(key, ("seawolf", 1.0))
            ttf, original = self.ttf(face)
            height = int(parts[1]) * FONT_OVERSAMPLE * scale * (1.0 if original else FONT_FIT)
            # the TrueType size whose ascent + descent is the height
            ascent, descent = ImageFont.truetype(str(ttf), 100).getmetrics()
            size = max(4, round(height * 100 / (ascent + descent)))
            # the original prints with GDI, without an outline: a black one smears the dark text of the lists
            # on the parchment into bold blots. Only the titles of seadogs keep one over the pictures (ours)
            outline = 2 if key == "seadogs" and height >= 30 else 0
            ascent, descent = ImageFont.truetype(str(ttf), size).getmetrics()
            self.fonts[name] = (size, outline, (ascent + descent + outline * 2) / FONT_OVERSAMPLE, ttf)
        return name

    # ---------- pictures ----------

    def image(self, relative):
        path = self.pdm.find(self.base + relative.replace("$", LANGUAGE))
        if path is None:
            return None
        return Image.open(path).convert("RGB")

    def keyed(self, image):
        mask = Image.new("L", image.size)
        mask.putdata([0 if p == KEY_COLOR else 255 for p in image.getdata()])
        rgba = image.convert("RGBA")
        rgba.putalpha(mask)
        return rgba

    def texture(self, image, name):
        """A picture in a power of two texture; returns the texture name and its size."""
        w, h = 1, 1
        while w < image.width:
            w *= 2
        while h < image.height:
            h *= 2
        canvas = Image.new(image.mode, (w, h))
        canvas.paste(image, (0, 0))
        write_tx(canvas, self.resource / f"textures/interfaces/pdm/{name}.tga.tx", mip_chain=False)
        return f"interfaces\\pdm\\{name}.tga", w, h

    def ship_portraits(self):
        """The pictures of the ships (IMAGES/GOODS/SHIPS/<id>_lg.tga) as ship_<id> textures, stretched to the whole
        power of two texture (the node stretches them back), and SHIPSPRITE, the frame of shipsprite_rect where the
        script puts one (MSG_INTERFACE_MSG_TO_NODE, 2)."""
        folder = self.pdm.find("IMAGES/GOODS/SHIPS")
        for f in sorted(folder.glob("*_lg.tga"), key=lambda f: f.name.lower()):
            image = Image.open(f).convert("RGBA").resize((256, 256), Image.LANCZOS)
            write_tx(image, self.resource / f"textures/interfaces/pdm/ship_{f.name[:-7].lower()}.tga.tx",
                     mip_chain=False)
        # the picture of the gun (IMAGES/GOODS/GOODS/<file>64.tga, 64 x 64 as r_cannon of [ShipYard])
        for name in ("culverin", "demicann", "demiculv"):
            image = Image.open(self.pdm.find(f"IMAGES/GOODS/GOODS/{name}64.tga")).convert("RGBA")
            write_tx(image, self.resource / f"textures/interfaces/pdm/cannon_{name}.tga.tx", mip_chain=False)
        return ([("PICTURE", "SHIPSPRITE"), ("PICTURE", "CANNONSPRITE")],
                ["[SHIPSPRITE]", "position = 310,135,489,285", "bNotUse = 1", "",
                 "[CANNONSPRITE]", "position = 62,416,126,480", "bNotUse = 1", ""])

    def save_grid(self, e):
        """The saves of [SaveGame] and [LoadGame] (IconsRect): a grid of the cells of icon1.tga (the selected one) and
        icon2.tga, 142 x 145. In a cell the screenshot of the save (savesprite_rect, the script puts it in, MSG_INTERFACE_
        LOADPICTUREFROMSAVE), the name on the ribbon (FileNameRect) and the text under it (FileTextRect). CELL<n> is
        a click on the whole cell. The cells are SAVE_COLUMNS wide and SAVE_ROWS high in IconsRect, one row of them
        a step of the arrows (the pitch is ours: the original does it in the DLL)."""
        ax, ay, aw, ah = (int(v) for v in e["IconsRect"].split(","))
        sx, sy, sw, sh = (int(v) for v in e["savesprite_rect"].split(","))
        nx, ny, nw, nh = (int(v) for v in e["FileNameRect"].split(","))
        tx, ty, tw, th = (int(v) for v in e["FileTextRect"].split(","))
        icons = []
        for name in ("icon1", "icon2"):
            image = self.image(e[name])
            tex, w, h = self.texture(self.keyed(image), "save_" + name)
            icons.append((tex, image.width / w, image.height / h, image.width, image.height))
        cw, ch = icons[0][3], icons[0][4]
        pitch_x, pitch_y = aw // SAVE_COLUMNS, ah // SAVE_ROWS
        nodes, lines = [], []

        def cell_font(key, default):
            a = attrs(e[key])
            return self.font(a.get("font", default)), rgb(a.get("rgb"), "255,255,255")

        name_font, name_color = cell_font("EditFileName", "logbook_italic,19,0")
        text_font, text_color = cell_font("EditFileText", "logbook_italic,19,0")
        for k in range(SAVE_COLUMNS * SAVE_ROWS):
            x, y = ax + k % SAVE_COLUMNS * pitch_x, ay + k // SAVE_COLUMNS * pitch_y
            for suffix, (tex, ur, vb, w, h) in (("FRAME", icons[1]), ("SEL", icons[0])):
                nodes.append(("PICTURE", f"CELL{k}_{suffix}"))
                lines += [f"[CELL{k}_{suffix}]", f"position = {x},{y},{x + w},{y + h}", f"textureName = {tex}",
                          f"textureRect = 0,0,{ur:g},{vb:g}", "bNotUse = 1", ""]
            nodes.append(("PICTURE", f"CELL{k}_SHOT"))
            lines += [f"[CELL{k}_SHOT]", f"position = {x + sx},{y + sy},{x + sx + sw},{y + sy + sh}",
                      f"textureName = {icons[1][0]}", "textureRect = 0.6,0.6,0.61,0.61", "bNotUse = 1", ""]
            for suffix, (fx, fy, fw, fh), font, color, align in (
                    ("NAME", (nx, ny, nw, nh), name_font, SAVE_YELLOW, "center"),
                    # on the dark ribbon of a cell not selected the name is light (ours, the original keeps 8,8,8)
                    ("NAMEN", (nx, ny, nw, nh), name_font, SAVE_NAME_LIGHT, "center"),
                    ("TEXT", (tx, ty, tw, th), text_font, text_color, "center"),
                    # the text of the selected cell is yellow (the original shows it so)
                    ("TEXTY", (tx, ty, tw, th), text_font, SAVE_YELLOW, "center")):
                nodes.append(("FORMATEDTEXT", f"CELL{k}_{suffix}"))
                # a box lower than a line shows nothing: the line sits in the middle of the rect of the original
                line_h = round(self.fonts[font][2])
                fy -= (line_h - fh) // 2 if fh < line_h else 0
                fh = max(fh, line_h)
                lines += [f"[CELL{k}_{suffix}]", f"position = {x + fx},{y + fy},{x + fx + fw},{y + fy + fh}",
                          f"font = {font}", f"fontScale = {1 / FONT_OVERSAMPLE:.3f}",
                          f"lineSpace = {round(self.fonts[font][2])}", f"color = {color}", f"alignment = {align}",
                          "bNotUse = 1", ""]
            nodes.append(("FORMATEDTEXT", f"CELL{k}"))
            lines += [f"[CELL{k}]", f"position = {x},{y},{x + cw},{y + ch}", f"font = {name_font}", "color = 0,0,0,0",
                      "command = click", "bNotUse = 1", ""]
        return nodes, lines

    def stamp(self, file, name):
        """A brush of alpha (MAP.dll mask_black*.tga) centred in a power of two texture; returns the texture name."""
        image = Image.open(self.pdm.find(self.base + file)).convert("RGBA")
        w, h = 1, 1
        while w < image.width:
            w *= 2
        while h < image.height:
            h *= 2
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(image, ((w - image.width) // 2, (h - image.height) // 2))
        write_tx(canvas, self.resource / f"textures/interfaces/pdm/{name}.tga.tx", mip_chain=False)
        return f"interfaces\\pdm\\{name}.tga"

    def button_group(self, file):
        """<file>-nor.tga and -hi.tga in one atlas (None without them): TEXTBUTTON draws a left and a right piece of their
        own width and stretches the middle, so the halves are the pieces and the middle is 2 pixels."""
        stem = re.split(r"[\\/]", file)[-1].lower()
        check = stem in CHECKS
        # bsmall of STATUS\ is narrower than the one of BUTTONS\
        if not file.startswith(".."):
            stem = self.base.split("/")[1].rstrip("\\").lower() + "_" + stem
        group = "PDM_" + stem.upper().replace("-", "_")
        if group in self.pictures:
            return group, self.pictures[group][4]
        nor, hi = self.image(file + "-nor.tga"), self.image(file + "-hi.tga")
        if nor is None:
            return None
        hi = hi or nor
        w, h = nor.size
        # a check of [Options]: check-nor.tga is the tick, check-hi.tga the cross. The tick stays under the mouse,
        # the cross is <NODE>_OFF over the button, shown by the scripts (ours)
        select = 0 if check else h + 2
        atlas = Image.new("RGB", (w, h * 2 + 2))
        atlas.paste(nor, (0, 0))
        atlas.paste(hi, (0, h + 2))
        tex, tw, th = self.texture(self.keyed(atlas), stem)
        half = w // 2 - 1
        pictures = []
        for prefix, top in (("", 0), ("select ", select)):
            pictures += [(prefix + "left", 0, top, half, top + h),
                         (prefix + "middle", half, top, half + 2, top + h),
                         (prefix + "right", half + 2, top, w, top + h)]
        self.pictures[group] = (tex, tw, th, pictures, (w, h))
        return group, (w, h)

    def credits_text(self, out_name):
        """The credits (ours): the original scrolls TEXTS/<language>/INI/credits.ini by its DLL, in rect_credits.
        The lines become one centred FORMATEDTEXT CREDITSTEXT that program/screens.c scrolls: a title of a group
        (xo:400) after an empty line, a name on its own line, its description under it."""
        path = self.pdm.find(f"TEXTS/{LANGUAGE}/INI/credits.ini")
        rows = []
        for line in path.read_bytes().decode("cp1251").splitlines():
            m = re.match(r"s_credits(\d+)\s*=\s*(.*)", line.strip())
            if not m:
                continue
            a = attrs(m.group(2))
            if a.get("txt"):
                rows.append((int(m.group(1)), "xo" in a, a["txt"].replace('"', "'")))
        text = []
        for _, title, txt in sorted(rows):
            if title and text:
                text.append("")
            text.append(txt)
        self.credits[out_name] = "\\n".join(text)
        font = self.font("logbook,19,0")
        lines = ["[CREDITSTEXT]", "position = 0,152,800,590", f"font = {font}",
                 f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", f"lineSpace = {round(self.fonts[font][2])}",
                 "color = 255,255,231,111", "alignment = center", ""]
        return [("FORMATEDTEXT", "CREDITSTEXT")], lines

    def options_volume(self):
        """The volume of [Options] (ours): a row "- 80% +" beside the check of the effects, of the music and of the
        voices of the characters, and the check of the voices (LB_VOICEON) the original has not got. A click on - or +
        changes the volume by a step, the scripts (options.c) show the value."""
        group = "PDM_MENU_CHECK"
        tex, tw, th, _, (w, h) = self.pictures[group]
        big = self.font("logbook,27,0")
        small = "pdm_logbook_italic_18"
        nodes, lines = [], []
        # the check of the voices under the music, as the ones of the sound
        y = 255
        nodes += [("TEXTBUTTON", "LB_VOICEON"), ("PICTURE", "LB_VOICEON_OFF")]
        lines += ["[LB_VOICEON]", f"position = 264,{y},{264 + w},{y + h}", f"group = {group}", f"font = {big}",
                  f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", "strOffset = 4", "fontColor = 255,255,255,255",
                  "fontColorSelected = 255,255,255,255", "fontColorPressed = 255,255,255,255",
                  "unselectableFontColor = 255,128,128,128", "command = click", "command = activate",
                  "command = deactivate", "",
                  "[LB_VOICEON_OFF]", f"position = 264,{y},{264 + w},{y + h}", f"textureName = {tex}",
                  f"textureRect = 0,{(h + 2) / th:g},{w / tw:g},{(2 * h + 2) / th:g}", "bNotUse = 1", ""]
        for name, row in (("FX", 130), ("MUSIC", 205), ("VOICE", 255)):
            cy = row + h // 2 - 8
            for node, x0, x1, font, align, text in ((f"LB_{name}DOWN", 336, 358, small, "center", "-"),
                                                     (f"LB_{name}VAL", 360, 450, small, "center", "100%"),
                                                     (f"LB_{name}UP", 452, 474, small, "center", "+")):
                nodes.append(("FORMATEDTEXT", node))
                lines += [f"[{node}]", f"position = {x0},{cy},{x1},{cy + 22}", f"font = {font}",
                          f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", f"lineSpace = {round(self.fonts[font][2])}",
                          "color = 255,255,255,255", f"alignment = {align}"]
                lines += ["command = click", ""] if node != f"LB_{name}VAL" else [""]
        nodes.append(("FORMATEDTEXT", "LB_VOICELABEL"))
        lines += ["[LB_VOICELABEL]", f"position = 70,{255 + 7},230,{255 + 25}", f"font = {small}",
                  f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", f"lineSpace = {round(self.fonts[small][2])}",
                  "color = 255,255,255,255", "alignment = right", "string = OptVoices", ""]
        return nodes, lines

    # ---------- a screen ----------

    def position(self, a, w, h):
        """The rect of a w x h element by xo/yo (centre), xl/yl (left/top), xr/yr (right/bottom)."""
        if "xo" in a:
            x = int(a["xo"]) - w // 2
        elif "xr" in a:
            x = int(a["xr"]) - w
        else:
            x = int(a.get("xl", 0))
        if "yo" in a:
            y = int(a["yo"]) - h // 2
        elif "yr" in a:
            y = int(a["yr"]) - h
        else:
            y = int(a.get("yl", 0))
        return x, y

    def entries(self, section):
        """The keys of a screen: the text fields of [Common] (the help, the description, the name and the money
        of the hero under his face) and then its own; a key given again replaces the earlier one in its place,
        @key@ is the value of that key of the screen (lb_Sell = ...,@rgb_small@)."""
        own = self.ini[section]
        common = [] if section in NO_COMMON else [(k, v) for k, v in self.ini["Common"] if k.lower().startswith("edit")]
        out = {}
        for k, v in common + own:
            out[k] = v
        for k, (other, other_key) in FIELDS_OF.get(section, {}).items():
            out = {o: v for o, v in out.items() if o.lower() != k.lower()}
            out[k] = dict(self.ini[other])[other_key]
        macros = dict(own)
        # the nodes are drawn in their order: the background under the fields of [Common]
        keys = sorted(out, key=lambda k: k.lower() != "background")
        return [(k, re.sub(r"@(\w+)@", lambda m: macros.get(m.group(1), ""), out[k])) for k in keys]

    def field(self, key, a, w, h, align=None):
        """A FORMATEDTEXT the scripts fill: an EditXxx of the original (its dx, dy and font) or the place of
        a value of the screen (s_Xxx). The text of txt:"#Key#" is there from the start."""
        name = self.font(a.get("font", "logbook,18"))
        x, y = self.position(a, w, h)
        line = round(self.fonts[name][2])
        if a.get("type") == "2" and h > line:
            # type:2 of the original centres the text in its box, ours sits at the top of it (a title in a thin bar)
            y += (h - line) // 2
            h = line
        if align is None:
            align = "center" if "xo" in a else "right" if "xr" in a else "left"
        color = rgb(a.get("rgb"), "255,255,255")
        if key.lower() in ("editcontrolsdesc", "editcontrolskeys"):
            # the rows of the original lie in rect_controls (87,98,626,406) in dark ink (rgb 8,8,8 of control#)
            x, y, w, h = (105 if key.lower() == "editcontrolsdesc" else 400), 108, 220, 290
            color = "255,8,8,8"
        lines = [f"[{key.upper()}]", f"position = {x},{y},{x + w},{y + h}", f"font = {name}",
                 f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", f"lineSpace = {round(self.fonts[name][2])}",
                 f"color = {color}", f"alignment = {align}"]
        string = text_key(a.get("txt", ""))
        if string:
            lines.append(f"string = {string}")
        return x, y, lines

    def columns(self, out_name, areas, columns, frames):
        """The rows of the goods are drawn by the C++ of the DLLs: p_ShipTovarName = 80, p_ShipOnboard = 219 ...
        give the x of the columns in EditShipTovars and EditShopTovars. A FORMATEDTEXT LIST_<COLUMN> per column
        over the rows of the list, its font and colour, one line a row; the name column is left aligned up to
        the next one, the numbers are centred at their x (ours). The columns of a group outside one frame of
        the list ([SChest] puts its own in other places) are not a table: the scripts fill the Edit field."""
        nodes, lines = [], []
        for group in ("SHIP", "SHOP"):
            area = areas.get(f"EDIT{group}TOVARS")
            # [Transfer]: the names of the goods of the other ship (p_ShipTovarName1) stand in its list, over the store column
            cols = sorted((x, name) for name, x in columns.items()
                          if (group == "SHOP") == (name.startswith("SHOP") or name.endswith("TOVARNAME1")) and name.startswith(("SHIP", "SHOP")))
            if area is None or not cols:
                continue
            x, y, w, h, a = area
            if not any(all(f[0] <= c < f[2] for c, _ in cols) for f in frames):
                continue
            for i, (cx, name) in enumerate(cols):
                if name.endswith("TOVARNAME"):
                    right = cols[i + 1][0] - COLUMN_WIDTH // 2 if i + 1 < len(cols) else x + w
                    rect, align = (x, right), "left"
                else:
                    rect, align = (cx - COLUMN_WIDTH // 2, cx + COLUMN_WIDTH // 2), "center"
                node = f"LIST_{name}"
                _, _, l = self.field(node, a, w, h, align)
                l[1] = f"position = {rect[0]},{y},{rect[1]},{y + h}"
                nodes.append(("FORMATEDTEXT", node))
                lines += l + [""]
                self.lists.setdefault(out_name, []).append(name.lower())
        return nodes, lines

    def plate(self, file):
        """The plate under a title (frames\\m_titles.tga), its black keyed out."""
        stem = "plate_" + re.split(r"[\\/]", file)[-1].lower().rsplit(".", 1)[0]
        if stem not in self.plates:
            image = self.image(file)
            self.plates[stem] = None if image is None else (self.texture(self.keyed(image), stem), image.size)
        return self.plates[stem]

    def screen(self, file, section):
        self.read_screens(file)
        out_name = self.out_name(file, section)
        nodes, lines, titles, notes = [], [], [], []
        buttons, chart = [], {}
        areas, columns, frames = {}, {}, []
        entries = self.entries(section)
        title_attrs = attrs(dict(self.ini["Common"]).get("EditTitle", ""))
        for key, value in entries:
            low = key.lower()
            if section == "MainMap" and low in ("map_pos", "map_rect", "editisland", "editmessages", "lb_ok", "lb_yes", "lb_no"):
                chart[low] = value
                continue
            if low == "background":
                image = self.image(value)
                if image is None:
                    self.skipped.append(f"{section}.{key}: no {value}")
                    continue
                stem = "back_" + out_name
                rect = dict(entries).get("fon_rect")
                if rect:
                    nodes.append(("PICTURE", "BACKGROUND"))
                    # a window over the screen (the message box): the picture at fon_rect as it is
                    x, y, w, h = (int(v) for v in rect.split(","))
                    tex, tw, th = self.texture(image, stem)
                    lines += ["[BACKGROUND]", f"position = {x},{y},{x + w},{y + h}", f"textureName = {tex}",
                              f"textureRect = 0,0,{w / tw:g},{h / th:g}", ""]
                    continue
                # a window wider than 4:3 shows the bands beside the screen: the background stretched, blurred
                # and darkened under them, so they do not stay black (ours)
                wide = image.resize((512, 192), Image.LANCZOS).filter(ImageFilter.GaussianBlur(12))
                wide = ImageEnhance.Brightness(wide).enhance(0.55)
                tex, tw, th = self.texture(wide, stem + "_wide")
                nodes.append(("PICTURE", "BACKFILL"))
                lines += ["[BACKFILL]", f"position = {-WIDE_BAND},0,{800 + WIDE_BAND},600", f"textureName = {tex}",
                          f"textureRect = 0,0,1,{192 / th:g}", ""]
                nodes.append(("PICTURE", "BACKGROUND"))
                full = image.resize((1024, 768), Image.LANCZOS)
                tex, tw, th = self.texture(full, stem)
                self.back = (tex, 768 / th)
                lines += ["[BACKGROUND]", "position = 0,0,800,600", f"textureName = {tex}",
                          f"textureRect = 0,0,1,{768 / th:g}", ""]
            elif low.startswith("title"):
                a = attrs(value) if low != "titletxt" else dict(title_attrs, txt=value)
                name = self.font(a.get("font", "logbook,20"))
                size, _, line_h, _ = self.fonts[name]
                if "file" in a:
                    plate = self.plate(a["file"])
                    if plate is None:
                        self.skipped.append(f"{section}.{key}: no {a['file']}")
                    else:
                        (tex, tw, th), (w, h) = plate
                        x, y = self.position(a, w, h)
                        node = f"PLATE{len([n for n in nodes if n[1].startswith('PLATE')])}"
                        nodes.append(("PICTURE", node))
                        lines += [f"[{node}]", f"position = {x},{y},{x + w},{y + h}", f"textureName = {tex}",
                                  f"textureRect = 0,0,{w / tw:g},{h / th:g}", ""]
                key_name = text_key(a.get("txt", ""))
                if not key_name:
                    continue  # an empty title: the scripts write there (title1 of [Trade])
                if "xo" in a:
                    x, state = int(a["xo"]), "C"
                elif "xr" in a:
                    x, state = int(a["xr"]), "R"
                else:
                    x, state = int(a.get("xl", 0)), "L"
                if "yo" in a:
                    y = int(a["yo"]) - round(line_h / 2)
                elif "yr" in a:
                    y = int(a["yr"]) - round(line_h)
                else:
                    y = int(a.get("yl", 0))
                if "%s" in self.strings.get(key_name, ""):
                    # "Магазин на %s": the script puts the place in (string n of TITLES)
                    self.places[out_name] = (len(titles) + 1, self.strings[key_name])
                titles.append(f"string = {key_name},font:{name},pos:{{{x},{y}}},fc:{{{rgb(a.get('rgb'), '255,255,255')}}},"
                              f"bc:{{0,0,0,0}},scale:{1 / FONT_OVERSAMPLE:.3f},state:{{{state}}}")
            elif low.startswith("lb_"):
                a = attrs(value)
                if "file" in a and (text_key(a.get("txt", "")) or section != "MainMap"):
                    buttons.append((key, a))
                elif "file" not in a and section != "MainMap":
                    # a line of text that takes a click (the resolution of [Options], the weights of [Trade])
                    name = self.font(a.get("font", "logbook,18"))
                    w, h = int(a.get("dx", 150)), int(a.get("dy", round(self.fonts[name][2])))
                    x, y, l = self.field(key, dict(a, txt=""), w, h, "left")
                    nodes.append(("FORMATEDTEXT", key.upper()))
                    lines += l + ["command = click", ""]
                else:
                    # the buttons of the message box of the map, drawn by MAP.dll over map_message.tga
                    self.skipped.append(f"{section}.{key}: a button of a message box")
            elif low == "editfiles" and section in SAVE_GRID:
                notes.append(f"; {key} = {value}")  # the list of the files is the grid of the saves (save_grid)
            elif low.startswith("edit") and low != "editisland":
                a = attrs(value)
                if "dx" not in a or "dy" not in a:
                    notes.append(f"; {key} = {value}")
                    continue
                w, h = int(a["dx"]), int(a["dy"])
                if section == "ShipYard" and key.lower() == "edithelp":
                    a = dict(a, type="1"); h = max(h, 30)  # "Ваш ранг позволяет управлять вам кораблями до 6 класса" takes three lines of the list's panel (ours)
                x, y, l = self.field(key, a, w, h)
                if section == "ShipYard" and key.lower() == "edithelp":
                    y += 14; h -= 14; l[1] = f"position = {x},{y},{x + w},{y + h}"   # from the middle of its box down, as the one line was
                if (x, y) == (0, 0) or x < 0 or y < 0 or x + w > 800 or y + h > 600:
                    # a pattern of a row of a list (EditSkillName at 0,0) or off the screen (EditTotalMonthly)
                    notes.append(f"; {key} = {value}")
                    continue
                nodes.append(("FORMATEDTEXT", key.upper()))
                if (section, key) in SELECT_LISTS:
                    # the files of the saves: a row the cursor goes over, as the islands of the map (ours)
                    l += ["backColor = 96,255,196,0", "backOffset = 2,0,2,0", "wrapoff = 1", "command = activate",
                          "command = click", "command = upstep", "command = downstep"]
                lines += l + [""]
                areas[key.upper()] = (x, y, w, h, a)
            elif low.startswith("s_") and "txt:" in value:
                a = attrs(value)
                name = self.font(a.get("font", "logbook,18"))
                h = round(self.fonts[name][2])
                y = self.position(a, 0, h)[1]
                if y < 40:
                    notes.append(f"; {key} = {value}")  # a value inside a row of a list (s_OfficerName)
                    # or a text the DLL puts where it wants (xl:0,yl:0): "Деньги %d" of the shipyard, for the scripts
                    if y == 0 and text_key(a.get("txt", "")) in self.strings:
                        self.messages.setdefault(out_name, {})[low[2:]] = self.strings[text_key(a["txt"])]
                    if low == "s_money" and out_name == "shipyard":
                        # where the DLL puts it: the right bottom of the screen (the screenshot of the original, ours)
                        x, y, l = self.field("EditShipMoney", dict(a, xl="560", yl="530", font="logbook,20",
                                                                  rgb="250,240,175", txt=""), 200, 30)
                        nodes.append(("FORMATEDTEXT", "EDITSHIPMONEY"))
                        lines += l + [""]
                    continue
                # the text of the value: "Ранг %d", a unit after the value ("узлов") or nothing; the script
                # puts the value in (PdmScreens), the node shows no %d before it
                txt = a.get("txt", "")
                # a key common.ini has not ("#Reputation: %s") shows the bare value
                text = self.strings.get(text_key(txt), "" if txt.startswith("#") else txt)
                self.templates.setdefault(out_name, {})[key.upper()] = text
                x, y, l = self.field(key, dict(a, txt="" if "%" in text else a.get("txt", "")), S_WIDTH, h)
                nodes.append(("FORMATEDTEXT", key.upper()))
                # the shipyard: the class and the guns of the row of the type are switched by a click (ours, the original does it by arrows)
                lines += l + (["command = click"] if out_name == "shipyard" and key.upper() in SHIPYARD_CLICK else []) + [""]
            elif low.startswith("t_"):
                # the texts the screen shows in a message box (t_Exit = #YouWant2Exit#), for the scripts
                if text_key(value) in self.strings:
                    self.messages.setdefault(out_name, {})[low[2:]] = self.strings[text_key(value)]
            elif low == "titletxt":
                pass
            elif low.startswith("e_") and text_key(value.strip()) in self.strings:
                # the messages of the screen (e_BuyButClass = #ShipYardBuyButClass#), for the scripts
                self.messages.setdefault(out_name, {})[low[2:]] = self.strings[text_key(value.strip())]
                notes.append(f"; {key} = {value}")
            else:
                if low.startswith("p_"):
                    columns[key[2:].upper()] = int(re.split(r"[,/ \t]", value)[0])
                elif low.startswith("ramka_"):
                    frames.append([int(v) for v in value.split("//")[0].split(",")[1:5]])
                # the layout the scripts of a screen use: frames drawn into the background (ramka, vignette),
                # rects of lists, faces and ship sprites, the columns of the goods
                notes.append(f"; {key} = {value}")

        n, l = self.columns(out_name, areas, columns, frames)
        nodes += n
        lines += l
        if chart:
            n, l = self.chart(chart)
            nodes += n
            lines += l
        if out_name == "shipexchange":
            n, l = self.second_ship(lines)
            nodes += n
            lines += l
        if titles:
            nodes.append(("STRINGCOLLECTION", "TITLES"))
            lines += ["[TITLES]"] + titles + [""]

        # the buttons in the place of another one are the other state of it (lb_Sell / lb_SCancel,
        # lb_Yes / lb_Ok of the message box): hidden, the scripts show the one they need
        rects, shown = {}, []
        for key, a in buttons:
            group, (w, h) = self.button_group(a["file"]) or (None, (0, 0))
            if group is None:
                self.skipped.append(f"{section}.{key}: no {a['file']}-nor.tga")
                continue
            x, y = self.position(a, w, h)
            rects.setdefault((x, y, w, h), []).append(key)
            # the handles of the sliders of the original cannot be dragged: the rows of OPTIONS_VOLUME replace them (ours)
            gone = section == "Options" and key.lower() in ("lb_soundpos", "lb_musicpos")
            shown.append((key, a, group, x, y, w, h, rects[(x, y, w, h)][0] != key or gone))
        names = [k.upper() for k, a, *_, hidden in shown if not hidden and text_key(a.get("txt", ""))]
        for key, a, group, x, y, w, h, hidden in shown:
            font = self.font(a.get("font", "logbook,27,0"))
            line_h = self.fonts[font][2]
            node = key.upper()
            nodes.append(("TEXTBUTTON", node))
            string = text_key(a.get("txt", ""))
            lines += [f"[{node}]", f"position = {x},{y},{x + w},{y + h}"]
            lines += [f"string = {string}"] if string else []
            lines += [f"group = {group}", f"font = {font}", f"fontScale = {1 / FONT_OVERSAMPLE:.3f}",
                      f"strOffset = {round((h - line_h) / 2)}",
                      f"fontColor = {rgb(a.get('rgbn'), '255,255,255')}",
                      f"fontColorSelected = {rgb(a.get('rgba'), '255,255,255')}",
                      f"fontColorPressed = {rgb(a.get('rgbd'), '255,255,255')}",
                      f"unselectableFontColor = {rgb(a.get('rgbi'), '128,128,128')}",
                      "command = click", "command = activate"]
            if section in ("LoadGame", "SaveGame"):
                # the arrows go over the cells of the saves (save.c), not over the buttons
                lines += [f"command = {c}" for c in ("leftstep", "rightstep", "upstep", "downstep")]
            elif node in names:
                i = names.index(node)
                if i > 0:
                    lines.append(f"command = upstep,select:{names[i - 1]}")
                if i + 1 < len(names):
                    lines.append(f"command = downstep,select:{names[i + 1]}")
            lines += ["command = deactivate"] + (["bNotUse = 1"] if hidden else []) + [""]
            stem = re.split(r"[\\/]", a["file"])[-1].lower()
            if stem in CHECKS:
                tex, tw, th = self.pictures[group][:3]
                nodes.append(("PICTURE", node + "_OFF"))
                lines += [f"[{node}_OFF]", f"position = {x},{y},{x + w},{y + h}", f"textureName = {tex}",
                          f"textureRect = 0,{(h + 2) / th:g},{w / tw:g},{(2 * h + 2) / th:g}", "bNotUse = 1", ""]

        if section in SAVE_GRID:
            n, l = self.save_grid(dict(entries))
            nodes += n
            lines += l
        if out_name == "shipyard":
            n, l = self.ship_portraits()
            nodes += n
            lines += l
        if section == "Options":
            n, l = self.options_volume()
            nodes += n
            lines += l
        if section == "Credits":
            n, l = self.credits_text(out_name)
            nodes += n
            lines += l

        if section == "ShipYard":
            # the highlight of the selected row of the guns (the screenshots of the original): under the texts, the script shows one of them
            for i, y in enumerate((306, 343, 363)):
                nodes.append(("FORMATEDTEXT", f"GUNROW{i}"))
                lines += [f"[GUNROW{i}]", f"position = 60,{y},228,{y + 18}", "font = pdm_logbook_16", "fontScale = 0.667", "lineSpace = 18",
                          "color = 255,8,8,8", "alignment = left", "backColor = 96,255,196,0", "backOffset = 2,0,2,0", "wrapoff = 1", "bNotUse = 1", ""]

        if chart:
            # the date and the anchors go over the pictures of the frame (the items are drawn in the order of the list)
            for name in ("EDITTIME", "EDITANCHOR"):
                nodes.remove(("FORMATEDTEXT", name))
                nodes.append(("FORMATEDTEXT", name))
        head = [f"; converted by tools/pdm_ui.py from [{section}] of INI/{self.ini_name} of the original"]
        head += notes and ["; the layout of the original for the scripts of the screen:"] + notes
        head += ["[MAIN]"] + [f"item = {kind},{name}" for kind, name in nodes]
        if chart:
            head.append("start = ISLANDS")
        elif names:
            head.append(f"start = {names[0]}")
        if chart:
            # the list of the anchors (mapparam.ini [Anchors]): rows to click, filled by map.c at anchor (ours: a list like the islands)
            at = lines.index("[EDITANCHOR]")
            lines[at + 1:at + 1] = ["command = activate", "command = click", "wrapoff = 1", "backColor = 96,255,196,0", "backOffset = 2,0,2,0"]
        out = self.resource / f"ini/interfaces/{out_name}.ini"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(head + [""] + lines), encoding="utf-8")
        self.screens[out_name] = (file, section)

    def second_ship(self, lines):
        """The values of the ship on the right of ShipExchange: RANSACK.dll draws the values of both ships with one
        function, the second at a shift of the first (the labels S_SHIP15.. of ransack.ini stand 516 px to the right of
        S_SHIP0..), so S_<NAME>1 is a copy of S_<NAME> 516 px to the right (ours: ransack.ini has no nodes for them)."""
        shift = 516
        names = ("S_TYPE", "S_CLASS", "S_HITPOINTS", "S_SPEEDRATE", "S_TURNRATE", "S_MAXCREW", "S_MINCREW", "S_CAPACITY", "S_GUNPORTS")
        nodes, out = [], []
        for name in names:
            if f"[{name}]" not in lines:
                continue
            at = lines.index(f"[{name}]")
            end = at + 1
            while end < len(lines) and lines[end] != "" and not lines[end].startswith("["):
                end += 1
            block = [f"[{name}1]"] + lines[at + 1:end]
            for i, line in enumerate(block):
                if line.startswith("position = "):
                    x0, y0, x1, y1 = (int(v) for v in line[11:].split(","))
                    block[i] = f"position = {x0 + shift},{y0},{x1 + shift},{y1}"
            nodes.append(("FORMATEDTEXT", name + "1"))
            out += block + [""]
        return nodes, out

    def out_name(self, file, section):
        """<section>.ini; a section of the same name in another file (MessageBox) gets the file after it."""
        name = section.lower()
        if self.screens.get(name, (file,))[0] != file:
            name += "_" + file.split(".")[0]
        return name

    # ---------- the world map ----------

    def chart(self, chart):
        """The map of MAP.dll: MAP\\$\\map_open.tga (the explored Caribbean with the islands drawn, 1200 x 900)
        seen through a window of map_rect at map_pos, the ship of the hero (ship.tga) on it and the list of
        the islands at EditIsland. program/map.c moves the window and the ship; the list it fills itself; a click
        on the map sails to the island under it (ours)."""
        x, y = (int(v) for v in chart["map_pos"].split(","))
        _, _, w, h = (int(v) for v in chart["map_rect"].split(","))
        full = self.image(f"{LANGUAGE}\\map_open.tga")
        tex, tw, th = self.texture(full, "map_open")
        # the fog of MAP.dll: map_close.tga over it, packed the same, opened by the stamps mask_black (the route)
        # and mask_black_island (an island found); map.c burns them (fogTexture of the PICTURE)
        fog, _, _ = self.texture(self.image("map_close.tga"), "map_close")
        stamps = [self.stamp(f"{name}.tga", f"map_{name}") for name in MAP_FOG_STAMPS]
        ship = self.keyed(self.image("ship.tga"))
        stex, sw, sh = self.texture(ship, "map_ship")
        a = attrs(chart["editisland"])
        font = self.font(a["font"])
        line_h = round(self.fonts[font][2]) + 2
        ix, iy = int(a["xl"]), int(a["yl"])
        # on a wide window map.c draws the background in two halves and repeats a strip of its middle
        # between them (BACK_TILE<n>, ours): the frame grows longer without stretching
        back, bv = self.back
        nodes, lines = [], []
        for name in ["BACK_RIGHT"] + [f"BACK_TILE{i}" for i in range(MAP_BACK_TILES)]:
            nodes.append(("PICTURE", name))
            lines += [f"[{name}]", "position = 0,0,0,0", f"textureName = {back}", f"textureRect = 0,0,1,{bv:g}", ""]
        nodes += [("PICTURE", "MAP"), ("PICTURE", "SHIP"), ("FORMATEDTEXT", "ISLANDS"), ("SCROLLER", "ISLSCROLL")]
        scroll_lines = self.island_scroller(ix + int(a["dx"]) + 4, iy, int(a["dy"]))
        # the message of an encounter (MAP.dll SetMessages): the scroll map_message.tga with EditMessages on it and the buttons
        # lb_Ok / lb_Yes ("В бой") / lb_No ("Игнорировать"); all of them are of no size until map.c shows them (Map_Message)
        scroll = self.keyed(Image.open(self.pdm.find(self.base + "map_message.tga")).convert("RGBA"))
        mtex, mw, mh = self.texture(scroll, "map_message")
        nodes.append(("PICTURE", "MSGSCROLL"))
        lines += ["[MSGSCROLL]", "position = 0,0,0,0", f"textureName = {mtex}",
                  f"textureRect = 0,0,{scroll.width / mw:g},{scroll.height / mh:g}", ""]
        # over the scroll, so it is made here and not with the other fields
        am = attrs(chart["editmessages"])
        _, _, l = self.field("EditMessages", am, int(am["dx"]), int(am["dy"]))
        nodes.append(("FORMATEDTEXT", "EDITMESSAGES"))
        lines += l + [""]
        # TEXTBUTTON like the buttons of a message box (a FORMATEDTEXT button showed no text in the frame, ours); the texts are
        # lbMapOK / lbMapEngage / lbMapIgnore of interface.ini, the dark brown of EditMessages, red when pressed
        places = {"lb_ok": ("350,371,450,401", "lbMapOK"), "lb_yes": ("265,365,385,395", "lbMapEngage"),
                  "lb_no": ("415,365,535,395", "lbMapIgnore")}
        for key in ("lb_ok", "lb_yes", "lb_no"):
            b = attrs(chart[key])
            bfont = "pdm_logbook_19"  # the font of the buttons of a message box; the seadogs font draws twice as big (ours)
            nodes.append(("TEXTBUTTON", key.upper()))
            lines += [f"[{key.upper()}]", "position = -2000,-2000,-1900,-1970", f"string = {places[key][1]}", f"font = {bfont}",
                      f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", "strOffset = 6", "fontColor = 255,49,24,0",
                      "fontColorSelected = 255,150,20,10", "fontColorPressed = 255,245,41,34",
                      "command = click", "command = activate", "command = deactivate", ""]
        lines += ["[MAP]", f"position = {x},{y},{x + w},{y + h}", f"textureName = {tex}",
                 f"textureRect = 0,0,{w / tw:g},{h / th:g}", f"fogTexture = {fog}"]
        lines += [f"fogStamp = {stamp}" for stamp in stamps]
        lines += ["command = click", "",
                 "[SHIP]", f"position = {x},{y},{x + ship.width},{y + ship.height}", f"textureName = {stex}",
                 f"textureRect = 0,0,{ship.width / sw:g},{ship.height / sh:g}", "",
                 "[ISLANDS]", f"position = {ix},{iy},{ix + int(a['dx'])},{iy + int(a['dy'])}",
                 f"font = {font}", f"fontScale = {1 / FONT_OVERSAMPLE:.3f}", f"lineSpace = {line_h}",
                 f"color = {rgb(a.get('rgb'), '255,255,255')}", "backColor = 96,255,196,0", "backOffset = 2,0,2,0",
                 "wrapoff = 1", "scrollerName = ISLSCROLL", "command = activate", "command = click", "command = upstep",
                 "command = downstep", ""] + scroll_lines
        self.map_size = full.size
        return nodes, lines

    def island_scroller(self, x, y, height):
        """The scroller of the list of the islands (scroll_up, scroll_down, scroll_polzun0..2 of map.ini): the track with
        the arrows (up-nor, down-nor of IMAGES/FRAMES/scroll) at its ends and the slider made of its three pieces.
        XI_SCROLLER draws and drags them and moves ISLANDS (scrollerName); the dark track between the arrows is ours."""
        folder = self.pdm.find("IMAGES/FRAMES/scroll")

        def load(name):
            return Image.open(next(f for f in folder.iterdir() if f.name.lower() == name)).convert("RGBA")
        up, down = load("up-nor.tga"), load("down-nor.tga")
        width, button = 28, 28
        track = Image.new("RGBA", (width, height), (40, 24, 8, 200))
        track.paste(up, (0, 0))
        track.paste(down, (0, height - down.height))
        ttex, tw, th = self.texture(track, "map_scrolltrack")
        top, mid, bottom = load("scroll-up.tga"), load("scroll-mid.tga"), load("scroll-down.tga")
        roller_h = 40
        roller = Image.new("RGBA", (width, roller_h), (0, 0, 0, 0))
        body = mid.resize((mid.width, roller_h - top.height - bottom.height))
        roller.paste(body, ((width - mid.width) // 2, top.height))
        roller.paste(top, ((width - top.width) // 2, 0))
        roller.paste(bottom, ((width - bottom.width) // 2, roller_h - bottom.height))
        rtex, rw, rh = self.texture(roller, "map_scrollroller")
        return ["[ISLSCROLL]", f"position = {x},{y},{x + width},{y + height}", f"baseTexture = {ttex}",
                f"rollerTexture = {rtex}", f"scrollTexPos = 0,0,{width / tw:g},{height / th:g}",
                f"rollTexPos = 0,0,{width / rw:g},{roller_h / rh:g}", f"begEndTexSize = {button / th:g}",
                f"begEndBaseSize = {button}", f"rollerHeight = {roller_h}", "OwnedControl = ISLANDS", ""]

    # ---------- the dialog ----------

    def dialog(self):
        """DIALOG_TERMINAL.dll prints the speech in rgb_npc_speech and the answers in rgb_our_speech with
        the font of [DialogTerminal]; its window has no picture (TEXTURES/dialog is empty), so the window
        of the dialog demo stands in, and the dialog entity takes the colours and the font."""
        terminal = dict(read_ini(self.pdm.find("INI/fonts.ini"))["DialogTerminal"])
        size, _, face = terminal["font"].split(",")
        font = self.font(f"dialog,{size}", face.strip())
        npc = [int(c) for c in terminal["rgb_npc_speech"].split(",")]
        our = [int(c) for c in terminal["rgb_our_speech"].split(",")]
        scale = f"{1 / FONT_OVERSAMPLE:.3f}"
        changes = {
            "mainfont": font, "subfont": font, "charnamefont": font,
            "mainFontScale": scale, "subFontScale": scale, "charnamescale": scale,
            "mainFontColor": make_dialog.argb(255, *npc), "charnamecolor": make_dialog.argb(255, *npc),
            # the answer under the cursor is rgb_our_speech, the others dimmer
            "subFontColorSelect": make_dialog.argb(255, *our),
            "subFontColor": make_dialog.argb(255, *(c * 2 // 3 for c in our)),
        }
        lines = [f"; converted by tools/pdm_ui.py from [DialogTerminal] of INI/fonts.ini ({face}, {size}); "
                 "the window of engine/demos/dialog/make_dialog.py"]
        for line in make_dialog.dialog_ini().splitlines():
            name = line.split("=", 1)[0].strip()
            lines.append(f"{name} = {changes[name]}" if "=" in line and name in changes else line)
        (self.resource / "ini").mkdir(parents=True, exist_ok=True)
        (self.resource / "ini" / "dialog.ini").write_text("\n".join(lines) + "\n", encoding="ascii")
        write_tx(make_dialog.window_texture(), self.resource / "textures/dialog/dialog.tga.tx", mip_chain=False)
        # the tick of the cursor: the original has none, the demo's click
        make_dialog.click_wav(self.resource / "sounds/interface/ok.wav")

        # the voices: SOUNDS/<id of the character>.wav, under the key of its card as pdm_data2c.py makes it
        used, voices = set(), []
        cards = sorted((self.game / "data/characters/CHARACTERS").glob("*.json"))
        for card in (load(f) for f in cards):
            k = key(card["id"], used)
            wav = self.pdm.find(f"SOUNDS/{card['id']}.wav")
            if wav is None:
                continue
            out = self.resource / "sounds/voices" / f"{k.lower()}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(wav, out)
            voices.append(f'\tPdmCharacters.{k}.greeting = "voices\\{k.lower()}.wav";')
        program = self.game / "program/data"
        program.mkdir(parents=True, exist_ok=True)
        (program / "pdm_voices.c").write_text(
            "// Generated by tools/pdm_ui.py: the voice a character greets with (SOUNDS/<id>.wav)\n"
            "void PdmVoices_Init()\n{\n" + "\n".join(voices) + "\n}\n", encoding="utf-8")
        self.voices = len(voices)

    def map_pointers(self):
        """The cursors of the map screen (INI/map.ini [Common] cursor = ..\\cursor.tga, MAP.dll: the flat flame arrow
        of IMAGES/cursor.tga, and eight arrows IMAGES/MAP/cursor0..7.tga that replace it at the edges of the window,
        up, up-right, right, ... up-left): 64 x 64 textures (the quad of the cursor shows a whole texture), and
        the lines of MousePointer the script gives to the screen (PdmScreens.pointer.<name>, MSG_INTERFACE_SET_MOUSE_POINTER).
        The active point: the tip of the arrow (the top left opaque pixel) or the middle of an edge arrow."""
        names = [("map", "IMAGES/cursor.tga")] + [(f"map{i}", f"IMAGES/MAP/cursor{i}.tga") for i in range(8)]
        for name, relative in names:
            path = self.pdm.find(relative)
            if path is None:
                self.skipped.append(relative)
                continue
            image = Image.open(path).convert("RGBA")
            if name == "map":
                tip = min(((x + y, x, y) for x in range(image.width) for y in range(image.height)
                           if image.getpixel((x, y))[3] > 0))
                at = (0, 0)
                hot = (tip[1] - 32, tip[2] - 32)
            else:
                at = ((64 - image.width) // 2, (64 - image.height) // 2)
                hot = (0, 0)
            canvas = Image.new("RGBA", (64, 64))
            canvas.paste(image, at)
            tex, _, _ = self.texture(canvas, f"pointer_{name}")
            self.pointers[name] = f"{tex},10,size:(64,64),pos:({hot[0]},{hot[1]})"

    def screen_data(self):
        """program/data/pdm_screens.c: PdmScreens.<screen>.title (n) and .text, the titles of the screens with
        a %s the scripts fill (the island of the trade and the shipyard), .s.<S_XXX>, the texts of the
        values of the screen, .list.<column> = LIST_<COLUMN>, the columns of its list, .t.<name>, the texts
        of its message boxes, and PdmScreens.goods / .items (names())."""
        # the texts of the shipyard the DLL takes by name: the guns, "Ваш корабль", the boat
        for key in ("Weapon0", "Weapon1", "Weapon2", "YourShip", "BoatWelcome"):
            if "ShipYard" + key in self.strings:
                self.messages.setdefault("shipyard", {})[key.lower()] = self.strings["ShipYard" + key]
        # the store: the marks of the balance column ("Экспорт", "Импорт") and "Деньги %d" under the lists
        for key, skey in (("exporting", "TradeExporting"), ("importing", "TradeImporting"), ("money", "t_TradeMoney")):
            if skey in self.strings:
                self.messages.setdefault("trade", {})[key] = self.strings[skey]
        lines = [f'\tPdmScreens.{name}.title = {n};\n\tPdmScreens.{name}.text = "{text}";'
                 for name, (n, text) in sorted(self.places.items())]
        lines += [f'\tPdmScreens.{name}.s.{node} = "{text}";'
                  for name, nodes in sorted(self.templates.items()) for node, text in nodes.items()]
        lines += [f'\tPdmScreens.{name}.list.{column} = "LIST_{column.upper()}";'
                  for name, columns in sorted(self.lists.items()) for column in columns]
        lines += [f'\tPdmScreens.{name}.t.{key} = "{text}";'
                  for name, texts in sorted(self.messages.items()) for key, text in texts.items()]
        lines += [f'\tPdmScreens.{name}.credits = "{text}";' for name, text in sorted(self.credits.items())]
        lines += [f'\tPdmScreens.pointer.{name} = "{line}";' for name, line in sorted(self.pointers.items())]
        lines += self.names("goods") + self.names("items") + self.names("ships") + self.records()
        # the journal: the buttons of the pages and the loyalty of the nations (interface.ini of the original)
        for key, skey in (("next", "LogBookNextPage"), ("prev", "LogbookPreviousPage"), ("loyal", "sStaffLoyal"),
                          ("neutral", "sStaffNeutral"), ("hostile", "sStaffHostile")):
            if skey in self.strings:
                lines.append(f'\tPdmScreens.logbook.t.{key} = "{self.strings[skey]}";')
        # the refusals of ShipExchange (RANSACK.dll): not enough crew, the class of the ship, the skills
        for key, skey in (("crew", "RanShip_PrizeButCrew"), ("class", "RansackChangeButClass"),
                          ("skills", "RanSack_GetShipButSkills")):
            if skey in self.strings:
                lines.append(f'\tPdmScreens.shipexchange.t.{key} = "{self.strings[skey]}";')
        lines += self.controls()
        (self.game / "program/data/pdm_screens.c").write_text(
            "// Generated by tools/pdm_ui.py: the titles with %s of the screens, the texts of their values, the\n"
            "// columns of their lists and the names of the goods, the items and the ships\nobject PdmScreens;\n\n"
            "void PdmScreens_Init()\n{\n" + "\n".join(lines) + "\n}\n", encoding="utf-8")

    def controls(self):
        """PdmScreens.keycontrols.c<i>.text / .keys / .head: the lines of the page of the keys, in the order of
        [KeyControls] control# of INI/menu.ini (key:-1 is a heading), the keys of INI/controls.ini (the current
        ones, the first and the second) as the names of interface.ini Key_<code>."""
        menu = read_ini(self.pdm.find("INI/menu.ini")).get("KeyControls", [])
        keys = {k.lower(): v for k, v in read_ini(self.pdm.find("INI/controls.ini")).get("Controls", [])}
        rows = sorted(((int(k[7:]), attrs(v)) for k, v in menu if re.fullmatch(r"control\d+", k.lower())))
        lines, n = [], 0
        for _, a in rows:
            text = self.strings.get(text_key(a.get("txt", "")), "")
            names = []
            key = int(a.get("key", "-1"))
            if key >= 0 and f"control{key}" in keys:
                parts = keys[f"control{key}"].split(",")
                names = [self.strings.get(f"Key_{c.strip()}", "") for c in parts[3:5] if c.strip() not in ("-1", "")]
            head = 1 if key < 0 else 0
            lines.append(f'\tPdmScreens.keycontrols.c{n}.text = "{text}";')
            lines.append(f'\tPdmScreens.keycontrols.c{n}.keys = "{" / ".join(x for x in names if x)}";')
            lines.append(f'\tPdmScreens.keycontrols.c{n}.head = {head};')
            lines.append(f'\tPdmScreens.keycontrols.c{n}.code = {a.get("code", "0")};')
            n += 1
        return [f"\tPdmScreens.keycontrols.count = {n};"] + lines

    def records(self):
        """PdmScreens.records.<key>: TEXTS/RECORDS/<name>.rcd, the lines the journal of the hero shows; the key is
        the name in lower case with every other sign than a letter or a digit as _ (Pdm_AddRecord does the same)."""
        folder = self.pdm.find("TEXTS/RECORDS")
        lines = []
        for rcd in sorted(folder.glob("*.rcd"), key=lambda f: f.name.lower()):
            key = re.sub(r"\W", "_", rcd.stem.lower(), flags=re.ASCII)
            text = " ".join(rcd.read_bytes().decode("cp1251").split()).replace('"', "'").replace("\\", "/")
            lines.append(f'\tPdmScreens.records.{key} = "{text}";')
            lines.append(f'\tPdmScreens.recordlines.{key} = "{self.wrap(text)}";')
        return lines

    def wrap(self, text):
        """The text of a record cut into lines of the width of a page of the journal (EditPage1, 280 px), the way
        ListPages of STATUS.dll cuts it (the original sums the widths of the signs of the font, and breaks at a space);
        the lines are joined with \\n. The width is that of the font of the page as it is printed (ours: 5 px less)."""
        entry = self.fonts.get("pdm_logbook_italic_16")
        if entry is None:
            return text
        size, _, _, ttf = entry
        font = ImageFont.truetype(str(ttf), size)
        gap = (font.getlength(" ") + size * 0.25) / FONT_OVERSAMPLE
        limit = PAGE_WIDTH - 5
        out, line, width = [], "", 0.0
        for word in text.split(" "):
            w = font.getlength(word) / FONT_OVERSAMPLE
            if line and width + gap + w > limit:
                out.append(line)
                line, width = word, w
            else:
                line, width = (word, w) if not line else (line + " " + word, width + gap + w)
        out.append(line)
        return "\\n".join(out)

    def names(self, kind):
        """PdmScreens.<kind>.<stem>.name and .about: TEXTS/RUSSIAN/GOODS/<kind>/<stem>.nme and .txt, the name and
        the description of a goods (PdmGoods.X.filename) or an item (PdmItems.X.description)."""
        folder = self.pdm.find(f"TEXTS/{LANGUAGE}/GOODS/{kind}")
        lines = []
        for nme in sorted(folder.glob("*.nme"), key=lambda f: f.name.lower()):
            stem = nme.stem.lower()
            if not re.fullmatch(r"[a-z_]\w*", stem):
                self.skipped.append(f"{kind}/{nme.name}: not a name of an attribute")
                continue
            txt = next((f for f in folder.iterdir() if f.name.lower() == stem + ".txt"), None)
            for field, path in (("name", nme), ("about", txt)):
                if path is not None:
                    text = " ".join(path.read_bytes().decode("cp1251").split())
                    text = text.replace('"', "'").replace("\\", "/")
                    lines.append(f'\tPdmScreens.{kind}.{stem}.{field} = "{text}";')
        return lines

    # ---------- the common files ----------

    def common(self):
        ini = self.resource / "ini"
        self.read_screens("menu.ini")
        cff = self.pdm.find("MODELS/cursor.cff")
        tf = self.pdm.find("TEXTURES/k_1n.tf")
        if cff is not None and tf is not None:
            strip = render_cursor_model(cff, tf)
            tex, _, _ = self.texture(strip, "cursor")
            # the strip is a texture of the power of two; the engine turns the frames at frames:(count,ms,width px)
            pointer = (f"{tex},10,size:({CURSOR_FRAME},{CURSOR_FRAME}),pos:({CURSOR_TIP - CURSOR_FRAME // 2},"
                       f"{CURSOR_TIP - CURSOR_FRAME // 2}),frames:({CURSOR_FRAMES},62)")
        else:
            cursor = self.image(dict(self.ini["Common"])["cursor"])
            tex, _, _ = self.texture(self.keyed(cursor), "cursor")
            pointer = f"{tex},10,size:({cursor.width},{cursor.height}),pos:(0,0)"
        (ini / "interfaces/interfaces.ini").write_text(
            "; converted by tools/pdm_ui.py. bDynamicScaling puts the 800x600 screens of the original in the\n"
            "; middle of a wider window; without [PC_SCREEN] the screen rect is upside down and nothing is drawn\n"
            "[PC_SCREEN]\nbDynamicScaling = 1\n\n"
            "[COMMON]\nRepeatDelay = 250\nmouseDblClickInterval = 600\n"
            f"MousePointer = {pointer}\nBlindTime = 1.0\n",
            encoding="utf-8")
        (ini / "interfaces/defaultnode.ini").write_text(
            "; converted by tools/pdm_ui.py: the defaults of the nodes of the original screens\n"
            "[TEXTBUTTON]\nfaceColor = 255,128,128,128\nfaceColorPressed = 255,128,128,128\n"
            "shadowColor = 0,0,0,0\nbuttonLeft = left\nbuttonMiddle = middle\nbuttonRight = right\n"
            "selectButtonLeft = select left\nselectButtonMiddle = select middle\nselectButtonRight = select right\n"
            "pressDelay = 20\npressPictureOffset = 1,1\nbackColor = 0,0,0,0\nUseActionByDeclick = 1\n\n"
            "[PICTURE]\ncolor = 255,128,128,128\n\n[STRINGCOLLECTION]\n", encoding="utf-8")
        pictures = ["; converted by tools/pdm_ui.py: the pictures of IMAGES of the original"]
        for group, (tex, w, h, pics, _) in self.pictures.items():
            pictures += [f"[{group}]", f"sTextureName = {tex.split(chr(92), 1)[1]}",
                         f"wTextureWidth = {w}", f"wTextureHeight = {h}"]
            pictures += [f"picture = {n},{x1},{y1},{x2},{y2}" for n, x1, y1, x2, y2 in pics] + [""]
        (ini / "interfaces/pictures.ini").write_text("\n".join(pictures), encoding="utf-8")

        texts = ini / "texts"
        (texts / LANGUAGE).mkdir(parents=True, exist_ok=True)
        (texts / "language.ini").write_text(
            f"[COMMON]\ndefaultLanguage = {LANGUAGE}\nstrings = common.ini\n\n"
            f"[DIRECTORY]\n{LANGUAGE} = {LANGUAGE}\n\n[FONTS]\n{LANGUAGE} = fonts.ini\n", encoding="utf-8")
        (texts / LANGUAGE / "common.ini").write_text(
            "; converted by tools/pdm_ui.py from TEXTS/RUSSIAN/INI/interface.ini of the original\n"
            + "".join(f'string = {k},"{v}"\n' for k, v in self.strings.items()), encoding="utf-8")

        # the interface editor of XINTERFACE always loads interface_normal
        self.fonts["interface_normal"] = self.fonts[self.font("logbook,20")]
        # the notes of the toolbar (hud.c) over the world: logbook 18 with a dark outline, without it the light
        # text is lost on the sand of a street (ours)
        size, _, _, ttf = self.fonts[self.font("logbook,18")]
        ascent, descent = ImageFont.truetype(str(ttf), size).getmetrics()
        self.fonts["pdm_hud_18"] = (size, HUD_OUTLINE, (ascent + descent + HUD_OUTLINE * 2) / FONT_OVERSAMPLE, ttf)
        used = ", ".join(f"{face} - {ttf.name}" + ("" if original else " (SIL Open Font License)")
                         for face, (ttf, original) in sorted(self.ttfs.items()))
        write_fonts({name: (ttf, size, outline) for name, (size, outline, _, ttf) in self.fonts.items()},
                    self.resource, f"converted by tools/pdm_ui.py: the fonts of INI/fonts.ini of the original: {used}",
                    shadow=False)  # the original prints with GDI, without a shadow (ours: No_shadow)
        self.widen_spaces()

    def widen_spaces(self):
        """The word gap of a free font is narrow at the small sizes of the lists (the words run together):
        a quarter of the height is added to Spacebar of every font of INI/fonts.ini (ours)."""
        path = self.resource / "ini/fonts.ini"
        text = path.read_text(encoding="utf-8")
        for name, (size, outline, _, ttf) in self.fonts.items():
            head = f"[{name.upper()}]"
            start = text.index(head)
            end = text.find("\n[", start + 1)
            end = len(text) if end < 0 else end
            body = re.sub(r"Spacebar = (\d+)", lambda m: f"Spacebar = {int(m.group(1)) + round(size * 0.25)}",
                          text[start:end], count=1)
            text = text[:start] + body + text[end:]
        path.write_text(text, encoding="utf-8")


# the screens of the game; the common files (interfaces.ini, pictures, strings) list what is converted,
# so every run converts all of them and the screens of the command line come on top
# pictures of the strip that lengthens the map frame on a wide window: 8 x 200 px covers 32:9
MAP_BACK_TILES = 8
# the stamps of the fog of the map in the order of fogStamp (0 the route, 1 an island), MAP.dll
MAP_FOG_STAMPS = ("mask_black", "mask_black_island")
# the screens of MENU.dll, MAP.dll, TOWN.dll, STATUS.dll and RANSACK.dll
SCREEN_FILES = ["menu.ini", "map.ini", "town.ini", "status.ini", "ransack.ini"]
# the buttons that are checks: their picture of -hi.tga is the state off
CHECKS = {"check"}
# the fields that are lists with a cursor: the files of the saves
# a field a screen takes from another one (ours): [LoadGame] has no description of its own, the one of [Common]
# is small and under the frame of the background, the scripts show the header of a save in it
FIELDS_OF = {"LoadGame": {k: ("SaveGame", k) for k in (
    "EditDesc", "IconsRect", "icon1", "icon2", "savesprite_rect", "FileTextRect", "FileNameRect", "EditFileText",
    "EditFileName", "lb_ScrollUp", "lb_ScrollDown")}}
SAVE_GRID = ("LoadGame", "SaveGame")
SAVE_COLUMNS, SAVE_ROWS = 4, 2
SAVE_YELLOW = "255,255,224,48"
SAVE_NAME_LIGHT = "255,200,164,110"
SELECT_LISTS = {("LoadGame", "EditFiles"), ("SaveGame", "EditFiles"), ("ShipYard", "EditShip")}
# the shipyard: the class, the current gun and the rows of the guns to buy take a click (the screenshots of the original show them selectable)
SHIPYARD_CLICK = {"S_SHIP0", "S_SHIP10", "S_CALIBERSET", "S_LBSNUM0", "S_LBS0", "S_GOLDNUM0", "S_GOLD0", "S_LBSNUM1", "S_LBS1", "S_GOLDNUM1", "S_GOLD1"}
# the screens without the help, the description and the face of the hero of [Common]
NO_COMMON = {"MainMenu", "MainMap", "MessageBox", "Options", "KeyControls", "Credits"}
# the width of the place of a value (s_Rank = txt:"%d",xr:490,...): the original prints it from a point (ours)
S_WIDTH = 200
# the width of a column of numbers of a list (ours: the widest number with its unit)
COLUMN_WIDTH = 80


def main():
    pdm, game = sys.argv[1], sys.argv[2]
    c = Converter(pdm, game)
    for file in SCREEN_FILES:
        for section in [s for s in read_ini(c.pdm.find("INI/" + file)) if s != "Common"]:
            c.screen(file, section)
    c.dialog()
    c.common()
    c.map_pointers()
    c.screen_data()
    print(f"pdm_ui: {len(c.screens)} screens, the dialog, {c.voices} voices, {len(c.strings)} strings, {len(c.fonts)} fonts, "
          f"{len(c.pictures)} picture groups, {len(c.plates)} plates; skipped: " + "; ".join(c.skipped))


if __name__ == "__main__":
    main()
