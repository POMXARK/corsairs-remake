# The original Sea Dogs (PDM 1.061) on Storm Engine, Windows: the menu of game.sh. Builds the engine
# (build.ps1 of the game root), converts the installed original and starts the game (run.ps1).
# Usage: game.ps1                       the menu
#        game.ps1 build Debug|Release
#        game.ps1 run [Debug|Release] [menu|sea|sailto|battle|town|review|quest|story]
#        game.ps1 convert | package | logs | keys | check
#        game.ps1 test [Debug|Release] [-Names story,town-tavern]   the autotests of autotest/scenarios.txt
# Paths are set in pdm-game/local.ps1 (not in git), e.g.  $env:PDM = 'D:\Games\Корсары'
param([string]$Command = 'menu', [string]$Config = 'Debug', [string]$Scene = 'menu', [string[]]$Names = @())
$ErrorActionPreference = 'Stop'
$Dir = $PSScriptRoot
$Root = Split-Path $Dir
if (Test-Path "$Dir/local.ps1") { . "$Dir/local.ps1" }
if (-not $env:PDM) { $env:PDM = [System.IO.Path]::GetFullPath((Join-Path $Root '../Корсары')) }
$Dist = if ($env:DIST) { $env:DIST } else { Join-Path $Root 'dist/corsairs-pdm-windows' }
$Logs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'My Games\Sea Dogs\Logs'

function Get-Engine([string]$Cfg) { Join-Path $Root "engine/build/default/$Cfg/engine.exe" }

function Invoke-Build([string]$Cfg) { & "$Root/build.ps1" -Config $Cfg }

function Invoke-Run([string]$Cfg, [string]$Name)
{
    foreach ($v in 'SCENE', 'TOWN', 'TOWN_AUTO') { Remove-Item "env:$v" -ErrorAction SilentlyContinue }
    switch ($Name)
    {
        'quest' { $env:SCENE = 'town'; $env:TOWN = 'City_HighRock'; $env:TOWN_AUTO = '3' }
        'sailto' { $env:SCENE = 'sea'; $env:TOWN = 'City_GrandaAvilia'; $env:TOWN_AUTO = '15' }
        'town' { $env:SCENE = 'town'; $env:TOWN = 'City_HighRock' }
        default { $env:SCENE = $Name }
    }
    # the first run from an unpacked archive has no engine yet: it is built here (ours)
    if (-not (Test-Path (Get-Engine $Cfg))) { Invoke-Build $Cfg }
    if (-not (Test-Path (Get-Engine $Cfg))) { throw "no engine after the build: $(Get-Engine $Cfg)" }
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir/run.ps1" (Get-Engine $Cfg)
}

# the autotests of autotest/scenarios.txt (the same list as autotests.sh on Linux): each one starts run.ps1 with its
# variables and passes when its marker is in the new lines of compile.log and error.log got no new line
function Get-LineCount([string]$Path) { if (Test-Path $Path) { @(Get-Content $Path).Count } else { 0 } }

function Invoke-Tests([string]$Cfg, [string[]]$Only)
{
    $engine = Get-Engine $Cfg
    if (-not (Test-Path $engine)) { Invoke-Build $Cfg }
    if (-not (Test-Path $engine)) { throw "no engine after the build: $engine" }
    $compile = Join-Path $Logs 'compile.log'
    $errorLog = Join-Path $Logs 'error.log'
    $pass = 0
    $fail = 0
    foreach ($line in Get-Content "$Dir/autotest/scenarios.txt")
    {
        if ($line -match '^\s*(#|$)') { continue }
        $name, $scene, $town, $auto, $marker, $secs = $line -split '\|'
        if ($Only -and $name -notin $Only) { continue }
        $compile0 = Get-LineCount $compile
        $error0 = Get-LineCount $errorLog
        foreach ($v in 'SCENE', 'TOWN', 'TOWN_AUTO') { Remove-Item "env:$v" -ErrorAction SilentlyContinue }
        $env:SCENE = $scene
        if ($town) { $env:TOWN = $town }
        $env:TOWN_AUTO = $auto
        # run.ps1 starts the engine; the job is stopped after its time, and so is the engine it left running
        $job = Start-Job -ScriptBlock { param($script, $engine) & $script $engine } -ArgumentList "$Dir/run.ps1", $engine
        if (-not (Wait-Job $job -Timeout ([int]$secs))) { Stop-Job $job; Get-Process -Name engine -ErrorAction SilentlyContinue | Stop-Process -Force }
        Remove-Job $job -Force
        $new = @(Get-Content $compile -ErrorAction SilentlyContinue | Select-Object -Skip $compile0)
        $errors = (Get-LineCount $errorLog) - $error0
        if (($new -match $marker) -and $errors -eq 0) { Write-Host "PASS $name"; $pass++ }
        else
        {
            Write-Host "FAIL $name (new error.log lines $errors): no `"$marker`""
            $new | Select-String -Pattern 'PDM' | Select-Object -Last 5 | ForEach-Object { Write-Host "     $($_.Line)" }
            $fail++
        }
    }
    Write-Host "autotests: $pass passed, $fail failed"
    if ($fail -gt 0) { throw "$fail autotest(s) failed" }
}

function Invoke-Convert { $env:RECONVERT = '1'; try { Invoke-Run 'Debug' 'story' } finally { Remove-Item env:RECONVERT } }

# the Release engine with its DLLs and shaders, the scripts and the converted original: for oneself,
# it holds the data of the original
function Invoke-Package
{
    $engine = Get-Engine 'Release'
    if (-not (Test-Path $engine)) { throw 'no Release engine: game.ps1 build Release' }
    if (-not (Test-Path "$Dir/program/data/pdm_world.c")) { throw 'the original is not converted yet: game.ps1 convert' }
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Dist
    New-Item -ItemType Directory -Force -Path "$Dist/bin", "$Dist/game/save" | Out-Null
    $bin = Split-Path $engine
    Copy-Item "$bin/*.exe", "$bin/*.dll" "$Dist/bin/"
    Copy-Item -Recurse "$bin/resource" "$Dist/bin/resource"
    Copy-Item -Recurse "$Dir/program", "$Dir/engine.ini" "$Dist/game/"
    Copy-Item -Recurse "$Dir/resource" "$Dist/game/resource"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$Dist/game/resource/techniques"
    Copy-Item -Recurse "$bin/resource/techniques" "$Dist/game/resource/techniques"
    'string StartScene = "menu";', 'string StartTown = "City_GrandaAvilia";', 'int TownAuto = 0;', '#define RUN_TOWNAUTO 0', '#define RUN_SAVEDIR "save"', '#define RUN_SAVEPFX "save\"', 'int SoundFxOnly = 0;', 'int StartVolFx = 80;', 'int StartVolMusic = 70;', 'int StartVolVoice = 100;', 'int StartNpcVoice = 1;' |
        Set-Content -Encoding ascii "$Dist/game/program/data/start.c"
    # the engine looks for program/ and resource/ in its working folder
    "@echo off`r`ncd /d `"%~dp0game`"`r`nstart `"`" `"%~dp0bin\engine.exe`" %*`r`n" | Set-Content -Encoding ascii -NoNewline "$Dist/play.bat"
    Write-Host "the game: $Dist\play.bat"
}

function Show-Logs
{
    foreach ($f in 'error', 'system') { Write-Host "== $f.log"; Get-Content -Tail 20 "$Logs/$f.log" -ErrorAction SilentlyContinue }
    Write-Host '== compile.log, PDM'
    Select-String -Path "$Logs/compile.log" -Pattern 'PDM' -ErrorAction SilentlyContinue | Select-Object -Last 20 | ForEach-Object Line
}

function Show-Keys
{
    @'
Главное меню   стрелки — выбор, Enter или мышь — нажать
Город          W/S — вперёд/назад, A/D — поворот, мышь — поворот и камера, Shift — бег
               E — заговорить с ближайшим; в двери и воротах справа сверху значок выхода,
               Пробел — пройти
Диалог         стрелки — выбор ответа, Пробел/Enter/ЛКМ — ответить, PageUp/PageDown — листать,
               Esc — выйти из разговора
Море           W/S — поднять/убрать паруса, A/D — руль, мышь — камера, Q/E — камера ближе/дальше,
               R — время ×1/×3/×6, M — карта мира, Пробел — в порт (у гавани, значок справа сверху)
               Tab — меню команд (в порт, карта, время), стрелки — выбор, Enter — выполнить, Esc — закрыть
               F — залп бортами, которые смотрят на врага (в бою)
Везде          Esc — меню игры: продолжить, настройки, выход (в диалоге — только из разговора)
'@ | Write-Host
}

function Show-Check
{
    Write-Host "PDM:      $env:PDM $(if (Test-Path "$env:PDM/RESOURCE") { 'ok' } else { '— нет RESOURCE\' })"
    foreach ($cfg in 'Debug', 'Release') { Write-Host "${cfg}:  $(Get-Engine $cfg) $(if (Test-Path (Get-Engine $cfg)) { 'собран' } else { 'не собран' })" }
    Write-Host "данные:   $(if (Test-Path "$Dir/program/data/pdm_world.c") { 'сконвертированы' } else { 'ещё нет (первый запуск)' })"
    foreach ($t in 'git', 'py', 'python', 'cmake', 'conan') { Write-Host "${t}: $((Get-Command $t -ErrorAction SilentlyContinue).Source)" }
}

function Show-Menu
{
    $cfg = 'Debug'
    while ($true)
    {
        Write-Host @"

  Корсары (PDM 1.061) на Storm Engine — сборка: $cfg
  1) Играть: главное меню         6) Собрать движок ($cfg)
  2) Город (Хайрок)               7) Сменить сборку Debug/Release
  3) Море                         8) Сконвертировать оригинал заново
  4) Смотр флота                  9) Собрать пакет для игры (dist\)
  5) Квест Хайрока (автотест)     c) Проверить окружение
  b) Морской бой   s) Плыть к NPC (автотест)   t) Все автотесты
  k) Управление   l) Логи   q) Выход
"@
        $choice = Read-Host '>'
        try
        {
            switch ($choice)
            {
                '1' { Invoke-Run $cfg 'menu' }
                '2' { Invoke-Run $cfg 'town' }
                '3' { Invoke-Run $cfg 'sea' }
                '4' { Invoke-Run $cfg 'review' }
                '5' { Invoke-Run $cfg 'quest' }
                'b' { Invoke-Run $cfg 'battle' }
                's' { Invoke-Run $cfg 'sailto' }
                't' { Invoke-Tests $cfg @() }
                '6' { Invoke-Build $cfg }
                '7' { $cfg = if ($cfg -eq 'Debug') { 'Release' } else { 'Debug' } }
                '8' { Invoke-Convert }
                '9' { Invoke-Package }
                'c' { Show-Check }
                'k' { Show-Keys }
                'l' { Show-Logs }
                { $_ -in 'q', '0' } { return }
            }
        }
        catch { Write-Host "ошибка: $_" }
    }
}

switch ($Command)
{
    'menu' { Show-Menu }
    'build' { Invoke-Build $Config }
    'run' { Invoke-Run $Config $Scene }
    'convert' { Invoke-Convert }
    'package' { Invoke-Package }
    'logs' { Show-Logs }
    'keys' { Show-Keys }
    'check' { Show-Check }
    'test' { Invoke-Tests $Config $Names }
    default { Get-Content $PSCommandPath -TotalCount 6 | Select-Object -Skip 2 | Write-Host; exit 1 }
}
