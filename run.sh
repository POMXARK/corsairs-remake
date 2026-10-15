#!/bin/bash
# Runs the game: downloads free assets, builds the sea battle assets with the generators of the engine
# demos (engine/demos), converts the menu assets (.tx textures, fonts.ini) and starts the engine in game/.
# Usage: run.sh <path to built engine executable>
# The engine is built from the engine/ submodule (see engine/LINUX_BUILD or the fork README).
set -euo pipefail
ENGINE="$(realpath "$1")"
DIR="$(cd "$(dirname "$0")" && pwd)"
GAME="$DIR/game"
DEMOS="$DIR/engine/demos"

"$DIR/tools/fetch_assets.sh" "$DIR/assets"
# PT Serif: the sound demo draws its font and make_hud.py the compass letters with it
"$DEMOS/dialog/fetch_assets.sh" "$DIR/assets/ptserif"
# the sea battle: sea, brig, particles, sounds and music, cannonball, island, HUD textures
python3 -I "$DEMOS/sea/make_sea.py" "$GAME/resource"
python3 -I "$DEMOS/ship/make_ship.py" "$GAME/resource"
python3 -I "$DEMOS/particles/make_particles.py" "$GAME/resource"
python3 -I "$DEMOS/sound/make_sound.py" "$DIR/assets/ptserif" "$GAME/resource"
python3 -I "$DEMOS/battle/make_battle.py" "$GAME/resource"
python3 -I "$DEMOS/island/make_island.py" "$GAME/resource"
python3 -I "$DEMOS/hud/make_hud.py" "$DIR/assets/ptserif" "$GAME/resource"
# last: the sound demo writes its own fonts.ini, the game's fonts (with Cyrillic) replace it
python3 -I "$DIR/tools/make_assets.py" "$DIR/assets" "$GAME/resource"
# shaders are copied next to the engine by the build
ln -sfn "$(dirname "$ENGINE")/resource/techniques" "$GAME/resource/techniques"

# the engine indexes resources by scanning the working directory, so it runs from game/
cd "$GAME"
exec "$ENGINE"
