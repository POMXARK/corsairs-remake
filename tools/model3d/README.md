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
