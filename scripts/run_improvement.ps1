param(
    [string]$TaskFile = "prompts\weekly_improvement.md",
    [string]$BaseRef,
    [string]$PythonPath,
    [int]$Timeout = 3600,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git not found." }
if (-not $PythonPath) {
    if (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe")) {
        $PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    } else {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
}

$Runner = Join-Path $ProjectRoot "scripts\run_improvement.py"
$RunnerArguments = @(
    $Runner,
    "--project-root", $ProjectRoot,
    "--task-file", $TaskFile,
    "--timeout", $Timeout
)
if ($BaseRef) { $RunnerArguments += @("--base-ref", $BaseRef) }
if ($DryRun) { $RunnerArguments += "--dry-run" }

& $PythonPath @RunnerArguments
exit $LASTEXITCODE
