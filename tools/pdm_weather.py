#!/usr/bin/env python3
"""Converts RESOURCE/weather.ini of the original Sea Dogs (PDM 1.061): the weather periods of the day.

Each block __THE__NEXT__TIME__PERIOD__ <n> holds one moment of the day (angle 0,<hour>) with the colours
of the light (ambient_spectrum, direct_spectrum), the fog, the wind and the sky texture. The game
interpolates between the neighbours by the hour.

Writes program/data/pdm_weather.c: PdmWeather.count, PdmWeather.p<i>.{hour, ambient.rgb, direct.rgb, ambientK,
fog.rgb, fogDensity, wind, amp, sky}; the sky is a folder of weather\\skies\\ picked by the texture name.

usage: pdm_weather.py <Sea Dogs install dir with RESOURCE> <game_dir>
"""
import sys
from pathlib import Path


def sky_dir(tex):
    t = tex.lower()
    if 'night' in t:
        return 'storm'
    if 'zak' in t:
        return 'sunset'
    if 'overcast' in t or 'clouday' in t or t.startswith('sky_r'):
        return 'storm'
    if t.startswith(('sky_mor', 'sky_cloud')):
        return 'haze'
    return 'day'


def rgb(s):
    return [int(v) for v in s.split(',')]


def main():
    src, game = Path(sys.argv[1]), Path(sys.argv[2])
    text = (src / 'RESOURCE' / 'weather.ini').read_bytes().decode('cp1251')
    periods, cur = [], None
    for line in text.splitlines()[1:]:
        t = line.split(None, 1)
        if not t:
            continue
        if t[0] == '__THE__NEXT__TIME__PERIOD__':
            cur = {}
            periods.append(cur)
        elif cur is not None and len(t) > 1:
            cur[t[0]] = t[1].strip()
    out = ['// written by tools/pdm_weather.py from weather.ini', 'object PdmWeather;', '', 'void PdmWeather_Init()', '{']
    out.append('\tPdmWeather.count = %d;' % len(periods))
    for i, p in enumerate(periods):
        hour = float(p['angle'].split(',')[1])
        a, d, f = rgb(p['ambient_spectrum']), rgb(p['direct_spectrum']), rgb(p['fog_color'])
        out.append('\tPdmWeather.p%d.hour = %.2f;' % (i, hour))
        for key, c in (('ambient', a), ('direct', d), ('fog', f)):
            out.append('\tPdmWeather.p%d.%s.r = %d; PdmWeather.p%d.%s.g = %d; PdmWeather.p%d.%s.b = %d;'
                       % (i, key, c[0], i, key, c[1], i, key, c[2]))
        out.append('\tPdmWeather.p%d.ambientK = %s; PdmWeather.p%d.fogDensity = %s;' % (i, p['ambient'], i, p['fog_density']))
        out.append('\tPdmWeather.p%d.wind = %s; PdmWeather.p%d.amp = %s; PdmWeather.p%d.sky = "%s";'
                   % (i, p['wind_speed'], i, p['sea_amplitude'], i, sky_dir(p['texture_sky'])))
    out.append('}')
    dst = game / 'program' / 'data' / 'pdm_weather.c'
    dst.write_text('\n'.join(out) + '\n')
    print('weather: %d periods -> %s' % (len(periods), dst))


main()
