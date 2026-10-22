# Сборка и запуск: «Корсары» (PDM 1.061) на Storm Engine

Эта версия — оригинальная игра «Корсары» на открытом движке Storm Engine. В репозиториях нет ни одного файла оригинала:
- модели, текстуры, локации, диалоги и звуки берутся из установленной у вас копии игры и конвертируются при первом запуске;
- логика оригинала (она была C++ в DLL) переписана скриптами в `pdm-game/program/`.

Что сделано и что ещё нет — [port-plan.md](port-plan.md). Команды для проверок — [test-commands.md](test-commands.md).

## Репозитории и ветки

| Что | Репозиторий | Ветка |
|---|---|---|
| Игра: скрипты, конвертеры, этот документ | [POMXARK/corsairs-remake](https://github.com/POMXARK/corsairs-remake) | `pdm-launch` |
| Движок (submodule `engine/`) | [POMXARK/storm-engine](https://github.com/POMXARK/storm-engine) | `pdm-launch` |

- **Ветки.** `main` у corsairs-remake — первый ремейк на свободных ассетах (`game/`, `run.sh` в корне), без оригинала. У движка `pdm-launch` ответвлена от `miniaudio-sound` (звук без FMOD), а та — от `linux-build` (сборка на Linux).
- **Версия движка.** Игра закрепляет точный коммит движка в submodule: `git submodule update` берёт именно его, это рабочая пара.
- **Upstream** — [PiratesAhoy/storm-engine](https://github.com/PiratesAhoy/storm-engine). В нём этих изменений нет, собирать игру с ним нельзя.

```bash
git clone --recursive -b pdm-launch https://github.com/POMXARK/corsairs-remake.git
cd corsairs-remake
git submodule update --init --recursive    # если клонировали без --recursive
```

## Что нужно от оригинала

- **Установленные «Корсары» 1.061** (Акелла / 1С, 2000), русская версия, обновлённая патчем до 1.061. Нужна папка игры с `RESOURCE/`, `MODULES/` и `ENGINE.INI`. Английская Sea Dogs не проверялась: тексты и шрифты конвертеры берут русские.
- **Путь к ней** — переменная `PDM`. По умолчанию это `../Корсары` рядом с папкой репозитория.

Как версия собирается из оригинала (`pdm-game/run.sh`, на Windows — `pdm-game/run.ps1`), по шагам:

1. `tools/pdm2storm.py` переводит таблицы, персонажей, корабли, диалоги и квесты в JSON (`pdm-game/data/`).
2. `engine/demos/sea|ship/make_*.py` строят море, небо и настройки парусов. Это ассеты движка, не оригинала.
3. `tools/pdm_ship.py` переводит каждый корпус из `WORLDS/Ships.idf` в модель Storm (`.gm`), с такелажем.
4. `tools/pdm_ui.py` переводит экраны интерфейса, окно диалога, шрифты и голоса.
5. `tools/pdm_world.py` переводит города и интерьеры (`WORLDS/locations/*.loc`), патчи ходьбы и персонажей с анимацией. Это самый долгий шаг, около 6 минут.
6. `tools/pdm_sound.py` переводит музыку, звуки и их алиасы.
7. `tools/pdm_data2c.py` и `pdm_logic2c.py` превращают данные и логику сюжета в скрипты `program/data/*.c`.

Первый запуск идёт 10–15 минут, следующие запускаются сразу. Каждый шаг выполняется, только если его результата ещё нет. Всё сконвертировать заново — `RECONVERT=1` (или пункт меню 8). Конвертеры идемпотентны: повторный прогон даёт те же байты.

Результат лежит в `pdm-game/resource`, `pdm-game/data` и `pdm-game/program/data`, всего около 0,8 ГБ. Эти папки в `.gitignore`: данные оригинала не коммитить и не раздавать. Пакет `dist/` (ниже) тоже только для себя.

## Меню и команды

Всё делается одним скриптом: `pdm-game/game.sh` на Linux, `pdm-game/game.bat` на Windows. Без аргументов он показывает меню:

```
  Корсары (PDM 1.061) на Storm Engine — сборка: debug
  1) Играть: главное меню         6) Собрать движок (debug)
  2) Город (Хайрок)               7) Сменить сборку debug/release
  3) Море                         8) Сконвертировать оригинал заново
  4) Смотр флота                  9) Собрать пакет для игры (dist/)
  5) Квест Хайрока (автотест)     c) Проверить окружение
  k) Управление   l) Логи   q) Выход
```

Те же действия — командами:

| Linux | Windows | Что делает |
|---|---|---|
| `game.sh build debug` | `game.bat build Debug` | собрать движок (Release — `release`) |
| `game.sh run debug menu` | `game.bat run Debug menu` | играть; сцены: `menu`, `town`, `sea`, `battle`, `review`, `quest`, `story` |
| `game.sh convert` | `game.bat convert` | сконвертировать оригинал заново |
| `game.sh package` | `game.bat package` | Release-движок с игрой в `dist/` |
| `game.sh check` | `game.bat check` | где оригинал и движок, что собрано, какие есть инструменты |
| `game.sh logs` / `keys` | `game.bat logs` / `keys` | хвосты логов / клавиши |

**Свои пути** задаются в файле рядом со скриптом, он не в git:
- `pdm-game/local.env` (Linux);
- `pdm-game/local.ps1` (Windows).

```bash
# pdm-game/local.env
PDM=/games/Корсары
ENGINE_SRC=/src/storm-engine      # исходники движка, по умолчанию engine/
BUILD_DEBUG=/src/build            # папки сборки, по умолчанию engine/build/linux-{debug,release}
BUILD_RELEASE=/src/build-release
DIST=/games/corsairs-pdm-linux    # куда класть пакет, по умолчанию dist/corsairs-pdm-linux
. /src/env.sh                     # CONAN_HOME, CC=clang, PATH — всё, что нужно сборке
```

```powershell
# pdm-game/local.ps1
$env:PDM = 'D:\Games\Корсары'
```

`local.ps1` с кириллицей в пути сохраняйте в **UTF-8 с BOM**: Windows PowerShell 5.1 читает файл без BOM как ANSI и портит путь. Скрипты в git уже с BOM.

## Linux

### Подготовка

Один раз установите пакеты и инструменты: clang, CMake ≥ 3.24, Ninja, Conan 2, X11/XCB- и SDL2-заголовки, Vulkan-драйвер. Полный список, команды `apt` и решения ошибок — в [engine/docs/ru/08-linux-build.md](../engine/docs/ru/08-linux-build.md). Для конвертеров нужен Python 3 с Pillow и numpy (`pip install Pillow numpy`).

```bash
pdm-game/game.sh check      # что найдено, а чего не хватает
```

### Debug-сборка (для разработки)

```bash
pdm-game/game.sh build debug        # cmake + Conan + dxvk-native + engine
pdm-game/game.sh run debug          # первый запуск ещё и конвертирует оригинал
```

- **Первая конфигурация** скачивает и собирает зависимости Conan — от нескольких минут до часа, несколько ГБ в `CONAN_HOME`.
- **Движок** — `<build>/Debug/engine`.
- **Отладка:**
  - логи — `~/.local/share/Akella/Sea Dogs/Logs/{error,system,compile}.log`, `game.sh logs`. `error.log` после запуска должен быть пуст;
  - трассы скриптов — строки `PDM` в `compile.log`;
  - отладчик — `cd pdm-game && gdb --args <build>/Debug/engine`: движок ищет `program/` и `resource/` от текущей папки;
  - окна редактора — `pdm-game/run.sh <build>/Debug/engine --editor`;
  - переменные запуска (`SCENE`, `TOWN`, `TOWN_AUTO`, `SOUND_FX_ONLY`) — в [test-commands.md](test-commands.md).

### Release-сборка и пакет для игры

```bash
pdm-game/game.sh build release      # отдельная папка сборки, свои пакеты Conan
pdm-game/game.sh run release        # проверить из исходников
pdm-game/game.sh package            # dist/corsairs-pdm-linux
dist/corsairs-pdm-linux/play.sh     # игра без исходников и Python
```

`package` собирает папку:
- `bin/` — Release-движок, его библиотеки из дерева сборки (dxvk-native, mimalloc) и шейдеры;
- `game/` — скрипты и сконвертированный оригинал;
- `play.sh` — запуск.

Игра стартует с главного меню. Перед `package` оригинал должен быть сконвертирован: хватит одного запуска игры или `game.sh convert`.

## Windows

### Подготовка

1. **Visual Studio 2022** (или Build Tools 2022/2019) с нагрузкой «Разработка классических приложений на C++».
2. **Python 3** с python.org, галочка «Add to PATH».
3. **Git**; клонирование — как выше, с `--recursive`. Без git — архив (`python3 tools/make_archive.py`, до 100 МБ), сборка из него — [archive.md](archive.md).
4. **DirectX End-User Runtime (June 2010)**, если при запуске не хватает `d3dx9_43.dll`.

Conan, CMake, Ninja, Pillow и numpy `build.bat` ставит через pip сам. Подробности и ошибки — [engine/docs/ru/08-linux-build.md](../engine/docs/ru/08-linux-build.md), раздел о Windows.

### Сборка и запуск

Двойной щелчок по `pdm-game\game.bat` открывает то же меню. Командами:

```bat
pdm-game\game.bat build Debug       :: engine\build\default\Debug\engine.exe (build.ps1 в корне игры)
pdm-game\game.bat run Debug menu    :: первый запуск конвертирует оригинал
pdm-game\game.bat build Release
pdm-game\game.bat package           :: dist\corsairs-pdm-windows\play.bat
```

- **Логи** — `Документы\My Games\Sea Dogs\Logs`.
- **Отладка** — Visual Studio: «Открыть папку» `engine\`, пресет `default`, конфигурация Debug, рабочая папка `pdm-game\`.

> Windows-скрипты (`game.ps1`, `run.ps1`) работают в Windows PowerShell 5.1 (PowerShell 7 не нужен). Сборка Debug и конвертация на Windows доходили до локаций; если что-то упадёт, пришлите вывод окна и `system.log`.

## Анимации персонажей

`tools/pdm_character.py` переводит `.ani` оригинала в `.an`/`.ani` Storm:
- **Частота.** Анимации идут 10 кадров в секунду, как в оригинале.
- **Ходьба и бег.** Ускорены в 2 раза (`WALK_RATE`, `RUN_RATE`, наше значение). Без этого герой и пираты ходят вдвое медленнее человека. Скорость перемещения (`Walk speed`) умножается на тот же коэффициент, чтобы ноги не скользили. Подробности — в [decompile.md](decompile.md).
- **Жесты.** Если внутри жеста стоянки (`do_some*`) есть скачок позы, действие обрезается до него. Пример — `do_some1` героя налезает на `stap_back_calm`.
- **Переходы.** У жестов и разговора есть плавный переход 0,2 с (`Blend time`).

Проверка рывков без запуска игры:

```
python3 tools/pdm_anim_check.py pdm-game/resource [модель …] [--all]
```

Она сообщает о трёх видах рывков:
- **шов цикла** — последний кадр не сходится с первым;
- **рывок на кадре** — скачок посреди действия;
- **скачок позы** — разрыв между позой действия и `idle_1`, если между ними нет плавного перехода.

Сейчас остаются рывки в жестах солдат (`soldier_*`, idle_2/idle_4) и швы поворота у трактирщиков.

## Управление

| Где | Клавиши |
|---|---|
| Главное меню | стрелки — выбор, Enter или мышь — нажать |
| Город | W/S — вперёд/назад, A/D — поворот, мышь — поворот и камера, Shift — бег, E — заговорить с ближайшим; в двери и воротах справа сверху значок выхода, Пробел — пройти |
| Диалог | стрелки — ответ, Пробел/Enter/ЛКМ — ответить, PageUp/PageDown — листать, Esc — выйти из разговора |
| Море | W/S — поднять/убрать паруса, A/D — руль, мышь — камера, Q/E — камера ближе/дальше, R — время ×1/×3/×6, M — карта мира, Пробел — в порт (у гавани, значок справа сверху); Tab — меню команд (в порт, карта, время): стрелки, Enter — выполнить, Esc — закрыть; F — залп бортами, которые смотрят на врага (в бою) |
| Карта мира | вверх/вниз — остров в списке, Enter/ЛКМ — плыть к нему, ЛКМ по острову на карте — туда же, «Выход» — назад в море |
| Город и море | F1 — статус героя (снаряжение, товары, корабль, журнал, сундук), кнопки внизу — страницы, Esc/«Выход» — назад в игру |
| Везде | Esc — меню игры: продолжить, настройки, выход (в диалоге — только из разговора, на экране — назад) |
| Город и море | F3 — быстрое сохранение (`save/quick`), F7 — загрузить его; в бою, при абордаже, в диалоге и на карте мира не сохраняется. При выходе из города в море игра сохраняется сама в `save/auto` |
| Окно (Linux) | Ctrl+Alt — отпустить мышь, клик в окне — снова захватить |

## Разрешение и окно

По умолчанию игра идёт в окне 1280×720 с рамкой. Три способа поменять, от разового к постоянному:

1. Переменные запуска (только этот запуск):
   ```bash
   SCREEN=1920x1080 pdm-game/run.sh build/Debug/engine     # размер окна
   FULLSCREEN=1 pdm-game/run.sh build/Debug/engine          # на весь экран
   FULLSCREEN=0 SCREEN=1600x900 pdm-game/run.sh build/Debug/engine
   ```
   Windows: `$env:SCREEN='1920x1080'; $env:FULLSCREEN='1'; .\pdm-game\run.ps1`.
2. Ключи движка — для собранной игры (`play.sh` из `game.sh package` передаёт их движку, `play.sh --size 1920x1080`): `--size 1920x1080`, `--fullscreen`, `--windowed`, `--mouse-release`.
3. Постоянно — `pdm-game/engine.ini` (в собранной игре — `game/engine.ini`):
   ```ini
   full_screen = 0        ; 1 — на весь экран
   screen_x = 1280        ; ширина
   screen_y = 720         ; высота
   window_borders = 1     ; рамка окна
   mouse_release = 1      ; Linux: Ctrl+Alt отпускает мышь
   ```

В игре то же меняется на экране «Настройки» (Escape → «Настройки»): «Разрешение» перебирает размеры, галочка «Полный Экран», затем «Применить» — окно меняется сразу и запоминается в `engine.ini`.

Ключи запуска сильнее `engine.ini`. На весь экран берётся заданное разрешение; если монитор его не поддерживает, лучше указать родное (`SCREEN=2560x1440 FULLSCREEN=1`). Интерфейс оригинала рассчитан на 4:3 (800×600): на широком экране (Full HD, 2K — 16:9) он стоит по центру без растяжения, а по бокам — тот же фон, размытый и затемнённый (`tools/pdm_ui.py`, `BACKFILL`).

Мышь: на Linux движок держит её в окне (камера крутится мышью). При `mouse_release = 1` (по умолчанию в pdm-game) Ctrl+Alt её отпускает: курсор свободен, игра не реагирует на движения; клик в окне снова захватывает. На Windows мышь не захватывается, отпускать не нужно.

Клавиши задаются в скриптах: `Town_MapKeys` (`program/town.c`), `Sea_MapShipKeys` (`program/sea.c`), `Menu_Start` (`program/menu.c`), `Screen_Init` (`program/screens.c`).

## Что пока не работает

- Нет вступительного ролика и экранов списка сохранений (только F3/F7); HUD моря — без боевых команд (П4).
- В порт заводит подход к гавани острова, Пробел или команда «На землю» в меню Tab (у гавани); на карту мира — уплыть от острова, M или команда карты. Порт есть только у островов с живым городом: у Эмуно, Иначетлы, Алиандо и Чактчи значка «На землю» нет.

Полный список — раздел «Статус» в [port-plan.md](port-plan.md).
