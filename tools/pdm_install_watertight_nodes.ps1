# Installs the node packs of PixelArtistry's watertight workflows (github.com/pixelartistry/PixelArtistry-Watertight-Meshes)
# into any ComfyUI, e.g. Comfy Desktop: the installer of the author expects Easy-Install (python_embeded).
# The commits are the ones the installer pins (2026-09-26). Models are not downloaded: ComfyUI shows the missing ones.
#
# usage: powershell -ExecutionPolicy Bypass -File tools\pdm_install_watertight_nodes.ps1 -Comfy <ComfyUI folder> -Python <python.exe of ComfyUI>
#   the folder holds custom_nodes and models; the python is the one in the .venv of ComfyUI (WTiVo is built for Python 3.12)
param(
    [Parameter(Mandatory = $true)][string]$Comfy,
    [Parameter(Mandatory = $true)][string]$Python
)
$ErrorActionPreference = "Stop"
$nodes = Join-Path $Comfy "custom_nodes"
if (-not (Test-Path $nodes)) { throw "no custom_nodes in $Comfy" }
if (-not (Test-Path $Python)) { throw "no $Python" }
$packs = @(
    @("WTiVo-WatertightVoxel-ComfyuiNode", "fb9e9ea6a7deec965d3a4bf43ba7a4a9ff3856f3"),
    @("ComfyUI-Mesh-Quad-Reconstruct", "74048b3415537e26cc72b46b082a010cd0e357ce"),
    @("ComfyUI-CuMesh-Decimate", "c4edeb96bf637239cecb731d2869469a3025d742"),
    @("ComfyUI-Memory-Cleaner", "3357282290278c96ffa0da180d43bc5eac5f2286"),
    @("LODTailor-The-Mesh-Trimmer-ComfyuiNode", "3d25b7d4aa382fa5dac210eb5d8d0eadc4a4f183"),
    @("LODTailor-Bake-Forger", "f13589c22558e3ca49dfa87dce709233eb3cc86b"),
    @("Trellis2-Mesh-Encoder", "860313e67f0f69d402310dc325707bab8bec2fe9"),
    @("ComfyUI_LODsmith_Merge_Watertight", "5da6dd69c02d0f3d4ae743d090cfac79aefe7f96"),
    @("WTiVo-FastMergeByDistance", "5392949165ceed1e74448b1949d6e0dc9b34dd92")
)
foreach ($p in $packs) {
    $dir = Join-Path $nodes $p[0]
    if (-not (Test-Path $dir)) {
        git init -q $dir
        git -C $dir remote add origin "https://github.com/Mstafa-awad/$($p[0]).git"
    }
    git -C $dir fetch -q --depth 1 origin $p[1]
    git -C $dir checkout -q -f FETCH_HEAD
    Write-Host "[OK] $($p[0]) $($p[1].Substring(0, 8))"
}
foreach ($n in "Trellis2-Mesh-Encoder", "WTiVo-FastMergeByDistance") {
    & $Python -m pip install --disable-pip-version-check -q -r (Join-Path $nodes "$n\requirements.txt")
}
& $Python -c "import sys; sys.path.insert(0, r'$nodes\WTiVo-WatertightVoxel-ComfyuiNode'); import torch, wtivo; print('[OK] wtivo', sys.version.split()[0], torch.__version__)"
if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] wtivo does not import: its build is for Python 3.12 and the torch of the author (2.8.0 + CUDA 12.8)" }
Write-Host "Restart ComfyUI."
