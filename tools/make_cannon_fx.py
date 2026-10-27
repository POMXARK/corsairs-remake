#!/usr/bin/env python3
"""The guns of the movies (the sprites of flash and smoke come from fire.tf of the original, see pdm_effects.py): two particle systems built from the blocks of the particles demo (its atlas stays the same).
gunflash: a muzzle flash and a puff of white smoke; shothit: a hit on a hull, a flash, dark splinters and a pall of pale smoke.
The hulls of the shots stand a few units from the camera (the keys of the movies are in small units) and the demo builds for
metres, so every size, speed and spread is times the factor of the system (see FX in pdm_cutscene.py for the distances).
usage: make_cannon_fx.py <resource dir>; writes particles/{gunflash,shothit}.xps (the sprite atlas comes from make_particles.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "particles"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "common"))
import make_particles  # noqa: E402
from make_particles import Colors, Graph, billboard, emitter, fade  # noqa: E402
from storm_formats import Frames, write_xps  # noqa: E402

FLASH_K = 1.3
HIT_K = 0.2


def sizes(k, *points):
    return Graph.life([(t, v * k) for t, v in points])


def flipbook(rows=3):
    """The frames of fire.tf (rows 0..2 of the atlas: flame, burst, smoke), as EXPLOSION_X plays them over the life of a sprite."""
    cell = 1.0 / make_particles.CELLS
    inset = 1.0 / make_particles.ATLAS
    return Frames((col * cell + inset, row * cell + inset, cell - 2 * inset, cell - 2 * inset)
                  for row in range(rows) for col in range(4))


def smoke_frames():
    """The 4 frames of the grey smoke row of fire.tf."""
    cell = 1.0 / make_particles.CELLS
    inset = 1.0 / make_particles.ATLAS
    return Frames((col * cell + inset, 2 * cell + inset, cell - 2 * inset, cell - 2 * inset) for col in range(4))


def sprite(name, rate, count, life, speed, size, spin=0.0, spread=(0.0, 0.0, 0.0), attach="none", rows=3, tint=(1.0, 1.0, 1.0), **physics):
    """A billboard that runs through the 12 frames of fire.tf over its life and fades in the last third."""
    b = billboard(name, rate=rate, count=count, life=life, speed=speed, size=size,
                  color=Colors([(0.0, tint, (1.0, 1.0, 1.0)), (1.0, tuple(c * 0.9 for c in tint), (1.0, 1.0, 1.0))]),
                  transparency=fade([(0, 0), (60, 10), (100, 100)]), row=0, frame_count=4, spin=spin, spread=spread,
                  **physics)
    b["Texture"] = flipbook(rows)
    b["Animation frame"] = Graph.life([(0, 0.0), (100, rows * 4 - 0.1)])
    b["Attached emitter"] = attach
    return b


def gunflash():
    """The shot, after CANCLOUDS.dll: a few white puffs of the smoke row at the gun port that hang there for a second."""
    k = FLASH_K
    puff = sprite("blast", rate=60, count=4, life=(1.0, 1.5), speed=(0.0, 0.1 * k), size=sizes(k, (0, 0.35), (100, 0.9)),
                  spin=10.0, spread=(0.05 * k, 0.03 * k, 0.05 * k), rows=1)
    puff["Texture"] = smoke_frames()
    puff["Animation frame"] = Graph.life([(0, 0.0), (100, 3.9)])
    return [(emitter("blast", 0.08, False, 20.0), [puff])]


def shothit():
    """A hit on a hull, after EXPLOSION_X: 64 pieces thrown up in all directions, half of them with a trail of fire.tf
    sprites; its numbers (units of the original, speed 0..1, gravity 0.5, a trail of 9 sprites a second living 0.65..1.35 s)
    times the factor of the system."""
    k = HIT_K
    trail = sprite("trail", rate=14, count=14, life=(0.65, 1.35), speed=(0.0, 0.1 * k * 4), size=sizes(k, (0, 0.5), (100, 0.9)),
                   spin=10.0, rows=1, tint=(1.0, 0.7, 0.35))
    pieces = billboard(
        "pieces", rate=500, count=36, life=(1.5, 3.0), speed=(0.3 * k * 5, 1.8 * k * 5),
        size=Graph.const(0.06 * k, 0.2 * k),
        color=Colors([(0.0, (0.03, 0.025, 0.02), (0.08, 0.06, 0.04)), (1.0, (0.03, 0.025, 0.02), (0.08, 0.06, 0.04))]),
        transparency=fade([(0, 0), (80, 10), (100, 100)]),
        row=3, frame_count=3, mass=1.0, gravity=8.0, spin=12.0)
    cell = 1.0 / make_particles.CELLS
    inset = 1.0 / make_particles.ATLAS
    # the cells of the row of sparks: a block, a splinter and a plank; every piece takes one and tumbles
    tumble = Frames([(col * cell + inset, 3 * cell + inset, cell - 2 * inset, cell - 2 * inset) for col in (1, 2, 3)])
    pieces["Texture"] = tumble
    pieces["Animation frame"] = Graph.const(0.0, 2.99)
    pieces["Attached emitter"] = "trail"
    blast = sprite("blast", rate=100, count=4, life=(0.4, 0.7), speed=(0.0, 0.5 * k), size=sizes(k, (0, 0.6), (100, 1.4)),
                   spin=30.0, spread=(0.8 * k, 0.6 * k, 0.4 * k), additive=True)
    # fire on the hull: orange flames of the first row of fire.tf (not additive, so they keep their colour) that burn after the hit
    fire = sprite("fire", rate=30, count=24, life=(0.8, 1.6), speed=(0.0, 0.8 * k), size=sizes(k, (0, 0.8), (100, 1.9)),
                  spin=10.0, spread=(0.5 * k, 0.4 * k, 0.4 * k), rows=1, tint=(1.0, 0.8, 0.45), additive=True)
    # embers: small orange flakes thrown out with the pieces
    embers = billboard(
        "embers", rate=500, count=24, life=(0.8, 2.0), speed=(0.3 * k * 5, 1.6 * k * 5), size=Graph.const(0.04 * k, 0.1 * k),
        color=Colors([(0.0, (1.0, 0.55, 0.15), (1.0, 0.8, 0.3)), (1.0, (0.8, 0.25, 0.05), (1.0, 0.5, 0.1))]),
        transparency=fade([(0, 0), (70, 10), (100, 100)]), row=3, frame_count=1, mass=1.0, gravity=12.0)
    embers["Texture"] = pieces["Texture"]
    # small dark splinters, many and quick
    splinters = billboard(
        "splinters", rate=500, count=40, life=(1.0, 2.2), speed=(0.5 * k * 5, 3.0 * k * 5), size=Graph.const(0.02 * k, 0.06 * k),
        color=Colors([(0.0, (0.03, 0.025, 0.02), (0.08, 0.06, 0.04)), (1.0, (0.03, 0.025, 0.02), (0.08, 0.06, 0.04))]),
        transparency=fade([(0, 0), (80, 10), (100, 100)]), row=3, frame_count=3, mass=1.0, gravity=8.0, spin=20.0)
    splinters["Texture"] = tumble
    splinters["Animation frame"] = Graph.const(1.0, 2.99)
    column = sprite("column", rate=14, count=30, life=(1.5, 2.5), speed=(0.5 * k, 1.5 * k), size=sizes(k, (0, 1.5), (100, 4.0)),
                    spin=8.0, spread=(0.4 * k, 0.1 * k, 0.4 * k), rows=1)
    column["Texture"] = smoke_frames()
    column["Animation frame"] = Graph.life([(0, 0.0), (100, 3.9)])
    return [(emitter("blast", 0.1, False, 60.0), [blast]), (emitter("pieces", 0.1, False, 70.0), [pieces]),
            (emitter("trail", 3.0, False, 30.0), [trail]), (emitter("column", 2.0, False, 15.0), [column]),
            (emitter("fire", 2.0, False, 50.0), [fire]), (emitter("embers", 0.1, False, 80.0), [embers]),
            (emitter("splinters", 0.1, False, 80.0), [splinters])]


if __name__ == "__main__":
    out = Path(sys.argv[1]) / "particles"
    write_xps(gunflash(), out / "gunflash.xps")
    write_xps(shothit(), out / "shothit.xps")
