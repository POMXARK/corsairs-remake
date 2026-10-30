# Команды для проверки pdm-game

Шаблоны команд, которыми проверяется каждый этап переноса ([port-plan.md](port-plan.md)). Все проверки идут без нажатий клавиш: сцену ведёт autotest на `PostEvent`. Новые команды добавляются сюда по мере появления. Как устроены автотесты и как проверяется их результат — [autotests.md](autotests.md).

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
| `TOWN_AUTO=2` | то же и разговор с первым NPC таверны, у которого есть диалог: герой идёт к нему пешком (без телепорта), к стоящему за прилавком — к ближнему краю его точки, цель шагами по 0,25 м сдвигается к герою, пока Goto не примет её; заходит только в ту дверь, к которой шёл |
| `TOWN_AUTO=4` | герой выходит в море, через 5 с возвращается к причалу (`Sea_ToPort`) и идёт в таверну; в каждом выходе стоит 1,5 с под значком действия (справа сверху), на море видна картинка корабля с полосами |
| `TOWN_AUTO=5` | герой выходит в море, корабль ставится на 250 м дальше от гавани и плывёт к ней сам (время ×6); у гавани — заход в порт (`Sea_AtHarbour`), затем таверна; запускать с `TOWN=City_HighRock`: у Granda Avilia в данных нет гавани (harbour 0,0), корабль проходит мимо и уходит на карту мира |
| `TOWN_AUTO=6` | герой выходит в море, оттуда на карту мира, автотест кликает по Хайроку на карте (так же, как мышь: `mousepos` → `Map_Click`), корабль плывёт к нему (из Хайрока — к Granda Avilia), выходит в море в 400 м от гавани, заходит в порт и идёт в таверну; в море время ×6 (так же в `TOWN_AUTO=5`); на карте туман: в логе `PDM map: fog, … found`, кадры 2–9 с — открыт только путь Хайрок ↔ Granda Avilia |
| `TOWN_AUTO=7` | с `SCENE=battle`: у города героя в 120 м по курсу появляется пират Umberto 'Lump' на шлюпе Lightning и атакует; героем в автотесте правит SEA_AI (задача ATTACK), оба под парусами; герой меняет заряд после каждого залпа, враг выбирает свой; лог `PDM: battle, … fires cannonX with <заряд>`, `… loads <заряд>`, `PDM: battle, … hull N, sails S, crew C (<заряд>)`, конец — `the enemy sinks after …`, `the hero sinks` или через 200 с `time is up` с корпусом, парусами и командой обоих, затем `PDM: autotest done, battle` |
| `TOWN_AUTO=8` | с `SCENE=battle`: тот же пират, обоим кораблям SEA_AI ставит задачу ABORDAGE; ближе 40 м — абордаж: лог `PDM: boarding, crews …`, дуэль в каюте `PDM: boarding, X hits Y …`, конец — `PDM: autotest done, boarding, won N` |
| `TOWN_AUTO=9` | с `SCENE=battle`: тот же пират, через 1 с команда «Плыть к» — корабль героя переносится борт к борту с врагом в 30 м (`MSG_SHIP_TELEPORT`); лог `PDM: battle, sail to … m abeam`, затем `sail to done, boarding 1` |
| `TOWN_AUTO=50` | с `CAM=cx,cy,cz,hx,hy,hz`: герой ставится в точку h, камера смотрит на него из точки c (так снимаются вывески с обеих сторон; координаты — по `pdm_props3d.sign_axes`); `TOWN=City_HighRock` для английского города |
| `TOWN_AUTO=11` | с `SCENE=battle`: вражеского корабля нет, герой на мановаре, форт его острова ему враг; SEA_AI ведёт корабль к форту (ATTACK) и стреляет по пушкам, форт отвечает; камера держит форт сбоку от корабля; лог `PDM: fort of …, N guns`, `PDM: fort fires …`, `PDM: fort, a gun is out, K of N`, конец — `all guns out` или `the hero sinks`, затем `PDM: fort, S shots, K guns out` и `autotest done, battle` (около 3 мин) |
| `TOWN_AUTO=12` | с `SCENE=sea`: сохранение в море (F3) → порт → загрузка (F7) → снова море на том же месте → порт → сохранение в городе → герой отходит на 2 м → загрузка; лог `PDM save: save\quick, sea …`, `PDM save: loaded …`, `PDM save: autotest, the ship at X, Z, saved at X, Z`, `PDM save: autotest, the hero in … at X, Z, saved at X, Z` (числа совпадают), `autotest done, save` (около 40 с) |
| `TOWN_AUTO=15` | с `SCENE=sea`: пират Umberto 'Lump' на шлюпе LightningAppear150 m перед hero, facing them; button "Sail to" pressed through the sea command bar of the game itself, no `PostEvent` of the launch and no simulated keys — messages `MSG_BATTLE_LAND_MAKE_COMMAND 46105` (hub steps, same as the land menu of `TOWN_AUTO=10`): `"activate"` opens the bar, first `"confirm"` on the command name asks `BI_CommandEndChecking` (`hud.c:Hud_CommandEndChecking` answers 6238 = `SEA_SAIL_TO_MODE`) and the bar is rebuilt by `FillIcons` into the bar of target icons (hull cards, the fort/town icon of the island), `"right"` steps to the next icon and the second `"confirm"` launches it through `BI_LaunchCommand` → `Sea_SailTo`; at the Highrock spawn the reach holds the pirate hull and the fort, the pressed fort icon stops the hero 60 m off the fort (`PDM: sea, sail to the pressed fort`, `PDM: sea, sail to Highrock fort at …`, `PDM: sea, sail to done`); then the ship goes to the world map; in the launcher `game.bat` the item «Плыть к (autotest)» (letter `s`) and the command `game.ps1 run Debug sailto`, the press script lives in `autotest\sea_sail.c` |
| `TOWN_AUTO=13` | с `SCENE=sea`: меню поверх игры → «Сохранить игру» → «Новая запись» (`save\game1`) → «Загрузить игру», курсор на ней, описание из заголовка → загрузка → удаление с «Да» → «Настройки», окно 1600x900 и обратно; лог `PDM save: autotest, …`, в system.log `Render: the screen WxH`, конец `autotest done, screens` (около 50 с) |
| `TOWN_AUTO=10` | меню суши (Tab): автотест открывает его сообщением `MSG_BATTLE_LAND_MAKE_COMMAND "activate"`, шагает `"right"` до места (раз в 0,7 с, подпись над значком меняется) и подтверждает `"confirm"`: магазин → улица → дворец → улица → таверна → улица → верфь → улица → таверна → моря (inside a place its menu offers only street and sea, so autotest leaves each one by street back; the gate asks for the door marker of type 4, `Town_HasDoor` in `town.c`); лог `PDM hud: land command <место> (autotest)`, затем `PDM hud: land command <место>` из `BI_LaunchCommand` и `PDM town: in …`, в конце `PDM: sea at …`; внизу слева строка значков без текущего места; Пиктограммымы рисувa из atlases `resource/textures/battle_interface/pdm/commands.tga.tx` — not in git, `run.ps1` regenerates them if missing; with `TOWN=City_HighRock` the autotest runs through the whole starting city of Highrock |
| `TOWN_AUTO=3` | с `TOWN=City_HighRock`: первое поручение города — вино для стражника Билли (квест от начала до конца) |
| `SCENE=screens` | все экраны интерфейса по очереди (2,5 с), новая игра, F1 в городе, страница «Корабль», трюм, сундук и торговля со списками (в торговле автотест покупает и продаёт кликами по `LB_BUY`/`LB_SELL`; лог `PDM trade: bought N of … for P at <остров>, money M, load L/C`), Esc, выход |
| `SCENE=story` | самопроверка сюжетной машины (все действия оригинала), потом выход |
| `SOUND_FX_ONLY=1` | без музыки и фона локаций: слышны только шаги и эффекты |
| `PDM=…` | папка установленной игры (по умолчанию `../../Корсары`) |

## Отдельные конвертеры

Генераторы `program/data/*.c` запускаются, только если их файла нет. Чтобы пересобрать один из них, удалите его выход или запустите конвертер напрямую:

```bash
python3 -I corsairs-remake/tools/pdm_world.py $PDM corsairs-remake/pdm-game          # локации, патчи, персонажи (~6 мин)
python3 -I corsairs-remake/tools/pdm_world.py $PDM corsairs-remake/pdm-game tavern_spa   # одна локация
python3 -I corsairs-remake/tools/pdm_sound.py $PDM corsairs-remake/pdm-game          # звук и музыка
python3 -I corsairs-remake/tools/pdm_ui.py $PDM corsairs-remake/pdm-game             # экраны, диалог, голоса
python3 -I corsairs-remake/tools/pdm_hud.py $PDM corsairs-remake/pdm-game            # тулбар моря: команды, картинки кораблей с флагами, полосы
python3 -I corsairs-remake/tools/pdm_character.py $PDM <out> <model.cff> <anim.idf>  # один персонаж
python3 -I corsairs-remake/tools/pdm_island.py $PDM corsairs-remake/pdm-game/resource all --data corsairs-remake/pdm-game/data  # острова, карты глубин, места корабля (~2 мин)
python3 -I corsairs-remake/engine/demos/sea/make_sea.py corsairs-remake/pdm-game/resource --waves fft   # волны FFT (без --waves — синусоиды демо)
python3 -I corsairs-remake/tools/pdm_anim_check.py corsairs-remake/pdm-game/resource [модель …] [--all]  # рывки анимаций: шов цикла, скачок кадра, поза без blend
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

## Озвучка реплик

Полностью — `docs/voice-over.md`. Из `corsairs-remake`:

```bash
python3 -I tools/pdm_voice_lines.py pdm-game                 # реплики → data/voice/lines.jsonl; два прогона — один md5
python3 -I tools/pdm_voice_lines.py pdm-game --bind          # привязать готовые wav (program/data/pdm_voice_lines.c)
python3 -I tools/pdm_voice_refs.py pdm-game                  # текст образцов Whisper'ом
python3 -I tools/comfy_voice_batch.py pdm-game --limit 10    # проба через ComfyUI
python3 -I tools/pdm_voice_check.py pdm-game                 # CER и темп → redo.txt / listen.txt
```

Проверка движка без нейросети — тоны на реплики падре Игнасио и `TOWN_AUTO=2` со звуком (`voice-over.md`, шаг 8): слышно приветствие, затем тон узла, ответ обрывает тон.

## 3D-модели нейросетью

Полностью — `docs/ai-models.md`. Из `corsairs-remake`:

```bash
python3 -I tools/pdm_model_views.py pdm-game hero1                 # 4 вида → data/ai_models/views/hero1_*.png
python3 -I tools/comfy_model_batch.py pdm-game --only hero1        # GLB через ComfyUI → data/ai_models/glb
python3 -I tools/pdm_glb2gm.py pdm-game hero1                      # в игру; два прогона — один md5
python3 -I tools/pdm_glb2gm.py pdm-game hero1 --restore            # вернуть оригинал
```

## Мир и патчи

```bash
# вид сверху: зелёный — пол после вырезания препятствий, красный — модель в полосе тела, синий — точки .loc
python3 corsairs-remake/tools/ptc_top.py $RES $RES/WORLDS/locations/tavern_spa.loc <out>.png

# невидимые стены: швы пола (за ребром без соседа снова пол той же высоты) и несвязные части пола;
# на ровном полу швов быть не должно, части — только дворы за стенами (~10 с на город)
python3 -I corsairs-remake/tools/ptc_seams.py $RES City_GrandaAvilia tavern_spa

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
