"""Builds the port: a stone quay with a pier running out to sea, crates, the player's sailor as a
location character, the old sailor Tom on the pier and the dialog window.

Usage: make_port.py <output resource dir>
Writes models/port/{port.gm,port_patch.ptc}, textures/port/*.tga.tx, the player as
models/characters/sailor.gm with animation/sailor.{an,ani}, Tom as models/demo/sailor.gm with
animation/demo/sailor.{an,ani}, textures/dialog/dialog.tga.tx, ini/dialog.ini and
sounds/interface/ok.wav. The textures, the pier, the sailor and the dialog window come from the
generators of the engine demos (location, dialog); the fonts of the dialog are written by
make_assets.py with the other game fonts.

The port is a location: the model has a BSP (the camera stops at it, shadows fall on it) and the
patch is the floor the player walks on: one grid of 1 m cells over the quay and the pier, at the
height of the deck, without the cells by the crates, the edges and Tom.
"""
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "engine" / "demos"
for path in (DEMOS / "common", DEMOS / "location", DEMOS / "dialog"):
    sys.path.insert(0, str(path))
import make_dialog  # noqa: E402
import make_location  # noqa: E402
import sailor  # noqa: E402
from storm_formats import Mesh, write_gm, write_ptc, write_tx  # noqa: E402

DECK = make_dialog.DECK_TOP  # the quay and the pier are one level, 1.5 m over the sea
# the pier: x across, z along it, out to sea towards +z
make_dialog.DECK_NEAR, make_dialog.DECK_FAR = -16.0, 10.0
PIER_HALF_WIDTH = make_dialog.DECK_HALF_WIDTH
# the quay: in front of the warehouse wall, the pier starts at its edge
QUAY = (-15.0, 15.0, -27.0, -16.0)  # x0, x1, z0, z1
WALL_HEIGHT = 4.5
CRATES = [(-6.0, -19.5), (-7.0, -21.5), (-6.0, -21.5), (8.0, -24.5), (1.0, -8.5)]  # 1 m crates, on cells
TOM = (0.0, 4.5)  # where Tom stands, on a cell
# the walkable area: the cell centres at whole x and half z; the edges keep the sailor's centre a
# metre off the water and the wall
WALK_QUAY = (-13.5, 13.5, -25.0, -16.0)
WALK_PIER = (-1.5, 1.5, -16.0, 9.0)
GROUND, WOOD = 0, 1


# ---------------------------------------------------------------- model

def quay_meshes():
    x0, x1, z0, z1 = QUAY
    top = Mesh("quay", "cobbles.tga")
    # a grid instead of one quad: per-vertex lighting and fog need vertices across the surface
    index = {}
    cols, rows = 30, 11
    for j in range(rows + 1):
        for i in range(cols + 1):
            x = x0 + (x1 - x0) * i / cols
            z = z0 + (z1 - z0) * j / rows
            index[i, j] = top.vertex((x, DECK, z), (0, 1, 0), (x / 2.0, z / 2.0))
    for j in range(rows):
        for i in range(cols):
            top.quad(index[i, j], index[i + 1, j], index[i + 1, j + 1], index[i, j + 1])

    stone = Mesh("quay_sides", "stone_wall.tga")
    # the sea side and the ends go down under the water, the warehouse wall rises at the back
    make_location.box(stone, (x0, -4.0, z0), (x1, DECK, z1), 2.0, faces="+x-x+z")
    make_location.box(stone, (x0 - 0.6, -4.0, z0 - 0.6), (x1 + 0.6, DECK + WALL_HEIGHT, z0), 2.0, faces="+x-x+y+z")

    crates = Mesh("crates", "crate.tga")
    for cx, cz in CRATES:
        make_location.crate_box(crates, cx, cz, 1.0, DECK)
    return [top, stone, crates]


def pier_meshes():
    meshes = make_dialog.pier_meshes()
    # the location loads the textures of its model from textures\port\
    for mesh in meshes:
        mesh.texture = mesh.texture.split("\\")[-1]
    return meshes


# ---------------------------------------------------------------- patch

def inside(x, z, rect):
    x0, x1, z0, z1 = rect
    return x0 <= x <= x1 and z0 <= z <= z1


def walkable(cx, cz):
    if not (inside(cx, cz, WALK_QUAY) or inside(cx, cz, WALK_PIER)):
        return False
    if (cx, cz) == TOM:
        return False
    # the cell of a crate and the ones around it: the sailor is 0.35 m wide
    return all(abs(cx - x) > 1.0 or abs(cz - z) > 1.0 for x, z in CRATES)


def patch_triangles():
    """Two triangles per walkable 1 m cell; neighbouring cells share their vertices, so the quay and
    the pier are one floor."""
    triangles = []
    for i in range(-14, 14):
        for j in range(-26, 10):
            cx, cz = float(i), j + 0.5
            if not walkable(cx, cz):
                continue
            x0, x1, z0, z1 = cx - 0.5, cx + 0.5, cz - 0.5, cz + 0.5
            corners = [(x0, DECK, z0), (x1, DECK, z0), (x1, DECK, z1), (x0, DECK, z1)]
            material = WOOD if cz > QUAY[3] else GROUND
            triangles.append(((corners[0], corners[2], corners[1]), material))
            triangles.append(((corners[0], corners[3], corners[2]), material))
    return triangles


def main():
    resource = Path(sys.argv[1])
    textures = resource / "textures" / "port"
    write_tx(make_location.cobbles(), textures / "cobbles.tga.tx")
    write_tx(make_location.stone_wall(), textures / "stone_wall.tga.tx")
    write_tx(make_location.planks(border=True), textures / "crate.tga.tx")
    write_tx(make_dialog.planks(), textures / "planks.tga.tx")
    write_tx(make_dialog.wood_post(), textures / "post.tga.tx")
    write_gm(quay_meshes() + pier_meshes(), resource / "models" / "port" / "port.gm", bsp=True)
    count = write_ptc(patch_triangles(), resource / "models" / "port" / "port_patch.ptc",
                      materials=("ground", "wood"))

    # the player: Character loads models\characters\<model> with textures from textures\characters\
    sailor.write_textures(resource / "textures" / "characters")
    cycles = [sailor.IDLE, sailor.WALK, sailor.RUN, sailor.TURN]
    sailor.write_sailor(resource / "models" / "characters" / "sailor.gm", resource / "animation" / "sailor.an",
                        "", cycles)
    make_location.write_ani(resource / "animation" / "sailor.ani")
    # Tom: a model standing on the pier, as in the dialog demo
    sailor.write_textures(resource / "textures" / "demo")
    sailor.write_sailor(resource / "models" / "demo" / "sailor.gm", resource / "animation" / "demo" / "sailor.an",
                        "demo\\", [sailor.IDLE])
    make_dialog.write_ani(resource / "animation" / "demo" / "sailor.ani", [sailor.IDLE])

    # the window is drawn pixel for pixel over the screen, a mip chain would only blur it
    write_tx(make_dialog.window_texture(), resource / "textures" / "dialog" / "dialog.tga.tx", mip_chain=False)
    (resource / "ini").mkdir(parents=True, exist_ok=True)
    (resource / "ini" / "dialog.ini").write_text(make_dialog.dialog_ini(), encoding="ascii")
    make_dialog.click_wav(resource / "sounds" / "interface" / "ok.wav")
    print(f"port patch {count} triangles")


if __name__ == "__main__":
    main()
