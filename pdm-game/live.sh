#!/bin/bash
# Live control of pdm-game on Linux (the counterpart of the windows-live-control skill): the game runs in the background,
# a loop writes a screenshot of its window every INTERVAL seconds, the keys and clicks go in by single commands.
# usage: live.sh start <engine> [SCENE=...]   - start the game and the screenshots (OUT=/tmp/pdm-live, INTERVAL=20)
#        live.sh snap [name]                  - a screenshot now (OUT/<name>.png, default now.png)
#        live.sh key <xdotool key>            - press a key       live.sh click X Y   - click at X, Y pixels of the window
#        live.sh move X Y | type TEXT | rect | log | stop
# The input goes to the real display: the window gets the focus, do not work in other windows meanwhile.
set -uo pipefail
OUT="${OUT:-/tmp/pdm-live}"
INTERVAL="${INTERVAL:-20}"
export OUT
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
wid() { cat "$OUT/wid" 2>/dev/null; }
grab() { xdotool windowactivate "$(wid)" 2>/dev/null; sleep 0.3; eval "$(xdotool getwindowgeometry --shell "$(wid)")"; ffmpeg -loglevel error -y -f x11grab -draw_mouse 0 -video_size "${WIDTH}x${HEIGHT}" -i "$DISPLAY+$X,$Y" -frames:v 1 "$1"; }
snap() { grab "$OUT/${1:-now}.png"; }
case "${1:-}" in
start)
    ENGINE="$(realpath "$2")"; shift 2
    "$0" stop >/dev/null 2>&1
    env "$@" "$DIR/run.sh" "$ENGINE" > "$OUT/game.log" 2>&1 &
    echo $! > "$OUT/game.pid"
    for _ in $(seq 1 120); do
        # the window of this very game (by the process): a window of an earlier copy may still be around
        P=$(pgrep -n -x engine-1 || true)
        W=""; [ -n "$P" ] && W=$(xdotool search --onlyvisible --pid "$P" 2>/dev/null | tail -1 || true)
        [ -n "$W" ] && break
        sleep 1
    done
    [ -n "${W:-}" ] || { echo "no window"; exit 1; }
    echo "$W" > "$OUT/wid"
    ( n=0; while kill -0 "$(cat "$OUT/game.pid")" 2>/dev/null; do n=$((n+1)); WID="$W"; "$0" snap "auto-$(printf %03d $n)" >/dev/null 2>&1; cp "$OUT/auto-$(printf %03d $n).png" "$OUT/last.png"; sleep "$INTERVAL"; done ) > /dev/null 2>&1 &
    echo $! > "$OUT/snap.pid"
    echo "window $W, screenshots in $OUT every ${INTERVAL}s (last.png)" ;;
snap) snap "${2:-now}"; echo "$OUT/${2:-now}.png" ;;
key) xdotool windowfocus "$(wid)" 2>/dev/null; xdotool keydown "$2"; sleep 0.15; xdotool keyup "$2" ;;
type) xdotool windowfocus "$(wid)" 2>/dev/null; xdotool type --delay 150 "$2" ;;
move) xdotool mousemove --window "$(wid)" "$2" "$3" ;;
click) xdotool windowfocus "$(wid)" 2>/dev/null; xdotool mousemove --window "$(wid)" "$2" "$3"; sleep 0.15; xdotool mousedown 1; sleep 0.15; xdotool mouseup 1 ;;
rect) xdotool getwindowgeometry "$(wid)" ;;
log) tail -n "${2:-20}" "$HOME/.local/share/Akella/Sea Dogs/Logs/compile.log"; cat "$HOME/.local/share/Akella/Sea Dogs/Logs/error.log" ;;
stop) kill "$(cat "$OUT/snap.pid" 2>/dev/null)" "$(cat "$OUT/game.pid" 2>/dev/null)" 2>/dev/null; pkill -x engine-1 2>/dev/null; echo stopped ;;
*) sed -n 2,9p "$0" ;;
esac
