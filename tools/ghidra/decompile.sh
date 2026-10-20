#!/usr/bin/env bash
# Декомпилирует DLL оригинальных «Корсаров» в C: headless-анализ Ghidra + DumpDecomp.java.
# usage: GHIDRA=<ghidra_dir> decompile.sh <out_dir> <file.dll>...
#   out_dir/<dll>.c — все функции, out_dir/<dll>.strings.txt — строки, out_dir/<dll>.log — лог анализа.
# Нужен JDK 21+ (JAVA_HOME). Временный проект создаётся в out_dir/.proj и удаляется.
set -u
GHIDRA=${GHIDRA:?path to ghidra_12.x_PUBLIC}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?out dir}; shift
mkdir -p "$OUT/.proj"; OUT=$(cd "$OUT" && pwd)
for f in "$@"; do
  b=$(basename "$f")
  echo "== $b $(date +%T)"
  "$GHIDRA/support/analyzeHeadless" "$OUT/.proj" pdm -import "$f" \
     -scriptPath "$HERE" -postScript DumpDecomp.java "$OUT" -deleteProject -overwrite > "$OUT/$b.log" 2>&1
  ls -l "$OUT/$b.c" 2>/dev/null || echo "FAIL $b, see $OUT/$b.log"
done
