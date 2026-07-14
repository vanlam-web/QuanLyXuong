param(
    [string]$DistPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist-new"),
    [string]$SmokeDataDir = "C:\QuanLyXuong\SmokeData",
    [int]$ServerPort = 18000,
    [int]$DashboardPort = 15000
)

$ErrorActionPreference = "Stop"

function Stop-PortOwner([int]$Port) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

function Wait-HttpOk([string]$Url, [int]$Seconds = 20) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw "Smoke endpoint did not respond: $Url"
}

$DistPath = (Resolve-Path -LiteralPath $DistPath).Path
$serverExe = Join-Path $DistPath "server.exe"
$dashboardExe = Join-Path $DistPath "Dashboard.exe"

foreach ($path in @($serverExe, $dashboardExe)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing built executable: $path"
    }
}

New-Item -ItemType Directory -Force -Path $SmokeDataDir | Out-Null
Stop-PortOwner $ServerPort
Stop-PortOwner $DashboardPort

$serverProcess = $null
$dashboardProcess = $null
try {
    $env:QLX_DB_DIR = $SmokeDataDir
    $env:QLX_RUNTIME_MODE = "v2"
    $env:QLX_ENABLE_AUTO_CRM = "0"
    $env:QLX_ENABLE_SERVER_ZALO = "0"

    $env:QLX_SERVER_HOST = "127.0.0.1"
    $env:QLX_SERVER_PORT = [string]$ServerPort
    $serverProcess = Start-Process -FilePath $serverExe -WorkingDirectory $DistPath -WindowStyle Hidden -PassThru
    Wait-HttpOk "http://127.0.0.1:$ServerPort/docs"

    $env:QLX_DASHBOARD_HOST = "127.0.0.1"
    $env:QLX_DASHBOARD_PORT = [string]$DashboardPort
    $dashboardProcess = Start-Process -FilePath $dashboardExe -WorkingDirectory $DistPath -WindowStyle Hidden -PassThru
    Wait-HttpOk "http://127.0.0.1:$DashboardPort/"

    Write-Host "Built executable smoke OK"
} finally {
    foreach ($process in @($dashboardProcess, $serverProcess)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Stop-PortOwner $ServerPort
    Stop-PortOwner $DashboardPort
}
