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
# SCENE=story runs the self-test of the story machine (every action of the original) and quits.
# The window (docs/build.md): FULLSCREEN=1 the full screen, FULLSCREEN=0 a window with a frame, SCREEN=1920x1080 its size;
# by default engine.ini (a window of 1280x720). The engine options --fullscreen, --windowed, --size WxH do the same.
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
# the screens of the interface (INI/menu.ini, the world map of INI/map.ini), their pictures, texts and fonts, the dialog window and the voices;
# again for a map made before its fog
grep -qs 'fogStamp' "$DIR/resource/ini/interfaces/mainmap.ini" && grep -qs 'LB_VOICEON_OFF' "$DIR/resource/ini/interfaces/options.ini" && grep -qs 'PDM_HUD_18' "$DIR/resource/ini/fonts.ini" && [ -f "$DIR/program/data/pdm_screens.c" ] && [ -f "$DIR/program/data/pdm_voices.c" ] || python3 -I "$TOOLS/pdm_ui.py" "$PDM" "$DIR"
# the towns and interiors (WORLDS/locations/*.loc), their patches and the characters with animation
[ -f "$DIR/program/data/pdm_world.c" ] || python3 -I "$TOOLS/pdm_world.py" "$PDM" "$DIR"
# the cabin of the boarding, the fighters with the blade drawn and the plates of the bars, after the characters (it
# writes their .ani again); again for the data written before the plates
grep -qs "PdmBoarding.hud" "$DIR/program/data/pdm_boarding.c" || python3 -I "$TOOLS/pdm_boarding.py" "$PDM" "$DIR"
# the islands (DESC/<Island>.def, WORLDS/islands_x.idf), where the ship appears at each, their names and forts
grep -qs '"fort"' "$DIR/data/islands/Highrock.json" || python3 -I "$TOOLS/pdm_island.py" "$PDM" "$DIR/resource" all --data "$DIR/data"
# the toolbar of the sea (the commands, the pictures of the ships with flags, the bars) and its notes
grep -qs "info_rows" "$DIR/program/data/pdm_hud.c" || python3 -I "$TOOLS/pdm_hud.py" "$PDM" "$DIR"
# the music, the sounds and their aliases, the sounds of the kinds of location
[ -f "$DIR/program/data/pdm_sound.c" ] || python3 -I "$TOOLS/pdm_sound.py" "$PDM" "$DIR"
python3 -I "$TOOLS/pdm_data2c.py" "$DIR/data" "$DIR/program"
python3 -I "$TOOLS/pdm_logic2c.py" "$DIR/data" "$DIR/program"
# the neural voice-over of the speeches (docs/voice-over.md): binds the files that exist, none is fine
[ -f "$DIR/program/data/pdm_voice_lines.c" ] || python3 -I "$TOOLS/pdm_voice_lines.py" "$DIR"
# the scene to start with: menu, sea (the hero on his ship), review (all ship types side by side) or story
echo "string StartScene = \"${SCENE:-menu}\";" > "$DIR/program/data/start.c"
echo "string StartTown = \"${TOWN:-City_GrandaAvilia}\";" >> "$DIR/program/data/start.c"
echo "int TownAuto = ${TOWN_AUTO:-0};" >> "$DIR/program/data/start.c"
echo "int SoundFxOnly = ${SOUND_FX_ONLY:-0};" >> "$DIR/program/data/start.c"
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
