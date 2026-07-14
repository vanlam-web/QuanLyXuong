param(
    [string]$DistDashboard = "Z:\Tools\dist\Dashboard.exe",
    [string]$LocalDashboard = "C:\QuanLyXuong\Dashboard_Local.exe",
    [string]$DistPublic = "Z:\Tools\dist\public",
    [string]$LocalPublic = "C:\QuanLyXuong\public"
)

$ErrorActionPreference = "Continue"

$runningDashboards = Get-CimInstance Win32_Process -Filter "name = 'Dashboard_Local.exe' or name = 'Dashboard_V2.exe'"
$runningDashboards | ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}
foreach ($dashboard in $runningDashboards) {
    try { Wait-Process -Id $dashboard.ProcessId -Timeout 8 -ErrorAction Stop } catch {}
}

Start-Sleep -Seconds 2
Copy-Item -LiteralPath $DistDashboard -Destination $LocalDashboard -Force
if (Test-Path -LiteralPath $DistPublic -PathType Container) {
    New-Item -ItemType Directory -Force -Path $LocalPublic | Out-Null
    Copy-Item -Path (Join-Path $DistPublic "*") -Destination $LocalPublic -Recurse -Force
}
Start-Process -FilePath $LocalDashboard -WorkingDirectory (Split-Path -Parent $LocalDashboard) -WindowStyle Hidden
