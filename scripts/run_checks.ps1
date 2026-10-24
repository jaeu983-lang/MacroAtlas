$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run: py -3 -m venv .venv"
}

$ReportDir = Join-Path $ProjectRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Report = Join-Path $ReportDir "health_check_$Stamp.txt"

"Started: $(Get-Date -Format o)" | Tee-Object -FilePath $Report
& $Python -m pytest 2>&1 | Tee-Object -FilePath $Report -Append
$TestExit = $LASTEXITCODE

if ($TestExit -ne 0) {
    "TESTS: FAILED (exit $TestExit)" | Tee-Object -FilePath $Report -Append
    exit $TestExit
}

& $Python -m macro_data_platform.health 2>&1 | Tee-Object -FilePath $Report -Append
$HealthExit = $LASTEXITCODE
"Finished: $(Get-Date -Format o)" | Tee-Object -FilePath $Report -Append

if ($HealthExit -ne 0) { exit $HealthExit }
"TESTS: PASSED" | Tee-Object -FilePath $Report -Append
exit 0
