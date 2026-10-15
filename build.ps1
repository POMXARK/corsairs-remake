# Builds the engine of the game (the engine/ submodule) with the editor windows of the game (editor/)
# on Windows; then run.bat starts the game. The steps are in engine/build.ps1.
# Usage: build.ps1 [-Config Debug|Release]
param([ValidateSet('Debug', 'Release')][string]$Config = 'Debug')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path "$PSScriptRoot/engine/build.ps1")) { throw 'engine/ is empty: git submodule update --init --recursive' }
& "$PSScriptRoot/engine/build.ps1" -Config $Config -ExtraModules "$PSScriptRoot/editor"
