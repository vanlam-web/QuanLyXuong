param(
    [ValidateSet("User", "Machine")]
    [string]$Scope = "User",
    [switch]$Apply,
    [switch]$Legacy
)

$ErrorActionPreference = "Stop"

if (-not $Apply) {
    Write-Host "Dry-run only. Add -Apply to write environment variables."
    Write-Host ""
}

if ($Legacy) {
    $values = @{
        QLX_RUNTIME_MODE = "legacy"
        QLX_ENABLE_AUTO_CRM = "1"
        QLX_ENABLE_SERVER_ZALO = "1"
        QCVL_BRIDGE_DRY_RUN = "1"
    }
} else {
    $values = @{
        QLX_RUNTIME_MODE = "v2"
        QLX_ENABLE_AUTO_CRM = "0"
        QLX_ENABLE_SERVER_ZALO = "0"
        QCVL_BRIDGE_DRY_RUN = "1"
    }
}

Write-Host "Target scope: $Scope"
foreach ($item in $values.GetEnumerator() | Sort-Object Name) {
    Write-Host "$($item.Key)=$($item.Value)"
}

if (-not $Apply) {
    exit 0
}

$target = [EnvironmentVariableTarget]::$Scope
foreach ($item in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($item.Key, $item.Value, $target)
}

Write-Host ""
if ($Legacy) {
    Write-Host "Legacy mode variables applied. Restart apps/terminal to use them."
} else {
    Write-Host "V2 mode variables applied. Restart apps/terminal to use them."
}
