param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipPayloadSample
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
    if ($LASTEXITCODE -ne 0) { throw "Quality gate failed." }
}

Run-Step "2. Healthcheck" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-QuanLyXuongHealth.ps1") -Role Server
    if ($LASTEXITCODE -ne 0) { throw "Healthcheck failed." }
}

Run-Step "3. V2 readiness" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-V2Readiness.ps1") -ProjectRoot $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "V2 readiness failed or has warnings. Apply V2 env before publishing V2."
    }
}

if (-not $SkipPayloadSample) {
    Run-Step "4. QCVL payload sample" {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Export-QcvlBridgeSample.ps1") -ProjectRoot $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw "QCVL payload sample export failed." }
    }
} else {
    Write-Host ""
    Write-Host "4. QCVL payload sample skipped"
}

Write-Host ""
Write-Host "V2 preflight OK"
