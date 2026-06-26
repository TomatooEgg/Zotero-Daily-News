$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if ($env:OS -ne "Windows_NT") {
  throw "build_windows.ps1 must be run on Windows."
}

$BootstrapPython = "python"
$BuildVenv = Join-Path $ProjectDir ".build-venv"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$DistDir = Join-Path $ProjectDir "dist"
$PortableName = "Zotero-Daily-News-Windows-x86_64-Portable.zip"
$MsiName = "Zotero-Daily-News-Windows-x86_64.msi"

Write-Host "==> Installing build dependencies"
if (-not (Test-Path $Python)) {
  & $BootstrapPython -m venv $BuildVenv
}
& $Python -m pip install -q --upgrade pip
& $Python -m pip install -q -r requirements.txt
& $Python -m pip install -q "cx_Freeze>=7.2"

Write-Host "==> Cleaning old Windows build outputs"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $ProjectDir "build")
New-Item -ItemType Directory -Force $DistDir | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $DistDir $PortableName)
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $DistDir $MsiName)

Write-Host "==> Building Windows executable directory"
& $Python setup_windows.py build_exe

$ExeDir = Get-ChildItem -Path (Join-Path $ProjectDir "build") -Directory |
  Where-Object { $_.Name -like "exe.*" } |
  Select-Object -First 1
if (-not $ExeDir) {
  throw "cx_Freeze did not create build\exe.*"
}

Write-Host "==> Creating portable ZIP"
Compress-Archive -Path (Join-Path $ExeDir.FullName "*") -DestinationPath (Join-Path $DistDir $PortableName) -Force

Write-Host "==> Building MSI"
& $Python setup_windows.py bdist_msi
$BuiltMsi = Get-ChildItem -Path $DistDir -Filter "*.msi" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $BuiltMsi) {
  throw "cx_Freeze did not create an MSI in dist"
}
if ($BuiltMsi.Name -ne $MsiName) {
  Move-Item -Force $BuiltMsi.FullName (Join-Path $DistDir $MsiName)
}

Write-Host ""
Write-Host "Windows artifacts:"
Write-Host "  MSI:      $(Join-Path $DistDir $MsiName)"
Write-Host "  Portable: $(Join-Path $DistDir $PortableName)"
