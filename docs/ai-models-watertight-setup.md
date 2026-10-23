# Установка цепочки PixelArtistry (watertight 3D) на Windows

Журнал настоящей установки на машине пользователя (Windows 11, RTX 5080 16 ГБ) и подводные камни. Общая схема конвейера — [ai-models.md](ai-models.md). Что проверено, отмечено «✔», остальное ещё не пройдено до конца.

## Зачем это нужно

Результат шаблона Comfy-Org (`RemeshMesh` 768, solid fill, сглаживание) для персонажа плохой: детали стёрты, руки склеены с плащом, поверхность «масляная». Автор PixelArtistry (видео https://www.youtube.com/watch?v=dmDrktqyT5o, репозиторий github.com/pixelartistry/PixelArtistry-Watertight-Meshes, MIT) берёт ту же модель Pixal3D / TRELLIS.2, но после неё строит сетку другими нодами MostAadTech:

1. Quad Reconstruct — чистит сырую сетку;
2. **WTiVo** — водонепроницаемая сетка из вокселей (1536, 12 млн proxy points; на 16 ГБ 2048 и 25 млн);
3. **LODTailor** — облегчает, сохраняя watertight;
4. Fast Merge — склеивает дубли вершин;
5. для игры: low-poly + запекание карт (Bake Forger), текстура 4096.

Дополнительно: фон убирает BiRefNet, поле зрения Pixal3D берёт MoGe (у нас было фиксированных 20°), шагов 20–24 вместо 12.

## Почему этот сценарий лучший

- Качество важнее лицензии (требование пользователя), а это единственная локальная цепочка, где сетка получается из вокселей, а не сглаживается. Руки и плащ остаются раздельными.
- Всё локально, без облака и платных API.
- Граф автора берётся как есть, и мы ничего не придумываем: `pdm_comfy_api.py` превращает его в API-граф, а остальной конвейер (`pdm_models_all.py` → оптимизация → `.gm`) не меняется.
- Один и тот же граф даёт и watertight-меш (01/01b), и игровой low-poly с картами (02), и текстуру для готовой сетки (03).
- Проверено автором на RTX 5080: 1536 — около 2 минут, 2048 — около 3,5 минут и 11 ГБ RAM.

Минусы: нужна отдельная среда Python 3.12 + Torch 2.8.0/CUDA 12.8 (см. ниже), ноды под GPL-3.0, результат зависит от seed (бывают дырки, нужен повторный запуск).

## Что ставится (по порядку)

### 0. Только Windows, ComfyUI запущен
Конвертер `pdm_comfy_api.py` берёт имена параметров у запущенного ComfyUI (`/object_info`), поэтому все ноды должны быть установлены до конвертации.

### 1. ComfyUI Easy-Install (не Comfy Desktop)  ✔

Установщик автора ожидает Easy-Install: `python_embeded`, `ComfyUI\custom_nodes`.

Подводные камни:
- **Comfy Desktop не подходит.** Его venv — Python 3.13. WTiVo поставляется как `cppmodules.cp312-win_amd64.pyd`, то есть нужен Python 3.12. Ошибка: `No module named 'wtivo_core'` / `'cppmodules'`.
- Установщик автора в Comfy Desktop не работает, потому что там нет `python_embeded`. Скрипт `tools/pdm_install_watertight_nodes.ps1` ставит те же ноды на тех же коммитах в любой ComfyUI, но в Desktop (Python 3.13) WTiVo всё равно не импортируется.
- Папку Easy-Install не распаковывать в корень диска, Program Files и пути с пробелами, запускать не от администратора.
- Лежит у нас в `C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install` (внутри репозитория, добавлена в `.gitignore`: иначе `git add -A` потащит гигабайты). Запуск — `Start ComfyUI.bat`.
- Comfy Desktop при запуске Easy-Install закрыть: порт 8188 один, конвертер мог говорить с ним, а не с нужным сервером. Какой процесс отвечает, видно так:
  `Get-CimInstance Win32_Process | ? CommandLine -match "main.py" | select ExecutablePath`.

### 2. Модели из Comfy Desktop без повторной загрузки  ✔ (найдены), ссылка на них — не проверена

Модели Desktop лежат в `C:\Users\User\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models` (подсказал yaml `Roaming\Comfy Desktop\instance-model-paths\inst-*.yaml`). Там уже есть trellis_2, pixal3d, moge, birefnet, dino_v3 и Qwen Image. Подключаются файлом `ComfyUI\extra_model_paths.yaml` в Easy-Install (`base_path` = эта папка, ключи `diffusion_models`, `vae`, `clip_vision`, `text_encoders`, `background_removal`, `geometry_estimation`) либо добавкой Easy-Models-Linker.

### 3. Torch 2.8.0 + CUDA 12.8  (ожидает)

Easy-Install ставит последний Torch (у нас 2.11, CUDA 13.0), а установщик Trellis2 останавливается на `Torch 2.11 is not supported. Supported: 2.8`. Нужно: `Add-Ons\Torch-Pack` → `Torch 2.8.0+cu128`. Для RTX 5080 (Blackwell) cu128 подходит. Затем снова запустить установщик Trellis2.

### 4. Trellis2 + Pixal3D (VisualBruno)  (ожидает)

`Add-Ons\Trellis2+Pixal3D @visualbruno`: ноды ComfyUI-Trellis2, из них CuMesh и O-Voxel. Для workflow 03 нужен ещё `Trellis2\encoders\shape_enc_next_dc_f16c32_fp16`.

### 5. Ноды PixelArtistry  (ожидает)

Файл `watertightMeshes_win_installer.bat` (читал целиком, он безопасный: клонирует 9 пакетов Mstafa-awad на закреплённых коммитах 2026-09-26, `pip` двух из них в `python_embeded`, докачивает модели из huggingface по запросу `[Y/N]`) кладётся в `Add-Ons`, ComfyUI закрыт, двойной щелчок. В итоге должны остаться только `[OK]`. Он сам выбирает сборку WTiVo: для RTX 50 — по умолчанию. Установщик не запускать из Desktop.

### 6. Конвертация и запуск

```
curl.exe -L -o tools\\model3d\\PixelArtistry_01b.json https://raw.githubusercontent.com/pixelartistry/PixelArtistry-Watertight-Meshes/HEAD/workflows/PixelArtistry_01b_Image_to_Watertight_Mesh_2K.json
python tools\\pdm_comfy_api.py tools\\model3d\\PixelArtistry_01b.json --save 331 --blender "C:\\Blender\\blender.exe" --out tools\\model3d\\watertight_api.json
python tools\\pdm_models_all.py pdm-game hero1 --steps model,optimize --workflow tools\\model3d\\watertight_api.json --crop 0.05 --redo
```

`--save`: 331 для 01/01b, 343 для 02, 341 для 03. Blender нужен чистый, без аддонов (иначе ошибки в консоли): распакованный zip и пустая папка `portable` рядом с `blender.exe`.

## Подводные камни по порядку, как они встретились

| Симптом | Причина | Что сделать |
|---|---|---|
| `unrecognized arguments: --save` | на Windows старая версия скрипта | `git pull` |
| `FileNotFoundError: PixelArtistry_01b_….json` | файла workflow нет в текущей папке | скачать curl'ом в `tools\\model3d` |
| `ComfyUI does not know the node MemoryCleaner` | ноды PixelArtistry не установлены (или отвечает не тот ComfyUI) | шаги 1–5; проверить `custom_nodes` и процесс на порту |
| `does not answer … 10061` | ComfyUI не запущен | `Start ComfyUI.bat`, ждать `To see the GUI go to` |
| `<вы>` в пути | в команде остался шаблон | подставить `User` |
| `no custom_nodes in …\\Documents\\ComfyUI` | Desktop хранит данные в `AppData\\Local\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\ComfyUI` | путь из командной строки процесса `main.py` |
| `wtivo_core`/`cppmodules` не найден | Python 3.13 в Comfy Desktop | отдельный Easy-Install (Python 3.12) |
| `Torch 2.11 is not supported` | Torch-Pack не переключён | `Torch 2.8.0+cu128` |
| PowerShell читает `3d` как число | — | шаг конвейера называется `model` |
| `No module named 'rtree'` в pdm_glb_optimize | не стоят зависимости оптимизатора для системного Python 3.14 | `pip install --user trimesh rtree fast-simplification`, затем `--steps optimize` |

## Если что-то пойдёт не так

- Дырки в сетке — запустить ещё раз (seed структуры случайный).
- Нехватка памяти на 2K — перезапустить ComfyUI, закрыть другие программы, либо взять 01 (1536).
- Блендер падает с ошибкой аддонов — portable Blender без аддонов.
- Проверка watertight — Blender 3D Print Toolbox → Check All; при импорте low-poly включать Merge Vertices.

## Авторство

PixelArtistry (workflows, MIT), MostAadTech / Mstafa-awad (WTiVo, LODTailor, Quad Reconstruct, Bake Forger, Fast Merge, CuMesh Decimate, Memory Cleaner, Mesh Encoder), VisualBruno (ComfyUI-Trellis2), Tavris1 (ComfyUI-Easy-Install), Comfy-Org (шаблоны Pixal3D & TRELLIS.2, MIT), Tencent ARC (Pixal3D), Microsoft (TRELLIS.2). Ноды MostAadTech — GPL-3.0 или MIT: для коммерческого использования проверять лицензию каждой ноды и модели.
