# Builds Caissa into dist\Caissa\Caissa.exe
# Usage:  .\build.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "py" }

if (-not (Test-Path (Join-Path $root "vendor\stockfish"))) {
  Write-Host "Fetching Stockfish first..."
  & $python (Join-Path $root "tools\fetch_stockfish.py")
}

if (-not (Test-Path (Join-Path $root "assets\caissa.ico"))) {
  Write-Host "Building the application icon..."
  & $python (Join-Path $root "tools\make_icon.py")
}

& $python -m PyInstaller --noconfirm (Join-Path $root "caissa.spec")
Write-Host ""
Write-Host "Built: $(Join-Path $root 'dist\Caissa\Caissa.exe')"
