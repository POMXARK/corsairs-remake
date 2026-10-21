# Документы проекта

| Файл | О чём |
|---|---|
| [PLAN.md](PLAN.md) | цель ремастера и роадмап портфолио по этапам |
| [GUIDE.md](GUIDE.md) | пошаговая инструкция под Windows 11 + RTX 5080 и AI-инфраструктура |
| [RESEARCH.md](RESEARCH.md) | обзор форков Storm Engine и похожих проектов (октябрь 2026) |
| [original-vs-remake.md](original-vs-remake.md) | как сделан оригинал и ремейк, отличия, находки, скрины внутренних тестов |
| [pdm-formats.md](pdm-formats.md) | форматы оригинальных «Корсаров» (TF, TGA, CFF, A, D, IDF, DEF, MTX, SHP, QL) и конвертер всего RESOURCE `tools/convert.*` |
| [voice-over.md](voice-over.md) | нейроозвучка реплик NPC: извлечение и привязка реплик, бесплатные модели с клоном голоса, пакетный прогон через ComfyUI API, подключение к движку |
| [ai-models.md](ai-models.md) | нейрогенерация 3D-моделей: виды модели, бесплатные шаблоны ComfyUI (Pixal3D, TRELLIS.2), пакетный прогон, перенос костей в `.gm` |
| [archive.md](archive.md) | сборка из архива без git (Windows): что поставить, `local.ps1`, первый запуск собирает движок и конвертирует оригинал |

Как устроен движок, форматы файлов, рецепты механик и сборка под Linux — в руководстве движка: [engine/docs/ru](../engine/docs/ru). Видео запусков демо пишет `engine/demos/common/record.sh`; сами видео в git не хранятся.
