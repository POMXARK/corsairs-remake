#!/bin/bash
# Talks to the characters of a town from several sides: every character (the town guards by default, or the ids
# given) from every angle of ANGLES, one run per pair. The run starts the town with TOWN_AUTO=2, the hero walks
# up to the character, stands TALK_RADIUS off him at the angle and talks; the first answer goes to the log and the
# run ends. A pair passes when its marker is in the new lines of compile.log and error.log got no new lines.
# Usage: talk-angles.sh <path to built engine executable> [character id ...]
# TOWN=<town> (default City_HighRock), ANGLES="0 90 180 270" (degrees from the character's +x),
# LOGS=<dir with compile.log, error.log> (default: the Linux logs of the engine).
set -uo pipefail
ENGINE="$(realpath "$1")"
shift
DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOWN="${TOWN:-City_HighRock}"
ANGLES="${ANGLES:-0 90 180 270}"
LOGS="${LOGS:-$HOME/.local/share/Akella/Sea Dogs/Logs}"
lines() { wc -l < "$1" 2>/dev/null || echo 0; }

# no ids: every town guard named in the game data
if [ $# -eq 0 ]; then
    set -- $(grep -rhoE "[A-Za-z_]+___Town_Guard" "$DIR/data" | sort -u)
fi

pass=0
fail=0
skip=0
for npc in "$@"; do
    for angle in $ANGLES; do
        compile0=$(lines "$LOGS/compile.log")
        error0=$(lines "$LOGS/error.log")
        TOWN="$TOWN" SCENE=town TOWN_AUTO=2 TALK_NPC="$npc" TALK_ANGLE="$angle" \
            timeout -k 5 240 "$DIR/run.sh" "$ENGINE" > /dev/null 2>&1
        code=$?
        new=$(tail -n +$((compile0 + 1)) "$LOGS/compile.log" 2>/dev/null)
        errors=$(( $(lines "$LOGS/error.log") - error0 ))
        # the engine keeps the ids of the characters in lower case
        marker="PDM dialog: autotest talked to ${npc,,} from angle $angle,"
        if printf '%s\n' "$new" | grep -qF "$marker" && [ "$errors" -eq 0 ]; then
            echo "PASS $npc from $angle (exit $code)"
            pass=$((pass + 1))
        elif printf '%s\n' "$new" | grep -qiF "nobody to talk to ($npc)"; then
            # the character is not in this town (the guards are spread over the towns): not a failure
            echo "SKIP $npc from $angle: not in $TOWN"
            skip=$((skip + 1))
            break
        else
            echo "FAIL $npc from $angle (exit $code, new error.log lines $errors): no \"$marker\""
            printf '%s\n' "$new" | grep "PDM" | tail -5 | sed 's/^/     /'
            fail=$((fail + 1))
        fi
    done
done
echo "talk-angles: $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]
