#!/bin/bash
# Runs the autotests of autotest/scenarios.txt one after another (run.sh starts each one) and checks, for each:
# its marker appears in the new lines of compile.log, and error.log got no new lines.
# Usage: autotests.sh <path to built engine executable> [name ...]   (no names: every scenario)
# LOGS=<dir with compile.log, error.log> (default: the Linux logs of the engine)
set -uo pipefail
ENGINE="$(realpath "$1")"
shift
DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS="${LOGS:-$HOME/.local/share/Akella/Sea Dogs/Logs}"
lines() { wc -l < "$1" 2>/dev/null || echo 0; }

pass=0
fail=0
while IFS='|' read -r name scene town auto marker secs; do
    case "$name" in ''|\#*) continue ;; esac
    if [ $# -gt 0 ] && ! printf '%s\n' "$@" | grep -qx "$name"; then continue; fi
    compile0=$(lines "$LOGS/compile.log")
    error0=$(lines "$LOGS/error.log")
    SCENE="$scene" TOWN="$town" TOWN_AUTO="$auto" timeout -k 5 "$secs" "$DIR/run.sh" "$ENGINE" > /dev/null 2>&1
    code=$?
    new=$(tail -n +$((compile0 + 1)) "$LOGS/compile.log" 2>/dev/null)
    errors=$(( $(lines "$LOGS/error.log") - error0 ))
    if printf '%s\n' "$new" | grep -qE "$marker" && [ "$errors" -eq 0 ]; then
        echo "PASS $name (exit $code)"
        pass=$((pass + 1))
    else
        echo "FAIL $name (exit $code, new error.log lines $errors): no \"$marker\""
        printf '%s\n' "$new" | grep "PDM" | tail -5 | sed 's/^/     /'
        fail=$((fail + 1))
    fi
done < "$DIR/autotest/scenarios.txt"
echo "autotests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
