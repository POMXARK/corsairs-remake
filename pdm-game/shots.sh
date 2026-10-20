#!/bin/bash
# Checks a scene of pdm-game without input: records SECONDS of it with the engine's record.sh and
# writes the frames at the given seconds next to the video, to look at (out/<scene>-<s>.jpg).
# usage: SCENE=sea|review shots.sh <engine> <out dir> <seconds> <frame second>...
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$1" OUT="$2" LEN="$3"
shift 3
SCENE="${SCENE:-sea}"
mkdir -p "$OUT"
export SCENE
"$DIR/../engine/demos/common/record.sh" "$DIR" "$ENGINE" "$OUT/$SCENE.mp4" "sleep:$LEN" > "$OUT/$SCENE.log" 2>&1 || true
for s in "$@"; do
    ffmpeg -loglevel error -y -ss "$s" -i "$OUT/$SCENE.mp4" -frames:v 1 "$OUT/$SCENE-$s.jpg"
    echo "$OUT/$SCENE-$s.jpg"
done
cat "$HOME/.local/share/Akella/Sea Dogs/Logs/error.log"
