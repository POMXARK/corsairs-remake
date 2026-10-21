"""Converts the screens of the original Sea Dogs interface (RESOURCE/INI/menu.ini, town.ini, ...)
into XINTERFACE screens of Storm Engine.

Usage: pdm_ui.py <Sea Dogs install dir with RESOURCE> <game dir> [Section ...]
The sections default to MainMenu. Writes into <game dir>/resource:
  ini/interfaces/{interfaces,defaultnode,pictures}.ini and <section>.ini per screen,
  ini/texts/language.ini and texts/russian/common.ini (the strings of TEXTS/RUSSIAN/INI/interface.ini),
  ini/fonts.ini and textures/fonts/*.tx (the fonts of INI/fonts.ini rendered from a free font),
  textures/interfaces/pdm/*.tx (the pictures of IMAGES),
  ini/dialog.ini and textures/dialog/dialog.tga.tx (the dialog window: [DialogTerminal] of INI/fonts.ini),
  sounds/voices/<character>.wav (SOUNDS/<id>.wav, the greeting of a character when a dialog opens) and
  <game dir>/program/data/pdm_voices.c, which gives them to the characters.

The pattern: every screen of the original is one ini section of one grammar, read by MENU.dll,
TOWN.dll, STATUS.dll ... on an 800x600 virtual screen:
  background = ..\fons\menu-fon-$.tga          a picture under the screen, $ = the language
  ramka      = type,x1,y1,x2,y2               a frame of frames\<type>.tga pieces
  titleN     = txt:"#Key#",font:"name,size,0",xo:..,yo:..,rgb:"r,g,b"
  lb_Name    = txt:"#Key#",file:"..\buttons\mbutton",xo:..,yo:..,font:..,rgbn/rgba/rgbd/rgbi:"r,g,b"
               a button of <file>-{nor,hi,down,dis}.tga with the text colours of the states
  t_Name     = #Key#                           a text the screen shows in a message box
The positions: xo/yo the centre, xl/yl the left/top, xr the right edge. A key may be followed by ':'
instead of ',' (xr:585:yo:175 in [Options]). The paths are relative to [Common] path = MENU\ and do
not care about the case of letters.
"""
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageFont

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
# the fonts of the original (INI/fonts.ini: log-russ, seawolf) are not free; Old Standard (OFL) stands in
FONT_TTF = TOOLS.parent / "engine/demos/interface/assets/OldStandard-Bold.ttf"
# the fonts are rendered this many times bigger than the virtual screen asks and scaled down by the node,
# so the text stays sharp in a window bigger than 800x600
FONT_OVERSAMPLE = 1.5
# Old Standard is wider than log-russ: at the full height "Продолжить игру" does not fit its button
FONT_FIT = 0.85
# black is the colour key of the pictures of the original (the corners of the buttons, the cursor)
KEY_COLOR = (0, 0, 0)
ATTR = re.compile(r'(\w+):(?:"([^"]*)"|([^,:"]+))')


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
        menu_ini = self.pdm.find("INI/menu.ini")
        self.ini = read_ini(menu_ini)
        self.base = "IMAGES/" + dict(self.ini["Common"])["path"]
        self.strings = self.read_strings()
        self.fonts = {}     # name -> (size of the virtual screen, line height of the atlas)
        self.pictures = {}  # group -> (texture, width, height, [(name, x1, y1, x2, y2)], size of a button)
        self.skipped = []

    # ---------- texts and fonts ----------

    def read_strings(self):
        strings = {}
        path = self.pdm.find(f"TEXTS/{LANGUAGE}/INI/interface.ini")
        for line in path.read_bytes().decode("cp1251").splitlines():
            if "=" in line and not line.lstrip().startswith(("//", "[")):
                key, value = line.split("=", 1)
                strings.setdefault(key.strip(), value.strip().replace('"', "'"))
        return strings

    def font(self, spec):
        """font:"logbook,27,0" -> pdm_logbook_27; the size is the height of a line, as CreateFont takes it."""
        parts = spec.split(",")
        name = f"pdm_{parts[0].strip()}_{parts[1].strip()}"
        if name not in self.fonts:
            height = int(parts[1]) * FONT_OVERSAMPLE * FONT_FIT
            # the TrueType size whose ascent + descent is the height
            ascent, descent = ImageFont.truetype(str(FONT_TTF), 100).getmetrics()
            size = max(4, round(height * 100 / (ascent + descent)))
            outline = 1 if height < 30 else 2
            ascent, descent = ImageFont.truetype(str(FONT_TTF), size).getmetrics()
            self.fonts[name] = (size, outline, (ascent + descent + outline * 2) / FONT_OVERSAMPLE)
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

    def button_group(self, file):
        """<file>-nor.tga and -hi.tga in one atlas: TEXTBUTTON draws a left and a right piece of their
        own width and stretches the middle, so the halves are the pieces and the middle is 2 pixels."""
        stem = re.split(r"[\\/]", file)[-1].lower()
        group = "PDM_" + stem.upper()
        if group in self.pictures:
            return group, self.pictures[group][4]
        nor, hi = self.image(file + "-nor.tga"), self.image(file + "-hi.tga")
        w, h = nor.size
        atlas = Image.new("RGB", (w, h * 2 + 2))
        atlas.paste(nor, (0, 0))
        atlas.paste(hi, (0, h + 2))
        tex, tw, th = self.texture(self.keyed(atlas), stem)
        half = w // 2 - 1
        pictures = []
        for prefix, top in (("", 0), ("select ", h + 2)):
            pictures += [(prefix + "left", 0, top, half, top + h),
                         (prefix + "middle", half, top, half + 2, top + h),
                         (prefix + "right", half + 2, top, w, top + h)]
        self.pictures[group] = (tex, tw, th, pictures, (w, h))
        return group, (w, h)

    # ---------- a screen ----------

    def position(self, a, w, h):
        """The rect of a w x h element by xo/yo (centre), xl/yl (left/top), xr (right)."""
        if "xo" in a:
            x = int(a["xo"]) - w // 2
        elif "xr" in a:
            x = int(a["xr"]) - w
        else:
            x = int(a.get("xl", 0))
        if "yo" in a:
            y = int(a["yo"]) - h // 2
        else:
            y = int(a.get("yl", 0))
        return x, y

    def screen(self, section):
        nodes, lines, titles = [], [], []
        buttons = []
        for key, value in self.ini[section]:
            low = key.lower()
            if low == "background":
                image = self.image(value)
                if image is None:
                    self.skipped.append(f"{section}.{key}: no {value}")
                    continue
                stem = "back_" + section.lower()
                full = image.resize((1024, 768), Image.LANCZOS)
                tex, tw, th = self.texture(full, stem)
                nodes.append(("PICTURE", "BACKGROUND"))
                lines += ["[BACKGROUND]", "position = 0,0,800,600", f"textureName = {tex}",
                          f"textureRect = 0,0,1,{768 / th:g}", ""]
            elif low.startswith("title"):
                a = attrs(value)
                name = self.font(a.get("font", "logbook,20"))
                size, _, line_h = self.fonts[name]
                if "xo" in a:
                    x, state = int(a["xo"]), "C"
                elif "xr" in a:
                    x, state = int(a["xr"]), "R"
                else:
                    x, state = int(a.get("xl", 0)), "L"
                y = int(a["yo"]) - round(line_h / 2) if "yo" in a else int(a.get("yl", 0))
                key_name = text_key(a.get("txt", ""))
                if "file" in a:
                    self.skipped.append(f"{section}.{key}: the plate {a['file']}")
                titles.append(f"string = {key_name},font:{name},pos:{{{x},{y}}},fc:{{{rgb(a.get('rgb'), '255,255,255')}}},"
                              f"bc:{{0,0,0,0}},scale:{1 / FONT_OVERSAMPLE:.3f},state:{{{state}}}")
            elif low.startswith("lb_"):
                buttons.append((key, attrs(value)))
            elif low == "ramka" or low.startswith("vignette"):
                # frames\%s%d.tga and frames\decor\%s%d.tga are not in the installed game
                self.skipped.append(f"{section}.{key}: the frame pieces are missing from the original")
            elif low.startswith("t_"):
                pass  # the texts of the message boxes, kept in common.ini
            else:
                self.skipped.append(f"{section}.{key}")

        if titles:
            nodes.append(("STRINGCOLLECTION", "TITLES"))
            lines += ["[TITLES]"] + titles + [""]

        names = [k.upper() for k, _ in buttons]
        for i, (key, a) in enumerate(buttons):
            group, (w, h) = self.button_group(a["file"])
            font = self.font(a.get("font", "logbook,27,0"))
            line_h = self.fonts[font][2]
            x, y = self.position(a, w, h)
            node = names[i]
            nodes.append(("TEXTBUTTON", node))
            lines += [f"[{node}]", f"position = {x},{y},{x + w},{y + h}",
                      f"string = {text_key(a.get('txt', ''))}",
                      f"group = {group}", f"font = {font}", f"fontScale = {1 / FONT_OVERSAMPLE:.3f}",
                      f"strOffset = {round((h - line_h) / 2)}",
                      f"fontColor = {rgb(a.get('rgbn'), '255,255,255')}",
                      f"fontColorSelected = {rgb(a.get('rgba'), '255,255,255')}",
                      f"fontColorPressed = {rgb(a.get('rgbd'), '255,255,255')}",
                      f"unselectableFontColor = {rgb(a.get('rgbi'), '128,128,128')}",
                      "command = click", "command = activate"]
            if i > 0:
                lines.append(f"command = upstep,select:{names[i - 1]}")
            if i + 1 < len(names):
                lines.append(f"command = downstep,select:{names[i + 1]}")
            lines += ["command = deactivate", ""]

        head = [f"; converted by tools/pdm_ui.py from [{section}] of INI/menu.ini of the original", f"[MAIN]"]
        head += [f"item = {kind},{name}" for kind, name in nodes]
        if names:
            head.append(f"start = {names[0]}")
        out = self.resource / f"ini/interfaces/{section.lower()}.ini"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(head + [""] + lines), encoding="utf-8")

    # ---------- the dialog ----------

    def dialog(self):
        """DIALOG_TERMINAL.dll prints the speech in rgb_npc_speech and the answers in rgb_our_speech with
        the font of [DialogTerminal]; its window has no picture (TEXTURES/dialog is empty), so the window
        of the dialog demo stands in, and the dialog entity takes the colours and the font."""
        terminal = dict(read_ini(self.pdm.find("INI/fonts.ini"))["DialogTerminal"])
        size, _, face = terminal["font"].split(",")
        font = self.font(f"dialog,{size}")
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

    # ---------- the common files ----------

    def common(self):
        ini = self.resource / "ini"
        cursor = self.image(dict(self.ini["Common"])["cursor"])
        tex, _, _ = self.texture(self.keyed(cursor), "cursor")
        (ini / "interfaces/interfaces.ini").write_text(
            "; converted by tools/pdm_ui.py. bDynamicScaling puts the 800x600 screens of the original in the\n"
            "; middle of a wider window; without [PC_SCREEN] the screen rect is upside down and nothing is drawn\n"
            "[PC_SCREEN]\nbDynamicScaling = 1\n\n"
            "[COMMON]\nRepeatDelay = 250\nmouseDblClickInterval = 600\n"
            f"MousePointer = {tex},10,size:({cursor.width},{cursor.height}),pos:(0,0)\nBlindTime = 1.0\n",
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
        write_fonts({name: (FONT_TTF, size, outline) for name, (size, outline, _) in self.fonts.items()},
                    self.resource, "converted by tools/pdm_ui.py: the fonts of INI/fonts.ini of the original "
                    "drawn with Old Standard Bold (SIL Open Font License)")


def main():
    pdm, game = sys.argv[1], sys.argv[2]
    sections = sys.argv[3:] or ["MainMenu"]
    c = Converter(pdm, game)
    for section in sections:
        c.screen(section)
    c.dialog()
    c.common()
    print(f"pdm_ui: {len(sections)} screens, the dialog, {c.voices} voices, {len(c.strings)} strings, {len(c.fonts)} fonts, "
          f"{len(c.pictures)} picture groups; skipped: " + "; ".join(c.skipped))


if __name__ == "__main__":
    main()
