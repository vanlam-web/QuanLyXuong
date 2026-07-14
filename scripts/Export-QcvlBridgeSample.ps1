param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$SinceMinutes = 720,
    [int]$Limit = 20
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $ProjectRoot "support-bundles\bridge-sample-$timestamp"
$jsonlPath = Join-Path $outputDir "production-events.jsonl"
$statePath = Join-Path $outputDir "state.json"
$logPath = Join-Path $outputDir "bridge-sample.log"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

python (Join-Path $ProjectRoot "app\bridge_qcvl.py") `
    --dry-run `
    --no-save-checkpoint `
    --state-file $statePath `
    --log-file $logPath `
    --since-minutes $SinceMinutes `
    --limit $Limit `
    --dump-jsonl $jsonlPath

Write-Host "Bridge payload sample:"
Write-Host $jsonlPath
Write-Host "Log:"
Write-Host $logPath

