#!/bin/bash
# The original Sea Dogs (PDM 1.061) on Storm Engine: the data and models come from an installed copy
# of the game and are converted on the first run; the game logic is the scripts in program/.
# Usage: run.sh <path to built engine executable> [engine options]
# PDM=<Sea Dogs install dir with RESOURCE> (default: ../../Корсары next to the repository)
# RECONVERT=1 converts everything again. The game starts with the main menu (SCENE=menu);
# SCENE=sea starts at sea at once, SCENE=menu-newgame presses "Новая Игра" by itself, SCENE=review starts with the fleet review,
# SCENE=town starts in the town TOWN (default City_GrandaAvilia), TOWN_AUTO=1 walks into its tavern and out,
# TOWN_AUTO=2 also talks to the first character of the tavern with a dialog,
# SCENE=story runs the self-test of the story machine (every action of the original) and quits.
set -euo pipefail
ENGINE="$(realpath "$1")"
DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$DIR/../tools"
DEMOS="$DIR/../engine/demos"
PDM="${PDM:-$DIR/../../../Корсары}"
[ "${RECONVERT:-0}" = 1 ] && rm -rf "$DIR/resource" "$DIR/data" "$DIR/convert-report.json"

if [ ! -f "$DIR/resource/.converted" ]; then
    # the tables, characters, ships and the story data as JSON in data/
    python3 -I "$TOOLS/pdm2storm.py" "$PDM" "$DIR" --only actions,dialogs,tables,desc,characters,ships,quests
    # the sea, the sky and the sail settings of the engine demos
    python3 -I "$DEMOS/sea/make_sea.py" "$DIR/resource"
    python3 -I "$DEMOS/ship/make_ship.py" "$DIR/resource"
    # every hull of WORLDS/Ships.idf (the forts are parts of the islands)
    for hull in $(python3 -I -c 'import json,sys; print(" ".join(sorted({dict(o)["filename"].lower() for o in json.load(open(sys.argv[1]))["objects"]} - {"fort"})))' \
                  "$DIR/data/tables/WORLDS/Ships.json"); do
        python3 -I "$TOOLS/pdm_ship.py" "$PDM" "$DIR/resource" "$hull" | tail -1
    done
    # the settings of the rope and vant entities written by pdm_ship.py (rope width, shroud texture layout)
    cat "$DIR/resource/ini/rigging_pdm.ini" >> "$DIR/resource/ini/rigging.ini"
    mkdir -p "$DIR/resource/sounds" "$DIR/resource/ini/aliases"
    touch "$DIR/resource/.converted"
fi
# the screens of the interface (INI/menu.ini ...), their pictures, texts and fonts, the dialog window and the voices
[ -f "$DIR/resource/ini/interfaces/mainmenu.ini" ] && [ -f "$DIR/program/data/pdm_voices.c" ] || python3 -I "$TOOLS/pdm_ui.py" "$PDM" "$DIR" MainMenu
# the towns and interiors (WORLDS/locations/*.loc), their patches and the characters with animation
[ -f "$DIR/program/data/pdm_world.c" ] || python3 -I "$TOOLS/pdm_world.py" "$PDM" "$DIR"
python3 -I "$TOOLS/pdm_data2c.py" "$DIR/data" "$DIR/program"
python3 -I "$TOOLS/pdm_logic2c.py" "$DIR/data" "$DIR/program"
# the scene to start with: menu, sea (the hero on his ship), review (all ship types side by side) or story
echo "string StartScene = \"${SCENE:-menu}\";" > "$DIR/program/data/start.c"
echo "string StartTown = \"${TOWN:-City_GrandaAvilia}\";" >> "$DIR/program/data/start.c"
echo "int TownAuto = ${TOWN_AUTO:-0};" >> "$DIR/program/data/start.c"
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$DIR/resource/techniques"

cd "$DIR"
exec "$ENGINE" "${@:2}"
