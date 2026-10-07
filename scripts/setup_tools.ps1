# Downloads portable tools (FFmpeg) into ./tools so nothing is installed system-wide.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # makes Invoke-WebRequest much faster

$root  = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

$ffmpegDir = Join-Path $tools "ffmpeg"
if (Test-Path (Join-Path $ffmpegDir "bin\ffmpeg.exe")) {
    Write-Host "FFmpeg already present: $ffmpegDir"
} else {
    # gyan.dev "essentials" build includes AMD AMF (h264_amf), libx264, libass.
    $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $zip = Join-Path $tools "ffmpeg.zip"
    Write-Host "Downloading FFmpeg from $url ..."
    Invoke-WebRequest -Uri $url -OutFile $zip
    Write-Host "Extracting..."
    $tmp = Join-Path $tools "ffmpeg_tmp"
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
    if (Test-Path $ffmpegDir) { Remove-Item $ffmpegDir -Recurse -Force }
    Move-Item $inner.FullName $ffmpegDir
    Remove-Item $tmp -Recurse -Force
    Remove-Item $zip -Force
}

& (Join-Path $ffmpegDir "bin\ffmpeg.exe") -hide_banner -version | Select-Object -First 1
$enc = & (Join-Path $ffmpegDir "bin\ffmpeg.exe") -hide_banner -encoders 2>$null | Select-String "h264_amf|libx264"
$enc | ForEach-Object { Write-Host $_.Line }
Write-Host "Done."
