#!/bin/bash
# The original Sea Dogs (PDM 1.061) on Storm Engine: the data and models come from an installed copy
# of the game and are converted on the first run; the game logic is the scripts in program/.
# Usage: run.sh <path to built engine executable> [engine options]
# PDM=<Sea Dogs install dir with RESOURCE> (default: ../../Корсары next to the repository)
# RECONVERT=1 converts everything again. The game starts with the main menu (SCENE=menu);
# SCENE=sea starts at sea at once, SCENE=menu-newgame presses "Новая Игра" by itself, SCENE=review starts with the fleet review,
# SCENE=town starts in the town TOWN (default City_GrandaAvilia), TOWN_AUTO=1 walks into its tavern and out,
# TOWN_AUTO=2 also talks to the first character of the tavern with a dialog, TOWN_AUTO=3 (TOWN=City_HighRock)
# does the errand of the guard Billy (the first quest of the town), TOWN_AUTO=4 sails out and back to the pier,
# TOWN_AUTO=5 sails out and into the port by the harbour of the island,
# SEA_WAVES=sines makes the waves of the engine demos (a sum of sines) instead of the FFT sea (with RECONVERT=1);
# SCENE=screens shows every screen of the interface in turn, then F1 (the status) in the town, and quits;
# SCENE=battle starts at sea with a pirate attacking (F fires), TOWN_AUTO=7 fires by itself until he sinks and quits,
# TOWN_AUTO=8 sails to him, boards him, fights his captain in the cabin by itself and quits;
# SCENE=sea TOWN_AUTO=12 saves at sea, lands, loads, lands again, saves in the town, loads and quits;
# SCENE=sea TOWN_AUTO=13 saves from the menu over the game, loads that file from the list, deletes it, sets the
# window to 1600x900 in the options and back, and quits;
# SCENE=cutscene plays the intro movie and quits, SCENE=cutscene-<movie> one movie of DESC (bunt, death, scene8...); SCENE=story runs the self-test of the story machine (every action of the original) and quits.
# The window (docs/build.md): FULLSCREEN=1 the full screen, FULLSCREEN=0 a window with a frame, SCREEN=1920x1080 its size;
# by default engine.ini (a window of 1280x720). The engine options --fullscreen, --windowed, --size WxH do the same.
# VOLUME_FX, VOLUME_MUSIC, VOLUME_VOICE (0..100) and NPC_VOICE=0|1 set the sound of the page "Настройки" at the start, as
# settings.ini does (the variable wins).
# SOUND_FX_ONLY=1 mutes the music and the ambience of the locations, to hear the steps and the effects.
set -euo pipefail
ENGINE="$(realpath "$1")"
DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$DIR/../tools"
DEMOS="$DIR/../engine/demos"
PDM="${PDM:-$DIR/../../../Корсары}"
[ "${RECONVERT:-0}" = 1 ] && rm -rf "$DIR/resource" "$DIR/data" "$DIR/convert-report.json"

# every hull of WORLDS/Ships.idf (the forts are parts of the islands)
hulls() {
    for hull in $(python3 -I -c 'import json,sys; print(" ".join(sorted({dict(o)["filename"].lower() for o in json.load(open(sys.argv[1]))["objects"]} - {"fort"})))' \
                  "$DIR/data/tables/WORLDS/Ships.json"); do
        python3 -I "$TOOLS/pdm_ship.py" "$PDM" "$DIR/resource" "$hull" | tail -1
    done
}

if [ ! -f "$DIR/resource/.converted" ]; then
    # the tables, characters, ships and the story data as JSON in data/
    python3 -I "$TOOLS/pdm2storm.py" "$PDM" "$DIR" --only actions,dialogs,tables,desc,characters,ships,quests
    # the sea, the sky and the sail settings of the engine demos
    python3 -I "$DEMOS/sea/make_sea.py" "$DIR/resource" --waves "${SEA_WAVES:-fft}"
    python3 -I "$DEMOS/ship/make_ship.py" "$DIR/resource"
    hulls
    # the settings of the rope and vant entities written by pdm_ship.py (rope width, shroud texture layout)
    cat "$DIR/resource/ini/rigging_pdm.ini" >> "$DIR/resource/ini/rigging.ini"
    mkdir -p "$DIR/resource/sounds" "$DIR/resource/ini/aliases"
    touch "$DIR/resource/.converted"
fi
# the battle (program/battle.c): the blast and the splash of the particles demo, the cannonball and the shot
# holes of the battle demo; the hulls again where they were made before they had the gun labels
if [ ! -f "$DIR/resource/particles/explosion.xps" ]; then
    python3 -I "$DEMOS/particles/make_particles.py" "$DIR/resource"
    python3 -I "$DEMOS/battle/make_battle.py" "$DIR/resource"
    hulls
fi
# the guns of the movies (the flash of a shot, the hit on a hull) from the blocks of the particles demo
[ -f "$DIR/resource/textures/weather/skies/haze/sky_up.tga.tx" ] || python3 -I "$TOOLS/make_haze_sky.py" "$DIR/resource"
[ -f "$DIR/resource/textures/effects/fire.tx" ] || python3 -I "$TOOLS/pdm_effects.py" "$PDM" "$DIR/resource"
[ -f "$DIR/resource/particles/shothit.xps" ] || python3 -I "$TOOLS/make_cannon_fx.py" "$DIR/resource"
[ -f "$DIR/resource/textures/weather/skies/clear/sky_up.tga.tx" ] || python3 -I "$TOOLS/make_clear_sky.py" "$DIR/resource"
[ -f "$DIR/resource/textures/weather/moon.tga.tx" ] || python3 -I "$TOOLS/make_moon.py" "$DIR/resource"
[ -f "$DIR/resource/textures/cinema/binocular.tga.tx" ] || python3 -I "$TOOLS/make_binocular.py" "$DIR/resource"
# the screens of the interface (INI/menu.ini, the world map of INI/map.ini), their pictures, texts and fonts, the dialog window and the voices;
# again for a map made before its fog
grep -qs 'fogStamp' "$DIR/resource/ini/interfaces/mainmap.ini" && grep -qs 'LB_VOICEON_OFF' "$DIR/resource/ini/interfaces/options.ini" && grep -qs 'PDM_HUD_18' "$DIR/resource/ini/fonts.ini" && [ -f "$DIR/program/data/pdm_screens.c" ] && [ -f "$DIR/program/data/pdm_voices.c" ] || python3 -I "$TOOLS/pdm_ui.py" "$PDM" "$DIR"
# the towns and interiors (WORLDS/locations/*.loc), their patches and the characters with animation
# eyes.ini comes with the eye grid of the heads (the blink): the characters of an older world are converted again alone (pdm_character.py all), and the boarding after them
WORLD_NEW=0
if [ ! -f "$DIR/program/data/pdm_world.c" ]; then WORLD_NEW=1; python3 -I "$TOOLS/pdm_world.py" "$PDM" "$DIR"
elif [ ! -f "$DIR/resource/ini/eyes.run" ]; then WORLD_NEW=1; python3 -I "$TOOLS/pdm_character.py" "$PDM" "$DIR/resource" all; fi
# the cabin of the boarding, the fighters with the blade drawn and the plates of the bars, after the characters (it
# writes their .ani again); again for the data written before the plates
if [ "$WORLD_NEW" = 1 ] || ! grep -qs "PdmBoarding.hud" "$DIR/program/data/pdm_boarding.c"; then python3 -I "$TOOLS/pdm_boarding.py" "$PDM" "$DIR"; fi
# the movies of the original (the intro of "Новая игра"): the scenes of DESC/*.ani, their models, textures and sounds
[ -f "$DIR/program/data/pdm_weather.c" ] || python3 -I "$TOOLS/pdm_weather.py" "$PDM" "$DIR"
grep -qs "PdmCut.intro" "$DIR/program/data/pdm_cutscenes.c" || python3 -I "$TOOLS/pdm_cutscene.py" "$PDM" "$DIR"
# the islands (DESC/<Island>.def, WORLDS/islands_x.idf), where the ship appears at each, their names and forts
grep -qs '"fort"' "$DIR/data/islands/Highrock.json" || python3 -I "$TOOLS/pdm_island.py" "$PDM" "$DIR/resource" all --data "$DIR/data"
# the toolbar of the sea (the commands, the pictures of the ships with flags, the bars) and its notes
grep -qs "info_rows" "$DIR/program/data/pdm_hud.c" || python3 -I "$TOOLS/pdm_hud.py" "$PDM" "$DIR"
# the music, the sounds and their aliases, the sounds of the kinds of location
[ -f "$DIR/program/data/pdm_sound.c" ] && [ -d "$DIR/resource/sounds/pdm/music" ] || python3 -I "$TOOLS/pdm_sound.py" "$PDM" "$DIR"
python3 -I "$TOOLS/pdm_data2c.py" "$DIR/data" "$DIR/program"
python3 -I "$TOOLS/pdm_logic2c.py" "$DIR/data" "$DIR/program"
# the neural voice-over of the speeches (docs/voice-over.md): binds the files that exist, none is fine
[ -f "$DIR/program/data/pdm_voice_lines.c" ] || python3 -I "$TOOLS/pdm_voice_lines.py" "$DIR"
# the scene to start with: menu, sea (the hero on his ship), review (all ship types side by side) or story
echo "string StartScene = \"${SCENE:-menu}\";" > "$DIR/program/data/start.c"
echo "string StartTown = \"${TOWN:-City_GrandaAvilia}\";" >> "$DIR/program/data/start.c"
echo "int TownAuto = ${TOWN_AUTO:-0};" >> "$DIR/program/data/start.c"
# HOUR=<0..24> starts the day of the sea at that hour (weather.ini periods), default 9
echo "float StartHour = $(LC_NUMERIC=C printf %.2f "${HOUR:-9}");" >> "$DIR/program/data/start.c"
# TOWN_AUTO=2 with TALK_NPC=<id> and TALK_ANGLE=<degrees>: the hero talks to that character from that side (talk-angles.sh)
echo "string TalkNpc = \"${TALK_NPC:-}\";" >> "$DIR/program/data/start.c"
echo "int TalkAngle = ${TALK_ANGLE:-0};" >> "$DIR/program/data/start.c"
echo "int SoundFxOnly = ${SOUND_FX_ONLY:-0};" >> "$DIR/program/data/start.c"
# the volume and the voices of the characters: the variable, else settings.ini, else the default (0..100)
setting() { local v="${!1:-}"; [ -n "$v" ] || v=$(sed -n "s/^$2[[:space:]]*=[[:space:]]*//p" "$DIR/settings.ini" 2>/dev/null | head -1); v="${v//[^0-9]/}"; echo "${v:-$3}"; }
echo "int StartVolFx = $(setting VOLUME_FX volume_fx 80);" >> "$DIR/program/data/start.c"
echo "int StartVolMusic = $(setting VOLUME_MUSIC volume_music 70);" >> "$DIR/program/data/start.c"
echo "int StartVolVoice = $(setting VOLUME_VOICE volume_voice 100);" >> "$DIR/program/data/start.c"
echo "int StartNpcVoice = $(setting NPC_VOICE npc_voice 1);" >> "$DIR/program/data/start.c"
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$DIR/resource/techniques"

# the window over engine.ini
WINDOW=()
[ "${FULLSCREEN:-}" = 1 ] && WINDOW+=(--fullscreen)
[ "${FULLSCREEN:-}" = 0 ] && WINDOW+=(--windowed)
[ -n "${SCREEN:-}" ] && WINDOW+=(--size "$SCREEN")
# the saves of the game (program/save.c: F3, F7, the save leaving a town)
mkdir -p "$DIR/save"
cd "$DIR"
exec "$ENGINE" "${WINDOW[@]}" "${@:2}"
