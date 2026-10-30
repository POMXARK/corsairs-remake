# Автотесты и записи

Как Claude проверяет каждый этап переноса: автотест играет сцену сам, итог читается из логов, видео пишется без нажатий и проверяется по кадрам. Готовые сценарии и их ожидаемые логи — в [test-commands.md](test-commands.md); здесь — как это устроено и какие команды идут подряд.

## Как устроен автотест

1. `pdm-game/run.sh` пишет переменные запуска в `program/data/start.c`:
   ```c
   string StartScene = "battle";   // SCENE=…
   int TownAuto = 7;               // TOWN_AUTO=…, 0 — обычная игра
   ```
2. `main.c` открывает сцену по `StartScene`, сцена смотрит на `TownAuto`: при 0 управляет игрок, иначе — сценарий.
3. Сценарий — цепочка событий: обработчик делает шаг и ставит следующий через `PostEvent("<событие>", <мс>)`. Например, в городе `Town_AutoGo` → `Town_AutoWhere` → `Town_AutoTalk` → `Town_AutoQuit`, в бою — ATTACK для SEA_AI и `Battle_AutoLimit` через 200 с.
4. Клавиатура и мышь не трогаются. Где игроку нужна клавиша, автотест вызывает тот же обработчик или шлёт то же сообщение, что и клавиша (`Map_Click` вместо клика по карте, `MSG_BATTLE_LAND_MAKE_COMMAND` вместо Tab). Так тест не мешает работать за компьютером: xdotool для игры не используется.
5. Каждый значимый шаг пишет `Trace("PDM: …")` в `compile.log`. Последняя строка — `PDM: autotest done, …`, затем `ExitProgram()`. Сцена без явного конца получает лимит времени (бой — 200 с, `time is up` с итогом обоих кораблей).

Новый автотест:
1. Свободный номер `TOWN_AUTO` (список — в test-commands.md).
2. `if (TownAuto == N)` в начале сцены: что поставить и какое событие запустить.
3. Обработчики шагов, `SetEventHandler` при создании сцены, `DelEventHandler` при выходе.
4. Трассы с числами, по которым видно, что механика сработала (корпус, паруса, команда, координаты), а не только «шаг пройден».
5. Строка в таблицу test-commands.md: что делает тест и какие строки лога ждать.

## Что делает каждый сценарий

Каждый сценарий — строка `pdm-game/autotest/scenarios.txt`; новый тест добавляется сюда и в этот список (одна строка: что делает и по какому маркеру считается пройденным).

| Сценарий | Что делает | Маркер |
|---|---|---|
| `story` | прогоняет все сюжетные действия и диалоги без графики (`Story_SelfTest`) | `PDM story test: … actions run` |
| `screens` | обходит страницы экранов (торговля, верфь, настройки…) таймером `Screen_Tour` | `PDM trade: bought` (**сейчас FAIL**, маркер не появляется, разобраться) |
| `town-tavern` / `town-talk` / `town-quest` | таверна, разговор с NPC, взятие квеста в городе | `PDM town: autotest done` |
| `town-land` | высадка и ходьба по городу Highrock | `PDM town: autotest done` |
| `town-face` | лица NPC при разговоре (камера на лицо) | `PDM face: autotest done` |
| `sea-out` / `sea-port` / `sea-map` | выход в море, возврат в порт, переход на карту мира | `PDM: sea …` |
| `battle-fire` / `battle-board` / `battle-sail` / `battle-fort` | залп, абордаж, парусная погоня, бой с фортом | `PDM: autotest done, battle…` |
| `save-sea` | автосохранение в море и загрузка его обратно | `PDM: autotest done, save` |
| `shipyard-screen` | `SCENE=town`, `TOWN_AUTO=19`, Хайрок: идёт к верфи, говорит с владельцем (Бишоп), выбирает ответ «верфь» (`PdmA_SHIPYARD`), экран открывается как в игре; проверяет значения узлов `S_*` и название/описание корабля (`Screen_ShipyardCheck`, `screens.c`). Новая игра и ролик не запускаются. Затем жмёт кнопки: «Купить» (отказ: старый корабль не продан), «Продать» (деньги +B), «Купить» (деньги −A, тип сменился); затем «Полностью» чинит полуразбитый корпус и паруса за нашу цену; значения проверяет скрипт, не пиксели | `PDM shipyard: repair ok` (до него `values ok`, `actions ok`) |
| `save-screens` | то же через страницы «Сохранить»/«Загрузить» | `PDM: autotest done, screens` |
| `options-sea` / `options-close` | смена разрешения на странице «Настройки» (из меню и над живой сценой) | `PDM options: …`, `PDM close: …` |
| `sea-sail-to` | «Плыть к» на панели моря (см. раздел выше) | `PDM: autotest done, sail to at sea` |
| `sign-*` | кадры вывесок с обеих сторон (раздел ниже) | `autotest done, sign look ok` |
| `menu-arrows` | стрелки главного меню (раздел ниже) | `PDM menu: arrows ok` |

## Стрелки главного меню (menu-arrows, TOWN_AUTO=16)

Проверяет, что клавиши ↑/↓ в главном меню без игры перешагивают неактивные пункты «Сохранить» и «Продолжить» (`SET_SELECTABLE 0`, `screens.c`), а не застревают на них. Без нажатий клавиш: `Menu_ArrowsStep` (`menu.c`) шлёт `MSG_INTERFACE_MENU_ACTION` (`downstep`/`upstep`, как клавиша) и читает узел через `MSG_INTERFACE_GET_CURRENT_NODE`. Ожидаемый путь вниз: `LB_NEWGAME → LB_LOADGAME → LB_OPTIONS → LB_CREDITS → LB_EXIT`, вверх — тем же путём обратно. Шаг 0 только читает стартовый узел (`activate` нажал бы кнопку и запустил игру). Проверяемый код: `inode.cpp:CINODE::DoAction` в движке.

```bash
pdm-game/autotests.sh build/Debug/engine menu-arrows
# в compile.log: «PDM menu: arrows step N, at <узел>, expected <узел>» и «PDM menu: arrows ok» (или «arrows FAIL»)
```

## Сценарий «Плыть к» (TOWN_AUTO=15)

Тест нажимает «Плыть к» на командной панели моря так же, как игрок, а не вызывает обработчик запуска. Цепочка в `program/autotest/sea_sail.c`: `Press` → `Step3` → `Step4` → `Step5` → `End`. Каждый шаг ставит следующий через `PostEvent`, каждое нажатие — `SendMessage(&BattleInterface, "ls", 46105, ...)`:

1. `"activate"` — открывает панель (шаг хаба `sea/i_battle.cpp`, как Tab на суше, правило 12: то же сообщение `MSG_BATTLE_LAND_MAKE_COMMAND`).
2. Первый `"confirm"` на имени команды — `battle_command.cpp:ExecuteConfirm` спрашивает `BI_CommandEndChecking`, `hud.c:Hud_CommandEndChecking` отвечает 6238 = `SEA_SAIL_TO_MODE`, запуска ещё нет. `FillIcons` (`sea/battle_ship_command.cpp`) перестраивает панель в значки целей: карточки кораблей и форт или город острова. Каждый значок проверяется `evntCheckEnableLocator` (`hud.c:Hud_LocatorCheck`).
3. `"right"` — `ExecuteRight`, без зацикливания, на краю остановка.
4. Второй `"confirm"` на значке цели — `BI_LaunchCommand` с аргументами `"lsls"` → `hud.c:Hud_LaunchCommand` → `Sea_SailTo`. Нажатый значок разрешается один раз. `Sea_CanSailTo` на каждом кадре откладывает `hudSailTargetChr/Name` на время проверки доступности, поэтому выбор расходуется только запуском.

Ожидается: `PDM: sea, sail to the pressed fort` (или `harbour`, `hull`), `PDM: sea, sail to Highrock fort at X, Z`, герой на расстоянии около 60 м от форта, затем `PDM: sea, to the world map from …`. Меню: `game.ps1 run Debug sailto`.

## Все автотесты разом

Список — `pdm-game/autotest/scenarios.txt`: имя, сцена, город, `TOWN_AUTO`, маркер в `compile.log` и предел времени. Один и тот же список читают обе команды:

```bash
pdm-game/autotests.sh build/Debug/engine                 # Linux, все сценарии
pdm-game/autotests.sh build/Debug/engine town-tavern     # один или несколько по имени
```

```powershell
pdm-game\game.ps1 test Debug                            # Windows, меню game.ps1: пункт «t»
pdm-game\game.ps1 test Debug -Names town-tavern,sea-sail-to
```

Тест засчитан, если маркер есть в новых строках `compile.log` и в `error.log` новых строк нет. Итог: `autotests: N passed, M failed`, код выхода 1 при провале.

## Разговор с NPC с разных сторон

Отдельный скрипт `pdm-game/autotest/talk-angles.sh` проверяет диалог со стражниками и другими жителями города: каждый NPC, с четырёх сторон (углы 0, 90, 180, 270 от его +x; `ANGLES` меняет набор). Герой появляется в городе, подходит к NPC и встаёт в `TALK_RADIUS` (1.5 м) от него под заданным углом, заговаривает, и первый ответ идёт в лог. Потом прогон заканчивается.

```bash
pdm-game/autotest/talk-angles.sh build/Debug/engine                          # все стражники (из данных), город TOWN=City_HighRock
TOWN=City_GrandaAvilia pdm-game/autotest/talk-angles.sh build/Debug/engine Rinaldo___Town_Guard
ANGLES="0 180" pdm-game/autotest/talk-angles.sh build/Debug/engine Billy___Town_Guard
```

Движку передаются переменные `TALK_NPC` и `TALK_ANGLE` (`run.sh` пишет их в `program/data/start.c`; при `TOWN_AUTO=2` без `TALK_NPC` работает прежний сценарий). Маркер на пару: `PDM dialog: autotest talked to <id> from angle <угол>,`. Id в движке приводятся к нижнему регистру, скрипт это учитывает.

Стражник, которого нет в выбранном городе, даёт `SKIP`, а не провал: стражники распределены по городам. Итог: `talk-angles: N passed, M failed, K skipped`.

## Окружение

```bash
W=/media/roman/383be9ee-c114-4bf8-8956-66b985661cb4/home/remake-linux
LOGS=~/.local/share/Akella/Sea\ Dogs/Logs
cd $W && . ./env.sh
cmake --build build --target engine -j16          # если менялся движок; скрипты игры собирать не нужно
```

## Прогон автотеста

```bash
SCENE=battle TOWN_AUTO=7 timeout -k 5 300 corsairs-remake/pdm-game/run.sh build/Debug/engine >/dev/null 2>&1; echo "exit $?"
```

- `timeout -k 5 300` — страховка, если тест не дошёл до `ExitProgram`: через 300 с движок останавливается, через 5 с добивается. `exit 124` значит, что тест завис.
- Долгие прогоны (бой, карта мира, запись) Claude запускает в фоне и ждёт уведомления о конце, а не опрашивает в цикле.
- Движок не убивается по `pkill -f build/Debug/engine`: под это попадёт и запущенная пользователем игра.

Несколько тестов подряд, с итогом каждого:

```bash
for a in 7 8; do
  SCENE=battle TOWN_AUTO=$a timeout -k 5 300 corsairs-remake/pdm-game/run.sh build/Debug/engine >/dev/null 2>&1
  echo "== $a exit $?"
  grep -E "PDM: (battle|boarding|autotest)" "$LOGS/compile.log" | grep -v " fires \| hits " | tail -12
  echo err $(wc -c < "$LOGS/error.log")
done
```

## Что смотреть в логах

Логи перезаписываются при каждом запуске, поэтому читаются сразу после прогона.

```bash
grep "PDM" "$LOGS/compile.log" | tail -40                 # ход сценария
grep -c "autotest done" "$LOGS/compile.log"               # 1 — тест дошёл до конца
wc -c < "$LOGS/error.log"                                 # 0 — ошибок скриптов нет
grep -i "error" "$LOGS/compile.log" | head                # ошибки компиляции скриптов
grep -i "error\|warning" "$LOGS/system.log" | head        # ресурсы, шейдеры, модели движка
```

Тест считается пройденным, если:
- есть `autotest done`;
- `error.log` пуст;
- числа в трассах меняются так, как задумано (корпус падает от ядер, паруса — от книппелей, команда — от картечи).

Известный шум `system.log`, на итог не влияет: `particles_inv`, `font_ps_font*.pso`, `Mounted ship with no active ShipsLights`.

Если скрипт не скомпилировался, логи бывают пустыми, а движок висит до `timeout`. Частая причина — `a && (b || c)` в скриптах Storm: компилятор его не принимает, условие надо разбить на два `if`.

Ещё две ловушки компилятора:
- имена без учёта регистра: `#define SAVE_QUICK` совпадает с функцией `Save_Quick`, и каждое использование даёт «missing '('»; defines называть иначе, чем функции;
- выражение с атрибутами, перенесённое на следующую строку, даёт «invalid syntax»; атрибуты сначала читать в переменные (`x = stf(a.b.x);`).

## Запись видео

`record.sh` из движка запускает игру, снимает её окно ffmpeg и останавливает движок после последнего шага. Для автотеста шаг один — `sleep:N`, остальное делает сценарий.

```bash
SCENE=battle TOWN_AUTO=7 \
  corsairs-remake/engine/demos/common/record.sh corsairs-remake/pdm-game build/Debug/engine \
  videos/battle-$(date +%Y%m%d).mp4 sleep:240
```

- `RECORD_AUDIO=1` — со звуком. Звук идёт в отдельный PulseAudio-приёмник и одновременно слышен в колонках.
- `PREVIEW=S` — кадр на S-й секунде рядом с видео (`.jpg`).
- `N` в `sleep:N` — длина записи. Берите чуть больше времени теста, иначе конец обрежется.
- Каждая запись попадает в `videos/index.tsv`: дата, сцена, коммит движка, файл.

Видео игры в git не идут: в кадре данные оригинала. Видео нейтральных демо движка коммитятся в `engine/demos/<demo>/media/`.

## Проверка видео по кадрам

Claude смотрит не всё видео, а кадры в ключевые моменты: загрузка, первый залп, попадание, конец.

```bash
V=videos/battle-20261022.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 $V                    # длина
for t in 5 75 150 230; do ffmpeg -loglevel error -y -ss $t -i $V -frames:v 1 /tmp/f$t.png; done
ffmpeg -loglevel error -y -ss 75 -i $V -frames:v 1 -vf "crop=600:300:0:780" /tmp/hud.png   # участок кадра (HUD слева внизу)
ffmpeg -loglevel error -y -i $V -vf "fps=1/10,scale=480:-1,tile=4x3" /tmp/sheet.png      # лист: кадр каждые 10 с
```

Время кадров берётся из трасс: от первой строки `compile.log` до нужного события плюс 2–3 с, пока окно появляется. Кадры Claude открывает как картинки и сверяет с тем, что написано в логе.

## Порядок проверки этапа

1. Сборка движка, если он менялся.
2. Автотест в фоне → `autotest done`, пустой `error.log`, числа в трассах.
3. Соседние автотесты, которые затрагивает изменение (бой → 7, 8, 9, 11).
4. Запись с `sleep:N` → кадры через ffmpeg.
5. Строка в test-commands.md, затем коммит.

## Вывески с обеих сторон (TOWN_AUTO=50)

Текст вывески должен читаться с обеих сторон доски. Проверка идёт без нажатий, камера и герой ставятся сценарием.

**Как найти вывески и поставить камеру.** `tools/pdm_signs_find.py <Корсары> [City_…]` берёт модель города из оригинала, находит вывески теми же правилами, что конвертер (`pdm_props3d.is_sign`: `viveska_*`, в Хайроке `tavern`, `ship_yard`, `store`), и считает для каждой стороны доски строку `CAM=cx,cy,cz,hx,hy,hz`:
- центр доски — середина её вершин; нормаль — векторное произведение рёбер (`pdm_props3d.sign_axes`);
- камера c стоит в 2,5 м от доски по нормали (`side +1`) или против неё (`side -1`), на высоте доски + 0,2 м;
- герой h стоит под доской на земле (y = 0: города лежат на нуле), поэтому доска и герой попадают в один кадр.

**Как это играет игра.** `run.sh` с `TOWN_AUTO=50` и `CAM=…` пишет шесть чисел в `start.c` (`TownCX…TownHZ`). Через 3 с после входа в город `Town_CamLook` (`town.c`) телепортирует героя в h (`MSG_CHARACTER_TELEPORT_AY`) и ставит камеру в c с взглядом на героя (`MSG_CAMERA_TOPOS`, последний аргумент 1). Трасса `PDM town: camera look from …, signs model 1` показывает, что модель `<город>_signs.gm` загружена. Через 22 с — `PDM town: autotest done, sign look ok` и выход. Вывеску без модели (город без `_signs.gm`) тест не пропустит: в конце будет `no signs model`.

**Команды.**
```bash
cd $W && . ./env.sh
# сценарии autotest/scenarios.txt (sign-*: таверна, верфь Хайрока, магазин Granda Avilia; по две стороны)
corsairs-remake/pdm-game/autotests.sh build/Debug/engine sign-tavern-front sign-tavern-back
# кадры всех вывесок города (по кадру на сторону, в out/<город>-<текстура>-<n>.jpg; смотреть глазами)
corsairs-remake/pdm-game/sign-shots.sh build/Debug/engine /tmp/signs "$PDM" City_HighRock
```
`autotests.sh` читает необязательное седьмое поле сценария — переменные `run.sh` словами `ИМЯ=значение` (здесь `CAM=…`). Автотест проверяет только, что модель вывесок загружена и `error.log` пуст; читаемость текста — по кадрам `sign-shots.sh` (зеркальный текст сразу виден). Запись иногда не стартует (`x11grab Failed to translate xcb geometry`): `sign-shots.sh` повторяет запуск до трёх раз.

## Тестовые и игровые файлы не смешиваются

Запуск с `TOWN_AUTO≠0` (любой автотест) пишет сохранения и `settings.ini` в `pdm-game/save-test/`, обычная игра — в `pdm-game/save/` (`run.sh` кладёт `RUN_SAVEDIR`/`RUN_SAVEPFX` в `start.c`). Режим теста берётся из запуска (`RUN_TOWNAUTO`), а не из файла сохранения: иначе сейв, записанный тестом, при загрузке из меню запускал автотест, и игра закрывалась (`autotest finds no door`). Новый тест, который пишет файлы, должен брать пути из `RUN_SAVEPFX`/`RUN_SAVEDIR`, а не из литерала `save\`.
