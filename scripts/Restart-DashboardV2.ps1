param(
    [string]$DistDashboard = "Z:\Tools\dist\Dashboard.exe",
    [string]$LocalDashboard = "C:\QuanLyXuong\Dashboard_Local.exe",
    [string]$DistPublic = "Z:\Tools\dist\public",
    [string]$LocalPublic = "C:\QuanLyXuong\public"
)

$ErrorActionPreference = "Stop"

function Assert-ProcessCount([string]$Name, [int]$Expected) {
    $items = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if ($items.Count -ne $Expected) {
        $detail = ($items | ForEach-Object {
            $path = ""
            try { $path = $_.Path } catch { $path = "" }
            "pid=$($_.Id) path=$path"
        }) -join "; "
        throw "Dashboard process count mismatch for $Name. expected=$Expected actual=$($items.Count) $detail"
    }
}

$runningDashboards = Get-CimInstance Win32_Process -Filter "name = 'Dashboard_Local.exe' or name = 'Dashboard_V2.exe'"
$runningDashboards | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
}
foreach ($dashboard in $runningDashboards) {
    try { Wait-Process -Id $dashboard.ProcessId -Timeout 8 -ErrorAction Stop } catch {}
}
Assert-ProcessCount "Dashboard_Local" 0

Start-Sleep -Seconds 2
Copy-Item -LiteralPath $DistDashboard -Destination $LocalDashboard -Force
if (Test-Path -LiteralPath $DistPublic -PathType Container) {
    New-Item -ItemType Directory -Force -Path $LocalPublic | Out-Null
    Copy-Item -Path (Join-Path $DistPublic "*") -Destination $LocalPublic -Recurse -Force
}
Start-Process -FilePath $LocalDashboard -WorkingDirectory (Split-Path -Parent $LocalDashboard) -WindowStyle Hidden
Start-Sleep -Seconds 2
Assert-ProcessCount "Dashboard_Local" 1
