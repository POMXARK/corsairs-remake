# Обзор: форки Storm Engine и похожие проекты (октябрь 2026)

Данные: GitHub API (форки и коммиты) + веб-поиск, 14.10.2026.

## Форки движка

| Репозиторий | Активность | Что внутри | Вывод |
|---|---|---|---|
| [storm-devs/storm-engine](https://github.com/storm-devs/storm-engine) | архив с 29.04.2024 | оригинал, GPL-3.0, DX9, Conan 1.59 | только как точка отсчёта |
| **[PiratesAhoy/storm-engine](https://github.com/PiratesAhoy/storm-engine)** | коммиты до янв. 2026, push июль 2026, 25★ | ведёт Hammie (мейнтейнер storm-devs); **Conan 2**, рефакторинг сервисов, исправления крашей (пена, небо, сжатые текстуры), call-stack из скриптов, бета-релизы через CI | **фактический преемник — брать за основу** |
| [WillTer/storm-engine](https://github.com/WillTer/storm-engine) | май–дек. 2025 | SDL3, OpenAL вместо старого звука, звук в отдельном потоке, рефакторинг файловой системы и сборки | интересные идеи для переноса (SDL3/OpenAL); один автор |
| [CaptainsHaven/storm-2.8-dx9-NH](https://github.com/CaptainsHaven/storm-2.8-dx9-NH) | янв.–апр. 2026 | Storm 2.8 на DX9 под New Horizons: оптимизации, утечки памяти, висячие указатели | движок NH: Refined Edition |
| [Konstrush/recon-storm-engine](https://github.com/Konstrush/recon-storm-engine) | до авг. 2025 | движок ReCon Team: геймплейные/интерфейсные правки | связан с командой Caribbean Legend |
| [q4a/Typhoon-Engine](https://github.com/q4a/Typhoon-Engine) | старт май 2026 | один энтузиаст переписывает Storm с нуля со слоем совместимости | очень ранняя стадия |

**Vulkan / DX12 / bgfx / RT-форков не найдено.** Переход на bgfx так и остался пунктом roadmap. Рендер везде — DirectX 9.

## Игры и большие моды

- **Caribbean Legend: Age of Pirates** — вышла в Steam 13.03.2026; ReCon Team + BlackMark Studio; ремастер «Города потерянных кораблей»: новое управление и интерфейс. Движок предоставлен BlackMark; обзоры называют главным минусом **устаревший движок**. ([пресс-релиз](https://www.gamespress.com/uk-UA/Caribbean-Legend-Age-of-Pirates-Launches-Today-on-Steam), [DTF](https://dtf.ru/games/4843057-caribbean-legend-stoit-li-igrat-fanatam-korsarov))
- **New Horizons: Refined Edition** — standalone-мод PotC (2026), «сильно модифицированный» Storm 2.8, DX9. ([GameWatcher](https://www.gamewatcher.com/news/new-horizons-refined-edition-standalone-mod-pirates-of-the-caribbean))
- **Корсары ГПК: Реконструкция** (ReCon) — на Storm Open Source, упор на стабильность.
- Ремастер «Возвращение легенды» обсуждается на [Seaward.ru](https://www.seaward.ru/forum/index.php?showtopic=14625&mode=linear); со слов участника форума, Unreal 5 не планируется.
- **Фанатских ремейков «Корсаров» на UE5/Unity не найдено** (для сравнения, такие есть у Far Cry, NFS Underground 2, P.T.).

## RTX Remix

Remix рассчитан на DX8/9 с **fixed-function** пайплайном. Storm использует шейдерные техники (`.shd`), значит совместимость под вопросом: игры с программируемыми шейдерами (пример — F.E.A.R.) обычно падают. ([документация](https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/1.2.4/docs/introduction/intro-compatibility.html)) Проверить за вечер, но не рассчитывать.

## Куда «пропал» редактор — разбор исходников (клоны в `remake/storm-engine`, `remake/captain-blood`)

### Storm 2.x (Корсары) — встроенного редактора никогда не было
Инструменты Акеллы были **внешними**, остатки лежат в `storm-engine/tools/`:
- `maya-plugin/`, `maya5.0-exporter/` — экспорт моделей/анимаций из Maya (исходники C++);
- `model-view/gm_view.exe`, `animation-view/aniview.exe` — просмотрщики (Borland C++ Builder/VCL 6, без исходников);
- `modding-tool/TOOL.exe` — **фанатский** .NET-инструмент PiratesAhoy (gm ⇄ VRML, скелеты, локаторы, анимации);
- blender-плагины gm/an/ptc (Python, современные, от сообщества);
- `docs/`: `particle-editor.doc`, `Редактор пены.txt`, `Lighter.doc` — описания утилит.

**Сюрприз:** `tools/particles-editor/` — это бинарники **Storm Engine 3.0** от 16.08.2005 (`ENGINE.exe` → строка `Storm Engine 3.0`, pdb `c:\Projects\Drive_v3\Engine\...`), внутри `missioneditor.dll`, `SoundEditor.dll`, `GUI_Manager.dll`, `DX8Render.dll`. То есть редактор частиц для Корсаров брали из следующего поколения движка.

### Что уже есть в современном форке
`storm-engine/src/libs/editor/` — **ImGui-оверлей «Developer Tools»** (добавлен ~январь 2024, автор Hammie, 135 строк):
- меню Tools: окна **Entities** и **Sound Service** (регистрируются в `src/libs/core/src/core_impl.cpp:125-137`);
- меню Debug: wireframe, sound/location/cannon debug (флаги читают `s_device.cpp:2782`, `location.cpp:1014`, `ai_ship_cannon_controller.cpp:559`, `sound_service.cpp:1256`);
- API `EngineEditor::RegisterEditorTool(title, callback)` — **точка расширения**: новые окна добавляются одной регистрацией.
- ImGui с docking, DX9 + SDL2 backend (Linux — только SDL).

→ Начинать свой редактор надо **отсюда**, а не с нуля.

### Storm 3.0 — «потерянный» редактор найден
Репозиторий **[storm-devs/captain-blood](https://github.com/storm-devs/captain-blood)** — полный исходный код движка Storm 3.0 (`DRIVE_V3.sln`, ~650 тыс. строк C++) игры «Age of Pirates: Captain Blood» (1C: Seawolf Studio, руководитель Sergey Makeev). **GPL-3.0**, выложен в ноябре 2022, коммит «Make the game build compilable & runnable using VS2022» (03.06.2024). Ресурсы: «only bare minimum provided — to be able to run editors».

| Модуль | Что это | Строк |
|---|---|---|
| `MissionEditor/` | **встроенный редактор уровней**: переключение F1 игра ⇄ редактор, дерево объектов, панели атрибутов (float/color/position/rotation/enum/locstring…), move/rotate-гизмо, fast preview, импорт, интеграция с VSS | 25k |
| `Editors/anxeditor/` | **граф анимаций** (узлы, связи, события, undo/redo, мастер-скелет) | ┐ |
| `Editors/SoundEditor/` | редактор звуковых банков | │ 68k |
| `Editors/RagDollED/` | редактор рэгдоллов (PhysX) с гизмо | │ |
| `Editors/ForceEditor/` | редактор кривых сил | ┘ |
| `Particles/editor/` | редактор частиц | 21k |
| `common_h/gui/` | своя GUI-библиотека (окна, деревья, списки, диалоги) | — |
| `ArcadeSea/` | **морской бой**: корабли, повреждения по частям, баллистика, **`Ocean3` — FFT-океан** (`fft.cpp`, `fft_sse.cpp`) | 38k |
| `ThirdParty/` | D3D9, **PhysX 2.8.1** | — |

Запуск редакторов — через ini: `Build/mission.ini` (`load class = MissionEditor`), `AnxEditor.ini`, `pedit.ini`, `RagDollED.ini`, `soundeditor.ini`.
45 форков, заметной активности нет — **сообщество им почти не занимается**.

### Выводы по редактору
1. Для Storm 2.x путь — расширять существующий ImGui-оверлей (`RegisterEditorTool`).
2. Из Storm 3.0 можно **переносить идеи и код** (обе GPL-3.0 — совместимы): структура MissionEditor (атрибуты/формы/гизмо), граф анимаций AnxEditor (= то, чего не хватает Корсарам для плавных анимаций), FFT-океан Ocean3, разрушение корабля по частям.
3. Альтернатива покрупнее: Storm 3.0 сам по себе ближе к «Black Flag» — у него есть и ближний бой (Captain Blood — слэшер), и морской бой с FFT-водой, и PhysX, и редакторы. Но ресурсов «Корсаров» он не понимает.

### Где использовался Storm 3.0
- Официальная история storm-devs: «версия 3.0 так и не вышла, проект заброшен; часть наработок влили в 2.x по мере выхода игр».
- Фактически ветка `Drive_v3` / «Storm Engine 3.0» стала движком **Captain Blood** (SeaWolf Studio, отделилась от Akella; 1C). Игра 10+ лет была в «аду разработки», доделана General Arcade, издана SNEG **6 мая 2025** (PC, PS4/5, Xbox, Switch); Metacritic PC 50/100.
- В «Корсары» попал как минимум редактор частиц (бинарники 2005 г. в `storm-engine/tools/particles-editor`).
- В Storm 2.8 («ГПК») по истории движка был **встроенный редактор** (тулбар для правки персонажей и локаций). В открытом коде остались следы: режим `editorMode` у `ShipWalk` (`src/libs/sailors/src/sailors.cpp:743`) и шейдерные техники `EditorBack/EditorFront`; флаг `--editor` в `src/apps/engine/src/main.cpp:129` сейчас включает ImGui-оверлей.

## Перенос Корсаров (Storm 2.x) на Storm 3.0 — почему не стоит

| Проблема | Storm 2.x (ККС) | Storm 3.0 (Captain Blood) |
|---|---|---|
| **Игровая логика** | ~18 МБ скриптов на собственном C-подобном языке (`sd-teho-public`), VM в движке (`src/libs/core/src/compiler.cpp`, 8 тыс. строк) | скриптовой VM нет; логика — C++-классы `MissionObject` + миссии из MissionEditor |
| **Объектная модель** | entity + атрибуты + `SendMessage` по именам классов (SEA, SHIP, LOCATION…) | `MissionObject` + `MOParams` |
| **Форматы** | `.gm`, `.an`, `.tx`, `.ptc`, локаторы в `.gm` | `.gmx`, `.anx`, `.txx`, `.mis` |
| **Платформа** | x64, CMake + Conan, SDL2, CI, начат Linux | только Win32 (41 проект), ветки под Xbox 360 (~356 файлов), inline asm (15 файлов), `.vcxproj` |
| **Зависимости** | современные (fmod, SDL, imgui) | PhysX 2.8.1 (давно не поддерживается), ссылки на StarForce SDK, CAProfAPI, Visual SourceSafe |
| **Жанр** | песочница: глобальная карта, торговля, квесты | линейный слэшер + аркадный морской бой |
| **Сообщество** | все моддеры | почти никого |

Перенос = переписать всю игру (или портировать VM скриптов и все entity-классы Storm 2 в Storm 3 — по сути слить два движка), плюс 64-бит, замена PhysX и чистка Xbox/DRM. Это годы.

**Правильный путь — выборочный перенос модулей из 3.0 в 2.x** (обе GPL-3.0):
1. `ArcadeSea/Ocean3` (FFT-океан) → новый entity моря в Storm 2 под флагом. Самый эффектный и изолированный кусок.
2. Идеи `MissionEditor` (атрибуты/формы/гизмо) → окна ImGui-оверлея через `RegisterEditorTool`.
3. `AnxEditor` (граф анимаций) → основа для плавных переходов анимаций персонажей.
4. Разрушение корабля по частям (`ArcadeSea/ships`) — позже.

## Что это значит для проекта

1. **Ниша свободна:** сообщество чинит стабильность и геймплей, а **современный рендер, редактор и ИИ-пайплайн ассетов не делает никто**. Именно это и есть твой вклад.
2. Основа — **форк PiratesAhoy/storm-engine** (живой, Conan 2, CI). Изменения, полезные всем (фиксы, логирование, ImGui-инструменты), отправлять туда PR — это open-source вклад в резюме.
3. Из WillTer можно перенять SDL3/OpenAL, если пойдёшь в Linux-порт.
4. Связаться с сообществом до больших работ: Discord storm-devs (ссылка в README), форум [PiratesAhoy](https://www.piratesahoy.net), Seaward.ru. Спросить, не делает ли кто-то уже рендер/bgfx.

## Совместимость 2.x ↔ 3.0 (замер по коду)

Метод: одноимённые файлы (66 пар из 801/1743), токенное сходство (difflib) без комментариев.

| Модуль | 2.x (storm-engine/src) | 3.0 (captain-blood) | Сходство | Вывод |
|---|---|---|---|---|
| SSE-хелперы | libs/sea/src/sse.h | ArcadeSea/sea/SSE.h | 0.96 | почти копия |
| Кватернион, плоскость | libs/math/include/math3d/* | common_h/math3d/* | 0.80 | общий предок |
| Вектор | math3d/vector.h | common_h/math3d/Vector.h | 0.63 | общий предок, расширен |
| Частицы (эмиттеры, data_desc) | libs/particles | Particles/system | 0.67–0.72 | общий предок; .xps-система та же по архитектуре |
| Частицы (bb_processor) | | | 0.22 | рендер переписан |
| Matrix | matrix.h | Matrix.h | 0.14 (ids 0.39) | сильно переписан |
| Паруса, канаты, корабль, море, трава, дождь, небо, персонаж, шрифты | | | 0.01–0.03 | **написаны заново** под MissionObject |
| Атрибуты, скриптовая VM | core/attributes, compiler.cpp | нет | — | VM в 3.0 отсутствует |
| Текстуры | .tx: TX_FILE_HEADER без сигнатуры (renderer/src/texture.h:56) | .txx: TXX_ID 'TXX ', cube/volume (System/XRender/TXX.h) | — | несовместимы, конвертер тривиален |
| Модели | .gm (GEOS) | .gmx (GMXService) | — | несовместимы |
| Океан | sea.cpp (2.x, свой) | ArcadeSea/Ocean3 (fft.h, Ocean.h) | — | новый код, кандидат на перенос |

**Итог:** общая кодовая база ≈ math + particles + мелкие хелперы. Всё, что видит игрок, в 3.0 переписано. Переносить в 2.x имеет смысл только изолированные модули: Ocean3 (FFT), идеи particle-редактора и MissionEditor (в ImGui), AnxEditor.

## Linux-порт Storm 2.x (история)

- **storm-devs/storm-engine#348** (q4a, 03.2022): порт через dxvk-native / Gallium Nine. 05.2022: «игра на Linux очень близка к Windows»; оставалось — нет интро-видео (aviplayer через ddraw/amstream), нет скриншотов F8. Код влит в master, ~113 мест `FIX_LINUX`.
- 2023: PR'ы Linux CI (#472, #475, #512), сборка GCC (#465), Nine (#473); открыт #464 «DXVK вместо DXVK Native».
- **q4a/storm-engine `nine-arm`** — сборка под ARM (не запускалась).
- Ветки upstream `bgfx`, `bgfx-2022` — попытка заменить DX9 на кроссплатформенный bgfx (не влита).
- upstream заархивирован 29.04.2024; PiratesAhoy в 2026 гоняет только Windows CI, `ci_linux.yml` содержит команды Conan 1 при Conan 2.12 → Linux-сборка, вероятно, сломана, но основа рабочая.
