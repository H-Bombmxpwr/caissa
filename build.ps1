# Builds Caissa into dist\Caissa\Caissa.exe
# Usage:  .\build.ps1              the application only
#         .\build.ps1 -Installer   also compile dist\Caissa-windows-x64-setup.exe
#
# The installer needs Inno Setup 6 (https://jrsoftware.org/isdl.php) and is what the
# release workflow ships as the recommended Windows download; caissa.iss explains why.
param([switch]$Installer)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "py" }

if (-not (Test-Path (Join-Path $root "vendor\stockfish\stockfish.exe"))) {
  Write-Host "Fetching Stockfish first..."
  & $python (Join-Path $root "tools\fetch_stockfish.py")
  if ($LASTEXITCODE -ne 0) { throw "Stockfish download failed" }
}

if (-not (Test-Path (Join-Path $root "assets\caissa.ico"))) {
  Write-Host "Building the application icon..."
  & $python (Join-Path $root "tools\make_icon.py")
}

& $python -m PyInstaller --noconfirm (Join-Path $root "caissa.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
Write-Host ""
Write-Host "Built: $(Join-Path $root 'dist\Caissa\Caissa.exe')"

if ($Installer) {
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found at $iscc" }
  & $iscc (Join-Path $root "caissa.iss")
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
  Write-Host ""
  Write-Host "Built: $(Join-Path $root 'dist\Caissa-windows-x64-setup.exe')"
}
