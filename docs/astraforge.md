# AstraForge для моделей «Корсаров»

AstraForge (https://github.com/Snodrod/AstraForge, исходники MIT) — Windows-студия поверх ComfyUI: картинка/описание → 3D → риг → экспорт. Здесь описано, что из его списка уже есть на ПК, как подключить имеющееся без повторной загрузки, и как использовать его для двух задач: улучшить модели оригинала и сделать «концептуально похожие» современные. Основной конвейер проекта (`docs/ai-models.md`) остаётся главным; AstraForge — удобная оболочка для ручной работы и сравнения.

## Что уже есть (проверено по SSH, 2026-11-02)

| Компонент установщика | Состояние | Примечание |
|---|---|---|
| AstraForge `C:\AstraForge` | стоит, профиль `lite` | `config\paths.json`: library, node, blender, forgeRuntime; `comfyDir`, `pixal3dDir` не заданы |
| Node.js | есть | свой `C:\AstraForge\runtime\node`, ещё системный 22.x |
| Blender 5.2 | есть | `C:\Program Files\Blender Foundation\Blender 5.2` (ещё 3.3 и 5.4 alpha в `C:\corsairs-remake`) |
| Ollama | есть | `qwen3` (теги `4b`, `32b`), `qwen3-coder`, `gemma`, `mistral` и др. **`qwen3-vl:8b` нет**, `qwen3:14b` нет |
| Pixal3D (веса) | есть, но **в другом формате** | `pixal3d_int8_convrot`, `pixal3d_multiview_int8_convrot`, `trellis_2_int8_convrot`, VAE, DINOv3, MoGe — в `Comfy-Desktop\ComfyUI-Shared\models`. AstraForge ждёт оригинал `TencentARC\Pixal3D\ckpts\*.safetensors` (~42 ГБ) |
| Pixal3D (движок) | есть как Easy-Install ComfyUI | Python 3.12.10, torch 2.8.0+cu128, ComfyUI-Trellis2 — тот же стек, но без метки `ASTRAFORGE PATCH` |
| Qwen-Image (edit 2511, 2.1) | есть | `diffusion_models`, `text_encoders`, `vae` в ComfyUI-Shared |
| Hunyuan3D-2 / 2mv / 2.1, SDXL, FLUX.2 klein, u2net, MV-Adapter | **нет** | в `checkpoints` только `stable_audio_3_medium` |
| Godot, клипы Quaternius | не проверялись, для нас не нужны | |

Места нет: на C: свободно **18,7 ГБ** (из 3,6 ТБ), D:/E: пусты (нет носителя), G: 3 ГБ, S: 1,3 ГБ. Полный набор установщика (88,7 ГБ) не поместится нигде — не ставить его целиком.

## Что ставить, а что нет

- **Pixal3D из AstraForge — не ставить.** Его движок и веса (~46–52 ГБ) дублируют то, что уже работает в вашем ComfyUI (воркфлоу `3d_pixal3d_multi_views.json`, `3d_pixal3d_trellis2_image_to_model.json`). Снимите в установщике `pixal3d`, `pixal3dw`, `pixal3dtest`.
- **Не ставить** `hy21`, `sdxl`, `vfx`, `godot`, `clips` (клипы нужны только для игр на Godot).
- **Можно поставить** `hy2` и `hymv` (по 4,9 ГБ — Hunyuan3D-2 и 2mv, влезают в 18,7 ГБ) как второй генератор формы для сравнения с Pixal3D. Для этого нужен ComfyUI AstraForge (`comfy`, ~10 ГБ с torch): вместе это почти всё свободное место. Поэтому сначала освободите C: или ставьте только если нужен именно Hunyuan.
- `vlm`: `ollama pull qwen3-vl:8b` (~6 ГБ) — только если хотите описывать картинки автоматически; не обязательно.

## Как подключить имеющееся

1. **Проверка без изменений:**
   ```powershell
   cd C:\AstraForge
   powershell -NoProfile -ExecutionPolicy Bypass -File installer\Install.ps1 -ScanOnly
   ```
   Установщик сам находит Node, Blender, Ollama и его модели (читает с диска) и ничего не качает.
2. **Свой ComfyUI вместо установки `comfy`:** переменная `ASTRA_COMFY_DIR` или ключ `comfyDir` в `config\paths.json`. Условие: в папке `.venv\Scripts\python.exe`, `main.py`, `comfy_extras\nodes_hunyuan3d.py`. Easy-Install использует `python_embeded`, а не `.venv`, поэтому **как есть не подходит**.
3. **Веса Hunyuan/SDXL:** положить (или сделать жёсткую ссылку `mklink /H`) в `C:\AstraForge\data\models\checkpoints` либо в `<comfy>\models\checkpoints`. Установщик не качает файл заново, если имя и размер совпадают.
4. **Pixal3D из AstraForge на готовом Easy-Install** (если всё же нужен): `ASTRA_PIXAL3D_DIR=C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI-Easy-Install`, запустить `python_embeded\python.exe -I installer\pixal3d\patch_trellis2.py <ComfyUI-Trellis2>` (предварительно сделать копию `nodes.py`) и положить оригинальные веса. Патч убирает автоскачивание DINOv3 и импорт meshlib. Не рекомендуется: оригинальные веса ~42 ГБ не помещаются, а int8-формат студия не читает.
5. **Перенос с C:** переменные `ASTRA_PIXAL3D_DIR`, `ASTRA_COMFY_DIR`, `ASTRA_FORGE_RUNTIME`; пути короткие, латиницей (до 90 символов).
6. Порты: студия 3210, её ComfyUI 8190, Pixal3D 8191. Ваш ComfyUI на 8188 не мешает.

## Улучшение моделей оригинала

AstraForge **не заменяет** привязку к оригинальному скелету `.an`: его Humanoid-риг другой. Поэтому используем только генерацию, а установку в игру делает наш `pdm_glb2gm.py`.

1. Виды оригинала в T-позе (Linux или Windows):
   `python tools\pdm_model_views.py pdm-game hero1 --size 1024 --tpose` → `pdm-game\data\ai_models\views_tpose\hero1_{front,right,back,left}.png`.
2. Улучшить виды в ComfyUI (`tools/comfy_view_refine.py`, Qwen-Image edit) — стиль, детали одежды, один и тот же персонаж на 4 кадрах.
3. Генерация формы: ваш ComfyUI (Pixal3D Multi Views, 4 вида) — основной путь; в AstraForge то же делает узел Pixal3D, если он стоит, а Hunyuan3D-2mv — альтернатива (до 4 видов).
4. Текстура: Pixal3D/TRELLIS.2 даёт PBR-текстуру; для Hunyuan — узел текстурирования AstraForge или MV-Adapter (нужен SDXL).
5. Упрощение: `pdm_mesh_optimize` / LODTailor (в поле `blender_path` указать Blender, например 5.4 alpha из `C:\corsairs-remake`). Для персонажей цель — десятки тысяч треугольников, не миллионы.
6. Экспорт GLB, затем установка в игру: `python tools\pdm_glb2gm.py …` (см. `docs/ai-models.md`). Результат проверять в игре, `error.log` пуст.

Проверка: сравните сетку из AstraForge и из вашего воркфлоу на одном персонаже (hero1) — по плотности, швам рук (T-поза) и размерам в игре.

## «Концептуально похожие современные» модели

Это не замена оригинала один в один, а новая модель по мотивам. Подходит для статичных предметов и для персонажей.

1. Источник: либо виды оригинала (шаг 1 выше) как референс, либо текстовое описание. Оригинальные картинки брать только из оригинала через конвертеры.
2. Современный вид: Qwen-Image edit с промптом вроде «тот же персонаж, современная детализация, PBR-материалы, реалистичные пропорции, пиратский костюм XVII века»; 4 ракурса, одна и та же T-поза. Сохранять соотношение частей тела (иначе привязка к костям даст перекос).
3. Далее те же шаги 3–6. Для статики (бочки, мебель) шаг привязки не нужен: меш подменяется масштабом и положением.
4. Корабли и локации так не заменять: у них метки (`locators`), привязанные к старой геометрии.
5. Для сравнения «до/после» делайте кадры через `demos/common/record.sh` и кладите в `media/`.

## Подводные камни

- Загрузка 88,7 ГБ, как на скриншоте установщика, провалится из-за места — снимать галочки по списку выше.
- Установщик возобновляет прерванные загрузки (`installer\downloads\`); после установки папку можно удалить.
- Бесплатные ноды meshlib (некоммерческая лицензия) патчем отключаются; дыры заделывает CuMesh.
- Запуск Pixal3D из AstraForge «поверх» рабочего Easy-Install может сломать воркфлоу из-за патча `nodes.py` — только с резервной копией.
- Перед любой установкой проверять место: `fsutil volume diskfree C:`.
