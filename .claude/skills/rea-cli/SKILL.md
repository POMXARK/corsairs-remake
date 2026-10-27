---
name: rea-cli
description: Реверс-инжиниринг бинарников через REA CLI (npx rea-agents@6.7.0) без MCP — декомпиляция PE/DLL через Ghidra, поиск строк, xrefs, трассировка функций, метаданные .NET/Go/Rust/JS. Использовать, когда утверждение о логике оригинала опирается на декомпиляцию DLL из MODULES/ или на строки и метаданные бинарника. Не использовать для обычного анализа исходников этого репозитория.
---

# REA CLI

REA CLI вызывает анализ одной командой, без сессии: каждый вызов — отдельный процесс, состояния между вызовами нет. Единственное «запоминание» — файл снимка (`--snapshot`). Тяжёлый вывод сохраняется в файл, в чат не печатается.

Для полной выгрузки всех DLL оригинала в C-файлы есть свой конвейер (см. skill `pdm-reverse-engineering`, `docs/decompile.md`). REA удобен, когда нужен один вопрос к одной функции или строке, а не весь модуль.

## Когда применять REA, а когда нет

| Задача | Инструмент |
|---|---|
| Одна функция или одна строка из `MODULES/*.dll`, нужен псевдокод и xrefs | REA `function` / `decompile` / `xrefs` |
| «Где в DLL эта строка и что её использует» | REA `search` + `trace` |
| Нужно grep-ать по всему модулю (несколько десятков функций) | `tools/ghidra/decompile.sh`, см. `docs/decompile.md` |
| Метаданные .NET-сборки, Go/Rust-бинарника, SQLite, JS/ASAR | REA `inspect-*` / `analyze-javascript-application` |
| Проверка, что утверждение о DLL сохранилось при сравнении двух сборок | REA `evidence-import`, `compare` |
| Исходники этого репозитория, git-история | Обычные `grep`, `git log`, не REA |

## Запуск

Версия закреплена: `rea-agents@6.7.0`. Всегда используйте её, иначе результаты не воспроизводятся.

Linux (ghidra из `$W/tools/ghidra_12.1.4_PUBLIC`, JDK 24 из `/usr/lib/jvm/jdk-24.0.1-oracle-x64`):

```bash
export GHIDRA_INSTALL_DIR=$W/tools/ghidra_12.1.4_PUBLIC
export JAVA_HOME=/usr/lib/jvm/jdk-24.0.1-oracle-x64
mkdir -p $W/ref/rea
npx -y rea-agents@6.7.0 function "$PDM/MODULES/MAN.dll" main --provider ghidra --snapshot $W/ref/rea/MAN.json --json > $W/ref/rea/MAN-function.json
```

Windows (PowerShell): вывод через `cmd /c`, а не через `>` PowerShell 5.1 пишет UTF-16 с BOM, и JSON ломается:

```powershell
cmd /c "npx -y rea-agents@6.7.0 function C:\path\MAN.dll main --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\MAN.json --json > C:\temp\opencode\rea-function.json"
```

Node должен быть 22.19+, 24.11+ или 26+. На Windows по умолчанию стоит Node 20, поэтому перед командой добавьте в PATH путь к Node 22 из nvm.

## Команды

```bash
REA="npx -y rea-agents@6.7.0"
T="$PDM/MODULES/MAN.dll"; S="--provider ghidra --snapshot $W/ref/rea/MAN.json --json"

$REA analyze "$T" $S                       # обзор; первый вызов импортирует бинарник и долгий
$REA search "$T" "walk" $S                 # поиск строки
$REA function "$T" FUN_10002a80 $S         # досье функции по имени
$REA decompile "$T" 0x10002a80 $S          # псевдокод по адресу
$REA xrefs "$T" 0x1000d0f0 $S              # кто ссылается на адрес
$REA trace "$T" "walk" $S                  # путь от строки до функции, которая её использует
$REA instructions "$T" 0x10002a80 $S       # только ассемблер
```

Для остальных форматов провайдер не нужен:

```bash
$REA inspect-managed-artifact A.dll --json > out.json           # .NET: идентичность, развёртывание
$REA inspect-managed-members A.dll --type X.Y --json > out.json
$REA inspect-go-binary prog --json > out.json                   # метаданные сборки Go
$REA inspect-rust-binary prog --json > out.json                 # список зависимостей Rust (.dep-v0)
$REA inspect-sqlite-database db.sqlite --table t --row-limit 20 --json > out.json
$REA analyze-javascript-application ./app --json > out.json     # папка JS или ASAR
```

Выбирайте workflow по содержимому файла, а не по расширению. Управляемый парсер нужен PE/CLI-метаданные: single-file .NET-хост и IL2CPP он не распаковывает, для них нужен нативный анализ.

Провайдер: `$REA providers --json` и `$REA capabilities --json` покажут, что доступно. Переменная `REA_ANALYSIS_PROVIDER` задаёт провайдера по умолчанию, `--provider` его переопределяет.

## Правила работы с контекстом

1. Не печатайте результат в чат. Каждый `--json` пишется в файл (`$W/ref/rea/` или `C:\temp\opencode\`), и потом читается нужная часть: `head`, `grep`, `python3 -c` с выборкой полей.
2. Один и тот же `--snapshot` для всех запросов к одному бинарнику. Точное совпадение (байты цели, операция, параметры) отдаётся из файла, без повторного запуска Ghidra.
3. Большие файлы свидетельств читайте постранично: `rea inspect-analysis-view` с `{"kind": "summary"}` или `{"kind": "page", "collection": ..., "offset": 0, "limit": 32}`.
4. `doctor` запускайте только когда команда упала. Не запускайте его перед каждой командой.

## Что смотреть в результате

- Адреса в REA и в `ref/pdm-decomp/*.c` совпадают: там `// <адрес> <имя>` перед каждой функцией. Если адрес не совпал, проверьте базу загрузки, а не запускайте анализ заново.
- Константы: `(float10)_DAT_…` — это `double` в данных DLL. Прочитать их: `python3 tools/pe_const.py <dll> <адрес>`.
- Ghidra иногда путает аргументы на стеке x87. Если логика выглядит странно, сверяйте с ассемблером (`instructions`).

## Ограничения Windows и известные проблемы

- `import-reference-source` на нативном Windows возвращает `unsupported_host`. Для сравнения «исходник ↔ бинарник» нужен Linux или WSL.
- Ghidra-провайдер на Windows только для чтения: переименовать функции через REA нельзя.
- Если анализ упал и закрыть сессию тоже не удалось, REA покажет обе ошибки. Частичные результаты остаются в исходном выводе.

## Юридическая граница

REA и Ghidra — открытые инструменты. Декомпилированный код Akella в git не кладётся: он лежит только локально (`$W/ref/`). В репозиторий идут скрипты и выводы о форматах и правилах. Закрытые утилиты j88-yo и всё, что ими сконвертировано, не используются, только справка по форматам (см. `memory/j88-yo-storm-tools.md`).
