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
