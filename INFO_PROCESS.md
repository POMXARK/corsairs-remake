# Процесс реконверсии моделей и запуск игры

## Статус запуска

**Результат**: движок стартует без краха, но выдаёт **чёрный экран** — рендер пайплайн не выводит изображение.

Запуск:
```
engine.exe (working dir: korsari-run/)
engine.ini → run = seadogs.c
```

Движок живёт, скрипт seadogs.c исполняется, модели загружаются без ошибок,
но визуальный вывод отсутствует (чёрный экран).

---

## Что сделано

### 1. Форматное расследование

- `.gm` и `.cff` — **полностью разные бинарные форматы**
- `.gm` = Storm RDF (version '1.05'), собственный формат движка
- `.cff` = проприетарный формат оригинальной игры (Cyclone/Sea Dogs quantized model)
- Движок хардкодит расширение: `sprintf_s(fnt, "resource\\models\\%s.gm", file_name)` в `geometry.cpp:113`

### 2. Разбор CFF формата (ground truth из Noesis plugin + CFF.bt)

```
FILE_HEADER (44B):
  origin(3f), scale(3f), texture_count(u32), material_count(u32),
  lod_count(u32), section_offset(u32), cull_radius(u32)

TEXTURES: uint8 len + ASCII bytes (× texture_count)

MATERIALS (× material_count):
  36B header + u32 count + count × 20B texture refs

LOD MODELS (× lod_count):
  mesh_count(u32) + zero(u32) + MESH[]

MESH HEADER (44B):
  origin(3f), uv_delim(f), radius(f), tex_index(u32),
  vertex_count(u32), face_count(u32), unknown(u32),
  anim_key_count(u32), name[4]  ← ИМЯ МЕШИ (4 байта!)

VERTEXES: 12 или 13 bytes/vertex
  i16 x,y,z + i16 u,v + u8 r,g,b [+1 pad]

FACES: u8×3 (vertexCount≤256) else u16×3
```

### 3. Конвертер CFF → GM

Файл: `tools/cff2gm.py`

- Single mode: `cff2gm.py <input.cff> [output.gm]`
- Batch mode: `cff2gm.py --batch <src_dir> <dst_dir>`
- Dequantize: `pos = origin + vert * scale / 32767.0`
- UV: `uv = raw / uv_delim`
- Winding: CFF хранит back-facing → реверс `(a,b,c)` → `(a,c,b)`
- Normals: area-weighted smooth normals из face cross-products
- Vertex size: try 13B → fallback 12B
- **Mesh names**: читаются 4-байтные имена из CFF (hull, mast1, etc.)

### 4. RDF .gm формат (целевой)

```
HEAD (72B): <11i 3f 3f 1f>
  RDF_VERSION, flags, len(strings), n_names, n_textures,
  n_materials, 0, n_labels, n_objects, n_triangles_total, 1,
  bbox_size(3f), bbox_center(3f), radius(f)

STRINGS: null-terminated ASCII concatenated
NAMES: int32[] offsets into strings
TEXTURE_NAMES: int32[] offsets into strings
MATERIALS (56B): <2i 4f 4i 4i>
LABELS: RDF_LABEL
OBJECTS (108B): <3i 3f f 6i 8i 4i i>
TRIANGLES: <3H> (uint16 × 3)
VB HEADER (8B): <2i> type, data_size
STATIC VERTEX (36B): <3f 3f I 2f> pos, normal, color, uv
```

### 5. Конвертация

- **677/679** .cff → .gm успешно
- 2 fail: `ABrigCan.cff` (mesh parse error), `Reef.CfF` (corrupted header)
- Результат скопирован в `korsari-run/resource/MODELS/`

---

## Что найдено (диагностика краха)

### Крах (исправлен)

**Симптом**: ACCESS_VIOLATION (0xC0000005) при запуске

**Место**: RVA 0x10A82A = `std::_Narrow_char_traits<char,int>::length` (strlen)

**Call stack**:
```
SHIP::Mount
  → MODELR::RestoreRender
    → NODER::FindNode(this, name)
      → storm::iEquals(name, this->name)
        → strlen(NULL) ← КРАХ
```

**Причина**: конвертер использовал имена `mesh_0`, `mesh_1` вместо реальных
имён из CFF (`hull`, `mast1`, `deck`, etc.). Движок ищет нода по имени
(`FindNode(root, "hull")`), не находит → null pointer → strlen(null) → AV.

**Фикс**: читать 4-байтное имя меши из CFF header и использовать в RDF .gm.

### Чёрный экран (текущая проблема)

Движок работает, модели загружаются, но рендер не выводит изображение.
Возможные причины:
- Не настроен render target / swap chain
- Отсутствуют шейдеры или texture resources
- Camera/frustum не инициализирован
- D3D device creation fails silently
- Скрипт seadogs.c не создаёт scene properly

---

## Файлы

| Путь | Назначение |
|------|-----------|
| `tools/cff2gm.py` | Конвертер CFF → GM |
| `engine/src/libs/geometry/src/rdf.h` | Структура RDF формата |
| `engine/src/libs/geometry/src/geometry.cpp:113` | Хардкод .gm extension |
| `engine/demos/common/storm_formats.py` | Генерация .gm (reference) |
| `docs/cff-format/CFF.bt` + README | Документация CFF |
| `seadogs-file-formats/plugins/noesis/fmt_sd_cff_clf.py` | Noesis plugin (ground truth) |
| `engine/src/apps/engine/src/main.cpp` | Crash dump handler (+79 строк) |
| `game/program/sea.c` | Временные MapKey+Main (нужен revert) |
| `korsari-run/engine.ini` | Конфиг (`run = seadogs.c`) |
| `korsari-run/resource/MODELS/` | 693 .gm файлов |

---

## Следующие шаги

1. **Диагностировать чёрный экран** — проверить D3D device, render target, camera init
2. Запустить с логом (spdlog) чтобы видеть что движок делает после загрузки моделей
3. Revert `game/program/sea.c` (удалить временные MapKey+Main)
4. Решить: оставить crash dump handler в main.cpp или убрать
5. По возможности починить ABrigCan.cff и Reef.CfF
