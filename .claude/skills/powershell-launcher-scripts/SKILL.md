---
name: powershell-launcher-scripts
description: Use when writing or editing this repository's auto-run scripts — the .ps1 launcher/game.ps1, its .bat wrapper/game.bat, run.ps1, logs.ps1 — or when one of them fails to parse when launched from cmd or by double-click. Covers the only correct run syntax on PowerShell 5.1, the encoding rules that decide whether Cyrillic survives (UTF-8 BOM for .ps1, ASCII+CRLF+chcp 852 for .bat), the menu/scene wiring that makes a demo or autotest launchable from game.bat, and the verified traps (Unterminated string, alias shadows, automatic variables, no &&, Read-Host EOF, constrained-sandbox type calls).
---

# Auto-run scripts of this repository: .ps1 and .bat done right

The launcher layer here is PowerShell 5.1 (`powershell.exe`) plus one `cmd` batch wrapper.
Both are old and their defaults decide whether the file runs at all — the traps below were
all actually hit on this machine while fixing the launcher of the Плыть к autotest.

## The version to use

PowerShell **5.1** only (`powershell.exe`, default on Windows 10/11). `game.ps1`, `run.ps1`,
`build.ps1`, `local.ps1` and the engine-demo harness `demo.ps1` were written for it and
verified on it (`AGENTS.md`, rule 4). Do not run them under PowerShell 7 (`pwsh.exe`):
encoding defaults and `Get-Content` behave differently. Check with
`powershell -NoProfile -Command '$PSVersionTable.PSVersion'` when in doubt.

## The one syntax to run any script

```
powershell -NoProfile -ExecutionPolicy Bypass -File <absolute\path>\script.ps1 [args]
```

- **`-File`, never `-Command`** to execute a script file. `-Command` hands the text to
  cmd's quoting twice: Cyrillic, apostrophes and `$` get mangled before PowerShell sees
  them. The file form is read by PowerShell itself, with the BOM deciding the encoding.
- `-NoProfile` — no user profile interference; `-ExecutionPolicy Bypass` — no unblock popup.
- Absolute path or `cd` first. Never `cmd /c powershell -Command "..."`.

From a shell in Claude Code, the launcher is entered through its .bat:

```
cmd /c "chcp 852 >nul & cd /d C:\corsairs-remake\pdm-game & game.bat run Debug sailto"
```

## What the files must contain (decides whether they parse at all)

### .ps1 — UTF-8 **with BOM** (`EF BB BF`) or pure ASCII

Without the BOM, PowerShell 5.1 decodes the file through the **console codepage**: every
Cyrillic string becomes mojibake, and one of the mojibake bytes-in-string is what turns
into the classic failure — `Unterminated string` parse errors on random lines and a crash
popup when `game.bat` double-clicks the launcher. This is exactly what happened to
`game.ps1` after it was resaved without a BOM. The BOM must survive every edit, copy and
git checkout.

Check it before and after any edit (byte ops only, text pipelines re-encode):

```
powershell -NoProfile -ExecutionPolicy Bypass -File C:\temp\shots\bom.ps1
# bom.ps1: $b = Get-Content $f -Encoding Byte -Read 0; first 3 bytes must be 239 187 191
```

To restore a lost BOM (byte prepend, never a text rewrite):

```
$b = Get-Content $f -Encoding Byte -Read 0
Set-Content $f -Encoding Byte -Value ([byte[]](239,187,191) + $b)
```

Then prove the whole file parses with the launcher's own no-game command:

```
cmd /c "chcp 852 >nul & cd /d C:\corsairs-remake\pdm-game & game.bat check"
```

`check` touches `PDM`, the engines and the data — if the .ps1 has a syntax error this is
where it shows, with the line number.

### .bat — ASCII only, CRLF, chcp first

A LF-only .bat breaks `cmd`. The wrapper is 6 lines of ASCII:

```
@echo off
chcp 852 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0game.ps1" %*
set RC=%ERRORLEVEL%
pause
exit /b %RC%
```

`chcp 852` makes the console print the launcher's Cyrillic menu; `pause` keeps the
double-clicked window open after a crash (read the scrollback, see below). Escape `%`
as `%%` inside .bat lines; args pass through as `%*`.

## Wiring a demo or autotest into the menu (rule 12)

Rule 12: every demo and every automated test must be launchable from the `game.bat`
menu; no test may live behind hand-set environment variables only. The scene itself
lives in the launcher — add both halves **the same turn** the test is written:

```powershell
# game.ps1, Invoke-Run switch: one line, the env the engine reads
'sailto' { $env:SCENE = 'sea'; $env:TOWN = 'City_GrandaAvilia'; $env:TOWN_AUTO = '14' }
# game.ps1, the menu list: one line the user sees
s) Плыть к NPC (автотест)
# and the menu switch case
's' { Invoke-Run $cfg 'sailto' }
```

The engine side (`sea.c`-style scripts) then keys its scenario on `TownAuto == 14` and
drives it with `PostEvent` — never simulated key presses. The proof of a scene is its
`Trace` lines in `compile.log` with wall-clock times plus an empty `error.log` (rule 9);
read them with `game.bat logs`.

Scenes as of now: `menu / town / sea / sailto / battle / review / quest / story`,
launcher commands `menu build run convert package logs keys check`.

## Verified traps (each one bit this repository)

- **No BOM on Cyrillic .ps1** → mojibake + `Unterminated string` + popup on double-click.
  Fix the BOM first, then look at content (`git diff` showing whole Cyrillic lines
  rewritten is the same bug — stop at encoding, not content).
- **`-Command` with non-ASCII** → same mojibake, different path, still cmd's quoting. Never
  inline script text into `-Command`.
- **Inline `-Command` with `$`** from this tool's shell: the sandbox escapes/strips `$`,
  `$c[4]`-style indexing breaks. Write the helper into a `.ps1` and run it with `-File`.
- **Bare `logs`** resolves to the `ls` alias, not `logs.ps1` — call named scripts with
  their extension or path.
- **No `&&` in PS 5.1** — that is cmd's; in PowerShell `;` ends statements. `&&` inside the
  .bat is fine.
- **Never assign automatic/read-only variables**: `$home`, `$input`, `$true`, `$PSArgs`… —
  `$env:VAR = 'value'` is how scenes pass settings down.
- **`Read-Host` under a piped stdin** sees EOF every call, so `echo q | game.bat menu`
  prints the menu forever — a test artifact, not a launcher bug; verify menu items
  through `game.bat check` or by invoking `Invoke-Run` with the scene argument instead.
- **Constrained PowerShell sandbox**: `[IO.IO]::ReadAllBytes`, `[IO.Stream]::ReadAllBytes`,
  `[System.Text.Encoding]::GetEncoding(...)` fail with "Unable to find type"/"MethodNotFound".
  Use `Get-Content <f> -Encoding Byte -Read 0` and byte math instead. `EACCES`-style blocks
  here are policy boundaries — do not retry the same command differently, escalate or
  restructure it.
- **Window died after `Press any key`**: `pause` did its job; the scrollback above holds
  the `ParserError`/`Unterminated string` block — fix the .ps1 encoding, not the game.
- **`git` LF→CRLF warnings** on `game.ps1` are normal; but never round-trip the file
  through text pipelines (`git show | Set-Content -Encoding UTF8` risks double-mangling) —
  use byte ops.

## Files involved

`pdm-game\game.bat` (the wrapper), `pdm-game\game.ps1` (the menu + `Invoke-Run`),
`pdm-game\run.ps1` (starts the engine with the env), `pdm-game\local.ps1` (paths, not in
git), `pdm-game\logs.ps1`, engine scripts under `pdm-game\program\*.c`.
