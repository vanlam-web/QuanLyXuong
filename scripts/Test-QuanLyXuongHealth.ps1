param(
    [string]$DataDir = "C:\QuanLyXuong\Data",
    [string]$OpenClawPath = "C:\Users\Admin\AppData\Roaming\npm\openclaw.cmd",
    [string]$NasDistPath = "\\192.168.1.188\AI\Tools\dist",
    [string]$ServerPort = $env:QLX_SERVER_PORT,
    [string]$DashboardPort = $env:QLX_DASHBOARD_PORT,
    [string]$AutoCrmPort = $env:QLX_AUTO_CRM_PORT,
    [int]$OutboxWarnThreshold = 0,
    [ValidateSet("All", "Server", "Machine")]
    [string]$Role = "All"
)

$ErrorActionPreference = "Continue"

function Test-Port([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(500)
        if ($connected) {
            $client.EndConnect($async)
        }
        $client.Close()
        return [bool]$connected
    } catch {
        return $false
    }
}

function Add-Check([System.Collections.Generic.List[object]]$Checks, [string]$Name, [bool]$Ok, [string]$Detail) {
    $Checks.Add([pscustomobject]@{
        ok = $Ok
        name = $Name
        detail = $Detail
    })
}

function Env-Bool([string]$Name, [bool]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
}

function Int-OrDefault([string]$Value, [int]$Default) {
    $parsed = 0
    if ([int]::TryParse($Value, [ref]$parsed)) { return $parsed }
    return $Default
}

function Test-AnyProcess([string[]]$Names) {
    foreach ($name in $Names) {
        if (@(Get-Process -Name $name -ErrorAction SilentlyContinue).Count -gt 0) {
            return $true
        }
    }
    return $false
}

function Get-ProcessDetails([string]$Name) {
    @(Get-Process -Name $Name -ErrorAction SilentlyContinue | ForEach-Object {
        $path = ""
        try { $path = $_.Path } catch { $path = "" }
        "pid=$($_.Id) path=$path"
    })
}

function Test-ProcessCountAtMostOne([string]$Name, [ref]$Detail) {
    $items = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if ($items.Count -le 1) {
        $Detail.Value = "$Name count=$($items.Count)"
        return $true
    }
    $duplicateLabels = @{
        "server_Local" = "Duplicate process server_Local"
        "Dashboard_Local" = "Duplicate process Dashboard_Local"
        "cnc_legacy_bridge" = "Duplicate process cnc_legacy_bridge"
    }
    $prefix = if ($duplicateLabels.ContainsKey($Name)) { $duplicateLabels[$Name] } else { "Duplicate process $Name" }
    $Detail.Value = "$prefix count=$($items.Count): $((Get-ProcessDetails $Name) -join '; ')"
    return $false
}

function Get-OutboxPendingCount([string]$DbPath) {
    $script = "import sqlite3, sys; conn=sqlite3.connect(sys.argv[1]); print(conn.execute(sys.argv[2]).fetchone()[0])"
    $sql = "SELECT COUNT(*) FROM outbox_events WHERE status='pending'"
    try {
        $output = & python @("-c", $script, $DbPath, $sql) 2>$null
        $count = 0
        if ([int]::TryParse(($output | Select-Object -First 1), [ref]$count)) {
            return $count
        }
        return $null
    } catch {
        return $null
    }
}

$checks = [System.Collections.Generic.List[object]]::new()
$serverPortNumber = Int-OrDefault $ServerPort 8000
$dashboardPortNumber = Int-OrDefault $DashboardPort 5000
$autoCrmPortNumber = Int-OrDefault $AutoCrmPort 8001
$autoCrmEnabled = Env-Bool "QLX_ENABLE_AUTO_CRM" $true
$serverZaloEnabled = Env-Bool "QLX_ENABLE_SERVER_ZALO" $true

Add-Check $checks "Data folder" (Test-Path -LiteralPath $DataDir -PathType Container) $DataDir

foreach ($dbName in @("InBat.db", "InDecal.db", "CNC.db")) {
    $dbPath = Join-Path $DataDir $dbName
    if ($Role -in @("All", "Server")) {
        Add-Check $checks "DB $dbName" (Test-Path -LiteralPath $dbPath -PathType Leaf) $dbPath
    }
}

if ($Role -in @("All", "Server")) {
    Add-Check $checks "Server port $serverPortNumber" (Test-Port $serverPortNumber) "FastAPI server.py"
    Add-Check $checks "Dashboard port $dashboardPortNumber" (Test-Port $dashboardPortNumber) "Dashboard.py"
    if ($autoCrmEnabled) {
        Add-Check $checks "Auto CRM port $autoCrmPortNumber" (Test-Port $autoCrmPortNumber) "Auto_CRM.py"
    } else {
        Add-Check $checks "Auto CRM disabled" $true "QLX_ENABLE_AUTO_CRM=0"
    }
    if ($autoCrmEnabled -or $serverZaloEnabled) {
        Add-Check $checks "OpenClaw command" (Test-Path -LiteralPath $OpenClawPath -PathType Leaf) $OpenClawPath
    } else {
        Add-Check $checks "OpenClaw not required in V2" $true "Auto_CRM/Zalo disabled"
    }
}
Add-Check $checks "NAS dist path" (Test-Path -LiteralPath $NasDistPath -PathType Container) $NasDistPath

if ($Role -in @("All", "Server")) {
    Add-Check $checks "Process server" (Test-AnyProcess @("server_Local", "server")) "server_Local/server"
    Add-Check $checks "Process Dashboard" (Test-AnyProcess @("Dashboard_Local", "Dashboard")) "Dashboard_Local/Dashboard"
    if ($autoCrmEnabled) {
        Add-Check $checks "Process Auto_CRM" (Test-AnyProcess @("Auto_CRM")) "Auto_CRM"
    } else {
        Add-Check $checks "Process Auto_CRM not required" $true "QLX_ENABLE_AUTO_CRM=0"
    }

    $serverDupDetail = ""
    Add-Check $checks "Process server duplicate guard" (Test-ProcessCountAtMostOne "server_Local" ([ref]$serverDupDetail)) $serverDupDetail

    $dashboardDupDetail = ""
    Add-Check $checks "Process Dashboard duplicate guard" (Test-ProcessCountAtMostOne "Dashboard_Local" ([ref]$dashboardDupDetail)) $dashboardDupDetail

    $cncDupDetail = ""
    Add-Check $checks "Process CNC bridge duplicate guard" (Test-ProcessCountAtMostOne "cnc_legacy_bridge" ([ref]$cncDupDetail)) $cncDupDetail
}
if ($Role -in @("All", "Machine")) {
    Add-Check $checks "Process QuanLyXuong" (Test-AnyProcess @("QuanLyXuong_Local", "QuanLyXuong")) "QuanLyXuong_Local/QuanLyXuong"

    $outboxFiles = @(Get-ChildItem -LiteralPath $DataDir -File -Filter "agent_outbox_*.db" -ErrorAction SilentlyContinue)
    if ($outboxFiles.Count -eq 0) {
        Add-Check $checks "Outbox db" $false "No agent_outbox_*.db in $DataDir"
    } else {
        foreach ($file in $outboxFiles) {
            $pending = Get-OutboxPendingCount $file.FullName
            if ($null -eq $pending) {
                Add-Check $checks "Outbox $($file.Name)" $false "Cannot read pending count"
            } else {
                Add-Check $checks "Outbox $($file.Name)" ($pending -le $OutboxWarnThreshold) "pending=$pending threshold=$OutboxWarnThreshold"
            }
        }
    }
}

$failed = 0
foreach ($check in $checks) {
    $status = if ($check.ok) { "OK" } else { "WARN" }
    if (-not $check.ok) { $failed += 1 }
    Write-Host ("[{0}] {1} - {2}" -f $status, $check.name, $check.detail)
}

Write-Host ("SUMMARY ok={0} warn={1}" -f ($checks.Count - $failed), $failed)

if ($failed -gt 0) {
    exit 1
}
