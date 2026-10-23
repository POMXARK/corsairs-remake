# Windows version of run.sh: converts the installed original (PDM 1.061) on the first run and starts
# the engine in pdm-game/. The variables are those of run.sh: $env:PDM, RECONVERT, SCENE, TOWN,
# TOWN_AUTO, SOUND_FX_ONLY, VOLUME_FX, VOLUME_MUSIC, VOLUME_VOICE (0..100), NPC_VOICE (0|1; settings.ini too),
# FULLSCREEN (1 the full screen, 0 a window with a frame) and SCREEN (1920x1080).
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
# a missing file is no match (Select-String stops the script on it under $ErrorActionPreference = 'Stop')
function Test-Pattern([string]$Pattern, [string]$Path) { (Test-Path $Path) -and [bool](Select-String -Quiet -Pattern $Pattern -Path $Path) }
function Get-Env([string]$Name, [string]$Default) { $v = [Environment]::GetEnvironmentVariable($Name); if ($v) { $v } else { $Default } }
# the volume and the voices of the characters: the variable, else settings.ini, else the default (0..100)
function Get-Setting([string]$Name, [string]$Key, [string]$Default)
{
    $v = Get-Env $Name ''
    if (-not $v -and (Test-Path "$Demo/settings.ini")) { $m = Select-String -Path "$Demo/settings.ini" -Pattern "^$Key\s*=\s*(\d+)" | Select-Object -First 1; if ($m) { $v = $m.Matches[0].Groups[1].Value } }
    $v = $v -replace '[^0-9]', ''
    if ($v) { $v } else { $Default }
}

if ((Get-Env 'RECONVERT' '0') -eq '1')
{
    foreach ($path in 'resource', 'data', 'convert-report.json') { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$Demo/$path" }
}
# every hull of WORLDS/Ships.idf (the forts are parts of the islands)
function Convert-Hulls
{
    $ships = Get-Content -Raw "$Demo/data/tables/WORLDS/Ships.json" | ConvertFrom-Json
    $hulls = $ships.objects | ForEach-Object {
        $o = @{}; foreach ($pair in $_) { $o[$pair[0]] = $pair[1] }; $o['filename'].ToLower()
    } | Where-Object { $_ -ne 'fort' } | Sort-Object -Unique
    foreach ($hull in $hulls) { Invoke-Python "$Tools/pdm_ship.py" $Pdm "$Demo/resource" $hull }
}

if (-not (Test-Path "$Demo/resource/.converted"))
{
    # the tables, characters, ships and the story data as JSON in data/
    Invoke-Python "$Tools/pdm2storm.py" $Pdm $Demo --only 'actions,dialogs,tables,desc,characters,ships,quests'
    # the sea, the sky and the sail settings of the engine demos
    Invoke-Python "$Demos/sea/make_sea.py" "$Demo/resource" --waves $(if ($env:SEA_WAVES) { $env:SEA_WAVES } else { "fft" })
    Invoke-Python "$Demos/ship/make_ship.py" "$Demo/resource"
    Convert-Hulls
    # the settings of the rope and vant entities written by pdm_ship.py
    Get-Content "$Demo/resource/ini/rigging_pdm.ini" | Add-Content "$Demo/resource/ini/rigging.ini"
    New-Item -ItemType Directory -Force -Path "$Demo/resource/sounds", "$Demo/resource/ini/aliases" | Out-Null
    New-Item -ItemType File -Force -Path "$Demo/resource/.converted" | Out-Null
}
# the battle: the blast and the splash, the cannonball and the shot holes; the hulls again where they were
# made before they had the gun labels
if (-not (Test-Path "$Demo/resource/particles/explosion.xps"))
{
    Invoke-Python "$Demos/particles/make_particles.py" "$Demo/resource"
    Invoke-Python "$Demos/battle/make_battle.py" "$Demo/resource"
    Convert-Hulls
}
# the screens of the interface, the dialog window and the voices; again for screens made before the fog of
# the map or the font of the notes of the toolbar
$MainMap = "$Demo/resource/ini/interfaces/mainmap.ini"
if (-not ((Test-Path $MainMap) -and ((Get-Content -Raw $MainMap) -match 'fogStamp') -and (Test-Pattern 'LB_VOICEON_OFF' "$Demo/resource/ini/interfaces/options.ini") -and (Test-Pattern 'PDM_HUD_18' "$Demo/resource/ini/fonts.ini") -and (Test-Path "$Demo/program/data/pdm_screens.c") -and (Test-Path "$Demo/program/data/pdm_voices.c")))
{
    Invoke-Python "$Tools/pdm_ui.py" $Pdm $Demo
}
# the towns and interiors, their patches and the characters with animation (several minutes)
if (-not (Test-Path "$Demo/program/data/pdm_world.c")) { Invoke-Python "$Tools/pdm_world.py" $Pdm $Demo }
# the cabin of the boarding and the fighters with the blade drawn, after the characters
if (-not (Test-Pattern 'PdmBoarding.hud' "$Demo/program/data/pdm_boarding.c")) { Invoke-Python "$Tools/pdm_boarding.py" $Pdm $Demo }
# the islands, where the ship appears at each and their forts
if (-not (Test-Pattern '"fort"' "$Demo/data/islands/Highrock.json")) { Invoke-Python "$Tools/pdm_island.py" $Pdm "$Demo/resource" all --data "$Demo/data" }
# the toolbar of the sea (the pictures with the class, the panel of the charges) and its notes
if (-not (Test-Pattern 'info_rows' "$Demo/program/data/pdm_hud.c")) { Invoke-Python "$Tools/pdm_hud.py" $Pdm $Demo }
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
    "int StartVolFx = $(Get-Setting 'VOLUME_FX' 'volume_fx' '80');"
    "int StartVolMusic = $(Get-Setting 'VOLUME_MUSIC' 'volume_music' '70');"
    "int StartVolVoice = $(Get-Setting 'VOLUME_VOICE' 'volume_voice' '100');"
    "int StartNpcVoice = $(Get-Setting 'NPC_VOICE' 'npc_voice' '1');"
) | Set-Content -Encoding ascii "$Demo/program/data/start.c"

# the window over engine.ini, as run.sh
if ((Get-Env 'FULLSCREEN' '') -eq '1') { $EngineArgs += '--fullscreen' }
elseif ((Get-Env 'FULLSCREEN' '') -eq '0') { $EngineArgs += '--windowed' }
if (Get-Env 'SCREEN' '') { $EngineArgs += @('--size', (Get-Env 'SCREEN' '')) }
Start-Demo -Folders 'save'
