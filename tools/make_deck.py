"""Builds the boarding: the deck of «Ворон» the captain and his sailors fight the pirates on, the
fencers (the sailor and the pirate in red stripes) with the fight actions, the saber they hold and the
bars the location draws over an enemy.

Usage: make_deck.py <output resource dir>
Writes models/deck/{deck.gm,deck_patch.ptc}, textures/deck/*.tga.tx, models/characters/{boarder,pirate}.gm
with animation/fencer.{an,ani} and textures/characters/pirate_*.tga.tx, models/Ammo/saber.gm with
textures/Ammo/*.tga.tx and textures/LocEfx/state_bars.tga.tx. The fencers, the saber and the bars come
from the generator of the melee demo (engine/demos/melee), the textures from the location and dialog demos.

The deck is a location: the model has a BSP and the patch is a grid of 1 m cells at the height of the
deck, a metre short of the bulwarks, without the cells by the masts, the hatch and the crates.
"""
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "engine" / "demos"
for path in (DEMOS / "common", DEMOS / "location", DEMOS / "dialog", DEMOS / "melee"):
    sys.path.insert(0, str(path))
import make_dialog  # noqa: E402
import make_location  # noqa: E402
import make_melee  # noqa: E402
import sailor  # noqa: E402
import sailor_fight  # noqa: E402
from storm_formats import Mesh, write_gm, write_ptc, write_tx  # noqa: E402

DECK = 3.0  # over the calm sea of the harbour scene
HALF_WIDTH = 4.0  # the inner faces of the bulwarks
BOW, STERN = 14.0, -14.0
BULWARK = (1.0, 0.25)  # height, thickness
KEEL = -2.0  # the hull goes this deep under the water
MASTS = [(0.0, -5.5), (0.0, 6.5)]  # on cell centres
MAST = (0.45, 16.0)  # width, height over the deck
HATCH = (0.0, 0.5, 1.0)  # centre x, z and half size: a 2 m grating 0.4 m high
CRATES = [(2.0, -10.5), (-2.0, 10.5), (-2.0, -2.5)]  # 1 m crates, on cells
# the walkable cells: centres at whole x and half z, a metre off the bulwarks
WALK = (-3.0, 3.0, -12.5, 12.5)
WOOD = 0
PIRATE = make_melee.PIRATE


# ---------------------------------------------------------------- model

def deck_meshes():
    top = Mesh("deck", "deck.tga")
    # a grid instead of one quad: per-vertex lighting and fog need vertices across the surface
    index = {}
    cols, rows = 8, 28
    for j in range(rows + 1):
        for i in range(cols + 1):
            x = -HALF_WIDTH + 2 * HALF_WIDTH * i / cols
            z = STERN + (BOW - STERN) * j / rows
            index[i, j] = top.vertex((x, DECK, z), (0, 1, 0), (x / 2.0, z / 2.0))
    for j in range(rows):
        for i in range(cols):
            top.quad(index[i, j], index[i + 1, j], index[i + 1, j + 1], index[i, j + 1])

    hull = Mesh("hull", "hull.tga")
    height, thick = BULWARK
    x0, x1 = -HALF_WIDTH - thick, HALF_WIDTH + thick
    z0, z1 = STERN - thick, BOW + thick
    # the sides from under the water to the rail, outside; the bulwarks over the deck, inside too
    make_location.box(hull, (x0, KEEL, z0), (x1, DECK + height, z1), 2.0, faces="+x-x+z-z")
    make_location.box(hull, (x0, DECK, STERN), (-HALF_WIDTH, DECK + height, BOW), 2.0, faces="+x+y")
    make_location.box(hull, (HALF_WIDTH, DECK, STERN), (x1, DECK + height, BOW), 2.0, faces="-x+y")
    make_location.box(hull, (x0, DECK, z0), (x1, DECK + height, STERN), 2.0, faces="+z+y")
    make_location.box(hull, (x0, DECK, BOW), (x1, DECK + height, z1), 2.0, faces="-z+y")

    masts = Mesh("masts", "mast.tga")
    width, mast_height = MAST
    for mx, mz in MASTS:
        h = width / 2
        make_location.box(masts, (mx - h, DECK, mz - h), (mx + h, DECK + mast_height, mz + h), 1.0)
        # a yard across the mast
        make_location.box(masts, (-5.0, DECK + 9.0, mz - 0.12), (5.0, DECK + 9.25, mz + 0.12), 1.0)

    crates = Mesh("crates", "crate.tga")
    for cx, cz in CRATES:
        make_location.crate_box(crates, cx, cz, 1.0, DECK)
    hx, hz, hs = HATCH
    make_location.box(crates, (hx - hs, DECK, hz - hs), (hx + hs, DECK + 0.4, hz + hs), 1.0)
    return [top, hull, masts, crates]


# ---------------------------------------------------------------- patch

def walkable(cx, cz):
    x0, x1, z0, z1 = WALK
    if not (x0 <= cx <= x1 and z0 <= cz <= z1):
        return False
    if any(abs(cx - x) < 1.0 and abs(cz - z) < 1.0 for x, z in MASTS):
        return False
    hx, hz, hs = HATCH
    if abs(cx - hx) <= hs + 0.5 and abs(cz - hz) <= hs + 0.5:
        return False
    # the cell of a crate and the ones around it: the sailor is 0.35 m wide
    return all(abs(cx - x) > 1.0 or abs(cz - z) > 1.0 for x, z in CRATES)


def patch_triangles():
    """Two triangles per walkable 1 m cell; neighbouring cells share their vertices."""
    triangles = []
    for i in range(-3, 4):
        for j in range(-13, 13):
            cx, cz = float(i), j + 0.5
            if not walkable(cx, cz):
                continue
            x0, x1, z0, z1 = cx - 0.5, cx + 0.5, cz - 0.5, cz + 0.5
            corners = [(x0, DECK, z0), (x1, DECK, z0), (x1, DECK, z1), (x0, DECK, z1)]
            triangles.append(((corners[0], corners[2], corners[1]), WOOD))
            triangles.append(((corners[0], corners[3], corners[2]), WOOD))
    return triangles


def main():
    resource = Path(sys.argv[1])
    textures = resource / "textures" / "deck"
    write_tx(make_dialog.planks(), textures / "deck.tga.tx")
    write_tx(make_location.planks(), textures / "hull.tga.tx")
    write_tx(make_dialog.wood_post(), textures / "mast.tga.tx")
    write_tx(make_location.planks(border=True), textures / "crate.tga.tx")
    write_gm(deck_meshes(), resource / "models" / "deck" / "deck.gm", bsp=True)
    count = write_ptc(patch_triangles(), resource / "models" / "deck" / "deck_patch.ptc", materials=("wood",))

    # the fencers: the captain and his sailors in blue stripes, the pirates in red, on one animation
    sailor_fight.self_check()
    # the sailor's textures are make_port.py's (the same names), the pirate's are written here
    sailor.write_textures(resource / "textures" / "characters", prefix="pirate_", **PIRATE)
    cycles = [sailor.IDLE, sailor.WALK, sailor.RUN, sailor.TURN] + sailor_fight.CYCLES
    labels = sailor_fight.blade_labels()
    an = resource / "animation" / "fencer.an"
    sailor.write_sailor(resource / "models" / "characters" / "boarder.gm", an, "", cycles, labels)
    sailor.write_sailor(resource / "models" / "characters" / "pirate.gm", an, "pirate_", cycles, labels)
    make_melee.write_ani(resource / "animation" / "fencer.ani")

    # BLADE loads models\Ammo\<name> with textures from textures\Ammo\
    ammo = resource / "textures" / "Ammo"
    write_tx(make_melee.steel(), ammo / "saber_steel.tga.tx")
    write_tx(make_melee.grip(), ammo / "saber_grip.tga.tx")
    write_tx(make_melee.brass(), ammo / "saber_brass.tga.tx")
    write_gm(make_melee.saber_meshes(), resource / "models" / "Ammo" / "saber.gm",
             labels=[("blade", "start", (0.0, 0.2, 0.0)), ("blade", "end", (0.0, 0.85, 0.0))])
    write_tx(make_melee.state_bars(), resource / "textures" / "LocEfx" / "state_bars.tga.tx")
    print(f"deck patch {count} triangles")


if __name__ == "__main__":
    main()
