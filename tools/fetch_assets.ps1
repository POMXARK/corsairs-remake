# Windows version of fetch_assets.sh: downloads the free assets used by the game (licenses in
# CREDITS.md) unless they are there. Usage: fetch_assets.ps1 <assets dir>
param([Parameter(Mandatory)][string]$Dir)
$ErrorActionPreference = 'Stop'
$fonts = 'https://github.com/google/fonts/raw/main/ofl/oldstandardtt'
$assets = [ordered]@{
    'OldStandard-Bold.ttf' = "$fonts/OldStandard-Bold.ttf"
    'OFL.txt' = "$fonts/OFL.txt"
    'ninth_wave.jpg' = 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Hovhannes_Aivazovsky_-_The_Ninth_Wave_-_Google_Art_Project.jpg/1920px-Hovhannes_Aivazovsky_-_The_Ninth_Wave_-_Google_Art_Project.jpg'
}
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
foreach ($file in $assets.Keys)
{
    $path = Join-Path $Dir $file
    # Wikimedia refuses requests without a user agent of their own
    if (-not (Test-Path $path)) { Invoke-WebRequest -UseBasicParsing -UserAgent 'corsairs-remake' -Uri $assets[$file] -OutFile $path }
}
