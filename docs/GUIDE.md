# Пошаговая инструкция: ремастер на Storm Engine + AI-инфраструктура

Платформа: **Windows 11 + RTX 5080 (16 ГБ)**. Проект некоммерческий, для тестирования возможностей и портфолио.
Общий план и обоснования — в [PLAN.md](PLAN.md). Здесь — что и в каком порядке делать руками.

> Проверено по GitHub (октябрь 2026):
> - `storm-devs/storm-engine` — GPL-3.0, **архивирован (read-only) с 29.04.2024**. Работать в своём форке.
> - Полностью поддерживается игра **«Корсары: Каждому своё» (Sea Dogs: To Each His Own)** — скрипты в `storm-devs/sd-teho-public`. «Город потерянных кораблей» и PotC New Horizons — в статусе WIP.
> - Официальная инструкция сборки рассчитана на **Visual Studio 2019 + Conan**. В VS 2022 ставим набор инструментов v142.

---

## Шаг 0. Правила проекта

1. Оригинальные ассеты игры и их ИИ-переработки **не коммитим** в публичные репозитории (см. «Права на ассеты» в PLAN.md).
2. Каждый шаг заканчивается коммитом + записью в `notes/journal.md` (что сделал, что сломалось, сколько заняло времени). Это сырьё для evals и резюме.
3. Оригинальную установку игры не трогаем — работаем с копией.

---

## Шаг 1. Установка софта (≈1 вечер)

### 1.1 Через winget (PowerShell от администратора)

```powershell
winget install Git.Git
winget install Kitware.CMake
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
winget install BlenderFoundation.Blender
winget install BaldurKarlsson.RenderDoc
winget install Ollama.Ollama
winget install Microsoft.VisualStudio.2022.Community
```

### 1.2 Компоненты Visual Studio (Visual Studio Installer → Изменить)

Рабочая нагрузка **«Разработка классических приложений на C++»** и в «Отдельных компонентах»:
- C++ CMake tools for Windows
- C++ Clang Compiler for Windows
- **MSVC v142 – VS 2019 C++ x64/x86 build tools**
- **C++ MFC for v142 build tools (x86 & x64)**
- Windows 10 SDK (последний 10.0.19041+) — именно 10, как в README движка

### 1.3 Conan

Основа — живой форк **PiratesAhoy/storm-engine** (см. [RESEARCH.md](RESEARCH.md)), он перешёл на **Conan 2** и сам настраивает свой conan remote:

```powershell
py -3.11 -m pip install "conan>=2"
conan profile detect
conan --version
```

(Архивный `storm-devs/storm-engine` требует Conan 1.59.0 — только если понадобится сравнить.)

### 1.4 DirectX 9 runtime

Скачать «DirectX End-User Runtimes (June 2010)» с сайта Microsoft, установить (нужны `d3dx9_*.dll`).

### 1.5 Игра

Купить в Steam **Sea Dogs: To Each His Own** (app 223330), установить. Скопировать папку игры:

```powershell
robocopy "C:\Program Files (x86)\Steam\steamapps\common\Sea Dogs To Each His Own" D:\remake\game /E
```

### 1.6 Claude Code

```powershell
irm https://claude.ai/install.ps1 | iex
claude --version
```

---

## Шаг 2. Структура рабочей папки

```
D:\remake\
  game\              копия игры (сюда запускаем движок)
  storm-engine\      форк движка (C++)
  sd-teho-public\    форк скриптов ККС
  storm-tools\       Python: конвертеры форматов (твой репо)
  storm-mcp\         Python: MCP-сервер для агента (твой репо)
  pipeline\          ComfyUI-скрипты, workflow (твой репо)
  notes\             journal.md, engine-map.md, field notes
  work\              промежуточные ассеты (НЕ в git)
```

---

## Шаг 3. Сборка движка (≈1–3 вечера)

### 3.1 Форк и клонирование

На GitHub: Fork **`PiratesAhoy/storm-engine`** (живой преемник, ветка `main`) и `storm-devs/sd-teho-public` в свой аккаунт.

```powershell
cd D:\remake
git clone https://github.com/<твой_ник>/storm-engine.git
git clone https://github.com/<твой_ник>/sd-teho-public.git
cd storm-engine
git checkout -b remake
```

### 3.2 Открыть в VS

1. VS 2022 → «Открыть локальную папку» → `D:\remake\storm-engine`.
2. VS сам запустит CMake-конфигурацию (окно Output → CMake). Conan скачает зависимости.
3. Выбрать конфигурацию **x64-Debug** (если её нет в списке — «Управление конфигурациями»).
4. Цель запуска (выпадающий список рядом с ▶) → **engine.exe**.

Если падает:
- ошибка про toolset → проверить, что стоит v142, либо в `CMakeSettings.json` добавить `"-T v142"` в аргументы генератора;
- ошибка Conan → смотреть версию (п. 1.3), чистить кэш `conan remove "*" -f`;
- **каждую ошибку и её решение — в `notes/journal.md`**. Здесь же впервые подключаем Claude Code (шаг 5) — пусть разбирает лог.

### 3.3 Скрипты и запуск

```powershell
# скрипты ККС поверх копии игры
robocopy D:\remake\sd-teho-public D:\remake\game /E /XD .git
```

(ветка `develop-rus` — русская версия: `git -C D:\remake\sd-teho-public checkout develop-rus` перед копированием.)

В VS: правой кнопкой на `engine.exe` в обозревателе целей → «Добавить конфигурацию отладки» → в `launch.vs.json`:

```json
{
  "version": "0.2.1",
  "configurations": [
    {
      "type": "default",
      "project": "CMakeLists.txt",
      "projectTarget": "engine.exe",
      "name": "engine (game)",
      "currentDir": "D:\\remake\\game"
    }
  ]
}
```

F5 → игра должна запуститься из твоей сборки. **Это первый milestone** — скриншот + коммит.

---

## Шаг 4. Отладка: базовый набор приёмов

| Ситуация | Инструмент |
|---|---|
| Краш | F5 в Debug → стек вызовов, окно Locals |
| «Что вообще происходит» | логи движка в папке игры (найти, куда пишет — `grep` по `log` в исходниках) + свой логгер |
| Графика | **RenderDoc не умеет DX9.** Решение: положить `d3d9.dll` из DXVK (x64) рядом с `engine.exe` → игра идёт через Vulkan → RenderDoc захватывает кадр |
| Память / UB | Address Sanitizer: в `CMakeSettings.json` для отдельной конфигурации `/fsanitize=address` |
| Производительность | встроенный в VS профилировщик (Alt+F2), Nsight Graphics для GPU |

Первая самостоятельная задача: добавить в загрузчик текстур строку лога `[tex] путь, ширина×высота, формат`. Через неё будешь видеть каждую подменённую текстуру.

---

## Шаг 5. Claude Code в репозитории движка

### 5.1 CLAUDE.md (положить в `D:\remake\storm-engine\CLAUDE.md`)

```markdown
# Storm Engine — remake fork

## Сборка
- VS 2022, toolset v142, CMake + Conan 1.x, конфигурация x64-Debug.
- CLI: `cmake --build out/build/x64-Debug --target engine`
- Запуск: engine.exe, рабочая папка D:\remake\game

## Правила
- Не изменять файлы в D:\remake\game кроме скриптов из sd-teho-public.
- Не коммитить ассеты игры (*.tx, *.gm, *.ani и т.п.).
- Новые фичи — за флагом в engine.ini, старое поведение по умолчанию.
- Перед завершением задачи — собрать проект без ошибок.

## Карта модулей
См. D:\remake\notes\engine-map.md (дополнять при изучении кода).
```

### 5.2 Первые задачи для агента

```text
1. Изучи структуру src/, составь notes/engine-map.md: модули, точки входа, где рендер, море, анимации, загрузка текстур и моделей, скриптовый движок.
2. Найди код загрузки текстур. Опиши формат файла текстуры по коду (заголовок, поля, mip-уровни) в notes/formats/texture.md.
3. То же для моделей и анимаций.
```

Твоя роль: проверить каждое утверждение по коду (открыть файл, строку). Ошибки агента — в `notes/journal.md`, это материал для evals.

---

## Шаг 6. `storm-tools` — конвертеры (Python)

```powershell
cd D:\remake
mkdir storm-tools; cd storm-tools; git init
py -3.11 -m venv .venv; .\.venv\Scripts\activate
pip install numpy pillow pytest
```

Структура:
```
storm_tools/
  texture.py     # read_tx(path) -> Image, write_tx(image, path, fmt)
  model.py       # read_gm(path) -> mesh -> export glTF
  validate.py    # проверки: степень двойки, формат, кол-во костей
  cli.py         # python -m storm_tools tex2png / png2tx / validate
tests/
```

Порядок:
1. `read_tx` по описанию формата из шага 5.2. Тест: прочитать 20 случайных текстур, сохранить PNG, глазами сверить.
2. `write_tx` → round-trip тест: `read(write(read(x))) == read(x)`.
3. Подменить одну текстуру (например, палубу) на перекрашенную вручную → увидеть в игре. **Milestone 2.**
4. Модели → glTF (для Blender) — после текстур.

Тесты, которым нужны файлы игры, помечать `@pytest.mark.game` и брать путь из переменной окружения `STORM_GAME_DIR` (в CI их пропускать).

---

## Шаг 7. ML-пайплайн текстур (ComfyUI на 5080)

### 7.1 Установка
1. ComfyUI Windows portable с GitHub (`comfyanonymous/ComfyUI`, раздел Releases) — для RTX 50 нужна сборка с PyTorch под CUDA 12.8+ (актуальные portable-сборки это включают).
2. Модели апскейла → `ComfyUI\models\upscale_models\` (4x-UltraSharp, RealESRGAN x4plus — проверить лицензию каждой).
3. Для img2img детализации — SDXL-чекпоинт с разрешающей лицензией + ControlNet Tile.
4. Запуск: `run_nvidia_gpu.bat`, интерфейс на http://127.0.0.1:8188.

### 7.2 Workflow
В UI собрать: `Load Image → Upscale Image (using Model) → [опц. KSampler img2img, denoise 0.2–0.35, ControlNet Tile] → Save Image`.
Меню → **Export (API)** → сохранить в `pipeline\workflows\upscale_api.json`.

### 7.3 Батч-скрипт `pipeline\batch_upscale.py`

```python
import json, sys, time, shutil, urllib.request
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
COMFY_DIR = Path(r"D:\ComfyUI_windows_portable\ComfyUI")
WF = json.loads(Path("workflows/upscale_api.json").read_text())
LOAD_NODE, SAVE_NODE = "1", "9"   # id нод из экспортированного json — подставить свои

def post(path, data):
    req = urllib.request.Request(COMFY + path, json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(COMFY + path))

def process(png: Path, out_dir: Path):
    shutil.copy(png, COMFY_DIR / "input" / png.name)
    wf = json.loads(json.dumps(WF))
    wf[LOAD_NODE]["inputs"]["image"] = png.name
    wf[SAVE_NODE]["inputs"]["filename_prefix"] = png.stem
    pid = post("/prompt", {"prompt": wf})["prompt_id"]
    while pid not in (hist := get(f"/history/{pid}")):
        time.sleep(0.5)
    for img in hist[pid]["outputs"][SAVE_NODE]["images"]:
        shutil.copy(COMFY_DIR / "output" / img["subfolder"] / img["filename"],
                    out_dir / f"{png.stem}.png")

if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*.png")):
        t = time.time(); process(p, dst); print(f"{p.name}: {time.time()-t:.1f}s")
```

### 7.4 Постобработка (обязательно, иначе игра упадёт или будет мыло)
- resize к ближайшей **степени двойки** (Pillow, LANCZOS); лимит 2048 для начала;
- альфа-канал: апскейлить отдельно (как grayscale) и склеивать обратно — многие апскейлеры альфу теряют;
- normal/roughness карты — отдельный шаг (Materialize или нейросетевая модель), понадобятся только на этапе 4 (шейдеры);
- обратно в формат игры — `storm_tools png2tx`;
- `storm_tools validate` перед копированием в `game\`.

Полная цепочка: `game → tex2png → work\orig → batch_upscale → work\up → postprocess → png2tx → validate → game`.
**Milestone 3:** видео «до/после» одной локации.

---

## Шаг 8. Локальная LLM (Ollama)

```powershell
ollama pull qwen2.5-coder:14b      # ~9 ГБ, влезает в 16 ГБ с запасом под контекст
ollama run qwen2.5-coder:14b "напиши функцию на python, округляющую число до степени двойки"
```

Перед выбором — проверить, не вышли ли более новые кодовые модели того же размера; сравнить на своих задачах (шаг 10).
Важно: **ComfyUI и Ollama одновременно на 16 ГБ не поместятся** — запускать по очереди (`ollama stop <model>`).

---

## Шаг 9. `storm-mcp` — свой MCP-сервер

```powershell
cd D:\remake; mkdir storm-mcp; cd storm-mcp; git init
py -3.11 -m venv .venv; .\.venv\Scripts\activate
pip install mcp
```

`server.py` — начальная версия:

```python
import subprocess, json, urllib.request
from pathlib import Path
from mcp.server.fastmcp import FastMCP

ENGINE = Path(r"D:\remake\storm-engine")
GAME = Path(r"D:\remake\game")
mcp = FastMCP("storm")

@mcp.tool()
def build(config: str = "x64-Debug") -> str:
    """Собрать движок. Возвращает только строки с ошибками/предупреждениями и итог."""
    r = subprocess.run(["cmake", "--build", f"out/build/{config}", "--target", "engine"],
                       cwd=ENGINE, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if " error " in l or " warning " in l]
    return f"exit={r.returncode}\n" + "\n".join(lines[-100:])

@mcp.tool()
def read_log(name: str, tail: int = 200) -> str:
    """Последние строки лога из папки игры."""
    return "\n".join((GAME / name).read_text(errors="replace").splitlines()[-tail:])

@mcp.tool()
def local_llm(prompt: str, model: str = "qwen2.5-coder:14b") -> str:
    """Отдать рутинную задачу локальной модели на RTX 5080."""
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
        json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(),
        {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["response"]

if __name__ == "__main__":
    mcp.run()
```

Регистрация в Claude Code:

```powershell
claude mcp add storm -- D:\remake\storm-mcp\.venv\Scripts\python.exe D:\remake\storm-mcp\server.py
claude mcp list
```

Дальше добавлять по мере надобности: `validate_assets` (через storm-tools), `run_scene` + `screenshot` (запуск engine.exe, скриншот окна, например через `mss`), `inspect_asset`.
**Milestone 4:** видео, где агент сам: правит код → `build` → запускает → читает лог → исправляет.

---

## Шаг 10. Evals

`evals\tasks.jsonl` — одна задача на строку, из реальных проблем `journal.md`:

```json
{"id": "build-01", "prompt": "Сборка падает с ошибкой ... Исправь.", "check": "build", "repo_ref": "<commit до исправления>"}
{"id": "fmt-01", "prompt": "Напиши функцию чтения заголовка текстуры ...", "check": "pytest tests/test_tex_header.py"}
```

`evals\run.py` для каждой задачи: `git worktree` на `repo_ref` → запуск исполнителя (Claude Code в headless-режиме `claude -p "..."`, или локальная модель через aider/свой скрипт) → команда `check` → запись `{id, executor, passed, seconds, cost}` в CSV.
Итог — таблица в README: где локальная модель справляется, где нет, и сколько это стоит. **Это и есть честные цифры для резюме.**

---

## Шаг 11. CI (GitHub Actions)

Для `storm-tools` и `storm-mcp`: `windows-latest`, `pip install`, `pytest -m "not game"`.
Для форка движка: сборка на `windows-latest` (Conan + CMake). Если runner'у не хватит v142 — сначала собирать только инструменты, движок позже.

---

## Чек-лист milestones

- [ ] M1 — движок собран, ККС запускается из своей сборки
- [ ] M2 — `storm-tools`: чтение/запись текстур, подмена одной текстуры в игре
- [ ] M3 — батч-апскейл локации, видео «до/после»
- [ ] M4 — `storm-mcp`: агент сам собирает и проверяет
- [ ] M5 — evals: таблица Claude vs локальная модель
- [ ] M6 — normal maps в шейдере кораблей (этап 4A из PLAN.md)
- [ ] M7 — standalone-симулятор экономики (этап 6)

После каждого milestone: коммит, запись в journal, 1–2 абзаца в README, скриншот/видео.
