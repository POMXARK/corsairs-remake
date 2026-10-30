#!/bin/bash
# The engine under gdb: a crash prints the backtrace into $BT (default: crash-bt.txt next to the build), the game
# itself runs as usual. Usage: ./run.sh ./gdb-engine.sh   (ENGINE=<built engine> if not build/Debug/engine of the checkout)
DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="${ENGINE:-$DIR/../../build/Debug/engine}"
BT="${BT:-$DIR/../../crash-bt.txt}"
exec gdb -q -batch -ex "handle SIGPIPE nostop noprint" -ex run -ex "bt 40" -ex "thread apply all bt 12" --args "$ENGINE" "$@" 2>&1 | tee "$BT"
