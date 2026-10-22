#!/usr/bin/env python3
"""Converts the boarding of the original Sea Dogs (PDM 1.061): the duel of the captains in the cabin.

The original boards in two steps (ACTIONS/brd_*.a): the movie of the crews fighting on the deck
(DESC/Fight_*.ani, PLAY Engine_movie "Fight_Eng"), then the captains fight in the cabin
MODELS/kayuta.cff on the floor Patch_kayuta.cff. WORLDS/CHARACTERS/brd_mans.idf names the fighter
of each nation, the fighters hold the blade drawn (stand_atack, hit_1..4, block_1..4, death_1/2).

Writes, in the units of the engine (metres, pdm_character.DEFAULT_SCALE):
  models/locations/kayuta.gm, patch_kayuta.ptc, textures/locations/*.tga.tx
  models/characters/<model>_brd.gm   every fighter model of anim_types.idf with the blade in the
                                     hand (pdm_character.convert blade="hand"), its .an/.ani with
                                     the fight actions
  textures/battle_interface/pdm/brd_left.tga.tx, brd_right.tga.tx
                                     the plates of the hero (top left) and of the enemy (top right):
                                     "Команда" (the health) and "Сила" (the energy), their bars
                                     transparent windows the engine fills from below (IBoardingStatus)
  program/data/pdm_boarding.c        PdmBoarding: the cabin, the places of the fighters, the
                                     fighter of each nation, the windows of the bars, PdmBoarding_Init()

usage: pdm_boarding.py <Sea Dogs install dir with RESOURCE> <game_dir>
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import pdm_character  # noqa: E402
from pdm2storm import parse_idf  # noqa: E402
from pdm_ship import index_files  # noqa: E402
from pdm_world import K, World, clean_patch, patch_triangles  # noqa: E402
from storm_formats import write_ptc, write_tx  # noqa: E402
from tf2tx import tf_image  # noqa: E402

CABIN, PATCH = "kayuta.cff", "Patch_kayuta.cff"
# the nations of brd_mans.idf by the index of the game (PdmNations: 0 england, 1 pirate, 2 france, 3 spain)
NATIONS = {"engl": 0, "pira": 1, "frnc": 2, "span": 3}
# Boarding.dll places the fighters in the cabin at (0, 0, +0.35), turned by pi, and (0, 0, -0.35)
PLACE_Z = 0.35
# Boarding.dll draws TEXTURES/boarding/brd_left.tf for the hero, brd_right.tf for the enemy
PLATES = {"hero": "brd_left", "enemy": "brd_right"}


def bar_windows(image):
    """The transparent windows of a plate, top (the crew, the health) and bottom (the energy): l, t, r, b."""
    alpha = image.getchannel("A")
    w, h = image.size
    boxes = []
    for y0, y1 in ((0, h // 2), (h // 2, h)):
        pts = [(x, y) for y in range(y0, y1) for x in range(w) if alpha.getpixel((x, y)) == 0]
        assert pts, "no window of a bar"
        boxes.append((min(p[0] for p in pts), min(p[1] for p in pts),
                      max(p[0] for p in pts) + 1, max(p[1] for p in pts) + 1))
    return boxes


def inside(tri, x, z):
    (ax, _, az), (bx, _, bz), (cx, _, cz) = tri
    d1 = (bx - ax) * (z - az) - (bz - az) * (x - ax)
    d2 = (cx - bx) * (z - bz) - (cz - bz) * (x - bx)
    d3 = (ax - cx) * (z - cz) - (az - cz) * (x - cx)
    return (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)


def floor_y(triangles, x, z):
    """The height of the floor at x, z, None off the floor."""
    for tri, _ in triangles:
        if inside(tri, x, z):
            return max(p[1] for p in tri)
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    res, game = Path(sys.argv[1]), Path(sys.argv[2])
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    world = World(res, game)
    out = world.out

    model = world.model(CABIN)
    triangles = clean_patch(patch_triangles(world.models[PATCH.lower()]))
    patch = Path(PATCH).stem.lower()
    write_ptc(triangles, out / "models" / "locations" / f"{patch}.ptc", materials=("snd_wood",))
    missing = world.write_textures()
    print(f"{model}: patch {patch}, {len(triangles)} triangles" + (f", missing {' '.join(missing)}" if missing else ""))

    places = []
    for z in (PLACE_Z * K, -PLACE_Z * K):
        y = floor_y(triangles, 0.0, z)
        assert y is not None, f"no floor at 0, {z:.2f}"
        places.append((0.0, y, z))

    # the fighters: the models of anim_types.idf animated by a set with the fight actions
    anims = index_files(res / "WORLDS" / "CHARACTERS")
    chars = index_files(res / "MODELS" / "CHARACTERS")
    fighters = []
    for obj in parse_idf(res / "WORLDS" / "anim_types.idf")["objects"]:
        f = dict(obj)
        name, anim = f.get("name", "0"), f.get("anim_file", "null").lower()
        stem = Path(name).stem.lower()
        if stem not in chars or anim not in anims or stem in fighters:
            continue
        if "hit_1" not in pdm_character.read_actions(anims[anim]):
            continue
        line = pdm_character.convert(res, out, name, anim, stem, K, world.textures, blade="hand")
        print(" ", line)
        if "skipped" not in line:
            fighters.append(stem)

    lines = [f'\tPdmBoarding.model = "{model}";', f'\tPdmBoarding.patch = "{patch}";']
    # the attacker comes from +z and faces -z, the defender the other way
    for side, (x, y, z), ay in zip(("attacker", "defender"), places, (3.1416, 0.0)):
        at = f"PdmBoarding.{side}"
        lines.append(f"\t{at}.x = {x:.3f}; {at}.y = {y:.3f}; {at}.z = {z:.3f}; {at}.ay = {ay:.4f};")
    hud = out / "textures" / "battle_interface" / "pdm"
    for side, stem in PLATES.items():
        image = tf_image(res / "TEXTURES" / "boarding" / f"{stem}.tf")
        write_tx(image, hud / f"{stem}.tga.tx", mip_chain=False)
        at = f"PdmBoarding.hud.{side}"
        lines.append(f'\t{at}.texture = "battle_interface/pdm/{stem}.tga"; '
                     f"{at}.width = {image.size[0]}; {at}.height = {image.size[1]};")
        for bar, (l, t, r, b) in zip(("health", "energy"), bar_windows(image)):
            lines.append(f"\t{at}.{bar}.left = {l}; {at}.{bar}.top = {t}; {at}.{bar}.width = {r - l}; "
                         f"{at}.{bar}.height = {b - t};")
    for obj in parse_idf(res / "WORLDS" / "CHARACTERS" / "brd_mans.idf")["objects"]:
        f = dict(obj)
        nation = NATIONS.get(f.get("name"))
        stem = Path(f.get("model", "").replace("\\", "/")).stem.lower()
        if nation is not None:
            lines.append(f'\tPdmBoarding.crew.n{nation} = "{stem if stem in fighters else ""}";')
    for stem in fighters:
        lines.append(f"\tPdmBoarding.fighters.{stem} = 1;")
    path = game / "program" / "data" / "pdm_boarding.c"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// written by tools/pdm_boarding.py from MODELS/kayuta.cff, WORLDS/CHARACTERS/brd_mans.idf\n"
                    "object PdmBoarding;\n\nvoid PdmBoarding_Init()\n{\n" + "\n".join(lines) + "\n}\n",
                    encoding="cp1251")
    print(f"{len(fighters)} fighters, places {places}")


if __name__ == "__main__":
    main()
