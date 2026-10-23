# Нейроозвучка реплик NPC

Как озвучить диалоги NPC голосами из оригинала: бесплатно, локально на RTX 5080, пачкой через ComfyUI или напрямую из Python. Как подключить звук к движку и привязать каждую реплику к своему NPC.

## Что есть в данных

| Что | Сколько | Где |
|---|---|---|
| Реплики NPC (текст узла диалога) | 1980 в 553 диалогах, 366 тыс. знаков, без подстановок (`%s`, имён) | `pdm-game/data/dialogs/DIALOGS/*.json` → `PdmDialogs.<диалог>.<узел>.text` в `program/data/pdm_logic.c` |
| Ответы героя (ссылки) | 2887 | там же, `links[].text`; в оригинале герой молчит, их не озвучиваем |
| Образец голоса NPC | 252 персонажа, по одному приветствию `SOUNDS/<id>.wav` | `pdm-game/resource/sounds/voices/<ключ>.wav` (`tools/pdm_ui.py`), 22050 Гц, моно, 16 бит |
| Кто говорит диалог | 538 из 553 диалогов назначает `Pdm_SetDialog("<персонаж>", "<диалог>")`, общих у нескольких NPC нет | `program/data/pdm_logic.c` |

Длина образцов: медиана 2,5 с, 155 из 252 короче 3 с, 6 длиннее 6 с. Этого хватает моделям «клон с 3 секунд». Короткие образцы проверяются отдельно (шаг 5).

Если говорить со скоростью 14 знаков в секунду, получится около 7 часов звука. В WAV 22050 Гц моно это примерно 1,2 ГБ.

## Как звучит в игре

1. Диалог открывается, NPC говорит приветствие из оригинала (`TownDialog.greeting`, работает уже сейчас).
2. Когда приветствие доиграло, звучит озвучка первой реплики.
3. Игрок выбирает ответ, текущая реплика обрывается, и звучит реплика нового узла.
4. При выходе из диалога звук останавливается.

Реплика без файла остаётся немой: озвучку можно добавлять частями.

## Выбор модели

Нужны три вещи: русский язык, клон голоса по короткому образцу (zero-shot) и лицензия, не запрещающая использование.

| Модель | Лицензия | Русский | Клон | Зачем |
|---|---|---|---|---|
| **Qwen3-TTS 1.7B Base** | Apache-2.0 | да (10 языков) | с 3 с | основная: короткие образцы, свободная лицензия |
| **Chatterbox Multilingual** (Resemble AI) | MIT | да (23 языка) | zero-shot | запасная; в ComfyUI ноды `ComfyUI_Fill-ChatterBox` |
| **Fun-CosyVoice3 0.5B** (Alibaba, FunAudioLLM) | Apache-2.0 | да (9 языков) | с 3 с, лучше 3–10 с | проверить против Qwen3-TTS (шаг 4б): меньше и быстрее, есть instruct и теги `[breath]` |
| **ESpeech-TTS-1** (F5-TTS, обучена на русском) | Apache-2.0 по карточке | только русский | по образцу и его тексту | если ударения и интонация у первых двух хуже |

Почему не другие:
- **ACE-Step, YuE, MiniMax Music** из шаблонов ComfyUI делают музыку и песни, а не речь.
- **XTTS-v2, Fish Speech / OpenAudio, F5-TTS base и её русские дообучения** (`hotstone228`, `attashe`) — веса под некоммерческими лицензиями (CPML, CC-BY-NC).

### ComfyUI или напрямую

ComfyUI — лишь одна из оболочек для запуска модели. Шаблоны и ноды в его Manager — это то, что кто-то уже обернул, а не список всех моделей. Почти у каждой TTS-модели есть свой репозиторий с Python API: `git clone`, `pip install -r requirements.txt`, веса с Hugging Face — и модель вызывается из скрипта. Обходить ComfyUI стоит, если:
- для модели нет нод или они отстают от новой версии;
- нужен режим, которого ноды не дают (у CosyVoice3 — `inference_cross_lingual`, теги `[breath]`, замена произношения);
- не хочется собирать граф: скрипт берёт `lines.jsonl` и пишет те же файлы.

Для пакетного прогона результат один: `comfy_voice_batch.py` и `cosyvoice_batch.py` пропускают готовые реплики, ведут `tries.json`, склеивают куски одинаково и в конце делают `--bind`. Скрипты можно чередовать, а `pdm_voice_check.py` проверяет файлы любого из них.

### CosyVoice 3 или Qwen3-TTS

Обе модели под Apache-2.0, обе знают русский и клонируют голос с 3 секунд. Опубликованных замеров на русском нет ни у той, ни у другой: в карточке CosyVoice3 только китайский и английский (CER 1,21 % на test-zh, WER 2,24 % на test-en). Поэтому выбор делается пробой на наших данных, а не по таблицам.

| | Qwen3-TTS 1.7B | Fun-CosyVoice3 0.5B |
|---|---|---|
| размер | 1,7 млрд | 0,5 млрд, веса ~2 ГБ: быстрее, меньше памяти |
| ударения `+` из `replace.tsv` | понимает | не понимает, скрипт их убирает; неверное ударение правится в `replace.tsv` другим написанием слова, проверяется на пробе |
| короткие образцы | с 3 с | 3–10 с лучше всего, до 2 с звук мягче. У нас медиана 2,5 с, 155 из 252 образцов короче 3 с |
| ComfyUI | ноды Qwen3-TTS | ноды `ComfyUI_FL-CosyVoice3` или TTS Audio Suite |
| без ComfyUI | свой репозиторий | `cosyvoice_batch.py` (шаг 4б) |

Короткие образцы — главный риск CosyVoice3 в нашем случае. Порядок пробы:
1. `--limit 20` одними и теми же репликами для каждой модели, в разные копии `resource/sounds/voices/lines`.
2. `pdm_voice_check.py` на каждой копии: средний CER и число строк в `redo.txt` сравнивают объективно.
3. На слух — те же 20 реплик, особенно персонажи с образцом короче 2 с.

Выигравшая модель озвучивает всё. Можно и смешать: персонажей, у которых голос «не держится» на одной модели, перегенерировать на другой (`--only <персонаж>`).

Перед установкой проверьте лицензию на странице модели на Hugging Face: у дообученных версий она часто другая, чем у базы.

**Права.** Голос клонируется из записей актёров оригинала, поэтому результат — производное от данных оригинала. С ним обращаемся как с остальным сконвертированным: генерируется локально в `pdm-game/resource/` и не коммитится (`resource` уже в `.gitignore`). В git идут только скрипты и workflow без аудио.

## Инструменты

| Файл | Что делает |
|---|---|
| `tools/pdm_voice_lines.py` | реплики → `data/voice/lines.jsonl`, привязка → `program/data/pdm_voice_lines.c` (шаги 1, 3, 7) |
| `tools/pdm_voice_refs.py` | текст образцов через Whisper → `data/voice/refs.tsv` (шаг 2) |
| `tools/comfy_voice_batch.py` | очередь ComfyUI на все реплики (шаг 4) |
| `tools/cosyvoice_batch.py` | то же через Python API Fun-CosyVoice3, без ComfyUI (шаг 4б) |
| `tools/pdm_voice_check.py` | проверка Whisper'ом, список на перегенерацию (шаг 5) |
| `tools/voice/llm_prep_prompt.txt` | системный промт локальной LLM для подготовки текста (шаг 3) |
| `tools/voice/instruct_prompt.txt` | описания голосов по классам моделей для моделей с instruct (шаг 4) |
| `tools/voice/replace.tsv` | словарь замен: ударения в именах, произношение (шаг 3) |
| `tools/voice/voice_api.json` | workflow ComfyUI, экспорт API (шаг 4, кладётся после сборки графа) |

Всё, что пишут скрипты, лежит в `pdm-game/data/voice/` и `pdm-game/resource/sounds/voices/lines/` и в git не идёт.

## Шаг 1. Извлечь реплики и привязать их к NPC

```bash
python3 -I tools/pdm_voice_lines.py pdm-game
# pdm_voice_lines: 1977 speeches of 240 speakers, 2662 chunks, 0 voiced, 25 notes in lines_report.txt
```

`run.sh` вызывает его сам, если нет `program/data/pdm_voice_lines.c`. Строка `lines.jsonl`:

```json
{"dialog": "Beuve_Hainault_first", "node": "node_1", "speaker": "Beuve_Hainault", "class": "citizen",
 "ref": "voices/beuve_hainault.wav", "text": "О, сэр - вы капитан? ...", "chunks": ["О, сэр — вы капитан? ..."],
 "out": "voices/lines/beuve_hainault_first/node_1.wav"}
```

Правила привязки:
- `dialog` и `node` — ключи из `PdmDialogs` в `program/data/pdm_logic.c`: скрипт читает то, что уже написал конвертер, поэтому ключи совпадают с игрой.
- `speaker` — из `Pdm_SetDialog("<персонаж>", "<диалог>")`. У 15 диалогов назначения нет (`sailor_second`, `leon_common_2` …): говорящий — персонаж, чьим `id` начинается имя файла `DIALOGS/<id>_<диалог>.d`. Такие случаи пишутся в `data/voice/lines_report.txt`.
- `ref` — приветствие говорящего (`pdm_voices.c`). Если его нет, берётся образец того же класса модели (`citizen6` → `citizen`, `negotiant4_dr` → `negotiant`); замена — в отчёте.
- `class` — класс модели, по нему `instruct_prompt.txt` выбирает описание голоса.
- `out` — путь в `resource/sounds/`, в нижнем регистре. Одинаковый текст у разных говорящих — разные файлы.

Скрипт идемпотентен: два прогона дают одинаковый md5 `lines.jsonl` и `pdm_voice_lines.c`.

## Шаг 2. Текст образцов

```bash
pip install faster-whisper
python3 -I tools/pdm_voice_refs.py pdm-game            # --device cpu без видеокарты, дольше
```

Qwen3-TTS (режим с текстом образца) и F5-TTS клонируют точнее, если знают, что сказано в образце. Приветствия расшифровываются Whisper large-v3 (MIT) в `data/voice/refs.tsv`: `<ref>\t<текст>`. Таблицу стоит проверить на слух: ошибка в тексте образца портит все реплики персонажа. Исправленные строки повторный запуск не трогает.

## Шаг 3. Подготовка текста

Без LLM это делает `pdm_voice_lines.py`:
- числа — словами (`500` → «пятьсот»), иначе модель может прочитать их по-английски;
- ` - ` и ` -- ` → `—`, многоточия остаются: по ним модель делает паузы;
- реплики длиннее 250 знаков делятся по предложениям (`chunks`). Куски озвучиваются тем же образцом и склеиваются с паузой 0,25 с: длинный кусок модель «уводит», темп плывёт, слова пропадают;
- замены из `tools/voice/replace.tsv`: `<что>\t<как сказать>`, например `Хайрок\tХайр+ок` (`+` перед ударной гласной понимают Qwen3-TTS и ESpeech; для другой модели проверьте на пробе).

С локальной LLM (склонение чисел, сокращения, иностранные имена кириллицей):

```bash
ollama pull qwen3:14b                    # или любая, что держит русский; 8 ГБ VRAM хватает qwen3:8b
python3 -I tools/pdm_voice_lines.py pdm-game --llm http://127.0.0.1:11434 --llm-model qwen3:14b
```

Промт — `tools/voice/llm_prep_prompt.txt`. Он запрещает менять смысл и порядок слов, а ответ, который сильно отличается по длине от исходника, отбрасывается: остаётся текст без LLM. Ответы кэшируются в `data/voice/llm_cache.jsonl` по md5 куска, поэтому второй прогон ничего не спрашивает и даёт тот же файл. Чтобы переспросить кусок, удалите его строку из кэша.

## Шаг 4. ComfyUI: очередь на все реплики

ComfyUI запускается на Windows с RTX 5080 (`GUIDE.md`). Реплики гонит скрипт через HTTP API, руками в интерфейсе ничего не нажимается.

### Собрать workflow один раз

1. ComfyUI Manager → установить ноды выбранной модели: Qwen3-TTS (поиск по `Qwen3-TTS`) или `ComfyUI_Fill-ChatterBox`. Модель скачается при первом запуске.
2. Собрать граф: `Load Audio` (образец) → нода TTS с клоном голоса → `Save Audio`.
3. Переименовать ноды (правый клик → Title). По этим именам скрипт их находит, какие бы ноды ни стояли внутри:
   - `REF_AUDIO` — `Load Audio`;
   - `TEXT` — текст реплики (поле ноды TTS или нода `String`);
   - `SAVE` — `Save Audio`;
   - `REF_TEXT` — текст образца (необязательно);
   - `SEED` — нода с сидом (необязательно);
   - `INSTRUCT` — описание голоса (необязательно, для моделей с instruct, например Qwen3-TTS VoiceDesign).
4. Прогнать вручную 5–10 реплик разных персонажей, подобрать температуру и скорость.
5. Workflow → **Export (API)** → `tools/voice/voice_api.json`. В нём только граф и настройки, его можно коммитить.

Имя входа с текстом у разных паков разное (`text`, `string`, `value`). Посмотрите его в `voice_api.json` и передайте `--text-input`, имя входа сида — `--seed-input`.

### Прогнать очередь

```bash
python3 -I tools/comfy_voice_batch.py pdm-game --limit 10                  # проба
python3 -I tools/comfy_voice_batch.py pdm-game --only padre_ignacio        # один персонаж или диалог
python3 -I tools/comfy_voice_batch.py pdm-game                             # всё, на ночь
python3 -I tools/comfy_voice_batch.py pdm-game --comfy http://192.168.1.10:8188   # ComfyUI на другой машине (--listen)
```

Что делает скрипт:
1. Загружает нужные образцы в `ComfyUI/input/pdm_voices/` через `/upload/image` (копировать руками не нужно).
2. Пропускает реплики, у которых файл уже есть: прогон можно прервать и продолжить.
3. Каждый кусок — отдельное задание `/prompt`; в очереди держится `--inflight` (2) задания, GPU не простаивает.
4. Забирает звук через `/history` и `/view`, поэтому ComfyUI может работать на другой машине.
5. Склеивает куски через ffmpeg: пауза 0,25 с, громкость `loudnorm I=-18`, 22050 Гц моно 16 бит, как оригинал.
6. В конце вызывает `pdm_voice_lines.py --bind`: в игру попадают только готовые файлы.

Сид задания — `--seed` (1) плюс число попыток реплики из `data/voice/tries.json`: повторный прогон даёт тот же звук, перегенерация — другой.

Сколько ждать — уточнит первая сотня реплик: модель на 1–2 млрд параметров на 5080 обычно быстрее реального времени. 7 часов речи займут 2–7 часов. Скрипт печатает оценку оставшегося времени.

## Шаг 4б. CosyVoice3 без ComfyUI

Подробная установка на Windows с ошибками и подводными камнями — [voice-cosyvoice-windows.md](voice-cosyvoice-windows.md).

На машине с видеокартой (Linux или Windows, Python 3.10):

```bash
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git ~/CosyVoice
cd ~/CosyVoice && conda create -n cosyvoice -y python=3.10 && conda activate cosyvoice
pip install -r requirements.txt
python -c "from huggingface_hub import snapshot_download; \
  snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')"
```

Из `corsairs-remake`, в том же окружении:

```bash
python -I tools/cosyvoice_batch.py pdm-game --repo ~/CosyVoice --limit 10            # проба
python -I tools/cosyvoice_batch.py pdm-game --repo ~/CosyVoice --only padre_ignacio  # один персонаж или диалог
python -I tools/cosyvoice_batch.py pdm-game --repo ~/CosyVoice                       # всё
python -I tools/cosyvoice_batch.py pdm-game --repo ~/CosyVoice --redo pdm-game/data/voice/redo.txt
```

Режим выбирается для каждой реплики:
- есть текст образца в `refs.tsv` (шаг 2) — `inference_zero_shot`, самый точный клон;
- текста нет — `inference_cross_lingual`, только по звуку;
- `--instruct` — `inference_instruct2` с описанием голоса из `instruct_prompt.txt`. Описание меняет манеру (возраст, настроение, темп), тембр по-прежнему берётся из образца.

Сид — `--seed` + попытки из `tries.json` + номер куска, повторный прогон даёт тот же звук. Модель выдаёт 24 кГц, `join` приводит к 22050 Гц моно, как в оригинале.

## Шаг 5. Проверка качества

```bash
python3 -I tools/pdm_voice_check.py pdm-game                       # слушает Whisper'ом то, что ещё не слушал
python3 -I tools/comfy_voice_batch.py pdm-game --redo pdm-game/data/voice/redo.txt
python3 -I tools/pdm_voice_check.py pdm-game                       # повторять, пока redo.txt не пуст
```

- Доля ошибочных букв (CER) больше `--cer` (0,15) или темп вне 0,04–0,15 с на знак (пропуск слов или «зависание») — реплика идёт в `redo.txt`, а после `--max-tries` (3) попыток — в `listen.txt`, на слух.
- `data/voice/report.tsv`: файл, CER, длина, с на знак, попытки, что услышал Whisper.
- Затем прослушать по 3–4 реплики каждого персонажа с образцом короче 1,5 с. Если голос не держится, персонажу дают другой образец: замена в `lines_report.txt` подскажет похожий класс.

## Шаг 6. Движок: голос реплики после приветствия

Игра создаёт сущность `dialog` — класс `DIALOG` (`storm-engine/src/libs/dialog/src/dialog.cpp`). Приветствие (`greeting`) она играла и раньше. Добавлен атрибут `voice` (ours):
- `voice = "<файл>"` останавливает реплику, которая ещё звучит, и запоминает новую;
- `Realize` запускает её, когда приветствие не играет: первая реплика ждёт конца приветствия, следующие начинаются сразу;
- деструктор останавливает реплику: выход из диалога обрывает голос.

Описание атрибута — в `storm-engine/docs/ru/05-modules.md`, раздел диалога.

## Шаг 7. Скрипт игры: привязка файла к узлу

- `program/data/pdm_voice_lines.c` (пишет `pdm_voice_lines.py`, только для существующих файлов):
  ```c
  object PdmVoiceLines;
  void PdmVoiceLines_Init() { PdmVoiceLines.Beuve_Hainault_first.node_1 = "voices\lines\beuve_hainault_first\node_1.wav"; ... }
  ```
- `Town_DialogNode` (`program/town.c`), после `TownDialog.Text = nd.text;`:
  ```c
  if (CheckAttribute(&PdmVoiceLines, townTalkKey + "." + node)) { TownDialog.voice = PdmVoiceLines.(townTalkKey).(node); }
  ```
- Ключ — та же пара «диалог / узел», по которой берётся текст. Поэтому звук всегда совпадает с показанной репликой, кто бы ни назначил диалог.

## Шаг 8. Проверка в игре

Автотест говорит с первым NPC таверны Granda Avilia (падре Игнасио, `padre_ignacio_first`, 8 реплик). Для проверки движка без нейросети подойдут тоны:

```bash
D=pdm-game/resource/sounds/voices/lines/padre_ignacio_first; mkdir -p $D
for n in 1 2 3 4 5 6 7 8; do ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=$((300+n*100)):duration=2" \
  -ar 22050 -ac 1 -c:a pcm_s16le $D/node_$n.wav; done
python3 -I tools/pdm_voice_lines.py pdm-game --bind
SCENE=town TOWN_AUTO=2 RECORD_AUDIO=1 \
  corsairs-remake/engine/demos/common/record.sh corsairs-remake/pdm-game build/Debug/engine \
  videos/voice-$(date +%Y%m%d).mp4 sleep:80
rm -r $D && python3 -I tools/pdm_voice_lines.py pdm-game --bind            # убрать тоны
```

Слышно: приветствие падре, затем тон реплики; каждый ответ обрывает прошлый тон и начинает следующий. `error.log` пуст.

## Настройки: громкость и выключение голосов

На странице «Настройки» три ряда `(-) 80% (+)`: звуковые эффекты, музыка и голоса NPC (шаг 10%, `options.c`,
`Sound_Volume()` передаёт три громкости в `MSG_SOUND_SET_MASTER_VOLUME`). Галочка «Голоса NPC» выключает
сгенерированные реплики: `town.c` тогда не ставит `TownDialog.voice`, диалог идёт молча, как до озвучки.
Значения живут до выхода из игры.

## Порядок работ

1. `pdm_voice_lines.py` (+ `--llm`) и `pdm_voice_refs.py` — на Linux или Windows, минуты.
2. Workflow и 10 пробных реплик в ComfyUI (`--limit 10`), выбор модели.
3. Полный прогон на ночь, `pdm_voice_check.py` и `--redo`, пока список не опустеет; `listen.txt` — на слух.
4. Папку `resource/sounds/voices/lines` и `data/voice` перенести на машину с игрой, если ComfyUI на другой; `--bind`.

## Источники

- Fun-CosyVoice3 0.5B, Apache-2.0, 9 языков с русским: [huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512), код и `example.py`: [github.com/FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice), ноды [ComfyUI_FL-CosyVoice3](https://github.com/filliptm/ComfyUI_FL-CosyVoice3)

- Qwen3-TTS, Apache-2.0, русский, клон с 3 с: [simonwillison.net](https://simonwillison.net/2026/Jan/22/qwen3-tts), [gitee.com/lxin0/Qwen3-TTS](https://gitee.com/lxin0/Qwen3-TTS)
- Chatterbox Multilingual, MIT, 23 языка: [huggingface.co/ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox/blob/refs%2Fpr%2F48/README.md), ноды [ComfyUI_Fill-ChatterBox](https://github.com/filliptm/ComfyUI_Fill-ChatterBox)
- ESpeech-TTS-1: [huggingface.co/ESpeech](https://huggingface.co/ESpeech/ESpeech-TTS-1_SFT-256K/blob/main/README.md); некоммерческие русские F5: [attashe/F5-TTS-RU](https://huggingface.co/spaces/attashe/F5-TTS-RU/raw/main/README.md)
- Обзоры и лицензии: [ocdevel.com](https://ocdevel.com/blog/20250720-tts), [chimitdorzhi.tech](https://chimitdorzhi.tech/en/ii-modeli/napravlenie/sintez-rechi/)

### Стартовые значения из окружения

`run.sh` / `run.ps1` / `game.sh` / `game.ps1` читают `VOLUME_FX`, `VOLUME_MUSIC`, `VOLUME_VOICE` (0–100) и `NPC_VOICE` (0/1): сначала переменная окружения, затем `pdm-game/settings.ini`, затем умолчание 80/70/100/1. Windows: `set VOLUME_FX=60` перед запуском `run.ps1`. Значения со страницы настроек в `settings.ini` не пишутся (скрипты не умеют писать файлы) — они действуют до выхода.

## Запись видео из игры (F9)

В `pdm-game/engine.ini` включено `record_video = 1`. F9 запускает `ffmpeg` (x11grab на Linux, gdigrab на Windows) на окно игры, повторное F9 заканчивает запись; файл `<дата>.mp4` лежит в каталоге Screenshots рядом со снимками F8. Нужен `ffmpeg` в PATH или `ffmpeg_path`. Звук — `record_audio_input`, например `-f pulse -i <sink>.monitor` или `-f dshow -i audio=<устройство>`. Не проверено на Windows.

Windows, звук игры: `record_audio_loopback = 1` в `engine.ini` (в `pdm-game` включено). Движок сам пишет то, что играет на устройстве вывода по умолчанию (WASAPI loopback, виртуальные устройства не нужны), и при остановке записи ffmpeg склеивает звук с видео: сначала в `Screenshots` появляются `<дата>.video.mp4` и `.pcm`, через пару секунд итоговый `<дата>.mp4`, части удаляются. Если звук отстаёт или опережает, меняйте `record_audio_skip_ms` (по умолчанию 300). `record_audio_input` (dshow) имеет приоритет. Не проверено на Windows: код собран только на Linux, где loopback-запись выключена.
