---
name: pdm-voice-over
description: Use when voicing the NPC speeches of the game (pdm-game/data/voice, resource/sounds/voices) with CosyVoice 3 on Windows, or when the voice run fails, stops, or uses the wrong mode (cross_lingual instead of zero_shot). Covers the Windows environment (conda cosyvoice, Python 3.10, RTX 5080), the order of steps (refs.tsv, probe, full run, check, redo), the files that must survive a repository update, and the traps seen in real runs.
---

# Озвучка реплик NPC (CosyVoice 3, Windows)

Полная инструкция с установкой и всеми подводными камнями: [docs/voice-cosyvoice-windows.md](../../../docs/voice-cosyvoice-windows.md). Общая картина и сравнение моделей: [docs/voice-over.md](../../../docs/voice-over.md). Этот skill — порядок действий и проверки, когда что-то пошло не так.

## Где что лежит

| Путь (`C:\corsairs-remake`) | Что это | В git? |
|---|---|---|
| `tools\cosyvoice_batch.py` | озвучка через CosyVoice 3 напрямую из Python | да |
| `tools\pdm_voice_refs.py` | тексты образцов через Whisper → `data\voice\refs.tsv` | да |
| `tools\pdm_voice_check.py` | проверка Whisper'ом, список `redo.txt` | да |
| `pdm-game\data\voice\lines.jsonl` | реплики: диалог, узел, образец (`ref`), текст, куски, файл (`out`) | нет (данные) |
| `pdm-game\data\voice\refs.tsv` | `voices/<имя>.wav` ⇥ текст образца | нет (данные) |
| `pdm-game\data\voice\tries.json`, `redo.txt` | счётчик перегенераций, список на переделку | нет |
| `pdm-game\resource\sounds\voices\*.wav` | 252 образца голосов | да |
| `pdm-game\resource\sounds\voices\lines\` | готовые реплики | нет (генерируется) |
| `C:\CosyVoice` | репозиторий модели и веса в `pretrained_models\` | нет |

`data\voice\` и `lines\` не лежат в git. Их можно потерять при `git fetch` с перезаписью, распаковке архива поверх папки или `git clean`. Перед любым обновлением репозитория скопируйте `data\voice\` наружу:

```powershell
Copy-Item -Recurse C:\corsairs-remake\pdm-game\data\voice C:\voice-backup\data-voice-$(Get-Date -Format yyyyMMdd)
```

## Окно PowerShell

Каждое новое окно сначала подключает conda. Без этого `python` идёт в системный Python 3.14, и импорты не находятся:

```powershell
& "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
conda activate cosyvoice
cd C:\corsairs-remake
python --version        # обязательно 3.10.x
```

Если версия 3.14 или нет `(cosyvoice)` в приглашении, остановитесь и подключите окружение заново.

## Порядок действий

1. **Тексты образцов.** Один раз, и только после того, как `refs.tsv` потерян или пуст:
   ```powershell
   python -I tools\pdm_voice_refs.py pdm-game --device cuda
   ```
   Строка `pdm_voice_refs: 252 samples, 252 new` — успех. Уже записанные строки не перезаписываются, поэтому правки руками сохраняются. Если нет CUDA-библиотек, `--device cpu`.

2. **Проверка на пустые тексты.** Образец без текста молча уходит в `cross_lingual`, это хуже клона:
   ```powershell
   Select-String -Path pdm-game\data\voice\refs.tsv -Pattern "\t$"
   ```
   Пустые или галлюцинированные строки («Субтитры сделал…», «Продолжение следует») поправьте руками. Строку с табуляцией и префиксом `voices/` не трогайте.

3. **Проба на 10 репликах:**
   ```powershell
   python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --limit 10
   ```
   В первой строке трассы должен быть `inference_zero_shot`, а не `inference_cross_lingual`. Если `cross_lingual`, значит у образца нет текста в `refs.tsv`: вернитесь к шагу 2.

4. **Полный прогон.** Не прерывайте без нужды:
   ```powershell
   python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice
   ```
   - Первая реплика может занять больше минуты, строка `N/всего ~M min left` появляется только после готовой реплики.
   - Прерывание Ctrl+C безопасно: готовые файлы пропускаются, повторный запуск продолжает.
   - Оценка 2–7 часов на RTX 5080.
   - В конце сам вызывает `pdm_voice_lines.py --bind`.

5. **Проверка и перегенерация:**
   ```powershell
   python -I tools\pdm_voice_check.py pdm-game
   python -I tools\cosyvoice_batch.py pdm-game --repo C:\CosyVoice --redo pdm-game\data\voice\redo.txt
   ```
   Повторять, пока `redo.txt` не опустеет.

## Что безвредно

- `modelscope ... 403 Authentication token does not exist`, `no frontend is avaliable`: не скачался `wetext`, русскому не мешает.
- `Sliding Window Attention is enabled but not implemented for sdpa`, `FutureWarning` у `weight_norm`, предупреждения `torchaudio` и `onnxruntime` про Memcpy.
- `hf_xet is not installed`.

## Ловушки, которые уже случались

| Симптом | Причина | Что делать |
|---|---|---|
| `FileNotFoundError: pdm-game\data\voice\refs.tsv` | папка `data\voice` потеряна при обновлении репозитория | шаг 1; искать файл `Get-ChildItem C:\ -Recurse -Filter refs.tsv` |
| `ModuleNotFoundError: No module named 'faster_whisper'` | запуск в системном Python 3.14 | подключить conda и `cosyvoice` (см. выше) |
| Трасса с `inference_cross_lingual` вместо `zero_shot` | пустой текст образца или нет ключа в `refs.tsv` | шаг 2 |
| `0/1 [01:02<?]` и пустой вывод | первая реплика ещё считается | подождать, не прерывать |
| `ImportError: TorchCodec is required for load_with_torchcodec` | torchaudio 2.9+ | откатить `torch==2.8.0 torchaudio==2.8.0` с `cu128` |
| `no kernel image is available`, `sm_120` | torch собран под CUDA ниже 12.8 | `cu128`, см. раздел 1.4 документа |
| `CUDA out of memory` при `--shard` | два-три процесса на одной карте | один процесс, `--fp16` для скорости |

Полный список (17 позиций) — в [docs/voice-cosyvoice-windows.md](../../../docs/voice-cosyvoice-windows.md), раздел 5.

## Что проверить до того, как сказать «озвучено»

- Файлы появились в `resource\sounds\voices\lines\` и их число растёт в ожидаемом темпе.
- Проба `--limit 10` дала `zero_shot`, и прослушаны 2–3 файла.
- `pdm_voice_check.py` и `redo.txt` пусты, либо оставшиеся переделаны.
- `pdm_voice_lines.py --bind` выполнен (сам по себе или руками), иначе реплики не привязаны к NPC.
- Скопированы обратно в Linux-копию: `resource\sounds\voices\lines\` и `data\voice\` (раздел 4.4 документа).
