param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TaskName = "QuanLyXuong Daily Data Backup",
    [string]$At = "23:30",
    [int]$KeepDays = 30,
    [int]$KeepMinimum = 10
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$backupScript = Join-Path $ProjectRoot "scripts\Backup-QuanLyXuongData.ps1"
$cleanupScript = Join-Path $ProjectRoot "scripts\Cleanup-QuanLyXuongBackups.ps1"
$logDir = Join-Path $ProjectRoot "backups\logs"
$taskScript = Join-Path $ProjectRoot "scripts\Run-ScheduledBackup.ps1"

if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) {
    throw "Backup script not found: $backupScript"
}
if (-not (Test-Path -LiteralPath $cleanupScript -PathType Leaf)) {
    throw "Cleanup script not found: $cleanupScript"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$taskContent = @"
`$ErrorActionPreference = "Stop"
`$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
`$logFile = Join-Path "$logDir" "backup-`$timestamp.log"
Start-Transcript -Path `$logFile -Force
try {
    & powershell -ExecutionPolicy Bypass -File "$backupScript" -BackupName "scheduled-`$timestamp" -IncludeLogs
    & powershell -ExecutionPolicy Bypass -File "$cleanupScript" -KeepDays $KeepDays -KeepMinimum $KeepMinimum
} finally {
    Stop-Transcript
}
"@

$taskContent | Set-Content -LiteralPath $taskScript -Encoding UTF8

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$taskScript`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Daily QuanLyXuong data backup" -Force | Out-Null

Write-Host "Installed scheduled backup task: $TaskName"
Write-Host "Runs daily at: $At"
Write-Host "Runner script: $taskScript"
Write-Host "Logs: $logDir"
