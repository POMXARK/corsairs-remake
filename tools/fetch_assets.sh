#!/bin/bash
# Downloads the free assets used by the game (licenses in CREDITS.md).
# Usage: fetch_assets.sh <assets dir>
set -euo pipefail
DIR="$1"
mkdir -p "$DIR"
FONTS=https://github.com/google/fonts/raw/main/ofl/oldstandardtt
[ -f "$DIR/OldStandard-Bold.ttf" ] || curl -sfL -o "$DIR/OldStandard-Bold.ttf" "$FONTS/OldStandard-Bold.ttf"
[ -f "$DIR/OFL.txt" ] || curl -sfL -o "$DIR/OFL.txt" "$FONTS/OFL.txt"
[ -f "$DIR/ninth_wave.jpg" ] || curl -sfL -A "corsairs-remake" -o "$DIR/ninth_wave.jpg" \
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Hovhannes_Aivazovsky_-_The_Ninth_Wave_-_Google_Art_Project.jpg/1920px-Hovhannes_Aivazovsky_-_The_Ninth_Wave_-_Google_Art_Project.jpg"
