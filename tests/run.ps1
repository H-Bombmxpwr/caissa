# Concatenates the ES5-safe sources with the test files and runs them under Windows Script Host.
# Usage:  powershell -File tests\run.ps1 [all|engine|ai|openings]
param([string]$Test = "all")
$root = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $env:TEMP ("bf-tests-" + [guid]::NewGuid().ToString("N") + ".js")
$files = @(
  (Join-Path $PSScriptRoot "shim.js"),
  (Join-Path $root "js\engine.js"),
  (Join-Path $root "js\ai.js"),
  (Join-Path $root "data\openings.js"),
  (Join-Path $root "data\endgames.js"),
  (Join-Path $root "data\studies.js")
)
if ($Test -eq "all") {
  $files += (Join-Path $PSScriptRoot "engine.test.js")
  $files += (Join-Path $PSScriptRoot "ai.test.js")
  $files += (Join-Path $PSScriptRoot "openings.test.js")
  $files += (Join-Path $PSScriptRoot "positions.test.js")
} else {
  $files += (Join-Path $PSScriptRoot "$Test.test.js")
}
$sb = New-Object System.Text.StringBuilder
foreach ($f in $files) { [void]$sb.AppendLine([System.IO.File]::ReadAllText($f)) }
[System.IO.File]::WriteAllText($tmp, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
cscript //nologo //E:JScript $tmp
$code = $LASTEXITCODE
Remove-Item $tmp -Force
exit $code
