param(
    [string]$NasRoot = "\\192.168.1.188\AI",
    [string]$NasUser = "adminnas",
    [string]$NasPassword = "Lam650909@1",
    [string]$LocalRunDir = "C:\QuanLyXuong",
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = "Stop"

$mutexName = "Global\QuanLyXuongV2Runtime"
$createdNew = $false
$mutex = [System.Threading.Mutex]::new($false, $mutexName, [ref]$createdNew)

function Write-RuntimeLog([string]$Message) {
    $logDir = Join-Path $LocalRunDir "Logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath (Join-Path $logDir "Runtime_NSSM.log") -Value $line -Encoding UTF8
}

if (-not $createdNew) {
    while ($true) {
        try { Write-RuntimeLog "Another QuanLyXuong V2 runtime owner is already active. This NSSM instance will wait." } catch {}
        Start-Sleep -Seconds 300
    }
}

function Stop-IfRunning([string]$ProcessName) {
    $processes = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
    foreach ($process in $processes) {
        Write-RuntimeLog "Stopping $ProcessName pid=$($process.Id)"
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}

function Copy-App([string]$SourceName, [string]$TargetName) {
    $source = Join-Path $NasRoot ("Tools\dist\" + $SourceName)
    $target = Join-Path $LocalRunDir $TargetName
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing runtime file: $source"
    }
    Copy-Item -LiteralPath $source -Destination $target -Force
    return $target
}

function Connect-Nas {
    & net use $NasRoot /delete /y | Out-Null
    & net use $NasRoot $NasPassword /user:$NasUser | Out-Null
}

try {
    New-Item -ItemType Directory -Force -Path $LocalRunDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $LocalRunDir "Data") | Out-Null

    while ($true) {
        try {
            Write-RuntimeLog "Starting QuanLyXuong V2 runtime cycle."

            Stop-IfRunning "server_Local"
            Stop-IfRunning "Dashboard_Local"
            Stop-IfRunning "Dashboard_V2"
            Stop-IfRunning "cnc_legacy_bridge"
            Stop-IfRunning "bridge_qcvl"
            Stop-IfRunning "Auto_CRM_Local"
            Stop-IfRunning "Auto_CRM"
            Start-Sleep -Seconds 5

            Connect-Nas

            $serverExe = Copy-App "server.exe" "server_Local.exe"
            $dashboardExe = Copy-App "Dashboard.exe" "Dashboard_Local.exe"
            $cncBridgeExe = $null
            $bridgeCandidate = Join-Path $NasRoot "Tools\dist\cnc_legacy_bridge.exe"
            if (Test-Path -LiteralPath $bridgeCandidate -PathType Leaf) {
                $cncBridgeExe = Copy-App "cnc_legacy_bridge.exe" "cnc_legacy_bridge.exe"
            }

            $env:QLX_RUNTIME_MODE = "v2"
            $env:QLX_ENABLE_AUTO_CRM = "0"
            $env:QLX_ENABLE_SERVER_ZALO = "0"
            $env:QCVL_BRIDGE_DRY_RUN = "1"
            $env:DASHBOARD_ADMIN_PIN = "8888"

            Write-RuntimeLog "Starting Dashboard :5000"
            Start-Process -FilePath $dashboardExe -WorkingDirectory $LocalRunDir -WindowStyle Hidden

            if ($cncBridgeExe) {
                Write-RuntimeLog "Starting CNC legacy bridge"
                Start-Process -FilePath $cncBridgeExe -ArgumentList @("--loop", "--interval", "10") -WorkingDirectory $LocalRunDir -WindowStyle Hidden
            } else {
                Write-RuntimeLog "CNC legacy bridge exe not found; skip."
            }

            Write-RuntimeLog "Starting API Server :8000 foreground"
            $serverProcess = Start-Process -FilePath $serverExe -WorkingDirectory $LocalRunDir -WindowStyle Hidden -PassThru
            Wait-Process -Id $serverProcess.Id
            Write-RuntimeLog "Server exited. Restarting runtime after $RestartDelaySeconds seconds."
        } catch {
            Write-RuntimeLog "Runtime cycle error: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds $RestartDelaySeconds
    }
} finally {
    try { $mutex.ReleaseMutex() | Out-Null } catch {}
    $mutex.Dispose()
}
