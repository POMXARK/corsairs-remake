#!/bin/bash
# The original Sea Dogs (PDM 1.061) on Storm Engine: the data and models come from an installed copy
# of the game and are converted on the first run; the game logic is the scripts in program/.
# Usage: run.sh <path to built engine executable> [engine options]
# PDM=<Sea Dogs install dir with RESOURCE> (default: ../../Корсары next to the repository)
# RECONVERT=1 converts everything again. SCENE=review starts with the fleet review.
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
python3 -I "$TOOLS/pdm_data2c.py" "$DIR/data" "$DIR/program"
# the scene to start with: sea (the hero on his ship) or review (all ship types side by side)
echo "string StartScene = \"${SCENE:-sea}\";" > "$DIR/program/data/start.c"
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$DIR/resource/techniques"

cd "$DIR"
exec "$ENGINE" "${@:2}"
