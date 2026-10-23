# Озвучка реплик CosyVoice 3 на Windows: установка, запуск, подводные камни

Пошаговая инструкция, проверенная на Windows 11, RTX 5080, 2026-10-22. Общая картина и сравнение моделей — в [voice-over.md](voice-over.md), здесь только то, что нужно, чтобы на чистой машине дойти до озвученных реплик.

Результат: `pdm-game/resource/sounds/voices/lines/<диалог>/<узел>.wav` для каждой из ~1977 реплик, голос берётся из образца персонажа (`voices/<имя>.wav`).

## 0. Что где происходит

| Машина | Что делает |
|---|---|
| Linux (разработка) | собирает `lines.jsonl` и образцы голосов из данных оригинала; игра |
| Windows с видеокартой | Whisper → `refs.tsv`, CosyVoice → WAV реплик |

На Windows нужны:
- `C:\CosyVoice` — репозиторий модели с весами (~6 ГБ);
- `C:\corsairs-remake` — с папками `tools\` (9 файлов) и `pdm-game\data\voice\lines.jsonl`, `pdm-game\resource\sounds\voices\*.wav` (252 образца).

Игровой архив `corsairs-remake-<дата>.zip` **не содержит `tools\`**. Скрипты берут из `dist/voice-tools.zip` или из репозитория `github.com/POMXARK/corsairs-remake`, ветка `pdm-launch`, папка `tools/`. Распаковывать так, чтобы получилось `C:\corsairs-remake\tools\cosyvoice_batch.py`.

## 1. Окружение

Нужен **Python 3.10**. Системный Python 3.14 не подходит: у `onnxruntime==1.18.0`, `numpy==1.26.4`, `onnx==1.16.0` нет колёс под него. Самый надёжный способ — Miniconda, потому что `pynini` (нужен CosyVoice для нормализации текста) на Windows ставится только из conda-forge.

### 1.1 Miniconda

`winget` на некоторых системах отсутствует. Ставить прямым установщиком (PowerShell):

```powershell
curl.exe -L -o "$env:TEMP\miniconda.exe" https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe
Start-Process -Wait "$env:TEMP\miniconda.exe" -ArgumentList "/InstallationType=JustMe","/RegisterPython=0","/AddToPath=0","/S","/D=$env:USERPROFILE\miniconda3"
Test-Path "$env:USERPROFILE\miniconda3\Scripts\conda.exe"    # True
```

`/AddToPath=0` — сознательно: `conda` не появляется в обычном `cmd`/PowerShell, её надо подключать вручную (см. 1.2). Страница anaconda.com/download ведёт на регистрацию, установщик берут по прямой ссылке выше.

### 1.2 Подключение conda в каждом новом окне PowerShell

```powershell
& "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
conda activate cosyvoice
cd C:\corsairs-remake
```

Признак правильного окна — `(cosyvoice)` в начале строки. Если его нет, команды `pip` уходят в системный Python (см. «Подводные камни», п. 1).

Если PowerShell запрещает скрипты: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### 1.3 Создание окружения

```powershell
conda create -n cosyvoice -y -c conda-forge --override-channels python=3.10
conda activate cosyvoice
python --version        # 3.10.x
pip --version           # путь внутри miniconda3\envs\cosyvoice
conda install -y -c conda-forge --override-channels pynini==2.1.5 ffmpeg
```

`--override-channels` обходит запрос на принятие условий канала `defaults`.

### 1.4 PyTorch под RTX 5080

Видеокарты серии 50 (Blackwell) требуют CUDA 12.8. Индекс `cu121` из `requirements.txt` CosyVoice **не подходит**.

```powershell
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
pip install "setuptools<81" wheel
```

Версия **2.8.0**, не новее (см. «Подводные камни», п. 19). Скачивание ~2,8 ГБ. Для других видеокарт (30xx/40xx) тоже подойдёт cu128.

### 1.5 Зависимости CosyVoice

```powershell
cd C:\CosyVoice
Get-Content requirements.txt | Where-Object { $_ -notmatch '^(torch|deepspeed|tensorrt|onnxruntime-gpu|openai-whisper)' } | Set-Content req_win.txt -Encoding ascii
pip install -r req_win.txt
pip install onnxruntime-gpu faster-whisper
pip install tiktoken more-itertools
pip install openai-whisper==20231117 --no-deps --no-build-isolation
```

Зачем так:
- Строки `torch*` убираем, чтобы pip не вернул старый torch 2.3 с `cu121` поверх `cu128`.
- `deepspeed`, `tensorrt*` — только Linux; в `requirements.txt` они помечены `sys_platform == "linux"`, мы их тоже выкидываем.
- `Set-Content -Encoding ascii` — в PowerShell 5 обычное перенаправление `>` пишет UTF-16, и pip файл не читает.
- `openai-whisper` CosyVoice импортирует (`cosyvoice/cli/frontend.py`: `import whisper`), поэтому его **нужно** поставить, но без зависимостей (`--no-deps`), иначе он потянет свой torch. Сборка без изоляции (`--no-build-isolation`) нужна, чтобы использовался установленный `setuptools` с `pkg_resources`.
- `faster-whisper` — для `pdm_voice_refs.py` и `pdm_voice_check.py`. Это другой пакет, не `openai-whisper`.

Установка идёт 5–15 минут; во время неё pip может долго «подбирать версии typer» — это нормально, ждать.

### 1.6 Веса модели

```powershell
python -c "from huggingface_hub import snapshot_download; snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='C:/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B')"
```

20 файлов, ~10 ГБ (llm.pt, llm.rl.pt, flow.pt, onnx-модели), заняло 14 минут при ~2 МБ/с. Сообщение «hf_xet is not installed» — предупреждение, не ошибка. Обрыв безопасен: повторный запуск докачивает.

### 1.7 Проверка

```powershell
cd C:\CosyVoice
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -c "import sys; sys.path[:0]=['C:/CosyVoice','C:/CosyVoice/third_party/Matcha-TTS']; from cosyvoice.cli.cosyvoice import AutoModel; AutoModel(model_dir='pretrained_models/Fun-CosyVoice3-0.5B'); print('OK')"
```

Ожидается `2.8.0+cu128 True NVIDIA GeForce RTX 5080` и в конце `OK`. Следующие строки в выводе безвредны:
- `Sliding Window Attention is enabled but not implemented for sdpa`;
- `FutureWarning: torch.nn.utils.weight_norm is deprecated`;
- `Memcpy nodes are added to the graph ... CUDAExecutionProvider` и `Some nodes were not assigned ...` (onnxruntime);
- `modelscope - ERROR - Authentication token does not exist` + `no frontend is avaliable`: не загрузился `wetext` (нормализация китайского и английского). Русскому не мешает.

## 2. Данные для озвучки

```powershell
cd C:\corsairs-remake
dir pdm-game\data\voice\lines.jsonl                      # ~1,7 МБ
dir tools\cosyvoice_batch.py
(dir pdm-game\resource\sounds\voices\*.wav).Count        # 252
```

`lines.jsonl` — по строке на реплику: диалог, узел, говорящий, образец (`ref`), текст, куски (`chunks`) и выходной файл (`out`).

## 3. Тексты образцов (Whisper)

Клон голоса точнее, когда модель знает, что произносится в образце. Тексты хранятся в `pdm-game\data\voice\refs.tsv`.

```powershell
python -I tools\pdm_voice_refs.py pdm-game --device cuda
```

Первый запуск скачивает `large-v3` (~3 ГБ). Готовые строки файла повторный запуск **не перезаписывает**, поэтому правки вручную сохраняются.

**Файл надо просмотреть и поправить руками.** Whisper ошибается на коротких образцах. Реальные примеры из первого прогона:

| Файл | Что распознал Whisper | Что надо |
|---|---|---|
| `christopher_claystone.wav` | «Субтитры сделал DimaTorzok» | реальную фразу персонажа (галлюцинация Whisper на тихом/коротком звуке) |
| `carlotta_fellidad.wav`, `catalina.wav` | «Вы ищете кого-нибудь, сеньор?» в «ёлочках» | убрать кавычки |
| `bruyant___town_guard.wav` | «— Идите, идите...» | убрать тире |
| `carlos___town_guard.wav` | «КОМО СТАЙ, СИНЬОР?» | как есть, но проверить на слух |

Искать подозрительные строки: «Субтитры», «Редактор», «Продолжение следует», «Спасибо за просмотр» — типичные галлюцинации Whisper на тишине.

## 4. Озвучка

### 4.1 Проба

```powershell
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --limit 10
```

Файлы появятся в `pdm-game\resource\sounds\voices\lines\`. Прослушать 2–3. Режимы выбираются автоматически:
- образец + его текст в `refs.tsv` → `zero_shot` (лучший клон);
- нет текста → `cross_lingual` (хуже);
- `--instruct` → `instruct2`: меняет манеру (возраст, настроение, темп) по `tools/voice/instruct_prompt.txt`, тембр остаётся из образца.

### 4.2 Полный прогон

```powershell
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice
```

- Печатает `N/всего файл ~M min left`.
- Прерывать можно Ctrl+C: готовые реплики пропускаются, повторный запуск продолжает.
- Оценка: 2–7 часов на RTX 5080. Не закрывать окно, не отправлять ПК в сон.
- Для одного персонажа/диалога: `--only alonso_mentato`.
- В конце сам вызывает `pdm_voice_lines.py --bind` (привязка файлов к репликам).

### 4.2а Несколько процессов на одной видеокарте (`--shard`)

Один процесс использует видеокарту не полностью: речь генерируется небольшими шагами, поэтому 2–3 процесса вместе обычно идут в 1,5–2 раза быстрее одного. Ключ добавлен в `cosyvoice_batch.py` (наш, в апстриме CosyVoice его нет).

`--shard K/N` значит «N процессов, этот берёт свою долю под номером K». Процесс берёт каждую N-ю реплику списка, начиная с K (в коде `todo[K::N]`). **Номера долей идут с нуля**: для трёх процессов это `0/3`, `1/3`, `2/3`. Доли `3/3` не бывает: она совпала бы с `0/3` (3, 6, 9… — те же реплики), поэтому скрипт на такое отвечает ошибкой.

```powershell
# в трёх окнах PowerShell, в каждом: conda-hook, conda activate cosyvoice, cd C:\corsairs-remake
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --shard 0/3
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --shard 1/3
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --shard 2/3
# когда все три закончили, один раз:
python -I tools\pdm_voice_lines.py pdm-game --bind
```

Правила:
- Сначала остановить прежний прогон без `--shard` (Ctrl+C), иначе он будет озвучивать то же самое.
- Доли делят работу по списку, составленному при запуске. Если окно закрыть и запустить `0/3` заново, оно возьмёт свою треть **оставшихся** реплик. Поэтому после остановки лучше перезапускать все доли вместе с тем же N.
- Число процессов можно менять между запусками (было 3, стало 2): готовые файлы пропускаются, остаток делится заново.
- Шарды **не** выполняют `--bind` в конце, его запускают вручную один раз после всех.
- Каждому процессу нужно примерно 4 ГБ видеопамяти и 5–6 ГБ оперативной. На RTX 5080 (16 ГБ) и 32 ГБ ОЗУ комфортно 2, впритык 3. Если память кончилась (ОЗУ > 90 %, процесс убит или `CUDA out of memory`), закрыть одно окно и перезапустить оставшиеся как `0/2`, `1/2`.
- Оценка `~M min left` в каждом окне считается только по своей доле. Общее время — это максимум из трёх.
- Сид зависит от реплики, а не от процесса: звук не зависит от того, сколько было долей.
- **Ускорения на одной видеокарте нет** (проверено на RTX 5080): три процесса дали rtf около 2,5 каждый вместо 0,85 у одного, суммарная скорость та же, а ПК при этом тормозит. `--shard` имеет смысл для нескольких видеокарт; на одной лучше один процесс. Опция `--fp16` (половинная точность) может дать выигрыш: сравнить rtf на `--limit 10` и проверить звук на слух.

### 4.3 Проверка и перегенерация

```powershell
python -I tools\pdm_voice_check.py pdm-game
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --redo pdm-game\data\voice\redo.txt
```

`pdm_voice_check.py` слушает результат Whisper'ом и пишет `redo.txt` с провалившимися репликами. `--redo` удаляет их и озвучивает заново **с другим сидом** (счётчик в `tries.json`). Повторять, пока `redo.txt` не опустеет.

Модель недетерминирована по сиду: один и тот же запуск даёт тот же звук, перегенерация — другой.

### 4.4 Возврат в игру

Скопировать на машину с игрой:
- `pdm-game\resource\sounds\voices\lines\` целиком;
- `pdm-game\data\voice\` (`lines.jsonl`, `refs.tsv`, `tries.json`).

## 5. Подводные камни и ошибки

Все из реальной установки.

### 1. `pip` ставит в Python 3.14 вместо окружения

Симптомы: в логе `C:\Python314\...` или `...Python314\site-packages`, `Defaulting to user installation because normal site-packages is not writeable`, `Requires-Python >=3.7,<3.11`, `No matching distribution found for onnxruntime==1.18.0`. Причина: окно открыто без `conda activate cosyvoice`; новое окно PowerShell **не помнит** активацию.
Лечение: подключить conda (1.2) и убедиться, что в строке есть `(cosyvoice)`, затем повторить установку. Всё, что поставлено в 3.14 до этого, для озвучки бесполезно.

### 2. `"conda" не является внутренней или внешней командой`

`conda` не в PATH (установка с `/AddToPath=0`) или окно обычное, а не Anaconda Prompt. В PowerShell подключать `conda-hook.ps1` (1.2). В `cmd` — `%USERPROFILE%\miniconda3\Scripts\activate.bat`.

### 3. `%USERPROFILE%` в PowerShell не работает

Это переменная `cmd`. В PowerShell: `$env:USERPROFILE`. Симптом: `Не удается найти путь "C:\Users\User\%USERPROFILE%\..."`.

### 4. `winget` не найден

Не везде установлен. Использовать прямой установщик Miniconda (1.1).

### 5. `pkg_resources` не найден при сборке `grpcio`

`ModuleNotFoundError: No module named 'pkg_resources'` — `setuptools` ≥ 81/82 больше не содержит `pkg_resources`. Нужны `setuptools<81`. Под Python 3.10 для `grpcio==1.57.0` есть готовое колесо, сборка не нужна; ошибка возникает только при установке в слишком новый Python.

### 6. Конфликты `setuptools` с другими пакетами

`llama-index-core requires setuptools>=80.9.0, but you have setuptools 69.5.1`: пакеты системного Python 3.14 хотят новый `setuptools`, а мы его понизили. Это следствие ошибки из п. 1. Починка вне окружения: `pip install "setuptools>=82"`. В окружении `cosyvoice` держать `setuptools<81`.

### 7. Torch не видит RTX 5080 / падает на ядрах

`torch.cuda.is_available()` = False, или `no kernel image is available`, или предупреждение `sm_120 is not compatible`. Причина: torch собран под CUDA ≤12.1. Нужен `--index-url https://download.pytorch.org/whl/cu128`. Устанавливать **до** `req_win.txt` и не давать pip его перезаписывать (строки `torch*` убраны из файла).

### 8. `findstr ... > req_win.txt` ломает pip

В PowerShell 5 `>` пишет UTF-16. Использовать `Get-Content | Where-Object | Set-Content -Encoding ascii` (1.5).

### 9. `No module named 'whisper'` при загрузке CosyVoice

CosyVoice импортирует `openai-whisper`, а мы его исключили из `req_win.txt`. Ставить отдельно (1.5): `--no-deps --no-build-isolation`.

### 10. `Xet Storage is enabled ... hf_xet is not installed`

Предупреждение. Загрузка идёт обычным HTTP, медленнее. Ускорить: `pip install hf_xet`.

### 11. `modelscope ... 403 ... Authentication token does not exist`, `no frontend is avaliable`

Не скачался `wetext` с modelscope. Нормализация текста для китайского/английского выключена, русский работает. Игнорировать.

### 12. Whisper-галлюцинации в `refs.tsv`

«Субтитры сделал DimaTorzok» и подобное на тихих или очень коротких образцах. Править руками, см. раздел 3. Скрипт не перезапишет исправленные строки.

### 13. Короткие образцы

Большинство образцов короче 3 с (медиана ~2,5 с); CosyVoice клонирует хорошо с 3–10 с. Самые длинные: `member_of_brotherhood` 10,9 с, `alonso_mentato` 7,6 с, `christian_auberive` 7,2 с. Для коротких голос выйдет менее похожим. Варианты: общий образец типа (`peasant`, `pirate`), режим `--instruct`, склейка нескольких фраз одного персонажа.

### 14. `faster-whisper` не находит CUDA-библиотеки

Ошибка с `cublas64_12.dll` или `cudnn`. Запустить `pdm_voice_refs.py` / `pdm_voice_check.py` с `--device cpu` (медленнее, но работает), либо поставить CUDA 12 runtime.

### 15. Зависимости pip не сходятся (`typer` и др.)

`pip is looking at multiple versions of typer` — не ошибка, а подбор версий. Ждать, не прерывать.

### 16. `pip install faster-whisper` меняет `huggingface-hub`

`transformers 4.51.3` требует `huggingface-hub<1.0`. Если CosyVoice падает с ошибкой импорта из `huggingface_hub`: `pip install "huggingface-hub<1.0"`.

### 17. Скрипты запускать с `-I` и из `C:\corsairs-remake`

`python -I` отключает подхват модулей из текущей папки. Пути в командах (`pdm-game`) относительные к `C:\corsairs-remake`. Из другой папки скрипт не найдёт данные.

### 19. `ImportError: TorchCodec is required for load_with_torchcodec`

С torchaudio 2.9+ (на сегодня ставится 2.11) `torchaudio.load/save` идут только через `torchcodec`, а `cosyvoice/utils/file_utils.py` вызывает `torchaudio.load(wav, backend='soundfile')`. Падает при первой же реплике, сразу после предупреждения про `wetext`. Лечение: откатить на `torch==2.8.0 torchaudio==2.8.0` с индексом `cu128` (поддерживает Blackwell, `soundfile`-бэкенд на месте). Ставить `torchcodec` не стоит: ему нужны DLL ffmpeg подходящей версии, а conda ставит ffmpeg 9.

### 18. Прогон оборвался

Ничего не потеряно: готовые реплики пропускаются. Запустить ту же команду снова.

## 6. Краткая шпаргалка

```powershell
& "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
conda activate cosyvoice
cd C:\corsairs-remake
python -I tools\pdm_voice_refs.py pdm-game --device cuda          # один раз, потом поправить refs.tsv
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --limit 10    # проба
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice               # всё
python -I tools\pdm_voice_check.py pdm-game                                   # проверка
python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --redo pdm-game\data\voice\redo.txt
```
