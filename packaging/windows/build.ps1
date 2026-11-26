# 在 Windows x64 上构建 PCL Launcher 单文件 exe
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

Write-Host "[1/3] 检查 PyInstaller 与窗口依赖"
python -m pip install --disable-pip-version-check --quiet --upgrade pyinstaller pywebview

Write-Host "[2/3] 构建单文件窗口 exe"
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "PCL-Launcher" `
  --icon "packaging\windows\icon.ico" `
  --version-file "packaging\windows\version_info.txt" `
  --add-data "web;web" `
  --hidden-import "webview.platforms.edgechromium" `
  --collect-all "webview" `
  pcl.py

$source = Join-Path $root "dist\PCL-Launcher.exe"
$targetDir = Join-Path $root "dist\windows"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item -Force $source (Join-Path $targetDir "PCL-Launcher.exe")
Write-Host "[3/3] 输出：$(Join-Path $targetDir 'PCL-Launcher.exe')"
