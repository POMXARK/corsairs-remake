# Форматы оригинальных «Корсаров» (PDM 1.061) и их конвертация

Что проверено на файлах игры и чем конвертируется в форматы Storm 2. Справка по форматам — [AlexKimov/seadogs-file-formats](https://github.com/AlexKimov/seadogs-file-formats) (шаблоны 010 Editor, плагины Noesis, wiki); ниже то, где она неполна или ошибается.

## Конвертер всего RESOURCE

```
tools/convert.sh  <папка_игры> <out>     # Linux / macOS
tools\convert.bat <папка_игры> <out>     # Windows (вызывает convert.ps1)
.\tools\convert.ps1 <папка_игры> <out>   # PowerShell
```

Все три — обёртки над `tools/pdm2storm.py` (нужен только Python 3.8+, для моделей — submodule `engine`). Ключи: `--only textures,models,...` — выбрать этапы, `-j N` — число процессов. На 16 ядрах весь PDM конвертируется за ~40 секунд:

| этап | что | куда | PDM 1.061 |
|---|---|---|---|
| textures | `.tf` → `.tx`, `.tga` без `.tf`-двойника → `.tx` | `out/resource` | 3167, 0 ошибок |
| models | `.cff` → `.gm` | `out/resource` | 677, 3 битых в оригинале |
| copy | остальное как есть (звук, ini, тексты, `.ani`…) | `out/resource` | 3232 |
| actions | `.a` → команды | `out/data/actions` | 715 |
| dialogs | `.d` → узлы, ссылки, действия | `out/data/dialogs` | 1108 |
| tables | `.idf` → объекты name/value | `out/data/tables` | 96 |
| desc | `.def` → локаторы частей корабля | `out/data/desc` | 97 |
| characters | `.mtx` → карточки персонажей | `out/data/characters` | 297 |
| ships | `.shp` → профили кораблей | `out/data/ships` | 94 (+1 шаблон старой версии) |
| quests | `.ql` → сюжетные линии: квест, условие, действие | `out/data/quests` | 76 |

`out/resource` читает движок, `out/data` — JSON в UTF-8 для игровых скриптов. Итог с ошибками — в `out/convert-report.json`. Папку для запуска движка собирает `tools/make_korsari_run.sh <PDM> <sd-teho-public> <out> [engine/build/Debug]` (тот же конвертер + ini и скрипты TEHO + шейдеры).

## TF — текстуры → `.tx` (`tools/tf2tx.py`)

```
0x05  u8   pixel type
0x06  u8   число 16-битных мипов
0x07  u8   число 8-битных палитровых картинок
0x08  u32  width, u32 height
0x10  мипы 16 bit, затем палитра 256×4 (R,G,B,pad), затем 8-битные индексы
```

| type | формат | файлов в PDM |
|---|---|---|
| 0 | R5G6B5 | 2338 |
| 1 | A1R5G5B5 | 388 |
| 2 | A4R4G4B4 | 16 (такелаж, Blob, курсоры) |

- `TF.bt` путает типы 0 и 1. Проверка: у type 1 в раскладке A1R5G5B5 соседние пиксели отличаются в среднем на 3.4 на канал, в R5G5B5A1 — на 12.3, то есть получается шум.
- **Альфа инвертирована**: установленный бит (у type 2 — 15) означает прозрачность. Проверено на `Dama_Body` (прозрачен только зигзаг сверху) и `mf_takelag` (прозрачны промежутки между верёвками).
- Палитровые картинки — запасной вариант, если 16-битных мипов нет.

## TGA — картинки интерфейса → `.tx` (`pdm2storm.py`)

425 из 450 TGA не имеют `.tf`-пары: иконки товаров, кнопки, фоны, карта. Все несжатые (image type 2):

- 305 файлов — 16 бит A1R5G5B5. Альфа-бит, как и в `.tf`, означает прозрачность: он не стоит ни в одном файле, и всё это непрозрачные картинки интерфейса. По стандарту TGA они вышли бы полностью прозрачными.
- 105 — 32 бит без альфы, 40 — 32 бит с обычной 8-битной альфой (гербы, свиток, такелаж, шрифты).
- Строки снизу вверх, если не стоит бит 0x20 дескриптора; `.tx` хранит сверху вниз.
- Надписи на карте (`MermaidReefs`, `goldway`…) имеют альфу 0 во всех пикселях: видимо, игра рисовала их аддитивно. Конвертер переносит альфу как есть.

## CFF — модели → `.gm` (`tools/cff2gm.py`)

Заголовок, текстуры, материалы и меши — как в [cff-format/README.md](cff-format/README.md). Чего там нет:

- **Вершина 13 или 12 байт.** 653 файла используют 13 байт (i16×3 pos, i16×2 uv, u8×3 color). 26 старых файлов (`torus`, `Shlop`, `tavern_new`, `Panorama`, …) — 12 байт: заголовок следующего меша начинается ровно после `vc*12 + fc*3`.
- **Кадр анимации 0 ставит часть на место.** У мешей персонажей и катсцен (`*_a.cff`) вершины лежат в локальной системе части. 28-байтный ключ: translation 3f, rotation 3f (радианы), номер кадра u32. Позиция: `v' = Ry·Rx·Rz·v + t`, как в `D3DXMatrixRotationYawPitchRoll`. Порядок выбран перебором на 84 персонажах по зазору в суставах: этот вариант выиграл в 65 случаях, следующий — в 8. В плагине Noesis ось Y повёрнута в другую сторону.
- Расширения в разном регистре (`.cff`, `.CfF`, `.Cff`) — искать без учёта регистра.
- Битые в оригинале: `ABrigCan.cff` (меш 59 на 2 байта короче заголовка) и `Reef.CfF` (`MaterialCount = 0xCCCCCCCC`, неинициализированная память MSVC). Игра, видимо, их не грузит. Конвертируется 677 из 679.

## A — скрипты действий (`tools/a_decode.py`)

Каждый байт `i` в 8-байтном блоке циклически сдвинут вправо на `i` бит. Алгоритм — `scripts/010editor/decodeActionFile.1sc`. После декодирования получается текст cp1251 на простом DSL, одна команда в строке:

```
SET_FOR Person "X" Location "Shark Island.tavern"
ADD Item "..." "1"
LAUNCH Story_line "Spanish_line"
```

### Как CORE.dll читает команду

Интерпретатор (`CORE.dll`, функция `0x100014a0`) берёт первое слово строки до пробела, табуляции или перевода строки и сравнивает его без учёта регистра с таблицей команд. Затем читает пары `<Тип> "значение"`; у `Item` и `Goods` есть второе значение в кавычках — количество.

Команды (индекс = номер в таблице): `CLOSE, ADD, DELETE, SET_FOR, COMPLETE, DESTROY, PLAY, LAUNCH, CHECK, ADVANCE, OPEN, MESSAGE BOX, SET`.

Типы объектов (у каждого в таблице есть сигнатура аргумента: `s` — строка, `l` — число, `sl` — строка и число):
`Person, Game, Ship, Item, Goods, Record, Quest, Location, Expirience, Module, Characteristics, File, Rank, Dialog, DLink, Story_line, String, Interface, Playside, Model, Reputation, DNode, State, Officer, Officer_Rank, Engine_movie, Quantity, hull_hp, team_hp`.

Что делают ветки, которые встречаются в данных:

| Команда | Что делает | Строк |
|---|---|---|
| `SET State "0" DLink "диалог:узел:ссылка"` | включает или выключает ссылку диалога | 522 |
| `SET_FOR Person "X" Dialog "Y"` | назначает персонажу диалог `DIALOGS/Y.d` | 398 |
| `SET_FOR Person "X" Location "остров.локация"` | телепорт; `void` убирает персонажа | 320 |
| `SET_FOR Story_line "L" Quest "Q"` | переключает линию на квест и запускает его действие | 224 |
| `ADD Record "R"` | запись в журнал `TEXTS/RECORDS/R.rcd` | 204 |
| `ADD`/`DELETE Item "money" "N"` | деньги; иначе — предмет | 214 |
| `ADD Expirience "N"` | опыт | 110 |
| `ADD`/`DELETE Reputation "N"` | репутация | 97 |
| `LAUNCH Story_line "L"` | открывает сюжетную линию | 74 |
| `OPEN Location "остров.локация"` | переносит игрока в локацию | 50 |
| `ADD`/`DELETE Person "X"` | персонаж в эскадру игрока или из неё | 55 |
| `SET_FOR Person/Location … Playside "нация"` | меняет нацию по `nations.idf` | 46 |
| `PLAY Engine_movie "M"` | ролик | 28 |
| `SET_FOR Person "X" Model "M"` | модель `characters/M.cff` | 24 |
| `ADD`/`DELETE Officer`, `Goods`, `SET_FOR Person … Ship/Item` | офицеры, груз, корабль `SHIPS/*.shp`, передача предмета | ≤ 20 каждая |
| `CLOSE Game "X"` | конец игры | 5 |

Сюжетную линию двигают сообщения в `CORE`: 9001 переводит линию на следующий квест и выполняет его действие, 9002 ставит квест по имени. После этого `CORE` до 5000 раз повторяет проверку, пока переходы идут каскадом.

**Мёртвый код в данных.** Таблицу команд ищут по одному слову, поэтому `MESSAGE BOX …` (16 строк, всплывающие подсказки) не совпадает ни с чем. `message_box` и `END` (2 строки) в таблице тоже нет. Все они игнорируются: эти подсказки в оригинале никогда не показывались. `test_dima.a` не расшифровывается ни одним сдвигом — тестовый мусор.

Конвертер раскладывает каждую строку по этим таблицам. В JSON у команды есть поля:

- `cmd` — каноническое имя команды; `null`, если `CORE` её проигнорирует, тогда рядом стоит `note`;
- `objects` — список `type` / `value` / `count`;
- `effect` — что делает команда.

## D — диалоги

Обычный текст cp1251: `<N узел>`, `<T реплика>`, `<L ссылка,...,узел>`.

## IDF — таблицы (`pdm2storm.py`, этап tables)

`u32, u32 count, u32`, затем `count` объектов: `u32 n` + `n × 132` байт (`u32` мусор/указатель, `name[64]`, `value[64]`, cp1251). Разбираются все 96 файлов до последнего байта. Порядок объектов важен: другие файлы ссылаются на них по индексу (`nation` в `.mtx` — номер в `nations.idf`: 0 england, 1 pirate, 2 france, 3 spain; груз `.shp` — номера в `Goods.idf`).

## DEF — устройство корабля (этап desc)

`u32 count` + `count × 296`: `u32 index, u32 class, u32 sub, char file[256], float pos[3], float rot[3], i32 link` ([DEF.bt](https://github.com/AlexKimov/seadogs-file-formats)). Классы 200–209: Model, Rey, Sail, Cannon, Flag, Waterline, Patch, CannonSet, AllCannons, ShipTrace; 210–212 встречаются, смысл не известен.

Сборка корабля — `tools/pdm_ship.py <PDM> <resource> <Ship>`. Скрипт берёт из DEF элементы `Model`: корпус, мачты `_ms*`, такелаж `_Tklg`, пушки `_can`. `Patch` (`ABrig_Patch.cff`, текстура `black`, все грани смотрят вниз) — чёрная крышка над трюмом, видимо маска, не пускавшая море оригинала внутрь корпуса; Storm 2 она не нужна. Обмотка граней в CFF не согласована: зеркальные половины (левая половина носа брига) записаны с обмоткой оригинала и смотрят внутрь — движок PDM рисовал без отсечения. Поэтому `cff2gm` делает грани двусторонними: к каждой добавляется обратная копия с противоположной нормалью. Смещение каждой части — сумма `pos` по цепочке `link`; модели частей не повёрнуты. Все части пишутся в один `models/ships/<Ship>/<Ship>.gm` в метрах (×26: ABrig длиной 1,17 единицы становится бригом около 30 м), их текстуры — в `textures/ships/<ship>/`. Паруса `.sls` (класс `Sail`) и флаги пока не переносятся.

## MTX — персонажи (этап characters)

2384 байта (`0x950`). `CHARACTER_EDITOR.dll` (`FUN_10003dc0`) собирает их поле за полем из объекта редактора, обратная функция — `FUN_10003ef0`. Первый `u32` — размер, по нему файл и проверяется.

| смещение | поле | подпись в редакторе |
|---|---|---|
| 0x058 | `char[32]` имя (рус.) | name |
| 0x078 | `char[32]` id, он же имя файла | file name |
| 0x0a8 | `i32` нация, индекс в `nations.idf` | nation |
| 0x0ac | `i32` отношение, индекс в `relations.idf` | relation |
| 0x2b4 | `i32` тип: 0 — обычный NPC, 2 — капитан с кораблём, 1 — три квестовых NPC | character is |
| 0x2c8 | `char[32]` модель `CHARACTERS\*.cff` | 3D model |
| 0x2e8 | `char[32]` корабль `*.shp` | ship |
| 0x308 | `char[64]` текущий диалог | current dialog |
| 0x348 | `char[64]` остров, 0x388 `i32` — номер локации | address («A:%d on island: %s») |
| 0x734 | `i32[9]` навыки: Sailing, Repair, Commerce, Accuracy, Reload, Coordination, Combat, Defence, Board Range | |
| 0x934 | `i32` ранг офицера: −1 нет, 0 FIRST_MATE … 5 CARPENTER | officer rank |

Порядок навыков подтверждается данными: у казначея Адама Муллена (ранг 2, MASTER_PURSER) ненулевой только третий навык — Commerce. Остальные непустые слова конвертер кладёт в `unknown`. У 96 персонажей в 0x0b0 лежит `0xCCCCCCCC` — неинициализированное поле.

## SHP — профили кораблей (этап ships)

792 байта: `u32` + структура `0x2f0` + блок `0x24`. Их пишет `TOOLS_SHIPEDITOR.dll` (`FUN_10004ad0`, три `fwrite`), а читает `FUN_10004c40`. Поля сопоставлены с формой редактора:

| смещение | поле |
|---|---|
| 0x000 | Player skill (1–12) |
| 0x008 | `char[32]` имя профиля |
| 0x028 | `char[32]` класс корабля из `Ships.idf` (Ship type) |
| 0x04c | Hull HP (0x048 обычно то же число — вероятно, Rig HP) |
| 0x05c | Crew number |
| 0x084 | Weapon type: 0 Demi-culverins, 1 Culverins, 2 Demi-cannons |
| 0x090 | `i32[128]` груз: количество по индексам `Goods.idf` (пушки, ядра, книппели, картечь, бомбы, товары) |
| 0x300 / 0x304 / 0x308 | Soldier / Cannoneer / Sailor Skill |

`SHIPS/reserved/empty.shp` — 740 байт: шаблон более ранней версии редактора (апрель 2000).

## QL — сюжетные линии (этап quests)

Файл `.ql` — одна сюжетная линия (story line), записи в нём — её квесты. Пишет их `QUEST_EDITOR.dll` (`FUN_10004570` дописывает квест в конец и обновляет счётчик в заголовке). Разбираются все 76 файлов до байта.

```
u32 0, u32 count, u32 0
count × {
  u32 0, u32 data_len, u32 указатель кучи (мусор)
  char name[64]        имя квеста; "void" — пустое состояние линии
  char action_alt[64]  действие (3 случая)
  char action[64]      ACTIONS/<action>.a, выполняется, когда условие выполнено (106 из 106 есть в ACTIONS)
  char extra[64]       всегда пусто
  u8 data[data_len]    условие
}
```

Условие: `u8 condition, u8 object`, дальше по типу — `u32 len + строка`, `i32` значение или и то и другое. Для ESCORT добавляется цель: `u8 object (7 = Location), u32 72, name[64], i32, i32`. Имена взяты из таблиц указателей в `.data` DLL, а не из выгрузки строк: короткое `KILL` в неё не попало.

| condition | object | пример |
|---|---|---|
| 0 NO CONDITION | — | `void` |
| 1 OBTAIN | 3 Item, 4 Goods + количество | `Item "money" 5000`, `Goods "Chocolate" 150` |
| 1 OBTAIN | 12 Rank, 20 Reputation | `Reputation 5` |
| 2 KILL | 0 Person | `Person "Frederick The Mole"` |
| 3 ESCORT | 0 Person → 7 Location | `"Tedoro Alameda"` → `sinistra` |
| 4 MATCH | | в PDM не встречается |

Типы объектов (индекс): Person, Game, Ship, Item, Goods, Record, Quest, Location, Expirience, Module, Characteristics, File, Rank, Dialog, DLink, Story line, String, Interface, Playside, Model, Reputation, DNode, State, Officer, Officer Rank, Engine movie.

Как это связано: действие `.a` запускает линию (`LAUNCH Story_line "X"`) или переключает её квест (`SET_FOR Story_line "Mullen_check_1000" Quest "void"`). Движок проверяет условие текущего квеста, а когда оно выполнено, запускает его `action`. Тот, в свою очередь, двигает линию дальше, выдаёт предметы, меняет диалоги персонажей (`SET_FOR Person "X" Dialog "Y"`).

## Логика игры — в DLL

В `MODULES/` 104 модуля Storm 1 (PE32 i386). Каждый экспортирует только `?CreateEntity@@YAPAVEntity@@PAD@Z`. Скриптов на C, как в Storm 2, нет. Логика — это DLL плюс данные: ACTIONS, QUESTS, DIALOGS (сюжетная машина описана выше в разделе QL). Поэтому скрипты TEHO оригинал не запустят — нужен свой `program/*.c`, который читает данные PDM.

Декомпиляция: `GHIDRA=<ghidra> tools/ghidra/decompile.sh <out> MODULES/*.dll` (Ghidra 12.1.4 headless + `DumpDecomp.java`) выгружает C всех функций и строки в `<out>/<dll>.c` и `.strings.txt`. Результат декомпиляции в git не кладём: это код Akella.
