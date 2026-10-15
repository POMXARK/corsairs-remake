# Windows version of run.sh: builds the assets of the game with the generators of the engine demos
# (engine/demos) and starts the engine in game/.
# Usage: run.ps1 [path to engine.exe] [engine options, e.g. --editor]
#   without the engine path engine/build/default/Debug/engine.exe is taken (cmake --preset=default in engine/)
$Root = $PSScriptRoot
$Demo = "$Root/game"
$DefaultEngine = "$Root/engine/build/default/Debug/engine.exe"
$Demos = "$Root/engine/demos"
if (-not (Test-Path "$Demos/common/demo.ps1")) { throw 'engine/ is empty: git submodule update --init --recursive' }
. "$Demos/common/demo.ps1" @args

& "$Root/tools/fetch_assets.ps1" "$Root/assets"
# PT Serif: the sound demo draws its font and make_hud.py the compass letters with it
& "$Demos/dialog/fetch_assets.ps1" "$Root/assets/ptserif"
# the sea battle: sea, brig, particles, sounds and music, cannonball, island, HUD textures
Invoke-Python "$Demos/sea/make_sea.py" "$Demo/resource"
Invoke-Python "$Demos/ship/make_ship.py" "$Demo/resource"
Invoke-Python "$Demos/particles/make_particles.py" "$Demo/resource"
# the world map between the port and the battle (before the sound demo, whose demo_log font the game keeps)
Invoke-Python "$Demos/worldmap/make_worldmap.py" "$Root/assets/ptserif" "$Demo/resource"
Invoke-Python "$Demos/sound/make_sound.py" "$Root/assets/ptserif" "$Demo/resource"
Invoke-Python "$Demos/battle/make_battle.py" "$Demo/resource"
Invoke-Python "$Demos/island/make_island.py" "$Demo/resource"
Invoke-Python "$Demos/hud/make_hud.py" "$Root/assets/ptserif" "$Demo/resource"
# the port: quay, pier, the sailors and the dialog window
Invoke-Python "$Root/tools/make_port.py" "$Demo/resource"
# the boarding: after the port, whose sailor textures the boarder shares
Invoke-Python "$Root/tools/make_deck.py" "$Demo/resource"
# last: the sound demo writes its own fonts.ini, the game's fonts (with Cyrillic) replace it
Invoke-Python "$Root/tools/make_assets.py" "$Root/assets" "$Demo/resource"

# the engine indexes resources by scanning the working directory, so it runs from game/
Start-Demo -Folders 'save'
