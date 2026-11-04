#!/bin/bash
# Run coat_autouv.py in 3DCoat on the Windows PC from Linux, wait and fetch the result.
# coat_run.sh in.obj out.obj [auto|seams|remesh|ops|uvcmd] [seams.txt]   (remesh: FACES=20000, DENS=voxels per unit, 0 = default;
# ops: OPS='relax:0.5;weld' - the separate tools of coat_autouv.py, see its docstring; uvcmd: OPS='$RemoveUVIntr;$JoinAllClusters')
# Needs ssh to the PC (WIN, KEY) and 3DCoat 2026 there. 3DCoat is started in the user's desktop session by a
# scheduled task (/it): a GUI started straight from ssh has no screen. A running 3DCoat is closed first.
set -e
WIN=${WIN:-User@192.168.1.214}
KEY=${KEY:-$HOME/.ssh/win_remake}
RD=${RD:-C:/Users/User/cof/coat}
EXE=${EXE:-C:\\Program Files\\3DCoat-2026\\3DCoatGL64.exe}
src=$1; dst=$2; mode=${3:-auto}; seams=$4
here=$(dirname "$(readlink -f "$0")")
tmp=$(mktemp -d)
s() { ssh -i "$KEY" "$WIN" "$@"; }
name=$(basename "$src")
printf '%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n' "$RD/$name" "$RD/coat_out.obj" "$RD/coat_log.txt" "$mode" "$RD/seams.txt" "${DENS:-0}" "${FACES:-20000}" "${OPS:-}" > "$tmp/_coat_job.txt"
# HIDE=desk (default): coat_hide.ps1 starts 3DCoat on its own hidden desktop: no window on the screen, the focus stays
# with the user (start /min did not work: 3DCoat restores its window after loading; kept minimized it draws no frames
# and the script never starts; HIDE=off moves it off the screen, but 3DCoat still takes the focus);
# HIDE=min: kept minimized (checks only); HIDE=0: a normal window (MIN=0 of the older runs means the same)
HIDE=${HIDE:-desk}; [ "${MIN:-1}" = 0 ] && HIDE=0
if [ "$HIDE" = 0 ]; then
  printf '@echo off\r\n"%s" -script %s\\coat_autouv.py\r\n' "$EXE" "${RD//\//\\}" > "$tmp/coat_run.bat"
else
  printf '@echo off\r\npowershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File %s\\coat_hide.ps1 -Exe "%s" -Script %s\\coat_autouv.py -Mode %s\r\n' \
    "${RD//\//\\}" "$EXE" "${RD//\//\\}" "$HIDE" > "$tmp/coat_run.bat"
fi
# the task starts the bat through wscript with window style 0: no console window, nothing takes the focus
printf 'CreateObject("WScript.Shell").Run "cmd /c %s\\coat_run.bat", 0, False\r\n' "${RD//\//\\}" > "$tmp/coat_run.vbs"
files=("$here/coat_autouv.py" "$here/coat_hide.ps1" "$tmp/_coat_job.txt" "$tmp/coat_run.bat" "$tmp/coat_run.vbs" "$src")
[ -n "$seams" ] && cp "$seams" "$tmp/seams.txt" && files+=("$tmp/seams.txt")
s "taskkill /f /im 3DCoatGL64.exe >nul 2>&1 & del ${RD//\//\\}\\coat_log.txt ${RD//\//\\}\\coat_out.obj >nul 2>&1 & exit 0"
scp -q -i "$KEY" "${files[@]}" "$WIN:$RD/"
# the task is made once and kept: a new task each run makes autorun watchers (AnVir) pop up and take the focus,
# 3DCoat then stops stepping frames (coathide: the older coatrun ran the bat itself and its console took the focus)
s "schtasks /query /tn coathide >nul 2>&1 || schtasks /create /f /tn coathide /sc once /st 00:00 /it /tr \"wscript.exe ${RD//\//\\}\\coat_run.vbs\" >nul 2>&1 & schtasks /run /tn coathide >nul"
t0=$(date +%s)
until s "type ${RD//\//\\}\\coat_log.txt 2>nul" | grep -q '^done'; do
  [ $(( $(date +%s) - t0 )) -gt 900 ] && { echo 'coat_run: no done in 15 min' >&2; exit 1; }
  timeout 10 tail -f /dev/null || true
done
s "type ${RD//\//\\}\\coat_log.txt" | tr -d '\r' | sed 's/^/  coat: /'
[ "$HIDE" != 0 ] && s "type ${RD//\//\\}\\coat_hide.log 2>nul" | tr -d "\r" | awk "/focus|failed/ || NR<=1 {print} END {print}" | sed "s/^/  hide: /"
scp -q -i "$KEY" "$WIN:$RD/coat_out.obj" "$dst"
s "taskkill /f /im 3DCoatGL64.exe >nul 2>&1 & exit 0"
rm -rf "$tmp"
echo "coat_run: $dst in $(( $(date +%s) - t0 )) s"
