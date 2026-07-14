param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,

    [string]$DataDir = "C:\QuanLyXuong\Data",
    [string]$BackupRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "backups\data"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Test-Port([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(500)
        if ($connected) {
            $client.EndConnect($async)
        }
        $client.Close()
        return [bool]$connected
    } catch {
        return $false
    }
}

function Backup-CurrentData([string]$Name) {
    $backupScript = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "scripts\Backup-QuanLyXuongData.ps1"
    & powershell -ExecutionPolicy Bypass -File $backupScript -DataDir $DataDir -BackupRoot $BackupRoot -BackupName $Name
}

$BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path
$BackupDbPath = Join-Path $BackupPath "db"

if (-not (Test-Path -LiteralPath $BackupDbPath -PathType Container)) {
    throw "Backup db folder not found: $BackupDbPath"
}

$requiredDb = @("InBat.db", "InDecal.db", "CNC.db")
foreach ($db in $requiredDb) {
    $path = Join-Path $BackupDbPath $db
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Backup missing required DB: $path"
    }
}

$runningPorts = @()
foreach ($port in @(8000, 5000, 8001)) {
    if (Test-Port $port) {
        $runningPorts += $port
    }
}

if ($runningPorts.Count -gt 0 -and -not $Force) {
    throw "Refusing restore while ports are active: $($runningPorts -join ', '). Stop services first or pass -Force."
}

if (-not (Test-Path -LiteralPath $DataDir -PathType Container)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
}

$preRestoreName = "pre-restore-" + (Get-Date -Format "yyyyMMdd-HHmmss")
Backup-CurrentData $preRestoreName

foreach ($item in Get-ChildItem -LiteralPath $BackupDbPath -File) {
    Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $DataDir $item.Name) -Force
}

$backupFilesPath = Join-Path $BackupPath "files"
if (Test-Path -LiteralPath $backupFilesPath -PathType Container) {
    foreach ($item in Get-ChildItem -LiteralPath $backupFilesPath -File) {
        Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $DataDir $item.Name) -Force
    }
}

Write-Host "Restored data from: $BackupPath"
Write-Host "Previous data backup: $(Join-Path $BackupRoot $preRestoreName)"
Write-Host "Data dir: $DataDir"
