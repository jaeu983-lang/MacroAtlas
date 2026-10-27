param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BaseRef,
    [string]$PythonPath,
    [string]$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($TaskUser -ne $CurrentUser) {
    throw "Interactive tasks must use the current signed-in user ($CurrentUser)."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git not found." }
$ResolvedBase = & git -C $ProjectRoot rev-parse --verify "${BaseRef}^{commit}"
if ($LASTEXITCODE -ne 0 -or -not $ResolvedBase) {
    throw "Base ref does not resolve to a commit: $BaseRef"
}
$ResolvedBase = $ResolvedBase.Trim()
$SymbolicBase = & git -C $ProjectRoot rev-parse --symbolic-full-name --verify $BaseRef
if ($LASTEXITCODE -ne 0 -or $SymbolicBase -notmatch '^refs/(heads|remotes)/') {
    throw "BaseRef must resolve to a local or remote branch so review PRs have a target."
}

if (-not $PythonPath) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
        $PythonPath = $VenvPython
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($PythonCommand) { $PythonPath = $PythonCommand.Source }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable not found. Pass -PythonPath with the selected environment's python.exe."
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path

$HealthScript = Join-Path $ProjectRoot "scripts\run_checks.ps1"
$ImproveScript = Join-Path $ProjectRoot "scripts\run_improvement.ps1"
$HealthArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}"' -f $HealthScript, $PythonPath
$ImproveArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}" -BaseRef "{2}"' -f $ImproveScript, $PythonPath, $BaseRef

$HealthAction = New-ScheduledTaskAction -Execute $PowerShell -Argument $HealthArguments -WorkingDirectory $ProjectRoot
$HealthTrigger = New-ScheduledTaskTrigger -Daily -At 7:30AM
$HealthSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$ImproveAction = New-ScheduledTaskAction -Execute $PowerShell -Argument $ImproveArguments -WorkingDirectory $ProjectRoot
$ImproveTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 9:00AM
$ImproveSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$Principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Limited

if ($DryRun) {
    [ordered]@{
        status = "DRY_RUN"
        base_ref = $BaseRef
        base_commit = $ResolvedBase
        python_path = $PythonPath
        task_user = $TaskUser
        logon_type = "Interactive"
        run_level = "Limited"
        tasks = @(
            @{ name = "MacroData-HealthCheck"; schedule = "Daily 07:30"; arguments = $HealthArguments },
            @{ name = "MacroData-AgentImprovement"; schedule = "Saturday 09:00"; arguments = $ImproveArguments }
        )
        registered = $false
    } | ConvertTo-Json -Depth 5 -Compress
    return
}

Register-ScheduledTask -TaskName "MacroData-HealthCheck" -Action $HealthAction -Trigger $HealthTrigger -Settings $HealthSettings -Principal $Principal -Description "Run local project tests and health checks" -Force | Out-Null
Register-ScheduledTask -TaskName "MacroData-AgentImprovement" -Action $ImproveAction -Trigger $ImproveTrigger -Settings $ImproveSettings -Principal $Principal -Description "Run Codex improvement on a dedicated Git branch" -Force | Out-Null

Write-Host "Registered tasks:"
Write-Host " - MacroData-HealthCheck (daily 07:30)"
Write-Host " - MacroData-AgentImprovement (Saturday 09:00; base $BaseRef)"
Write-Host "Tasks run as $TaskUser with interactive sign-in and limited privileges."
