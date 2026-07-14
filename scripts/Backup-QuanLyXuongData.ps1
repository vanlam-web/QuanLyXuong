param(
    [string]$DataDir = "C:\QuanLyXuong\Data",
    [string]$BackupRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "backups\data"),
    [string]$BackupName = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [switch]$IncludeLogs
)

$ErrorActionPreference = "Stop"

function Resolve-OptionalPath([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    return $Path
}

function Write-Manifest([string]$Path, [object]$Data) {
    $Data | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$DataDir = Resolve-OptionalPath $DataDir
if (-not (Test-Path -LiteralPath $DataDir -PathType Container)) {
    throw "Data folder not found: $DataDir"
}

$BackupRoot = Resolve-OptionalPath $BackupRoot
$BackupPath = Join-Path $BackupRoot $BackupName
$DbBackupPath = Join-Path $BackupPath "db"
$FilesBackupPath = Join-Path $BackupPath "files"

if (Test-Path -LiteralPath $BackupPath) {
    throw "Backup already exists: $BackupPath"
}

New-Item -ItemType Directory -Force -Path $DbBackupPath | Out-Null
New-Item -ItemType Directory -Force -Path $FilesBackupPath | Out-Null

$dbFiles = Get-ChildItem -LiteralPath $DataDir -File -Filter "*.db" | Sort-Object Name
$copiedFiles = @()
$backedUpDbs = @()

foreach ($db in $dbFiles) {
    $destination = Join-Path $DbBackupPath $db.Name
    $pythonCode = @"
import sqlite3, sys
source = sys.argv[1]
dest = sys.argv[2]
src = sqlite3.connect(source, timeout=30)
try:
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
finally:
    src.close()
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pythonCode))
    python -c "import base64,sys; code=sys.argv[1]; sys.argv=['backup', sys.argv[2], sys.argv[3]]; exec(base64.b64decode(code).decode('utf-8'))" $encoded $db.FullName $destination

    $hash = Get-FileHash -LiteralPath $destination -Algorithm SHA256
    $backedUpDbs += [pscustomobject]@{
        name = $db.Name
        source = $db.FullName
        backup = $destination
        size = (Get-Item -LiteralPath $destination).Length
        sha256 = $hash.Hash
    }
}

$extraPatterns = @("*.json", "*.txt")
foreach ($pattern in $extraPatterns) {
    Get-ChildItem -LiteralPath $DataDir -File -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        $destination = Join-Path $FilesBackupPath $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        $hash = Get-FileHash -LiteralPath $destination -Algorithm SHA256
        $copiedFiles += [pscustomobject]@{
            name = $_.Name
            source = $_.FullName
            backup = $destination
            size = (Get-Item -LiteralPath $destination).Length
            sha256 = $hash.Hash
        }
    }
}

if ($IncludeLogs) {
    Get-ChildItem -LiteralPath "C:\QuanLyXuong" -File -Filter "*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
        $destination = Join-Path $FilesBackupPath $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        $hash = Get-FileHash -LiteralPath $destination -Algorithm SHA256
        $copiedFiles += [pscustomobject]@{
            name = $_.Name
            source = $_.FullName
            backup = $destination
            size = (Get-Item -LiteralPath $destination).Length
            sha256 = $hash.Hash
        }
    }
}

$manifest = [pscustomobject]@{
    name = $BackupName
    createdAt = (Get-Date).ToString("s")
    dataDir = $DataDir
    backupPath = $BackupPath
    databases = $backedUpDbs
    files = $copiedFiles
}

Write-Manifest -Path (Join-Path $BackupPath "manifest.json") -Data $manifest

Write-Host "Backup created: $BackupPath"
Write-Host "Databases: $($backedUpDbs.Count)"
Write-Host "Files: $($copiedFiles.Count)"
