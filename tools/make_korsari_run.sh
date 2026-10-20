#!/usr/bin/env bash
# Собирает korsari-run: ресурсы оригинальных «Корсаров» (PDM 1.061), сконвертированные
# pdm2storm.py для Storm 2 (resource/ и data/), и скрипты-референс из sd-teho-public.
# usage: make_korsari_run.sh <PDM_dir> <sd-teho-public_dir> <out_dir> [engine_build_dir]
# engine_build_dir (build/Debug) даёт шейдеры resource/techniques, без них движок ничего не рисует.
set -euo pipefail
PDM=${1:?PDM dir}; TEHO=${2:?sd-teho-public dir}; OUT=${3:?out dir}; BUILD=${4:-}
TOOLS=$(cd "$(dirname "$0")" && pwd)
JOBS=${JOBS:-$(nproc)}

mkdir -p "$OUT/save"
echo "[1/3] PDM RESOURCE -> resource + data (tools/pdm2storm.py)"
python3 -I "$TOOLS/pdm2storm.py" "$PDM" "$OUT" -j "$JOBS"

echo "[2/3] TEHO ini + program"
# PDM хранит INI в верхнем регистре; движок ищет пути без учёта регистра, поэтому сливаем в ту же папку
rsync -a --ignore-existing "$TEHO/resource/ini/" "$OUT/resource/INI/"
ln -sfn "$TEHO/program" "$OUT/program"
sed -e 's/^modules path.*//' -e 's/^program_directory.*/program_directory = program/' \
    -e 's/^screen_x.*/screen_x = 1280/' -e 's/^screen_y.*/screen_y = 720/' \
    "$TEHO/engine.ini" > "$OUT/engine.ini"

echo "[3/3] shaders"
[ -n "$BUILD" ] && ln -sfn "$(cd "$BUILD" && pwd)/resource/techniques" "$OUT/resource/techniques"
echo done
