$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$env:NO_PROXY = (@($env:NO_PROXY, "localhost", "127.0.0.1", "::1") | Where-Object { $_ }) -join ","
$env:no_proxy = (@($env:no_proxy, "localhost", "127.0.0.1", "::1") | Where-Object { $_ }) -join ","

$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

& $Python (Join-Path $ProjectDir "launcher.py")
exit $LASTEXITCODE
