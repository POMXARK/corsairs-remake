# Конвертирует RESOURCE оригинальных «Корсаров» (PDM 1.061) для Storm Engine.
# usage: .\convert.ps1 <папка_игры> <out> [--only stage,...] [-j N]
$ErrorActionPreference = 'Stop'
$py = Get-Command py, python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { Write-Error 'нужен Python 3.8+ (https://www.python.org)'; exit 1 }
$pyArgs = @()
if ($py.Name -like 'py*.exe' -and $py.Name -notlike 'python*') { $pyArgs += '-3' }
& $py.Source @pyArgs -I (Join-Path $PSScriptRoot 'pdm2storm.py') @args
exit $LASTEXITCODE
