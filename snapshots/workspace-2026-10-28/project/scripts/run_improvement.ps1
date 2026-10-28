param(
    [string]$TaskFile = "prompts\weekly_improvement.md"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git not found." }
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) { throw "Codex CLI not found." }
if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) { throw "Git repository not initialized." }

$Status = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Could not inspect Git status." }
if ($Status) {
    throw "Working tree is not clean. Commit or stash your changes before scheduled improvement."
}

# Always branch from the primary branch, not from a prior unmerged agent branch.
$HasMain = git branch --list main
if ($LASTEXITCODE -ne 0) { throw "Could not list Git branches." }
if ($HasMain) {
    $BaseBranch = "main"
} else {
    $HasMaster = git branch --list master
    if (-not $HasMaster) { throw "Neither main nor master exists. Create an initial commit and primary branch first." }
    $BaseBranch = "master"
}
git switch $BaseBranch
if ($LASTEXITCODE -ne 0) { throw "Could not switch to primary branch $BaseBranch." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Branch = "agent/improvement-$Stamp"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw "Could not create improvement branch." }

$PromptPath = Join-Path $ProjectRoot $TaskFile
if (-not (Test-Path $PromptPath)) { throw "Prompt file not found: $PromptPath" }
$Prompt = Get-Content -Raw -Encoding UTF8 $PromptPath

$ReportDir = Join-Path $ProjectRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Report = Join-Path $ReportDir "improvement_$Stamp.txt"

@"
Started: $(Get-Date -Format o)
Branch: $Branch
"@ | Set-Content -Encoding UTF8 $Report

# Codex may edit and run local tests inside this workspace. No auto-merge or auto-commit.
# Network access is not enabled here by default; do not weaken sandbox settings to make a run pass.
& codex exec --sandbox workspace-write --ask-for-approval never $Prompt 2>&1 |
    Tee-Object -FilePath $Report -Append
$CodexExit = $LASTEXITCODE

"`nCodex exit code: $CodexExit" | Tee-Object -FilePath $Report -Append
"`n--- Git status ---" | Tee-Object -FilePath $Report -Append
git status --short 2>&1 | Tee-Object -FilePath $Report -Append
"`n--- Diff check ---" | Tee-Object -FilePath $Report -Append
git diff --check 2>&1 | Tee-Object -FilePath $Report -Append
"`n--- End: $(Get-Date -Format o) ---" | Tee-Object -FilePath $Report -Append

if ($CodexExit -ne 0) {
    Write-Warning "Codex failed. Review report: $Report"
    exit $CodexExit
}
Write-Host "Improvement run finished on branch $Branch. Review report and diff; nothing was merged."
