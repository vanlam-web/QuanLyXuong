param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$RollbackPath
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
$CurrentDistPath = Join-Path $ProjectRoot "dist"
$ReleasesPath = Join-Path $ProjectRoot "releases"
$FailedName = "failed-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$FailedPath = Join-Path $ReleasesPath $FailedName

if (-not $RollbackPath) {
    $latest = Get-ChildItem -LiteralPath $ReleasesPath -Directory -Filter "rollback-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $latest) {
        throw "No rollback folder found in $ReleasesPath"
    }

    $RollbackPath = $latest.FullName
}

$RollbackPath = Resolve-FullPath $RollbackPath
$RollbackDistPath = Join-Path $RollbackPath "dist"

if (-not (Test-Path -LiteralPath $RollbackDistPath -PathType Container)) {
    throw "Rollback dist folder not found: $RollbackDistPath"
}

foreach ($exe in $requiredExe) {
    $candidate = Join-Path $RollbackDistPath $exe
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Missing required file in rollback dist: $candidate"
    }
}

New-Item -ItemType Directory -Force -Path $ReleasesPath | Out-Null

if (Test-Path -LiteralPath $CurrentDistPath) {
    New-Item -ItemType Directory -Force -Path $FailedPath | Out-Null
    Copy-Item -LiteralPath $CurrentDistPath -Destination (Join-Path $FailedPath "dist") -Recurse
    New-Manifest -DistPath (Join-Path $FailedPath "dist") -OutputPath (Join-Path $FailedPath "manifest.json") -Name $FailedName -Kind "failed"
} else {
    New-Item -ItemType Directory -Force -Path $CurrentDistPath | Out-Null
}

Get-ChildItem -LiteralPath $RollbackDistPath -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $CurrentDistPath $_.Name) -Force
}

$rollbackName = Split-Path -Leaf $RollbackPath
New-Manifest -DistPath $CurrentDistPath -OutputPath (Join-Path $CurrentDistPath "CURRENT_RELEASE.json") -Name $rollbackName -Kind "rollback-current"

Write-Host "Rolled back to: $RollbackPath"
Write-Host "Previous failed dist saved to: $FailedPath"
