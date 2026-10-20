# Ход работы: запуск оригинальных Корсаров (PDM) на новом движке

## Цель
**Запустить меню игры на новом движке** (первая цель, задана пользователем). Все результаты и выводы
фиксируются в этом файле.

## Разбиение задачи «запуск меню» на подзадачи

Критерий готовности: в `system.log` видно загрузку `MainMenu.gm` + 13 моделей пунктов меню,
камера позиционирована по локейтору, ошибок фатального уровня нет; далее — визуальная проверка.

| # | Подзадача | Статус | Примечание |
|---|-----------|--------|------------|
| 1 | Движок стартует без краша (30+ сек) | ✅ | null-guard в `MODELR::Update()` (model.cpp) |
| 2 | Инициализация воды/моря проходит | ✅ | 64 синтетических TGA-кадра в `resource/sea/` |
| 3 | Цепочка видео → `Main_Start` проходит | ✅ | .wmv отсутствуют, но `ievntEndVideo` шлётся при неудаче → авто-проход case'ов |
| 4 | Сцена меню: `MainMenu.gm` + локейторы | ✅ | crate.gm (1232B) + `MainMenu_locators.gm` (1397B, 11 локейторов) |
| 5 | Placeholder-модели пунктов меню (13 .gm) | ⬜ | `menu02..07_active/passive.gm` + `seagull.gm` — копировать crate.gm |
| 6 | `resource/Loading/progress.tga` | ⬜ | синтетический TGA, убрать «Progress error!» |
| 7 | Шрифт `interface normal font rus` | ⬜ | `fonts\...tga` отсутствует; имя хардкод в C++; найти путь загрузки / синтезировать TGA-шрифт |
| 8 | Ошибка `Can't load texture r` (каждый кадр) | ⬜ | источник не найден; поиск по sea-библиотеке / feedback-текстурам |
| 9 | Запуск: проверить загрузку MainMenu + камеру в system.log | ⬜ | после подзадач 5–8 |
| 10 | Визуальная проверка: меню видно на экране | ⬜ | скриншот; при необходимости — правка позиций/камеры |

Зависимости: 5–8 независимы друг от друга (можно параллельно) → 9 → 10.
Формат-конвертеры (.tf→.tx, .cff→.gm, .ani→INI) — НЕ часть этой задачи, после запуска меню.

## Текущее состояние (блок)
- `engine.exe` (Debug, v2.9.0.1, 36 МБ) **падает**: `0xC0000005` ACCESS_VIOLATION, RVA `0x123E21`, детерминированно (все раны).
  Точка краша найдена: `CMatrix::EqMultiply(const CMatrix&, const CMatrix&)` (`matrix.h:475`) — второй операнд `m2` невалиден.
  Момент: загрузка островов (между trace IslaDeVieques и ошибкой IslaMona). **Блокирует запуск до меню.**
- Тестовые бинарники работают: `config-test.exe` (11 ассертов), `scene-test.exe` (63 ассерта).
- Минидампы не найдены. Логи движком при краше не записаны (краш до/вне инициализации логов — уточнить).

## Структуры

### Оригинальная игра: `C:\Program Files\1C\Корсары` (PDM v1.061, 2000–2001)
- `ENGINE.exe` — закрытый движок 1C (Storm 1)
- `MODULES/` — 104 DLL: **вся игровая логика** (CORE, SHIP, MAP, SAIL, CANNON...)
- `RESOURCE/` — 7819 файлов, 741 МБ (TEXTURES/.tf, MODELS/.cff, DIALOGS/.d, ACTIONS/.a, QUESTS/.ql, SOUNDS, MUSIC, SHIPS, CHARACTERS... + 450 сырых .tga)
- **Ни одного .c файла** — скриптов в установке нет вообще

### КРИТИЧЕСКОЕ уточнение
`storm-devs/sd-teho-public` — это скрипты для **«Морские псы: Каждый за своё» (TEHO/ГПК, ремейк на Steam)**,
**НЕ для PDM**. Логика PDM = 104 закрытые DLL. Прямой путь «запустить старую игру» через эти скрипты
невозможен; они взяты как ближайший референс по структуре `program/`.

### Новый движок: `C:\corsairs-remake\engine` (fork POMXARK, Storm 2.8)
- Ожидает: `program/*.c` (вся логика), `resource/` (форматы Storm 2), `engine.ini`
- **Не поддерживает загрузку DLL** — механизм MODULES удалён
- Форматы: `.tx`, `.gm`, `.ani` (текстовый INI!), `.an`, `.fx`, `.ptc`, `.col`, `.tga` (fallback, только Windows)

## Рабочая директория `C:\corsairs-remake\korsari-run\`
- `resource/` — копия PDM `RESOURCE/` (7819 файлов)
- `program/` — 920 .c из sd-teho-public (ветка `develop-rus`) — **это скрипты TEHO, не PDM**
- `engine.ini` — модифицирован: `run = seadogs.c`, `program_directory = program`, `run_in_background = 1`, убран `modules path`

## Форматы (репо AlexKimov/seadogs-file-formats → `C:\corsairs-remake\seadogs-file-formats`)

### Соответствие PDM ↔ Storm 2
| PDM | Storm 2 | Примечание |
|---|---|---|
| `.tf` (текстура) | `.tx` | бинар → бинар, другой формат |
| `.cff`/`.clf` (модель) | `.gm` | бинар → бинар, другой формат |
| `.ani` (**бинарный**) | `.ani` (**текстовый INI**) | **одно расширение, разные форматы!** |
| `.dlm` (маска острова) | `.zap` | |

### TF.bt (шаблон 010Editor, `templates/010Editor/TF.bt`)
- Заголовок: `UINT Signature = 250698` + `UBYTE Unknown` + `UBYTE Type` (0=RGB5551, 1=RGB565) +
  `UBYTE MipMapCount` + `UBYTE MaskCount` + `UINT Width` + `UINT Height`
- Пиксели — битовые поля RGB565 или RGB5551; мипмапы: размер /2 на каждом уровне

### CFF.bt (шаблон 010Editor, `templates/010Editor/CFF.bt`)
- Вертекс: `UINT16 X,Y,Z,U,V` + `UBYTE R,G,B`; координата = `P_X + X*S_X/32767.0` (нормализованные 16 бит)
- Секция материалов: 9×UINT + `UINT Count` + массив `{UINT TextureIndex, FLOAT, UINT×3}`
- Список текстур: `UBYTE Length` + `char FileName[Length]` (имена .tga внутри модели)

### Официальный конвейер конвертации
- **Модели**: `.cff/.clf` → 3dsMax (плагин `plugins/3dsmax/cff_clf/cff_clf_import.ms`) → экспорт glTF →
  `engine/tools/gltf2gm` → `.gm`
- **Текстуры**: `.tf` → TGA/BMP (Noesis/010Editor) → пайплайн движка → `.tx`
- Правило из `engine/AGENTS.md`: «Export as glTF for the engine, and keep the generation script next
  to the asset as make_<name>.py»

### Файлы-образцы (разобраны)
- PDM `.ani` = **бинарный** (заголовок `10 00 00 00 0B 00 00 00 DC 01 ...` + встроенное имя),
  новый движок парсит `.ani` как текстовый INI (`libs/animation/src/animation_service_imp.cpp`)
- PDM `.cff` содержит имена текстур (например `af_bort.tga`)

## Краш и инструменты отладки

### Символы
- `engine.pdb` **есть** в `build\default\Debug\` — адрес краша можно резолвить
- COFF-таблица символов внутри exe пустая (0 символов) → имена только через PDB

### Sentry (движок шлёт краш-репорты)
- `src/libs/diagnostics/src/lifecycle_diagnostics_service.cpp`: sentry-native + Crashpad
- DSN захардкожен (удалённый сервер разработчиков)
- БД Sentry: `<stash>/sentry-db` (см. ниже про stash)
- Хендлер: `crashpad_handler.exe` рядом с exe (есть в Debug)
- В `_DEBUG`: `sentry_options_set_debug(true)`; `beforeCrash` пишет SEH-инфо в spdlog-логгер "exceptions"

### Логи и пути (src/libs/core/src/storm/engine_settings.cpp)
- `<stash>/Logs/` — `system.log`, `error.log`, `compile.log`
- `<stash>` = `stash_folder` из engine.ini или путь по умолчанию; переопределение: `logs_folder` в engine.ini
- `<stash>/SaveData`, `<stash>/Screenshots`, `<stash>/Cache` (script cache)

### Инструменты на машине (ВАЖНО — обновление!)
- **В PATH компилятора нет, НО VS Build Tools 2019 установлен (MSVC 14.29.30133 = v142)**:
  `C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\MSVC\14.29.30133\bin\Hostx64\x64\`
  → `cl.exe`, `link.exe`, `dumpbin.exe`, `editbin.exe`, `lib.exe` и др. (VS 2017/14.16 тоже есть;
  VS 2022 BuildTools — только MSBuild, без C++)
- **Демохера нет** (cdb/windbg/procdump/kd отсутствуют)
- Python 3.14.0, cmake, Conan 2 — есть
- Сборка движка: `engine/build.bat` → `build.ps1` (один шаг), пресеты CMake

## Разбор краша 0xC0000005 (RVA 0x123E21): методология и инструменты

Как без отладчика локализовать AV-краш по RVA из WER. Всё воспроизводимо.

### Шаг 1. Код исключения + RVA — журнал событий Windows (WER)
```powershell
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderId='Windows Error Reporting'} -MaxEvents 20 |
  Where-Object { $_.Message -match 'engine.exe' } | ForEach-Object { $_.Message }
```
Событие WER (ID 1001) даёт P1..P8. **Правильная раскладка** (проверено по всем ранах):
- P1 = приложение (`engine.exe`), P2 = версия (`2.9.0.1`), P3 = timestamp приложения
- **P4 = код исключения** → `c0000005` (ACCESS_VIOLATION)
- **P5 = RVA в модуле** → `0000000000123e21`
- P6 = модуль (`engine.exe`), P7 = версия модуля, P8 = timestamp модуля

Вывод: **AV, НЕ stack overflow** (оверфолл был бы `C00000FD`) → гипотеза «стек» отброшена. RVA одинаков во всех ранах → детерминированный краш.

### Шаг 2. Секция RVA — `dumpbin /headers engine.exe`
`.text`: VA `0x1000`, size `0xEDB6B4`. RVA `0x123E21` (≈1.2 МБ) **внутри .text** → это код, не данные.

### Шаг 3. Дизассемблирование (что это и как получить)
**Disasm** = обратный перевод машинного кода в ассемблер. Нужен, чтобы по RVA увидеть инструкцию и функцию
(отладчика нет, COFF-символы в exe пустые).
```
dumpbin /disasm engine.exe > C:\temp\opencode\engine_disasm.txt
```
- **513 МБ** текста. `read` не откроет («binary file») → искать через bash/Python (`Select-String`, grep, по строкам).
- Адреса — 16-значные нули: `0000000140123E21:`. Image base = `0x140000000`.
- **VA краша** = `0x140000000 + 0x123E21` = **`0x140123E21`** (НЕ `0x1400123E21` — была арифм. ошибка).
- dumpbin /disasm **печатает имена функций** (mangled C++) строкой-заголовком — COFF содержит точки входа функций.

**Откуда сам `dumpbin`** (происхождение):
- Это **штатный инструмент MS** из комплекта компилятора **MSVC v142 (VS Build Tools 2019)** — того же, которым собирается `engine.exe`. Не ставился отдельно, не сторонний.
- Путь: `C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\MSVC\14.29.30133\bin\Hostx64\x64\dumpbin.exe`
- Версия `14.29.30159.0`, продукт «Microsoft Visual Studio». Флаг `/disasm` = встроенное дизассемблирование (без PDB, без стеков).

### Шаг 4. Инструкция и функция (поиск `0000000140123E21`)
```
?EqMultiply@CMatrix@@QEAAXAEBV1@0@Z:            ; строка 296515 (функция)
  0000000140123DF0: ...                          ; пролог: spill r8/rdx/rcx в [rsp+*]
  0000000140123E26: F3 41 0F 10 04 00           movss xmm0, [rdx+rax]   ; m1 — OK
  0000000140123E27: F3 41 0F 59 04 08           mulss xmm0, [r8+rcx]    ; ← КРАШ (AV)
```
Demangle → **`CMatrix::EqMultiply(const CMatrix &m1, const CMatrix &m2)`**.

### Шаг 5. Сопоставление с исходником — `engine/src/libs/math/include/matrix.h:475`
```cpp
// this = m1*m2, (m1 != this, m2 != this)
inline void CMatrix::EqMultiply(const CMatrix &m1, const CMatrix &m2)
{
    matrix[0] = m2.matrix[0] * m1.matrix[0] + ...   // строка 477
```
`mulss [r8+rcx]` при rcx=0 = чтение **`m2.matrix[0]`**. `m1.matrix[0]` (`movss [rdx+rax]`) прочиталось, а `m2` упало →
**второй операнд `m2` — NULL/дangling указатель** (use-after-free / null-deref при умножении 4×4 матриц).

### Интерпретация и оставшиеся вопросы
- Краш = умножение двух 4×4 матриц, **m2 невалиден**. Момент: загрузка островов → вероятно use-after-free
  матрицы трансформации (node/locator/geometry), удалённой или неинициализированной.
- `EqMultiply` вызывается из ~30 мест (node.cpp:114/202, bone.cpp:167/209, animation_imp.cpp, sea.cpp:1498,
   location.cpp, foam.cpp:111 и др.). **Точный caller требует стека вызовов** (см. «Следующие шаги»).

## Инструменты анализа бинарников (референс): что мощнее `dumpbin`

Найдено в поиске/GitHub. Приоритет под нашу задачу: **получить стек вызовов из minidump по `engine.pdb`**
и декомпилировать, кто передаёт невалидный `m2`.

### Дизассемблеры / декомпиляторы (статика)
- **Ghidra** (NSA, бесплатно, open-source) — github.com/NationalSecurityAgency/ghidra. Декомпилятор (C-like), скриптинг. Лучший free-вариант для статического анализа.
- **IDA Pro / IDA Free** (Hex-Rays) — hex-rays.com. Эталон дизассемблера; есть IDA Free, декомпилятор (Hex-Rays decompiler) в Pro. Умеет грузить PDB.
- **radare2 / rizin** (open-source; CLI + GUI «Cutter») — github.com/radareorg/radare2, github.com/rizin-sec/rizin. Быстрый, скриптуемый.
- **CFF** (бесплатный x86/x64 декомпилятор) — github.com/maltez/CFF.

### Динамическая отладка
- **x64dbg** (open-source, GUI-отладчик) — github.com/x64dbg/x64dbg. Живая отладка: брейкпоинты, стеки/регистры в реальном времени (то, чего нет в статике).

### Разбор minidump + PDB (НАШ ПУТЬ)
- **WinDbg Preview** (Microsoft, бесплатно, GUI+CLI) — learn.microsoft.com/windows-hardware/drivers/debugger. `!analyze -v`, `.sympath+ <путь к engine.pdb>`, полный стек, регистры, память. **Именно под это и делаем minidump.**

### Просмотрщики PE / ресурсов / DLL
- **PE-bear** (open-source, Qt GUI) — github.com/hasherezade/pe-bear. Заголовки, секции, импорты/экспорты, ресурсы, disasm (Capstone). Быстрый «первый взгляд» по DLL/exe.
- **Resource Hacker** (freeware) — angusj.com/resourcehacker. Ресурсы PE: иконки, диалоги, строки, .res/.mui — просмотр/извлечение.
- **ExeSpy** (open-source, кроссплатформенный) — github.com/andyjsmith/Exe-Spy. Заголовки, секции, импорты/экспорты, ресурсы, манифест, x86/x64 disasm.

**Рекомендация под нашу задачу:** (1) **WinDbg Preview** + `engine.pdb` — открыть minidump и снять стек краша;
(2) **Ghidra** (или IDA) — декомпилировать `CMatrix::EqMultiply` и вызывающий код, чтобы понять, кто передаёт невалидный `m2`;
(3) **PE-bear / Resource Hacker** — если нужно глянуть ресурсы/секции DLL PDM.

## Следующие шаги
1. **Резолвить RVA 0x123e21**: `dumpbin /disasm` вокруг адреса и сопоставить со исходниками (Debug-сборка,
   без оптимизаций — функции узнаваемы); либо пересобрать движок с FASTLINK-символами в самом exe
2. **Пересобрать движок** (`build.bat`) — получим цикл «инструментация → сборка → тест» и точные символы
3. Найти минидамп в `<stash>/sentry-db` (уточнить stash для korsari-run)
4. После фикса краша → запустить движок → **меню** (вероятно, нативное меню движка или `seadogs.c`)
5. Конвертеры форматов (.tf→.tx, .cff→.gm через 3dsMax/glTF, .ani бинар→INI) — после запуска

## Ссылки
- `C:\corsairs-remake\docs\GUIDE.md`, `docs\RESEARCH.md` — исходные обзоры
- `C:\corsairs-remake\engine\docs\ru\02-game-layout.md`, `03-scripting.md`, `04-formats.md`
- `C:\corsairs-remake\sd-teho-public\` (develop-rus) — скрипты TEHO как референс
- `C:\corsairs-remake\seadogs-file-formats\` — форматы Storm 1/2, шаблоны 010Editor, плагины 3dsMax
- `https://github.com/AlexKimov/seadogs-file-formats`

---

# ИТОГИ (обновление: состояние на текущий момент)

## Что сделано

### 1. Краш движка устранён
- Причина: null-ссылка в `MODELR::Update()` — модель без загруженной геометрии.
- Фикс: null-guard `if (root == nullptr) return;` в `engine/src/libs/model/src/model.cpp`.
- Результат: движок работает 30+ секунд без падений, доходит до инициализации меню.

### 2. Формат .gm полностью расшифрован
- Все структуры подтверждены по исходникам (`rdf.h`, `geom_static.cpp`):
  - RDF_HEAD (72B), RDF_LABEL (108B), RDF_OBJECT (104B), RDF_TRIANGLE (6B), RDF_MATERIAL (56B)
  - Порядок чтения: HEAD → globname → names → tname → materials → lights → labels → objects → triangles → vbuffs → vertices
  - `names`/`group_name` — байтовые смещения в строковую таблицу globname
- Шаблон: `engine/demos/model/resource/models/demo/crate.gm` (1232 байт) — проверен, грузится без ошибок.
- Инструменты: `tools/gm_inspect.py` (парсер/инспектор .gm), `tools/gm_gen_locators.py` (генератор).

### 3. Сцена главного меню создана
- `korsari-run/resource/models/MainMenu/MainMenu.gm` — копия crate.gm (1232B).
- `korsari-run/resource/models/MainMenu/MainMenu_locators.gm` — сгенерирован (1397B), 11 локейторов:
  - camera: P=(0,0,-10), углы (0,π,0) — камера смотрит на z=0
  - menu02..menu07: (0, 1.5..-1.0, 0), шаг 0.5
  - Light (0,2,-5), fonar (-3,0,-5), fire (3,0,-5), seagull (0,2,-8)
- Матрицы: `lbl.m[3]` = трансляция, вращение в m[0..2]; BuildMatrix/GetAngles верифицированы как точные инверсии.
- ntriangles=1 с dummy {0,0,0} — обход edge case CreateIndexBuffer(0).

### 4. Цепочка запуска прослежена до конца
- `seadogs.c:Main()` (строка ~270) → videoIdx цепочка → `Main_LogoVideo` → default case → `Main_Start` → `InitGame()` + `LaunchMainMenu()` (строка 393).
- **Видео НЕ blocker**: .wmv отсутствуют, но `CAviPlayer::PlayMedia` при неудаче шлёт `ievntEndVideo` → цепочка сама проходит все case'ы.
- **InfoHandler падает, но НЕ фатально**: `D3DERR_INVALIDCALL` в `GetRenderTargetData` (s_device.cpp:3959) → сущность не инициализирована → скрипт продолжает.
- «Progress error!» = `StartProgressView()` (s_device.cpp:4250) не находит `resource\Loading\progress.tga` — каталог `Loading` отсутствует в resource/.

### 5. Окружение и инструменты
- Рабочая директория `korsari-run/`: resource/ (7819 файлов), program/ (920 .c из TEHO), engine.ini.
- 64 синтетических TGA-кадра моря в `resource/sea/` — инициализация воды проходит.
- Сборка: `engine/build.ps1` (VS Build Tools 2019, MSVC v142). Бинарь: `build/default/Debug/engine.exe` (36 МБ).
- Лог: `%USERPROFILE%\Documents\My Games\Sea Dogs\Logs\system.log` (кольцевой буфер, ровно 20 КБ — хвост срезается).

## Что не сделано (блокеры)

### Блокер 1: Шрифт (критично для видимости меню)
- `Not Found Texture: fonts\interface normal font rus.tga` → «Can't init font interface_normal» → «can not init start font».
- В демках движка .tga шрифтов нет вообще (glob пуст). Источников загрузки шрифтов в engine/src grep не нашёл.
- Нужно: найти путь загрузки шрифта в C++ (xinterface/renderer), либо создать синтетический TGA-шрифт.

### Блокер 2: Placeholder-модели меню (13 файлов)
- `menu02..menu07_active.gm`, `menu02..menu07_passive.gm` + `seagull.gm` — не созданы.
- Решение принято: копировать crate.gm под каждым именем в `resource/models/MainMenu/`.

### Блокер 3: `Can't load texture r` (каждый кадр)
- Имя текстуры буквально «r» → путь `resource\textures\r.tx` → файл отсутствует.
- Источник НЕ найден: grep по `TextureCreate("r")`, `"r.tx"`, `name = "r"` в engine/src, libs/sea — пусто.
- Вероятно: sea/water рендер или InfoHandler feedback-текстура. Требуется расширенный поиск (создание текстуры по имени из кода, не литерала).

### Блокер 4: `resource\Loading\progress.tga`
- Каталог `Loading` отсутствует → «Progress error!» в логе. Не фатально, но требует создания каталога + синтетического TGA.

## Следующие шаги
1. **Краш `CMatrix::EqMultiply` (критично, блокирует всё до меню)** — получить точный caller:
   - Вариант A (надёжный): `MiniDumpWriteDump` в `main.cpp` (расширить SEH-хендлер на AV) + `dbghelp.lib` → minidump → полный стек по `engine.pdb`.
   - Вариант B: анализ исходников (node.cpp / locator / geometry) — какая матрица невалидна при загрузке островов.
2. Скопировать crate.gm под 13 имён (menuNN_active/passive + seagull) в `resource/models/MainMenu/`.
3. Создать `resource/Loading/progress.tga` (синтетический TGA) — убрать «Progress error!».
4. Найти источник текстуры «r» (поиск по sea-библиотеке, render-target feedback).
5. Разобраться со шрифтом: путь загрузки в C++ / синтетический TGA-шрифт.
6. Запустить движок → проверить в system.log загрузку MainMenu.gm и позицию камеры.
7. Обновить этот файл после запуска.

---

# ИТОГИ (обновление: crash handler + stack capture)

## Что сделано

### 1. Crash-хендлер в main.cpp (SEH → minidump + стек)
- `crash_dump_handler()` в `engine/src/apps/engine/src/main.cpp`:
  - `SetUnhandledExceptionFilter(crash_dump_handler)` — перехватывает ВСЕ исключения (в т.ч. AV 0xC0000005).
  - `CaptureStackBackTrace(0, 64, stack, nullptr)` → сырые return-адреса в `crash_stack.txt`.
  - `MiniDumpWriteDump(..., MiniDumpWithFullMemory | MiniDumpWithThreadInfo, ...)` → `crash.dmp` (585 МБ).
  - Ограничения MSVC SEH: только фиксированные `wchar_t[]` буферы, без C++ объектов с деструкторами, без аллокаций в `__try`.
- `dbghelp.lib` уже был в `SYSTEM_DEPS` (CMakeLists.txt строка 12) — изменения CMake не потребовались.
- Sentry в нашей сборке полностью отключён (`STORM_ENABLE_CRASH_REPORTS` не задан).
- Сборка прошла, краш воспроизведён: exit code -529697949 (AV), файлы созданы.

### 2. Стек вызовов получен: 36 фреймов в crash_stack.txt
- Формат: `frames=36\nframe[N]=XXXXXXXXXXXXXXXX\n` (hex без 0x, 16 цифр).
- Кластеры: движок — `0x7FF752xxxxxx`..`0x7FF753xxxxxx` (фреймы 0, 9-33), системные DLL — `0x7FFE6xxxxxxx` (фреймы 1-8, 34, 35).
- **Взаимная рекурсия**: фреймы 14-22 чередуются `0x7FF75370D43B` ↔ `0x7FF7537122D6` (Δ=0x4E9B) — две функции вызывают друг друга.
- **Первый реальный фрейм движка в стеке: frame[9] = 0x7FF752FCACC6** (после системных dispatch-фреймов 1-8).

### 3. Функция краша подтверждена
- `CMatrix::EqMultiply(const CMatrix&, const CMatrix&)` — matrix.h:475.
- Инструкция краша: `mulss xmm0, [r8+rcx]` = чтение `m2.matrix[0]` → **m2 — NULL/dangling**.
- VA краша: 0x140123E21, image base: 0x140000000, RVA: 0x123e21 (детерминировано во всех 5 прогонах по WER).
- В дизассембли: 32 прямых `call` через ILT-стаб `@ILT+117235(?EqMultiply@CMatrix@@QEAAXAEBV1@0@Z)`.

### 4. Инструменты
- **Ghidra 12.1.4 + JDK 21 + GhidraMCP** установлены и проверены (headless import engine.exe прошёл).
- MCP-конфиг: `engine/opencode.json` + глобальный `~/.config/opencode/opencode.json` — entry "ghidra" добавлен.
- **ТРЕБУЕТСЯ ПЕРЕЗАПУСК opencode** для активации ghidra MCP tools.
- Дизассембли dumpbin: `C:\temp\opencode\engine_disasm.txt` (513 МБ, **UTF-16LE**, 3 633 490 строк).

## Что не получилось / проблемы

### 1. module_base отсутствует в crash_stack.txt
- Edit в main.cpp (`GetModuleHandleW(nullptr)` → `module_base=%p`) применён, сборка прошла (engine.exe 19.10.2026 8:04:11), но в runtime-файле строки НЕТ.
- Возможные причины: выполнен не тот бинарь, кэш сборки, или edit не сохранился до build. Требуется диагностика.

### 2. crash.dmp деградирован
- ModuleList: size=0, rva=0 (пустой). Version field = 0xA05DA793 (нестандартный). Нет ThreadList.
- MiniDumpWriteDump не смог корректно записать модули/потоки (причина неясна — возможно ограничение SEH-контекста).
- Из дампа base извлечь нельзя → определять только через crash_stack.txt или дизассембли.

### 3. Прямое сопоставление call-site НЕ сработало
- Для frame[0]=0x7FF752F3B04B ни один из 32 прямых `call` не даёт page-aligned base.
- Интерпретация: frame[0] — не return от прямого вызова EqMultiply (возможно, tail call / inlined wrapper / другой контекст).

## Следующие шаги (приоритет)

1. **Определить ASLR base** — два пути:
   - (a) Починить запись `module_base` в main.cpp и перезапустить движок (прямой путь).
   - (b) Вычислить: для frame[9]=0x7FF752FCACC6 перебрать все `call @ILT+117235(...)` в дизассембли, `implied_base = frame[9] - ((call_VA + 5) - 0x140000000)`, проверить консистентность по всем engine-фреймам.
2. **Резолвить RVA всех 25 engine-фреймов** (приоритет frames 9-24, особенно парная рекурсия 14-22).
3. **Идентифицировать caller chain** — кто вызвал EqMultiply с невалидным m2; сопоставить с 53 source-level call sites.
4. **Запустить GhidraMCP** (после перезапуска opencode) — декомпиляция рекурсивной пары и caller'ов.

## План: см. `docs/debug-plan.md`
