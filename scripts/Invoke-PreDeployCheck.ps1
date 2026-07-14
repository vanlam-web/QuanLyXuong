param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipBackup,
    [switch]$SkipSupportBundle
)

$ErrorActionPreference = "Stop"

function Run-Step([string]$Title, [scriptblock]$Step) {
    Write-Host ""
    Write-Host "========================================"
    Write-Host $Title
    Write-Host "========================================"
    & $Step
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$scripts = Join-Path $ProjectRoot "scripts"

Run-Step "1. Quality gate" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-QuanLyXuongCode.ps1") -ProjectRoot $ProjectRoot
}

Run-Step "2. Healthcheck" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-QuanLyXuongHealth.ps1")
}

if (-not $SkipBackup) {
    Run-Step "3. Data backup" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Backup-QuanLyXuongData.ps1")
    }
} else {
    Write-Host ""
    Write-Host "3. Data backup skipped"
}

if (-not $SkipSupportBundle) {
    Run-Step "4. Support bundle" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "New-SupportBundle.ps1")
    }
} else {
    Write-Host ""
    Write-Host "4. Support bundle skipped"
}

Write-Host ""
Write-Host "Pre-deploy check OK"
