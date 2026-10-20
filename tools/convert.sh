#!/usr/bin/env bash
# Конвертирует RESOURCE оригинальных «Корсаров» (PDM 1.061) для Storm Engine.
# usage: convert.sh <папка_игры> <out> [--only stage,...] [-j N]
set -euo pipefail
PY=${PYTHON:-$(command -v python3 || command -v python)}
[ -n "$PY" ] || { echo "нужен Python 3.8+"; exit 1; }
exec "$PY" -I "$(cd "$(dirname "$0")" && pwd)/pdm2storm.py" "$@"
