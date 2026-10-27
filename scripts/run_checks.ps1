param(
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = $PythonPath

if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        throw "Virtual environment not found. Run: py -3 -m venv .venv"
    }
} elseif (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

$Runner = Join-Path $ProjectRoot "scripts\run_maintenance_qa.py"
& $Python $Runner --project-root $ProjectRoot
exit $LASTEXITCODE
