#!/bin/bash
# A ship of the original Sea Dogs on the Storm 2 sea: the sea, sky and rigging settings come from the
# generators of the engine demos, the ship is assembled from the game files by tools/pdm_ship.py.
# Usage: run.sh <path to built engine executable> [engine options]
# PDM=<Sea Dogs install dir with RESOURCE> (default: ../../Корсары next to the repository)
set -euo pipefail
ENGINE="$(realpath "$1")"
DIR="$(cd "$(dirname "$0")" && pwd)"
DEMOS="$DIR/../engine/demos"
PDM="${PDM:-$DIR/../../../Корсары}"

python3 -I "$DEMOS/sea/make_sea.py" "$DIR/resource"
# rigging.ini, mast.ini and the sail textures the sail entity loads by fixed names
python3 -I "$DEMOS/ship/make_ship.py" "$DIR/resource"
python3 -I "$DIR/../tools/pdm_ship.py" "$PDM" "$DIR/resource" ABrig
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$DIR/resource/techniques"
mkdir -p "$DIR/resource/sounds" "$DIR/resource/ini/aliases"

cd "$DIR"
exec "$ENGINE" "${@:2}"
