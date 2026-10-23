# Доработка геометрии оригинальной модели (UltraShape)

Нейросеть берёт грубую сетку оригинала (hero1, 1828 граней) и картинку-подсказку и достраивает на этой геометрии детали: пальцы, складки, лицо. Поза и силуэт задаются оригиналом, поэтому руки не слипаются с плащом, а глаза берутся с вида.

Что получается на выходе: **новая закрытая сетка без UV, костей и текстуры** (`data/ai_models/glb_refined/<имя>.glb`). Это исходник для запекания карт на оригинальные полигоны и для `pdm_model_check.py`, а не готовая модель игры.

## 0. Лицензия — прочитать до установки

UltraShape распространяется по **Tencent Hunyuan 3D 2.1 Community License** (`UltraShape-1.0/LICENSE`): она **не действует в ЕС, Великобритании и Южной Корее**, ограничивает использование по числу пользователей и не является свободной. Правило проекта — только свободные лицензии. Если вы в ЕС, использовать UltraShape нельзя, а если вне ЕС, решение остаётся за вами. Результат этой ветки в `CREDITS.md` без лицензии не вписывается. Свободная замена без нейросети: подогнать детализированную сетку `hero1_watertight.glb` на оригинальную топологию (проекция вершин), она ничего не устанавливает.

## 1. Что нужно

- Windows 11, ComfyUI из `C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI` (Python 3.12, torch 2.8.0+cu128, как в `ai-models-watertight-setup.md`).
- Видеокарта 16 ГБ (RTX 5080): модель занимает 8–12 ГБ, сама доработка ещё около 8 ГБ при `--octree 384`, 16 ГБ при 512. Ставьте `--low-vram`.
- Диск: веса несколько ГБ.

## 2. Установка (один блок PowerShell)

```powershell
cd C:\corsairs-remake
git pull origin pdm-launch
$cu = "C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes"
git clone https://github.com/jtydhr88/ComfyUI-UltraShape1 "$cu\ComfyUI-UltraShape1"
$py = (Get-ChildItem C:\corsairs-remake\ComfyUI-Easy-Install -Recurse -Filter python.exe -Depth 4 | Select-Object -First 1).FullName
$py
& $py -m pip install -r "$cu\ComfyUI-UltraShape1\requirements.txt"
New-Item -ItemType Directory -Force "C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models\UltraShape"
curl.exe -L -o "C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models\UltraShape\ultrashape_v1.pt" https://huggingface.co/infinith/UltraShape/resolve/main/ultrashape_v1.pt
```

- Строка `$py` печатает найденный Python: он должен лежать внутри `ComfyUI-Easy-Install` (embedded или venv ComfyUI), не системный. Если найден чужой, укажите путь вручную.
- Необязательные пакеты: `cubvh` (быстрый marching cubes), `flash_attn` — без них нода работает на запасных вариантах.
- Затем **перезапустить ComfyUI** и в консоли найти строку `[ComfyUI-UltraShape1] [OK] Loaded successfully!`. Строка `Failed to load` с Traceback означает не поставившуюся зависимость: поставьте её через `$py -m pip install <пакет>`.

## 3. Запуск

Нужны виды модели (`pdm_model_views.py`, шаг 1 из `ai-models.md`) — картинка `<имя>_front.png` подсказывает нейросети, как выглядит деталь. Оригинал в GLB команда делает сама (`pdm_gm2glb.py`).

```powershell
cd C:\corsairs-remake
git pull origin pdm-launch
python tools\pdm_model_views.py pdm-game hero1
python tools\pdm_mesh_refine.py pdm-game hero1 --comfy http://127.0.0.1:8188 --low-vram --octree 384
```

Результат: `pdm-game\data\ai_models\glb_refined\hero1.glb`. Посмотреть:
```powershell
& "C:\corsairs-remake\blender-5.4.0-alpha+main.93eeecf73c12-windows.amd64-release\blender.exe" -b -P C:\corsairs-remake\tools\pdm_glb_preview.py -- --out C:\corsairs-remake\hero1_refined.png --size 512 C:\corsairs-remake\pdm-game\data\ai_models\glb\hero1_orig.glb C:\corsairs-remake\pdm-game\data\ai_models\glb_refined\hero1.glb
start C:\corsairs-remake\hero1_refined.png
```
(слева оригинал, справа доработанная сетка; путь `--out` только абсолютный).

Часть за частью (как `--parts`): `python tools\pdm_model_views.py pdm-game hero1 --parts`, затем `python tools\pdm_mesh_refine.py pdm-game hero1_head hero1_arm_l ...`; сетка части берётся из `<имя>_orig.glb`, которую пишет `pdm_gm2glb.py`.

## 4. Параметры консоли `pdm_mesh_refine.py`

| Параметр | По умолчанию | Что делает |
|---|---|---|
| `game` `models...` | — | папка игры и модели (`hero1`, части `hero1_head`) |
| `--comfy` | `http://127.0.0.1:8188` | адрес запущенного ComfyUI |
| `--image` | `views_refined/<имя>_front.png`, иначе `views/` | картинка-подсказка |
| `--checkpoint` | `ultrashape_v1.pt` | файл весов из `models/UltraShape/` |
| `--config` | `infer_dit_refine.yaml` | конфиг из `UltraShape-1.0/configs` |
| `--dtype` | `bfloat16` | точность: `float16`, `bfloat16`, `float32` |
| `--low-vram` | выкл. | выгружать части модели в память CPU: медленнее, но меньше видеопамяти |
| `--steps` | 50 | шагов диффузии (10–200); больше — аккуратнее и дольше |
| `--guidance` | 5.0 | насколько картинка влияет на результат (1–15); если форма расходится с картинкой, поднять |
| `--octree` | 384 | разрешение сетки (256–2048): больше — больше деталей и видеопамяти (384 ≈ 8 ГБ, 512 ≈ 16 ГБ) |
| `--chunks` | 8000 | порция при декодировании (1000–50000); меньше — экономнее и медленнее |
| `--latents` | 0 | число латентов оригинала (0: из конфига); больше — больше деталей |
| `--seed` | 42 | зерно; `--redo` берёт следующее |
| `--mc-level` | 0.0 | порог поверхности (−0,1…0,1): сдвигает поверхность внутрь или наружу |
| `--box` | 1.0 | масштаб рамки (0,5–2): меняет размер результата в кадре |
| `--remove-bg` | выкл. | убрать фон с картинки-подсказки (виды уже на сером фоне) |
| `--redo` | выкл. | сделать заново то, что уже есть |
| `--out` | `data/ai_models/glb_refined` | куда класть результат |

## 5. Что дальше с результатом

1. Сравнить с оригиналом (команда предпросмотра выше).
2. Запечь карты (нормали, AO) доработанной сетки на оригинальные полигоны: оригинал `<имя>_orig.glb` — низкополигональная цель, `glb_refined` — высокополигональный источник (Bake Forger из workflow 03 или bake в Blender).
3. Установить в игру: топология, UV и кости оригинала не меняются, так что анимации работают без перепривязки.

Пункт 2 пока вручную: готового скрипта запекания в проекте нет.

## 6. Если не работает

| Сообщение | Причина и решение |
|---|---|
| `ComfyUI has no node UltraShape...` | нода не загрузилась: проверить консоль ComfyUI при запуске, шаг 2 |
| `CUDA out of memory` | `--low-vram`, `--octree 320`, `--chunks 4000`, закрыть Blender и браузер с WebGL |
| `Mesh file not found` | сетка не загрузилась в `input\pdm_models`: проверить, что ComfyUI запущен из той же папки |
| `Tensor size mismatch` | слишком простая сетка (отдельная часть из десятков граней); нода дополняет воксели сама, иначе взять часть крупнее |
| `no 3D file in the outputs` | узел Save 3D не прошёл проверку: смотрите текст `ComfyUI rejects nodes` выше |
| результат пустой или кашеобразный | поднять `--guidance 7`, `--steps 80`, проверить картинку `_front.png` (персонаж целиком, серый фон) |

Предупреждение: UltraShape обучен на грубых сетках Hunyuan3D (воксельные, 20–50 тысяч граней). Угловатый оригинал в 1828 граней далеко от этого, и результат непредсказуем: проверяйте глазами и `pdm_model_check.py`.

Авторство: UltraShape 1.0 (PKU-YuanGroup, Tencent), плагин ComfyUI-UltraShape1 (jtydhr88).
