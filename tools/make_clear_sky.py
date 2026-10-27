#!/usr/bin/env python3
"""The bright cloudless sky of Scene2 (the original shot is a plain light blue): a sky of the sea demo's generator without clouds.
usage: make_clear_sky.py <resource dir>; writes textures/weather/skies/clear/sky_{fr,lf,bk,rt,up}.tga.tx"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "sea"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "common"))
import make_sea  # noqa: E402
from storm_formats import write_tx  # noqa: E402

make_sea.SKY_PRESETS["day"] = dict(zenith=(105, 180, 240), horizon=(150, 208, 244), sun_height=0.85, sun_azimuth=-0.4,
                                   sun=(255, 255, 235), glow=0.05, clouds=0.0, cloud_light=(255, 255, 255), cloud_dark=(230, 240, 250))
out = Path(sys.argv[1]) / "textures" / "weather" / "skies" / "clear"
for face in make_sea.SKY_FACES:
    write_tx(make_sea.sky_face(face, "day"), out / f"{face}.tga.tx")
