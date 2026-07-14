param(
    [string]$DistDashboard = "Z:\Tools\dist\Dashboard.exe",
    [string]$LocalDashboard = "C:\QuanLyXuong\Dashboard_Local.exe"
)

$ErrorActionPreference = "Continue"

Get-CimInstance Win32_Process -Filter "name = 'Dashboard_Local.exe' or name = 'Dashboard_V2.exe'" |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }

Start-Sleep -Seconds 2
Copy-Item -LiteralPath $DistDashboard -Destination $LocalDashboard -Force
Start-Process -FilePath $LocalDashboard -WorkingDirectory (Split-Path -Parent $LocalDashboard) -WindowStyle Hidden
