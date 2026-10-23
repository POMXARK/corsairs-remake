# Текстуры вместо новой модели: глубина и высокое разрешение

Оригинальные модели имеют малое число граней и текстуры 64–256 px. Нейрогенерация меша целиком ломает руки и саблю
(docs/ai-models.md), поэтому два безопасных пути:

- **A. Только текстуры.** Меш `.gm` остаётся как есть (кости, анимации), текстуры становятся 512–1024 px без размытия.
- **B. Голова нейросетью, остальное текстурами.** Лицо — самое заметное, там нужна геометрия; тело, ноги, руки и сабля
  остаются оригинальными с новыми текстурами.

UV не зависят от размера текстуры: файл `.tx` подменяется под тем же именем, `.gm` не трогается.

## Что даёт «глубину»

В движке у моделей нет нормал-мап (они есть только у моря, `sea.cpp`), поэтому глубина — это:

1. **Геометрия** — только в варианте B для головы (нейро-меш с 12 000 граней вместо ~580).
2. **Рельеф в цвете** — `--depth`: складки, швы и просветы вышивки темнее, выступы светлее.

## Как избежать размытия

`--method esrgan` (по умолчанию) рисует новые детали моделью Real-ESRGAN x4plus (BSD-3-Clause) через ComfyUI.
`--method lanczos` — только запасной вариант без ComfyUI: он увеличивает, но деталей не добавляет, картинка остаётся мягкой.

Модель апскейла кладётся один раз в `ComfyUI-Easy-Install\ComfyUI\models\upscale_models\`:

```powershell
cd C:\corsairs-remake\ComfyUI-Easy-Install\ComfyUI\models\upscale_models
curl.exe -L -o RealESRGAN_x4plus.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
```

Файл `4x-UltraSharp.pth` резче, но лицензия CC BY-NC-SA (не коммерческая): брать его только если проект остаётся портфолио.
Выбирается `--upscaler 4x-UltraSharp.pth`.

## Вариант A: только текстуры

ComfyUI должен быть запущен.

```powershell
cd C:\corsairs-remake
git pull origin pdm-launch
python tools\pdm_tex_upscale.py pdm-game hero --depth 0.4
.\pdm-game\game.ps1 run Debug town
```

- `hero` — модель игрока в городе; `hero1` (Nicolas Sharp) берёт часть текстур `hero_*` общими, они поменяются и там.
- Сначала 512 px: `--max 512`; потом 1024: `--max 1024` (по умолчанию).
- Не понравился результат: `python tools\pdm_tex_upscale.py pdm-game hero --restore` вернёт оригиналы.
- Повторный запуск (другой `--depth`, другой `--scale`) всегда начинает с оригинала из `data/ai_models/tex_orig`, а не с прошлого результата.
- Часть текстур можно оставить: `--skip-tex hero_hvostik`, или менять только нужные: `--only-tex hero_body hero_new_body`.

## Вариант B: голова нейросетью, остальное текстурами

```powershell
cd C:\corsairs-remake
git pull origin pdm-launch
python tools\pdm_models_all.py pdm-game hero --parts --only-parts head --quality normal --install
python tools\pdm_tex_upscale.py pdm-game hero --depth 0.4 --skip-tex hero_head hero_hvostik
.\pdm-game\game.ps1 run Debug town
```

- Первая строка создаёт только голову: виды, рефайн и модель нужны для одной части, торс, руки, ноги и сабля остаются оригиналом.
- Вторая строка меняет текстуры всего остального; `--skip-tex` оставляет текстуры головы и хвоста, чтобы не испортить
  то, что пришло с нейро-головой. Если после установки имя текстуры головы другое, добавь его в `--skip-tex`.
- Откат головы: `python tools\pdm_glb2gm.py pdm-game hero --restore`; текстур: `python tools\pdm_tex_upscale.py pdm-game hero --restore`.

## Параметры

| Параметр | Что делает |
|---|---|
| `--scale 4` | во сколько раз увеличить |
| `--max 1024` | сторона не больше этого |
| `--method esrgan\|lanczos` | нейро-апскейл (по умолчанию) или запасной без ComfyUI |
| `--upscaler FILE` | файл из `models/upscale_models` |
| `--depth 0..1` | тёмные складки и швы, светлые выступы (0.4 — для начала) |
| `--only-tex`, `--skip-tex` | какие текстуры менять или оставить (без `.tga`) |
| `--restore` | вернуть оригиналы |

## Ограничения

- Текстуры `resource/textures` создаёт конвертер: `RECONVERT=1` сотрёт апскейл, запускай скрипт заново.
- Апскейл не меняет форму: гладкие рукава и квадратные плечи останутся, если нужна другая форма — только вариант B для этой части.
- Сабля `soldier_spa_palash` общая у нескольких моделей, поэтому меняется у всех.
