# Workflow ComfyUI для 3D-моделей

Сюда кладётся `image_to_model_api.json` — шаблон «Pixal3D: Multi Views to 3D» (или «Pixal3D & TRELLIS.2: Image to Model»), экспортированный через Workflow → Export (API), с узлами `IMAGE`, `IMAGE_RIGHT`, `IMAGE_BACK`, `IMAGE_LEFT`, `SEED`, `FACES`, `SAVE`. Как собрать — `docs/ai-models.md`, шаг 2.

## pixal3d_4views.json — готовые 4 вида → Pixal3D Multiview → GLB

Воркфлоу сделан из PixelArtistry-Pixal3D-Multiview (MIT): вырезаны шаги «текст → картинка» и «лист-развёртка» (Qwen), вместо них четыре узла `LoadImage`. Дальше как в оригинале: `RemoveBackground` (BiRefNet) → `ImageCropToMask` 1024² → `Pixal3DMultiViewConditioning` (FOV 20) → форма → текстура → запекание → GLB (`output/3d/ComfyUI`). Нужны только модели, которые уже стоят (qwen/pe_* не нужны).

Как пользоваться:
1. Виды: `python tools\pdm_model_views.py pdm-game <модель> --size 1024 --tpose`.
2. Скопировать `hero1_{front,left,back,right}.png` из `pdm-game\data\ai_models\views_tpose\` в `ComfyUI\input\`.
3. Перетащить `pixal3d_4views.json` в ComfyUI, в четырёх узлах `LoadImage` выбрать файлы, Run.
4. Меш скрученный/раздвоенный — поменять местами входы `left` и `right` в `Pixal3DMultiViewConditioning` (у `pdm_model_views` порядок front/right/back/left).

### pixal3d_4views_refine.json — то же, но сначала Qwen-Image 2.1 Edit перерисовывает каждый вид

Между `LoadImage` и `RemoveBackground` стоят четыре свёрнутых узла `Refine <вид>` (подграф шага 2 PixelArtistry, 1024×1024, один seed на все виды, `refine_prompt` выключен). Они убирают грани полигонов и размытую текстуру оригинала — иначе Pixal3D точно повторяет «лоу-поли» вид. Промпт каждого узла: тот же ракурс, та же T-поза и костюм, гладкая поверхность, реалистичная ткань; правится в развёрнутом узле. Перерисованные виды сохраняются в `output/PixelArtistry/03_views/`. Старая версия `pixal3d_4views.json` осталась. Нужна модель `qwen3.5_9b_…_pe_i2i` (у вас есть) — подграф её загружает, хотя `refine_prompt` выключен.


## pixal3d_parts_auto.json — то же, но персонаж режется на части сам

Сделан из `pixal3d_4views_refine.json` скриптом `make_parts_workflow.py`: четыре `LoadImage` заменены узлом `PDM Part Views`, после `Save 3D` стоит `PDM Part Save`. Узлы — в `comfy_nodes/pdm_parts` (свои, MIT как проект); ComfyUI умеет вызывать внешние скрипты только через такие узлы, обычными узлами это нельзя.

- **PDM Part Views** запускает `pdm_model_views.py --parts` (если видов части ещё нет), обрезает виды по фигуре (у головы поле меньше — лицо крупнее), отдаёт 4 вида и 4 промпта для узлов Qwen-перерисовки. У головы в промпте про открытые глаза, радужки и зрачки, у рук — про пять пальцев. `part_index` растёт сам после каждого запуска, поэтому **Batch count = 6** в меню Run проходит голову, торс, обе руки, саблю и ноги подряд.
- **PDM Part Save** кладёт GLB в `pdm-game/data/ai_models/glb/<модель>_<часть>.glb` и запускает `pdm_glb_optimize.py` с числом граней и текстурой части (голова 15 000/2048, торс 20 000/2048, руки 8 000/1024, сабля 4 000/1024, ноги 15 000/2048; `faces`/`tex` ≠ 0 меняют). Когда готовы все шесть, пишет команду установки в игру.
- Процесс виден в графе: у обоих узлов текстовое поле `log`, превью исходных видов, группы STEP 0…5 подсвечиваются по ходу, прогресс — в консоли ComfyUI.

Установка: `powershell -ExecutionPolicy Bypass -File tools\model3d\install_parts.ps1 -Comfy <папка ComfyUI>`, перезапустить ComfyUI, перетащить `pixal3d_parts_auto.json`. Перед запуском закрыть ENGINE.exe.
Не проверено на ComfyUI (написано без запуска): структура `FILE_3D` из `Save 3D` — узел ищет путь в строке, словаре или полях объекта, а если не нашёл, берёт самый новый `.glb` в `output`.
