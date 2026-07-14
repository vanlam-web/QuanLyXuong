param(
    [string]$BackupRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "backups\data"),
    [int]$KeepDays = 30,
    [int]$KeepMinimum = 10
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
    Write-Host "Backup folder not found: $BackupRoot"
    exit 0
}

$cutoff = (Get-Date).AddDays(-1 * [Math]::Max($KeepDays, 1))
$backups = Get-ChildItem -LiteralPath $BackupRoot -Directory | Sort-Object LastWriteTime -Descending
$toKeep = $backups | Select-Object -First ([Math]::Max($KeepMinimum, 0))
$keepPaths = @{}
foreach ($item in $toKeep) {
    $keepPaths[$item.FullName] = $true
}

$removed = 0
foreach ($backup in $backups) {
    if ($keepPaths.ContainsKey($backup.FullName)) {
        continue
    }
    if ($backup.LastWriteTime -gt $cutoff) {
        continue
    }

    Remove-Item -LiteralPath $backup.FullName -Recurse -Force
    $removed += 1
    Write-Host "Removed old backup: $($backup.FullName)"
}

Write-Host "Cleanup complete. Removed=$removed kept=$($backups.Count - $removed)"
