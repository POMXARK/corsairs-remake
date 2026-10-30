#!/bin/bash
# Shots of every shop sign from both sides: the signs are found by tools/pdm_signs_find.py, each side is
# one run of TOWN_AUTO=50 (the hero under the board, the camera 2.5 m in front of it), the frame at 15 s
# is kept as out/<town>-<texture>-<n>.jpg (the sides of a board are in neighbouring files, +1 then -1):
# to look at, the text must read right on both sides. error.log must stay empty after every run.
# usage: sign-shots.sh <engine> <out dir> <Корсары dir> [City_Name ...]
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$(realpath "$1")" OUT="$2" PDM="$3"
shift 3
mkdir -p "$OUT"
LOGS="${LOGS:-$HOME/.local/share/Akella/Sea Dogs/Logs}"
n=0
python3 -I "$DIR/../tools/pdm_signs_find.py" "$PDM" "$@" | while IFS=$'\t' read -r town stem at side cam; do
    name="$town-$stem-$n"; n=$((n + 1))
    # x11grab sometimes fails to open the window ("Failed to translate xcb geometry"): the run is repeated
    for try in 1 2 3; do
        rm -rf "$OUT/$name"
        TOWN="$town" CAM="$cam" SCENE=town TOWN_AUTO=50 "$DIR/shots.sh" "$ENGINE" "$OUT/$name" 20 15 > /dev/null 2>&1 < /dev/null
        [ -s "$OUT/$name/town-15.jpg" ] && break
    done
    if [ ! -s "$OUT/$name/town-15.jpg" ]; then echo "FAIL $name: no frame"; continue; fi
    mv "$OUT/$name/town-15.jpg" "$OUT/$name.jpg"
    if [ -s "$LOGS/error.log" ]; then echo "FAIL $name: error.log not empty"; else echo "ok   $name side $side $OUT/$name.jpg"; fi
done
