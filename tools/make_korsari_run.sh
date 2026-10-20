#!/usr/bin/env bash
# Собирает korsari-run: ресурсы оригинальных «Корсаров» (PDM 1.061), сконвертированные
# в форматы Storm 2 (.tf -> .tx, .cff -> .gm), и скрипты-референс из sd-teho-public.
# usage: make_korsari_run.sh <PDM_dir> <sd-teho-public_dir> <out_dir>
set -euo pipefail
PDM=${1:?PDM dir}; TEHO=${2:?sd-teho-public dir}; OUT=${3:?out dir}
TOOLS=$(cd "$(dirname "$0")" && pwd)
JOBS=${JOBS:-$(nproc)}

mkdir -p "$OUT"
echo "[1/4] copy PDM RESOURCE"
rsync -a "$PDM/RESOURCE/" "$OUT/resource/"

echo "[2/4] TEHO ini + program"
# PDM хранит INI в верхнем регистре; движок ищет пути без учёта регистра, поэтому сливаем в ту же папку
rsync -a --ignore-existing "$TEHO/resource/ini/" "$OUT/resource/INI/"
ln -sfn "$TEHO/program" "$OUT/program"
sed -e 's/^modules path.*//' -e 's/^program_directory.*/program_directory = program/' \
    -e 's/^screen_x.*/screen_x = 1280/' -e 's/^screen_y.*/screen_y = 720/' \
    "$TEHO/engine.ini" > "$OUT/engine.ini"

echo "[3/4] .tf -> .tx ($JOBS jobs)"
find "$OUT/resource/TEXTURES" -iname '*.tf' -print0 |
    xargs -0 -P "$JOBS" -I{} sh -c 'f="{}"; python3 -I "$0" -q "$f" "${f%.*}.tx" || echo "FAIL $f"' "$TOOLS/tf2tx.py"

echo "[4/4] .cff -> .gm"
python3 -I "$TOOLS/cff2gm.py" --batch "$OUT/resource/MODELS" "$OUT/resource/MODELS"
echo done
