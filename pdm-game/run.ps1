# Windows version of run.sh: converts the installed original (PDM 1.061) on the first run and starts
# the engine in pdm-game/. The variables are those of run.sh: $env:PDM, RECONVERT, SCENE, TOWN,
# TOWN_AUTO, SOUND_FX_ONLY.
# Usage: run.ps1 [path to engine.exe] [engine options]
#   without the engine path engine/build/default/Debug/engine.exe is taken (build.bat in the game root)
$Demo = $PSScriptRoot
$Root = Split-Path $Demo
$DefaultEngine = "$Root/engine/build/default/Debug/engine.exe"
$Demos = "$Root/engine/demos"
$Tools = "$Root/tools"
if (-not (Test-Path "$Demos/common/demo.ps1")) { throw 'engine/ is empty: git submodule update --init --recursive' }
. "$Demos/common/demo.ps1" @args

$Pdm = if ($env:PDM) { $env:PDM } else { Join-Path $Root '../Корсары' }
if (-not (Test-Path "$Pdm/RESOURCE")) { throw "no original at ${Pdm}: set `$env:PDM to the folder of the installed game" }
function Get-Env([string]$Name, [string]$Default) { $v = [Environment]::GetEnvironmentVariable($Name); if ($v) { $v } else { $Default } }

if ((Get-Env 'RECONVERT' '0') -eq '1')
{
    foreach ($path in 'resource', 'data', 'convert-report.json') { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$Demo/$path" }
}
if (-not (Test-Path "$Demo/resource/.converted"))
{
    # the tables, characters, ships and the story data as JSON in data/
    Invoke-Python "$Tools/pdm2storm.py" $Pdm $Demo --only actions,dialogs,tables,desc,characters,ships,quests
    # the sea, the sky and the sail settings of the engine demos
    Invoke-Python "$Demos/sea/make_sea.py" "$Demo/resource" --waves $(if ($env:SEA_WAVES) { $env:SEA_WAVES } else { "fft" })
    Invoke-Python "$Demos/ship/make_ship.py" "$Demo/resource"
    # every hull of WORLDS/Ships.idf (the forts are parts of the islands)
    $ships = Get-Content -Raw "$Demo/data/tables/WORLDS/Ships.json" | ConvertFrom-Json
    $hulls = $ships.objects | ForEach-Object {
        $o = @{}; foreach ($pair in $_) { $o[$pair[0]] = $pair[1] }; $o['filename'].ToLower()
    } | Where-Object { $_ -ne 'fort' } | Sort-Object -Unique
    foreach ($hull in $hulls) { Invoke-Python "$Tools/pdm_ship.py" $Pdm "$Demo/resource" $hull }
    # the settings of the rope and vant entities written by pdm_ship.py
    Get-Content "$Demo/resource/ini/rigging_pdm.ini" | Add-Content "$Demo/resource/ini/rigging.ini"
    New-Item -ItemType Directory -Force -Path "$Demo/resource/sounds", "$Demo/resource/ini/aliases" | Out-Null
    New-Item -ItemType File -Force -Path "$Demo/resource/.converted" | Out-Null
}
# the screens of the interface, the dialog window and the voices
if (-not ((Test-Path "$Demo/resource/ini/interfaces/mainmenu.ini") -and (Test-Path "$Demo/program/data/pdm_voices.c")))
{
    Invoke-Python "$Tools/pdm_ui.py" $Pdm $Demo MainMenu
}
# the towns and interiors, their patches and the characters with animation (several minutes)
if (-not (Test-Path "$Demo/program/data/pdm_world.c")) { Invoke-Python "$Tools/pdm_world.py" $Pdm $Demo }
# the islands and where the ship appears at each
if (-not (Test-Path "$Demo/data/islands")) { Invoke-Python "$Tools/pdm_island.py" $Pdm "$Demo/resource" all --data "$Demo/data" }
# the music, the sounds and their aliases
if (-not (Test-Path "$Demo/program/data/pdm_sound.c")) { Invoke-Python "$Tools/pdm_sound.py" $Pdm $Demo }
Invoke-Python "$Tools/pdm_data2c.py" "$Demo/data" "$Demo/program"
Invoke-Python "$Tools/pdm_logic2c.py" "$Demo/data" "$Demo/program"
# the scene to start with, as run.sh
@(
    "string StartScene = `"$(Get-Env 'SCENE' 'menu')`";"
    "string StartTown = `"$(Get-Env 'TOWN' 'City_GrandaAvilia')`";"
    "int TownAuto = $(Get-Env 'TOWN_AUTO' '0');"
    "int SoundFxOnly = $(Get-Env 'SOUND_FX_ONLY' '0');"
) | Set-Content -Encoding ascii "$Demo/program/data/start.c"

Start-Demo -Folders 'save'
