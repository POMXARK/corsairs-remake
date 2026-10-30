#!/bin/bash
# The original Sea Dogs (PDM 1.061) on Storm Engine, Linux: builds the engine, converts the installed
# original and starts the game, from a menu or by a command. The steps are told in docs/build.md.
#
# Usage: game.sh                      the menu
#        game.sh build debug|release  builds the engine (CMake + Conan + Ninja)
#        game.sh run [debug|release] [menu|sea|battle|town|review|quest|story]   starts the game
#        game.sh convert              converts the original once more (RECONVERT=1 of run.sh)
#        game.sh package              the Release engine and the converted game in dist/, play.sh starts it
#        game.sh logs | keys | check
#
# Paths, by default next to this repository, are set in pdm-game/local.env (not in git), e.g.
#   PDM=/games/Корсары                   the installed original (with RESOURCE/ and MODULES/)
#   ENGINE_SRC=/src/storm-engine         the engine sources, the engine/ submodule by default
#   BUILD_DEBUG=/src/build               its Debug build folder, BUILD_RELEASE its Release one
#   DIST=/games/corsairs-pdm             where game.sh package puts the game
#   . /src/env.sh                        anything the build needs: CONAN_HOME, CC=clang, PATH
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
[ -f "$DIR/local.env" ] && . "$DIR/local.env"
PDM="${PDM:-$ROOT/../Корсары}"
ENGINE_SRC="${ENGINE_SRC:-$ROOT/engine}"
BUILD_DEBUG="${BUILD_DEBUG:-$ENGINE_SRC/build/linux-debug}"
BUILD_RELEASE="${BUILD_RELEASE:-$ENGINE_SRC/build/linux-release}"
DIST="${DIST:-$ROOT/dist/corsairs-pdm-linux}"
LOGS="$HOME/.local/share/Akella/Sea Dogs/Logs"

build_dir() { [ "$1" = release ] && echo "$BUILD_RELEASE" || echo "$BUILD_DEBUG"; }
# single-config Ninja puts the engine into <build>/<Debug|Release>/
engine_of() { local b; b="$(build_dir "$1")"; [ "$1" = release ] && echo "$b/Release/engine" || echo "$b/Debug/engine"; }

build() {
    local cfg="${1:-debug}" type=Debug b
    [ "$cfg" = release ] && type=Release
    b="$(build_dir "$cfg")"
    [ -f "$ENGINE_SRC/CMakeLists.txt" ] || { echo "no engine at $ENGINE_SRC: git submodule update --init --recursive"; exit 1; }
    mkdir -p "$b"
    # the first configure installs the Conan packages of the configuration (minutes to an hour)
    [ -f "$b/build.ninja" ] || cmake -S "$ENGINE_SRC" -B "$b" -G Ninja -DCMAKE_BUILD_TYPE=$type \
        -DSTORM_EXTRA_MODULES="$ROOT/editor" -DSTORM_SOUND_BACKEND=miniaudio -Wno-dev
    # dxvk-native (Direct3D 9 on Vulkan) first, then the engine
    cmake --build "$b" --target dependencies
    cmake --build "$b" --target engine -j"$(nproc)"
    echo "engine: $(engine_of "$cfg")"
}

# the scene names of the menu, as the variables of run.sh
run() {
    local cfg="${1:-debug}" scene="${2:-menu}" engine
    engine="$(engine_of "$cfg")"
    # the first run from an unpacked archive has no engine yet: it is built here (ours)
    [ -x "$engine" ] || build "$cfg"
    [ -x "$engine" ] || { echo "no $cfg engine at $engine after the build"; exit 1; }
    case "$scene" in
        quest) export SCENE=town TOWN=City_HighRock TOWN_AUTO=3 ;;
        town)  export SCENE=town TOWN="${TOWN:-City_HighRock}" ;;
        *)     export SCENE="$scene" ;;
    esac
    PDM="$PDM" "$DIR/run.sh" "$engine"
}

convert() { RECONVERT=1 PDM="$PDM" SCENE=story "$DIR/run.sh" "$(engine_of debug)"; }

# a folder that runs without the sources: the Release engine with its libraries and shaders, the scripts
# and what was converted from the original. It holds the original's data: for oneself, not to hand out
package() {
    local engine lib
    engine="$(engine_of release)"
    [ -x "$engine" ] || { echo "no Release engine: game.sh build release"; exit 1; }
    [ -f "$DIR/program/data/pdm_world.c" ] || { echo "the original is not converted yet: game.sh convert"; exit 1; }
    rm -rf "$DIST"
    mkdir -p "$DIST/bin/resource" "$DIST/game/save"
    cp -L "$engine" "$DIST/bin/engine"
    cp -rL "$(dirname "$engine")/resource/techniques" "$DIST/bin/resource/"
    # the libraries of the build tree (dxvk, mimalloc): their paths are written into the engine, so
    # play.sh points LD_LIBRARY_PATH at bin/ instead
    for lib in $(ldd "$engine" | awk '/=> \// {print $3}' | grep -v "^/lib\|^/usr/lib"); do cp -L "$lib" "$DIST/bin/"; done
    cp -r "$DIR/program" "$DIR/engine.ini" "$DIST/game/"
    cp -r "$DIR/resource" "$DIST/game/"
    rm -rf "$DIST/game/resource/techniques"
    ln -s ../../bin/resource/techniques "$DIST/game/resource/techniques"
    # the scene the game starts with: the main menu
    printf 'string StartScene = "menu";\nstring StartTown = "City_GrandaAvilia";\nint TownAuto = 0;\n#define RUN_TOWNAUTO 0\n#define RUN_SAVEDIR "save"\n#define RUN_SAVEPFX "save\\"\nint SoundFxOnly = 0;\nint StartVolFx = 80;\nint StartVolMusic = 70;\nint StartVolVoice = 100;\nint StartNpcVoice = 1;\n' \
        > "$DIST/game/program/data/start.c"
    cat > "$DIST/play.sh" <<'EOF'
#!/bin/bash
# Corsairs (PDM 1.061) on Storm Engine: the engine runs in game/, where it looks for program/ and resource/
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D/game" && LD_LIBRARY_PATH="$D/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" exec "$D/bin/engine" "$@"
EOF
    chmod +x "$DIST/play.sh"
    echo "the game: $DIST/play.sh ($(du -sh "$DIST" | cut -f1))"
}

logs() {
    for f in error system; do echo "== $f.log"; tail -20 "$LOGS/$f.log" 2>/dev/null || echo "(none)"; done
    echo "== compile.log, PDM"; grep -a "PDM" "$LOGS/compile.log" 2>/dev/null | tail -20 || true
}

keys() {
    cat <<'EOF'
Главное меню   стрелки — выбор, Enter или мышь — нажать
Город          W/S — вперёд/назад, A/D — поворот, мышь — поворот и камера, Shift — бег
               E — заговорить с ближайшим; в двери и воротах справа сверху значок выхода,
               Пробел — пройти
Диалог         стрелки — выбор ответа, Пробел/Enter/ЛКМ — ответить, PageUp/PageDown — листать,
               Esc — выйти из разговора
Море           W/S — поднять/убрать паруса, A/D — руль, мышь — камера, Q/E — камера ближе/дальше,
               R — время ×1/×3/×6, M — карта мира, Пробел — в порт (у гавани, значок справа сверху)
               Tab — меню команд (в порт, карта, время), стрелки — выбор, Enter — выполнить, Esc — закрыть
               F — залп бортами, которые смотрят на врага (в бою)
Карта мира     вверх/вниз — остров, Enter/ЛКМ — плыть к нему, ЛКМ по острову на карте — туда же,
               «Выход» — назад в море
Везде          Esc — меню игры: продолжить, настройки, выход (в диалоге — только из разговора)
EOF
}

check() {
    printf "%-9s %s\n" "PDM:" "$PDM $( [ -d "$PDM/RESOURCE" ] && echo ok || echo '— нет RESOURCE/')"
    echo "движок:   $ENGINE_SRC ($(git -C "$ENGINE_SRC" rev-parse --abbrev-ref HEAD 2>/dev/null) $(git -C "$ENGINE_SRC" log --oneline -1 2>/dev/null | cut -c1-60))"
    for cfg in debug release; do
        printf '%-9s %s %s\n' "$cfg:" "$(engine_of $cfg)" "$( [ -x "$(engine_of $cfg)" ] && echo собран || echo 'не собран')"
    done
    echo "данные:   $( [ -f "$DIR/program/data/pdm_world.c" ] && echo сконвертированы || echo 'ещё нет (первый запуск)')"
    for t in cmake ninja conan clang python3; do printf '%-9s %s\n' "$t:" "$(command -v $t || echo нет)"; done
    python3 -c "import PIL, numpy" 2>/dev/null && echo "Pillow, numpy: есть" || echo "Pillow, numpy: pip install Pillow numpy"
}

menu() {
    local cfg=debug choice
    while true; do
        cat <<EOF

  Корсары (PDM 1.061) на Storm Engine — сборка: $cfg
  1) Играть: главное меню         6) Собрать движок ($cfg)
  2) Город (Хайрок)               7) Сменить сборку debug/release
  3) Море                         8) Сконвертировать оригинал заново
  4) Смотр флота                  9) Собрать пакет для игры (dist/)
  5) Квест Хайрока (автотест)     c) Проверить окружение
  b) Морской бой   k) Управление   l) Логи   q) Выход
EOF
        read -rp "> " choice || exit 0
        case "$choice" in
            1) (run $cfg menu) ;;
            2) (run $cfg town) ;;
            3) (run $cfg sea) ;;
            4) (run $cfg review) ;;
            5) (run $cfg quest) ;;
            b) (run $cfg battle) ;;
            6) (build $cfg) ;;
            7) [ $cfg = debug ] && cfg=release || cfg=debug ;;
            8) (convert) ;;
            9) (package) ;;
            c) check ;;
            k) keys ;;
            l) logs ;;
            q|0) exit 0 ;;
        esac || echo "(код $?)"
    done
}

case "${1:-menu}" in
    menu) menu ;;
    build) build "${2:-debug}" ;;
    run) run "${2:-debug}" "${3:-menu}" ;;
    convert) convert ;;
    package) package ;;
    logs) logs ;;
    keys) keys ;;
    check) check ;;
    *) sed -n 5,11p "$0"; exit 1 ;;
esac
