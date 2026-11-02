# Puts the nodes of the parts workflow (comfy_nodes/pdm_parts) into ComfyUI: they run pdm_model_views.py and
# pdm_glb_optimize.py of this repo and show their log in the graph.
#
# usage: powershell -ExecutionPolicy Bypass -File tools\model3d\install_parts.ps1 -Comfy <ComfyUI folder>
#   the folder holds custom_nodes and models (in Easy-Install it is ...\ComfyUI). Restart ComfyUI afterwards,
#   then drag tools\model3d\pixal3d_parts_auto.json into the window.
param([Parameter(Mandatory = $true)][string]$Comfy)
$ErrorActionPreference = "Stop"
$nodes = Join-Path $Comfy "custom_nodes"
if (-not (Test-Path $nodes)) { throw "no custom_nodes in $Comfy" }
$src = Join-Path $PSScriptRoot "comfy_nodes\pdm_parts"
$dst = Join-Path $nodes "pdm_parts"
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
Copy-Item $src $dst -Recurse
Write-Host "installed: $dst - restart ComfyUI"
