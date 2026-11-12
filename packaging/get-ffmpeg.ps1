# Downloads a static LGPL build of ffmpeg for Windows and copies ffmpeg.exe + ffprobe.exe to packaging\ffmpeg
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "ffmpeg"
if ((Test-Path "$dest\ffmpeg.exe") -and (Test-Path "$dest\ffprobe.exe")) { Write-Host "ffmpeg already present"; exit 0 }
New-Item -ItemType Directory -Force $dest | Out-Null
$zip = Join-Path $env:TEMP "ffmpeg-win64-lgpl.zip"
$tmp = Join-Path $env:TEMP "ffmpeg-win64-lgpl"
$url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
Write-Host "Downloading ffmpeg (about 80 MB)..."
$ProgressPreference = "SilentlyContinue"
Invoke-WebRequest -Uri $url -OutFile $zip
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$bin = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
if (-not $bin) { throw "ffmpeg.exe not found in the download" }
Copy-Item $bin.FullName "$dest\ffmpeg.exe"
Copy-Item (Join-Path $bin.DirectoryName "ffprobe.exe") "$dest\ffprobe.exe"
Remove-Item $zip -Force
Remove-Item -Recurse -Force $tmp
Write-Host "ffmpeg ready in $dest"
