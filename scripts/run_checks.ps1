param(
    [string]$PythonPath,
    [string]$Candidate,
    [string]$Base
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
$RunnerArguments = @("--project-root", $ProjectRoot)
if ($Candidate) {
    if (-not $Base) { throw "Base commit SHA is required with a candidate SHA." }
    $RunnerArguments += @("--candidate", $Candidate, "--base", $Base)
} elseif ($Base) {
    throw "Candidate commit SHA is required with a base SHA."
}
& $Python $Runner @RunnerArguments
exit $LASTEXITCODE
