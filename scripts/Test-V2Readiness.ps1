param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Add-Check([System.Collections.Generic.List[object]]$Checks, [string]$Name, [bool]$Ok, [string]$Detail = "") {
    $Checks.Add([pscustomobject]@{
        name = $Name
        ok = $Ok
        detail = $Detail
    }) | Out-Null
}

function Env-Value([string]$Name, [string]$Default = "") {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$checks = [System.Collections.Generic.List[object]]::new()

$runtimeMode = Env-Value "QLX_RUNTIME_MODE" "legacy"
$autoCrm = Env-Value "QLX_ENABLE_AUTO_CRM" "1"
$serverZalo = Env-Value "QLX_ENABLE_SERVER_ZALO" "1"
$bridgeDryRun = Env-Value "QCVL_BRIDGE_DRY_RUN" "1"
$dbDir = Env-Value "QLX_DB_DIR" "C:\QuanLyXuong\Data"

Add-Check $checks "Runtime mode is v2" ($runtimeMode -eq "v2") "QLX_RUNTIME_MODE=$runtimeMode"
Add-Check $checks "Auto CRM disabled" ($autoCrm -in @("0", "false", "False", "FALSE")) "QLX_ENABLE_AUTO_CRM=$autoCrm"
Add-Check $checks "Server Zalo disabled" ($serverZalo -in @("0", "false", "False", "FALSE")) "QLX_ENABLE_SERVER_ZALO=$serverZalo"
Add-Check $checks "QCVL bridge dry-run enabled" ($bridgeDryRun -ne "0") "QCVL_BRIDGE_DRY_RUN=$bridgeDryRun"
Add-Check $checks "Data folder exists" (Test-Path -LiteralPath $dbDir -PathType Container) $dbDir
Add-Check $checks "Bridge script exists" (Test-Path -LiteralPath (Join-Path $ProjectRoot "app\bridge_qcvl.py") -PathType Leaf) "app\bridge_qcvl.py"
Add-Check $checks "V2 direction doc exists" (Test-Path -LiteralPath (Join-Path $ProjectRoot "docs\V2_DIRECTION_DECISIONS.md") -PathType Leaf) "docs\V2_DIRECTION_DECISIONS.md"
Add-Check $checks "V2 plan exists" (Test-Path -LiteralPath (Join-Path $ProjectRoot "docs\V2_IMPLEMENTATION_PLAN.md") -PathType Leaf) "docs\V2_IMPLEMENTATION_PLAN.md"

Write-Host ""
Write-Host "== V2 readiness =="
foreach ($check in $checks) {
    $prefix = if ($check.ok) { "[OK]" } else { "[WARN]" }
    Write-Host "$prefix $($check.name) - $($check.detail)"
}

$failed = @($checks | Where-Object { -not $_.ok })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "V2 readiness has warnings. This is expected until V2 env is applied."
    exit 2
}

Write-Host ""
Write-Host "V2 readiness OK"

