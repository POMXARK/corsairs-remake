# Команды для проверки pdm-game

Шаблоны команд, которыми проверяется каждый этап переноса ([port-plan.md](port-plan.md)). Все проверки идут без нажатий клавиш: сцену ведёт autotest на `PostEvent`. Новые команды добавляются сюда по мере появления.

Во всех командах:

```bash
W=/media/roman/383be9ee-c114-4bf8-8956-66b985661cb4/home/remake-linux
PDM=/media/roman/383be9ee-c114-4bf8-8956-66b985661cb4/home/Корсары
RES=$PDM/RESOURCE
LOGS=~/.local/share/Akella/Sea\ Dogs/Logs
cd $W && . ./env.sh
```

Долгие команды (запись, полная конвертация) запускаются в фоне. Ориентир по времени: запись идёт столько, сколько указано в `sleep:N`; `pdm_world.py` работает около 6 минут.

## Сборка и запуск

Меню и команды для сборки, запуска и пакета — `pdm-game/game.sh` (описано в [build.md](build.md)). Ниже — то же вручную.

```bash
cmake --build build --target engine -j16                  # движок
corsairs-remake/pdm-game/run.sh build/Debug/engine        # игра, начиная с главного меню
RECONVERT=1 corsairs-remake/pdm-game/run.sh build/Debug/engine   # всё сконвертировать заново
```

Переменные `run.sh`:

| Переменная | Что делает |
|---|---|
| `SCENE=menu` | главное меню (по умолчанию) |
| `SCENE=menu-newgame` | меню само нажимает «Новая Игра» |
| `SCENE=sea` | сразу в море на корабле героя |
| `SCENE=review` | смотр флота: все типы кораблей рядом |
| `SCENE=town` | город `TOWN` (по умолчанию `City_GrandaAvilia`) |
| `TOWN_AUTO=1` | герой сам идёт от причала в таверну и обратно |
| `TOWN_AUTO=2` | то же и разговор с первым NPC таверны, у которого есть диалог |
| `TOWN_AUTO=4` | герой выходит в море, через 5 с возвращается к причалу (`Sea_ToPort`) и идёт в таверну |
| `TOWN_AUTO=3` | с `TOWN=City_HighRock`: первое поручение города — вино для стражника Билли (квест от начала до конца) |
| `SCENE=story` | самопроверка сюжетной машины (все действия оригинала), потом выход |
| `SOUND_FX_ONLY=1` | без музыки и фона локаций: слышны только шаги и эффекты |
| `PDM=…` | папка установленной игры (по умолчанию `../../Корсары`) |

## Отдельные конвертеры

Генераторы `program/data/*.c` запускаются, только если их файла нет. Чтобы пересобрать один из них, удалите его выход или запустите конвертер напрямую:

```bash
python3 -I corsairs-remake/tools/pdm_world.py $PDM corsairs-remake/pdm-game          # локации, патчи, персонажи (~6 мин)
python3 -I corsairs-remake/tools/pdm_world.py $PDM corsairs-remake/pdm-game tavern_spa   # одна локация
python3 -I corsairs-remake/tools/pdm_sound.py $PDM corsairs-remake/pdm-game          # звук и музыка
python3 -I corsairs-remake/tools/pdm_ui.py $PDM corsairs-remake/pdm-game MainMenu    # экраны, диалог, голоса
python3 -I corsairs-remake/tools/pdm_character.py $PDM <out> <model.cff> <anim.idf>  # один персонаж
```

## Запись видео

```bash
SCENE=town TOWN_AUTO=1 PREVIEW=20 RECORD_AUDIO=1 \
  corsairs-remake/engine/demos/common/record.sh corsairs-remake/pdm-game build/Debug/engine \
  videos/<этап>-<дата>.mp4 sleep:85
```

- `PREVIEW=S` — кадр-превью на секунде S, сохраняется рядом как `.jpg`.
- `RECORD_AUDIO=1` — со звуком.
- Предупреждение `x11grab Failed to translate xcb geometry` на запись не влияет.

Как пережать запись для `pdm-game/media/`, чтобы файл весил несколько МБ:

```bash
ffmpeg -y -i videos/<этап>-<дата>.mp4 -t 60 -vf "scale=960:-2,fps=30" \
  -c:v libx264 -crf 32 -preset slow -c:a aac -b:a 64k -ac 1 corsairs-remake/pdm-game/media/<этап>.mp4
cp videos/<этап>-<дата>.jpg corsairs-remake/pdm-game/media/<этап>.jpg
```

Кадры и видео для смотра флота и моря:

```bash
SCENE=review corsairs-remake/pdm-game/shots.sh build/Debug/engine <out> 60 10 30 50
```

## Логи

```bash
cat "$LOGS/error.log"                                # после каждого запуска должен быть пуст
grep "PDM" "$LOGS/compile.log"                       # трассы скриптов: сцена, локация, NPC, сюжет
grep "PDM town: in" "$LOGS/compile.log"              # переходы между локациями
grep "PDM story" "$LOGS/compile.log"                 # линии и квесты сюжета
grep -i "can't\|not found\|fail" "$LOGS/system.log"  # не найденные файлы
```

## Кадры

```bash
ffmpeg -v error -y -ss 30 -i <video> -frames:v 1 -vf scale=960:-2 <out>.jpg                # кадр на 30-й секунде
ffmpeg -v error -y -ss 30 -i <video> -frames:v 1 -vf "crop=iw/2:ih/2:iw/4:ih/4" <out>.jpg  # центр кадра крупнее
```

## Сюжет

```bash
# первое поручение Хайрока целиком, ~3,5 мин
SCENE=town TOWN=City_HighRock TOWN_AUTO=3 timeout 240 corsairs-remake/pdm-game/run.sh build/Debug/engine
# ход квеста: разговоры, журнал, смена диалогов, итог (деньги, репутация, опыт)
grep -a "PDM \(dialog\|story\|town: \(in\|autotest done\)\)" "$LOGS/compile.log" | grep -v "node \|answer"
grep -a "FAILED" "$LOGS/compile.log"                 # автотест не нашёл NPC или нужный ответ
grep -a "autotest hero at\|PDM dialog: .* at " "$LOGS/compile.log"   # где герой каждые 10 с; при FAILED — где стоят NPC
# запись квеста целиком: короче 260 с второй разговор с Билли не попадает в видео
SCENE=town TOWN=City_HighRock TOWN_AUTO=3 PREVIEW=40 RECORD_AUDIO=1 \
  corsairs-remake/engine/demos/common/record.sh corsairs-remake/pdm-game build/Debug/engine \
  videos/pdm-story-<дата>.mp4 sleep:260
```

Если герой застрял по дороге, путь по таблице патча рисуется от точки старта к цели; чёрным — точки из трассы `autotest hero at`:

```bash
SCALE=50 python3 -I corsairs-remake/tools/ptc_path.py \
  corsairs-remake/pdm-game/resource/models/locations/patch_tavern_eng.ptc 1.405 4.0 0.37 -9.94 <out>.png 2.08 -2.28
```

`pdm-game/resource/techniques` — ссылка на `build/Debug/resource/techniques`, то есть на копию `src/techniques` движка. Шейдеры (`animation.fx` и др.) правятся в `storm-engine/src/techniques`, затем `cmake --build`.

План автотеста — `Town_AutoPlan` в `program/town.c`: шаги `go <выход>` и `talk <персонаж> <действие ответа>`. Чтобы проверить другой квест, добавьте свой `TOWN_AUTO` с шагами.

Где стоит NPC и что делают его диалоги — по данным, без запуска:

```bash
grep -n "PdmCharacters.<Id>\.\(address\|dialog\|model\)" corsairs-remake/pdm-game/program/data/pdm_data.c
grep -n "PdmDialogs.<dialog>\.\w*\.\w*\.action = \"PdmA" corsairs-remake/pdm-game/program/data/pdm_logic.c
grep -n -A12 "^void PdmA_<action>" corsairs-remake/pdm-game/program/data/pdm_logic.c
```

## Звук

```bash
# средняя громкость по отрезкам (около -15 дБ — звук есть, -91 дБ — тишина)
for t in $(seq 0 10 80); do echo -n "$t: "; \
  ffmpeg -ss $t -i <video> -af volumedetect -t 8 -vn -f null - 2>&1 | grep -o "mean_volume.*"; done

# пики каждые 0,1 с; шаги — пик примерно раз в секунду
python3 corsairs-remake/tools/audio_peaks.py <video> 6 8
```

Проверка шагов без музыки:

```bash
SCENE=town TOWN_AUTO=1 SOUND_FX_ONLY=1 RECORD_AUDIO=1 \
  corsairs-remake/engine/demos/common/record.sh corsairs-remake/pdm-game build/Debug/engine videos/steps-test.mp4 sleep:35
python3 corsairs-remake/tools/audio_peaks.py videos/steps-test.mp4 6 8
```

## Мир и патчи

```bash
# вид сверху: зелёный — пол после вырезания препятствий, красный — модель в полосе тела, синий — точки .loc
python3 corsairs-remake/tools/ptc_top.py $RES $RES/WORLDS/locations/tavern_spa.loc <out>.png

# материалы пола в патчах (по ним выбираются звуки шагов)
strings corsairs-remake/pdm-game/resource/models/locations/*.ptc | grep -o "snd_[a-z]*" | sort | uniq -c

# события шагов в анимации персонажа
grep -A6 "^\[walk\]" corsairs-remake/pdm-game/resource/animation/hero1.ani

# пересобрать патч одной локации после правки вырезания стен (~1 мин); таблицу локаций pdm_world.c не трогает
python3 -I corsairs-remake/tools/pdm_world.py $PDM corsairs-remake/pdm-game City_HighRock
```

Конвертеры идемпотентны: второй прогон подряд даёт те же байты. Проверка:

```bash
G=corsairs-remake/pdm-game
conv() { python3 -I corsairs-remake/tools/pdm_ui.py $PDM $G; python3 -I corsairs-remake/tools/pdm_sound.py $PDM $G
         python3 -I corsairs-remake/tools/pdm_data2c.py $G/data $G/program; python3 -I corsairs-remake/tools/pdm_logic2c.py $G/data $G/program; }
sums() { find $G/program/data $G/resource/ini -type f -print0 | sort -z | xargs -0 md5sum; }
conv >/dev/null; sums > /tmp/a.md5; conv >/dev/null; sums | diff /tmp/a.md5 - && echo SAME
```

## Логика оригинала

Как получена декомпиляция и как в ней искать — [decompile.md](decompile.md).

```bash
cd $W/ref/pdm-decomp
grep -v "R60\|Heap\|KERNEL" MAN.dll.strings.txt | tail -80             # строки модуля: зацепки
grep -o "[0-9]*\.[0-9]\+" MAN.dll.c | sort | uniq -c | sort -rn | head  # числа в коде
python3 $W/corsairs-remake/tools/pe_const.py $PDM/MODULES/MAN.dll 1000c1f0 1000c200   # константы _DAT_…
```
