#!/usr/bin/env python3
"""The pale yellow haze of the last shot of Scene7: a sky of the sea demo's generator with the colours of a mist (the demo has day, sunset and storm).
usage: make_haze_sky.py <resource dir>; writes textures/weather/skies/haze/sky_{fr,lf,bk,rt,up}.tga.tx"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "sea"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "demos" / "common"))
import make_sea  # noqa: E402
from storm_formats import write_tx  # noqa: E402

# the generator keeps a noise seed per preset name: the haze borrows the clouds of "storm" (a low, flat cover)
make_sea.SKY_PRESETS["storm"] = dict(zenith=(232, 232, 188), horizon=(240, 240, 198), sun_height=0.5, sun_azimuth=2.6,
                                     sun=(255, 255, 220), glow=0.08, clouds=0.55, cloud_light=(244, 244, 206), cloud_dark=(214, 214, 170))
out = Path(sys.argv[1]) / "textures" / "weather" / "skies" / "haze"
for face in make_sea.SKY_FACES:
    write_tx(make_sea.sky_face(face, "storm"), out / f"{face}.tga.tx")
