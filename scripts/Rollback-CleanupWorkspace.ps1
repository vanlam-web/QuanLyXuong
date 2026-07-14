param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

$ErrorActionPreference = "Stop"
$ManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$records = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

foreach ($record in @($records | Sort-Object moved_at -Descending)) {
    if (-not (Test-Path -LiteralPath $record.target)) {
        Write-Host "Skip missing: $($record.target)"
        continue
    }
    if (Test-Path -LiteralPath $record.source) {
        Write-Host "Skip existing source: $($record.source)"
        continue
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $record.source) | Out-Null
    Move-Item -LiteralPath $record.target -Destination $record.source
    Write-Host "Restored: $($record.source)"
}
