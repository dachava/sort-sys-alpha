# Registers the weekly Scheduled Task that runs `sort-sys-alpha run`.
# Runs only once the PC has been idle for a while, so it never competes with
# a game for the GPU (PLAN.md milestone M4) -- `schedule.mode` in config.toml
# (not this script) decides whether that run auto-applies or just plans.
param(
    [string]$TaskName = "SortSysAlpha",
    [string]$DayOfWeek = "Sunday",
    [string]$At = "03:00",
    [int]$IdleMinutes = 10
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "uv not found on PATH. Run install.ps1 first."
}

$action = New-ScheduledTaskAction `
    -Execute $uv.Source `
    -Argument "run sort-sys-alpha run" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $At

$settings = New-ScheduledTaskSettingsSet `
    -RunOnlyIfIdle `
    -IdleDuration (New-TimeSpan -Minutes $IdleMinutes) `
    -IdleWaitTimeout (New-TimeSpan -Hours 2) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "SORT-SYS-ALPHA weekly Downloads sort" `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName': weekly on $DayOfWeek at $At, after $IdleMinutes+ min idle."
