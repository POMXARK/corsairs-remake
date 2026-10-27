---
name: edit-cutscene
description: Править ролик (сцену) вступления «Корсаров» в pdm-game и сверять его с оригиналом — какие файлы менять, как пересобрать, записать и сравнить кадры. Использовать, когда просят поправить воду, камеру, эффекты, свет или осадку кораблей в SceneN.
---

# Правка сцены ролика pdm-game

Рабочая папка `W=/media/roman/383be9ee-c114-4bf8-8956-66b985661cb4/home/remake-linux`, игра `$W/corsairs-remake`, движок `$W/build/Debug/engine`. Установленная игра (источник ассетов) — `$W/../Корсары` (относительно `corsairs-remake`: `../../Корсары`).

## Какие файлы
| Что менять | Файл |
|---|---|
| Данные сцены (ключи камеры, модели, звуки, небо, амплитуда, lift/draft, эффекты) | **не править руками**: `pdm-game/program/data/pdm_cutscenes.c` генерируется конвертером |
| Конвертер .ani → C: словари на сцену `DRAFTS` (высота комнаты), `TILTS` (наклон комнаты → линия моря), `SKIES`, `SUN_DIM`, `NIGHT_DARK`, `WEATHER_OF`, `AMPS`, `NO_SEA`/`CABIN_LIFT` (каюты), `FX_SCENES`/`FX_KINDS` (записи 20/25), `LIFT` | `tools/pdm_cutscene.py` |
| Исполнение сцены: камера (`Cut_Camera`, сплайн Catmull-Rom, `Cut_Smooth` — фильтр 0,5 с, сброс на склейках), волна под корпусами (`Cut_Ride`, 2 ступени фильтра), эффекты (`Cut_Effects`), небо/море/свет в начале сцены, фон `.room` | `pdm-game/program/cutscene.c` |
| Эффекты выстрела/взрыва (xps частиц) | `tools/make_cannon_fx.py` → `pdm-game/resource/particles/{gunflash,shothit}.xps` |
| Атлас частиц из оригинальных `.tf` (огонь, дым, осколки) | `tools/pdm_effects.py` → `pdm-game/resource/textures/particles_list.tga.tx` |
| Небо haze | `tools/make_haze_sky.py` |
| Документация находок | `docs/pdm-cutscenes.md`, `docs/pdm-water-original-vs-modern.md`, `docs/ru/*` |

Оригинальные ассеты (`pdm-game/resource`) в git не коммитить — они конвертируются из установленной игры.

## Цикл правки одной сцены
1. Найти эталон: планы оригинала `scratchpad/orig/shotNN.mp4` (номер плана ≠ номер сцены: Scene1 = `shot02`, Scene7 = `shot14`) или полное видео `$W/2026-10-27 17-54-36 (online-video-cutter.com).mp4`.
2. Править **источник**: словарь в `tools/pdm_cutscene.py` (данные) или `cutscene.c` / `tools/make_*.py` / `pdm_effects.py` (поведение). Затем перегенерировать:
   - `python3 -I tools/pdm_cutscene.py "$PWD/../../Корсары" pdm-game` (данные сцен; в run.sh вызывается только если нет `PdmCut.intro`);
   - `python3 -I tools/pdm_effects.py "$PWD/../../Корсары" pdm-game/resource` (атлас);
   - `python3 -I tools/make_cannon_fx.py pdm-game/resource` (системы частиц).
3. Записать одну сцену (фон, без нажатий клавиш): `cd pdm-game; SCENE=cutscene-sceneN timeout 300 ./shots.sh ../../build/Debug/engine <НОВЫЙ каталог в scratchpad> 31 12` (параметры: сколько секунд ждать и сколько кадров-превью). Каталог брать новый — `rm` с glob в scratchpad блокируется защитой.
4. Проверить `~/.local/share/Akella/Sea Dogs/Logs/error.log` — должен быть пуст (`grep -ci error`).
5. Сравнить кадры через ffmpeg: `ffmpeg -ss T -i … -frames:v 1 -vf scale=800:450`, пары оригинал|моё через `hstack`, сетка `fps=N/длит,tile=Nx1`. Время записи сцены ≈ время плана + сдвиг (подбирать по кадрам). Смотреть изображение, не угадывать.
6. Показать пользователю, спросить «ок / замечания» и только потом идти к следующей сцене. Гавань (Scene1–3) без просьбы не трогать.

## Что искать, если «не как в оригинале»
- **Эффекты** — записи .ani: тип 20 = `canclouds` (выстрел, x,y,z + углы), 25 = `explosion_x` (взрыв), 13 = звук; единицы как у ключей камеры (×K=2.3 + lift). Размеры системы масштабировать под расстояние до камеры (дальний борт ≈13 ед. → клубы ≈0.5).
- **Вода/осадка** — `amp` (из `sea_amplitude` записи ×125, или переопределить в `AMPS`), `draft` (отрицательный — корпус глубже), `lift` (модели и камера над нулём моря).
- **Дёргание** — фильтры в `Cut_Smooth`/`Cut_Ride`; снап фильтра только на настоящих склейках (`Cut_IsJump` между ключами), не по отставанию.
- **Каюта** (`NO_SEA`): без моря, lift=`CABIN_LIFT`, фон `.room` тёмный.
- **Флаги** едут с кораблём, если привязаны к кости группы (`RIDE_GAP`/`RIDE_TRAVEL`, `FAR_FLAG_SCALE`); линия моря в окне каюты — только `TILTS`; подробности в `docs/pdm-cutscenes.md` («Настройка сцен»).
- Ловушки скриптов Storm: `a && (b…)`, имя define = имя функции другого регистра, перенос строки с атрибутами.

## Фиксация
Коммит/push/bump submodule — только по просьбе (правила проекта): сообщение на английском (`feat:`/`fix:`, пункты `- файл — что — почему`, блок `Tests:`), push в `origin` (corsairs-remake), движок — в `fork`.
