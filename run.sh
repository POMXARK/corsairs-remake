#!/bin/bash
# Runs the game: downloads free assets, converts them to engine formats
# (.tx textures, fonts.ini) and starts the engine in game/.
# Usage: run.sh <path to built engine executable>
# The engine is built from the engine/ submodule (see engine/LINUX_BUILD or the fork README).
set -euo pipefail
ENGINE="$(realpath "$1")"
DIR="$(cd "$(dirname "$0")" && pwd)"
GAME="$DIR/game"

"$DIR/tools/fetch_assets.sh" "$DIR/assets"
python3 -I "$DIR/tools/make_assets.py" "$DIR/assets" "$GAME/resource"
# the deck scene: generated models and wood textures, no downloads
python3 -I "$DIR/tools/make_scene.py" "$GAME/resource"
# shaders are copied next to the engine by the build; empty folders are expected by the services
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$GAME/resource/techniques"
mkdir -p "$GAME/resource/sounds" "$GAME/resource/ini/aliases"

# the engine indexes resources by scanning the working directory, so it runs from game/
cd "$GAME"
exec "$ENGINE"
