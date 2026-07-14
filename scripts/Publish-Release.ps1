param(
    [Parameter(Mandatory = $true)]
    [string]$NewDistPath,

    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ReleaseName = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [string]$DataDir = "C:\QuanLyXuong\Data",
    [switch]$SkipDataBackup
)

$ErrorActionPreference = "Stop"

$requiredExe = @(
    "QuanLyXuong.exe",
    "server.exe",
    "Dashboard.exe",
    "bridge_qcvl.exe",
    "cnc_legacy_bridge.exe",
    "Auto_CRM.exe"
)

function Resolve-FullPath([string]$Path) {
    return (Resolve-Path -LiteralPath $Path).Path
}

function New-Manifest([string]$DistPath, [string]$OutputPath, [string]$Name, [string]$Kind) {
    $files = Get-ChildItem -LiteralPath $DistPath -File | Sort-Object Name | ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        [pscustomobject]@{
            name = $_.Name
            size = $_.Length
            sha256 = $hash.Hash
            lastWriteTime = $_.LastWriteTime.ToString("s")
        }
    }

    $manifest = [pscustomobject]@{
        name = $Name
        kind = $Kind
        createdAt = (Get-Date).ToString("s")
        source = $DistPath
        files = $files
    }

    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}

$ProjectRoot = Resolve-FullPath $ProjectRoot
$NewDistPath = Resolve-FullPath $NewDistPath
$CurrentDistPath = Join-Path $ProjectRoot "dist"
$ReleasesPath = Join-Path $ProjectRoot "releases"
$ReleasePath = Join-Path $ReleasesPath $ReleaseName
$RollbackPath = Join-Path $ReleasesPath "rollback-$ReleaseName"
$BackupScriptPath = Join-Path $ProjectRoot "scripts\Backup-QuanLyXuongData.ps1"
$DataBackupRoot = Join-Path $ProjectRoot "backups\data"

foreach ($exe in $requiredExe) {
    $candidate = Join-Path $NewDistPath $exe
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Missing required file in new dist: $candidate"
    }
}

New-Item -ItemType Directory -Force -Path $ReleasesPath | Out-Null

if (Test-Path -LiteralPath $ReleasePath) {
    throw "Release already exists: $ReleasePath"
}
if (Test-Path -LiteralPath $RollbackPath) {
    throw "Rollback already exists: $RollbackPath"
}

if (-not $SkipDataBackup) {
    if (-not (Test-Path -LiteralPath $BackupScriptPath -PathType Leaf)) {
        throw "Data backup script not found: $BackupScriptPath"
    }
    if (-not (Test-Path -LiteralPath $DataDir -PathType Container)) {
        throw "Data folder not found, refusing to publish without backup: $DataDir"
    }
    & powershell -ExecutionPolicy Bypass -File $BackupScriptPath -DataDir $DataDir -BackupRoot $DataBackupRoot -BackupName "pre-release-$ReleaseName"
}

if (Test-Path -LiteralPath $CurrentDistPath) {
    New-Item -ItemType Directory -Force -Path $RollbackPath | Out-Null
    Copy-Item -LiteralPath $CurrentDistPath -Destination (Join-Path $RollbackPath "dist") -Recurse
    New-Manifest -DistPath (Join-Path $RollbackPath "dist") -OutputPath (Join-Path $RollbackPath "manifest.json") -Name "rollback-$ReleaseName" -Kind "rollback"
}

New-Item -ItemType Directory -Force -Path $ReleasePath | Out-Null
Copy-Item -LiteralPath $NewDistPath -Destination (Join-Path $ReleasePath "dist") -Recurse
New-Manifest -DistPath (Join-Path $ReleasePath "dist") -OutputPath (Join-Path $ReleasePath "manifest.json") -Name $ReleaseName -Kind "release"

if (-not (Test-Path -LiteralPath $CurrentDistPath)) {
    New-Item -ItemType Directory -Force -Path $CurrentDistPath | Out-Null
}

Get-ChildItem -LiteralPath $NewDistPath -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $CurrentDistPath $_.Name) -Force
}

New-Manifest -DistPath $CurrentDistPath -OutputPath (Join-Path $CurrentDistPath "CURRENT_RELEASE.json") -Name $ReleaseName -Kind "current"

Write-Host "Published release: $ReleaseName"
Write-Host "Current dist: $CurrentDistPath"
if (-not $SkipDataBackup) {
    Write-Host "Data backup: $(Join-Path $DataBackupRoot "pre-release-$ReleaseName")"
}
if (Test-Path -LiteralPath $RollbackPath) {
    Write-Host "Rollback backup: $RollbackPath"
}
