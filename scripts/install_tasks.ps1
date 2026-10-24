$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$HealthScript = Join-Path $ProjectRoot "scripts\run_checks.ps1"
$ImproveScript = Join-Path $ProjectRoot "scripts\run_improvement.ps1"

$HealthAction = New-ScheduledTaskAction -Execute $PowerShell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$HealthScript`"" -WorkingDirectory $ProjectRoot
$HealthTrigger = New-ScheduledTaskTrigger -Daily -At 7:30AM
$HealthSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "MacroData-HealthCheck" -Action $HealthAction -Trigger $HealthTrigger -Settings $HealthSettings -Description "Run local project tests and health checks" -Force | Out-Null

$ImproveAction = New-ScheduledTaskAction -Execute $PowerShell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ImproveScript`"" -WorkingDirectory $ProjectRoot
$ImproveTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 9:00AM
$ImproveSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "MacroData-AgentImprovement" -Action $ImproveAction -Trigger $ImproveTrigger -Settings $ImproveSettings -Description "Run Codex improvement on a dedicated Git branch" -Force | Out-Null

Write-Host "Registered tasks:"
Write-Host " - MacroData-HealthCheck (daily 07:30)"
Write-Host " - MacroData-AgentImprovement (Saturday 09:00)"
Write-Host "Tasks run in the current user's context. Verify task conditions and sign-in requirements in Task Scheduler."
