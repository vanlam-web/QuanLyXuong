param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DistPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist"),
    [string]$LocalRunDir = "C:\QuanLyXuong",
    [switch]$Restart,
    [switch]$StartBridge,
    [switch]$SkipCncLegacyBridge,
    [int]$BridgeInterval = 30
)

$ErrorActionPreference = "Stop"

function Stop-IfRunning([string]$ProcessName) {
    $processes = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
    if ($processes.Count -eq 0) { return }
    foreach ($process in $processes) {
        Write-Host "Stopping $ProcessName pid=$($process.Id)"
        Stop-Process -Id $process.Id -Force
    }
}

function Stop-BridgePython {
    $processes = @(Get-CimInstance Win32_Process -Filter "name = 'python.exe' or name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*bridge_qcvl.py*" -or $_.CommandLine -like "*cnc_legacy_bridge.py*" })
    foreach ($process in $processes) {
        Write-Host "Stopping python bridge pid=$($process.ProcessId)"
        Stop-Process -Id $process.ProcessId -Force
    }
}

function Copy-App([string]$SourceName, [string]$TargetName) {
    $source = Join-Path $DistPath $SourceName
    $target = Join-Path $LocalRunDir $TargetName
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing V2 runtime file: $source"
    }
    Copy-Item -LiteralPath $source -Destination $target -Force
    return $target
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$DistPath = (Resolve-Path -LiteralPath $DistPath).Path
New-Item -ItemType Directory -Force -Path $LocalRunDir | Out-Null

if ($Restart) {
    Stop-IfRunning "server_Local"
    Stop-IfRunning "Dashboard_Local"
    Stop-IfRunning "Auto_CRM"
    Stop-IfRunning "bridge_qcvl"
    Stop-IfRunning "cnc_legacy_bridge"
    Stop-BridgePython
}

$env:QLX_RUNTIME_MODE = "v2"
$env:QLX_ENABLE_AUTO_CRM = "0"
$env:QLX_ENABLE_SERVER_ZALO = "0"
$env:DASHBOARD_ADMIN_PIN = if ([string]::IsNullOrWhiteSpace($env:DASHBOARD_ADMIN_PIN)) { "8888" } else { $env:DASHBOARD_ADMIN_PIN }
$env:QCVL_BRIDGE_DRY_RUN = if ([string]::IsNullOrWhiteSpace($env:QCVL_BRIDGE_DRY_RUN)) { "1" } else { $env:QCVL_BRIDGE_DRY_RUN }

$serverExe = Copy-App "server.exe" "server_Local.exe"
$dashboardExe = Copy-App "Dashboard.exe" "Dashboard_Local.exe"
$bridgeExe = $null
if (Test-Path -LiteralPath (Join-Path $DistPath "bridge_qcvl.exe") -PathType Leaf) {
    $bridgeExe = Copy-App "bridge_qcvl.exe" "bridge_qcvl.exe"
}
$cncBridgeExe = $null
if (Test-Path -LiteralPath (Join-Path $DistPath "cnc_legacy_bridge.exe") -PathType Leaf) {
    $cncBridgeExe = Copy-App "cnc_legacy_bridge.exe" "cnc_legacy_bridge.exe"
}

Start-Process -FilePath $serverExe -WorkingDirectory $LocalRunDir -WindowStyle Hidden
Start-Sleep -Seconds 2
Start-Process -FilePath $dashboardExe -WorkingDirectory $LocalRunDir -WindowStyle Hidden

if ($StartBridge) {
    if ($bridgeExe) {
        $bridgeArgs = @("--dry-run", "--loop", "--interval", [string]$BridgeInterval)
        Start-Process -FilePath $bridgeExe -ArgumentList $bridgeArgs -WorkingDirectory $LocalRunDir -WindowStyle Hidden
    } else {
        $bridgePath = Join-Path $ProjectRoot "app\bridge_qcvl.py"
        if (-not (Test-Path -LiteralPath $bridgePath -PathType Leaf)) {
            throw "Missing bridge script: $bridgePath"
        }
        $bridgeArgs = @($bridgePath, "--dry-run", "--loop", "--interval", [string]$BridgeInterval)
        Start-Process -FilePath "python" -ArgumentList $bridgeArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    }
}

$cncBridgeStarted = $false
if (-not $SkipCncLegacyBridge) {
    if ($cncBridgeExe) {
        $cncArgs = @("--loop", "--interval", "10")
        Start-Process -FilePath $cncBridgeExe -ArgumentList $cncArgs -WorkingDirectory $LocalRunDir -WindowStyle Hidden
        $cncBridgeStarted = $true
    } else {
        $cncBridgePath = Join-Path $ProjectRoot "app\cnc_legacy_bridge.py"
        if (Test-Path -LiteralPath $cncBridgePath -PathType Leaf) {
            $cncArgs = @($cncBridgePath, "--loop", "--interval", "10")
            Start-Process -FilePath "python" -ArgumentList $cncArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden
            $cncBridgeStarted = $true
        }
    }
}

Write-Host "V2 runtime started."
Write-Host "Server: $serverExe"
Write-Host "Dashboard: $dashboardExe"
Write-Host "Auto_CRM: not started"
Write-Host "Bridge: $(if ($StartBridge) { "started dry-run loop" } else { "not started" })"
Write-Host "CNC legacy bridge: $(if ($cncBridgeStarted) { "started" } else { "not started" })"
if ($bridgeExe) { Write-Host "Bridge exe: $bridgeExe" }
if ($cncBridgeExe) { Write-Host "CNC bridge exe: $cncBridgeExe" }
foreach ($name in @("server_Local", "Dashboard_Local", "cnc_legacy_bridge")) {
    $items = @(Get-Process -Name $name -ErrorAction SilentlyContinue)
    Write-Host "$name count=$($items.Count)"
    foreach ($item in $items) {
        Write-Host "  pid=$($item.Id) path=$($item.Path)"
    }
}

