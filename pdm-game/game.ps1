# The original Sea Dogs (PDM 1.061) on Storm Engine, Windows: the menu of game.sh. Builds the engine
# (build.ps1 of the game root), converts the installed original and starts the game (run.ps1).
# Usage: game.ps1                       the menu
#        game.ps1 build Debug|Release
#        game.ps1 run [Debug|Release] [menu|sea|town|review|quest|story]
#        game.ps1 convert | package | logs | keys | check
# Paths are set in pdm-game/local.ps1 (not in git), e.g.  $env:PDM = 'D:\Games\Корсары'
param([string]$Command = 'menu', [string]$Config = 'Debug', [string]$Scene = 'menu')
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
        'town' { $env:SCENE = 'town'; $env:TOWN = 'City_HighRock' }
        default { $env:SCENE = $Name }
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir/run.ps1" (Get-Engine $Cfg)
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
    'string StartScene = "menu";', 'string StartTown = "City_GrandaAvilia";', 'int TownAuto = 0;', 'int SoundFxOnly = 0;' |
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
               E — заговорить с ближайшим, в двери и ворота — войти
Диалог         стрелки — выбор ответа, Пробел/Enter/ЛКМ — ответить, PageUp/PageDown — листать,
               Esc — выйти из разговора
Море           W/S — поднять/убрать паруса, A/D — руль, мышь — камера, Q/E — камера ближе/дальше,
               Enter — вернуться в порт
Везде          Esc — выход из игры (в диалоге — только из разговора)
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
    default { Get-Content $PSCommandPath -TotalCount 6 | Select-Object -Skip 2 | Write-Host; exit 1 }
}
