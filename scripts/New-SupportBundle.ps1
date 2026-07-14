param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "support-bundles"),
    [string]$BundleName = ("support-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
)

$ErrorActionPreference = "Continue"

function Write-Text([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $Content | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Run-Capture([string]$Path, [scriptblock]$Command) {
    try {
        $output = & $Command 2>&1 | Out-String
        Write-Text $Path $output
    } catch {
        Write-Text $Path "ERROR: $($_.Exception.Message)"
    }
}

function Copy-IfExists([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

function Copy-Tail([string]$Source, [string]$Destination, [int]$Lines = 300) {
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        $content = Get-Content -LiteralPath $Source -Tail $Lines -ErrorAction SilentlyContinue
        Write-Text $Destination ($content -join [Environment]::NewLine)
    }
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$BundlePath = Join-Path $OutputRoot $BundleName
$ZipPath = "$BundlePath.zip"

if (Test-Path -LiteralPath $BundlePath) {
    throw "Bundle folder already exists: $BundlePath"
}
if (Test-Path -LiteralPath $ZipPath) {
    throw "Bundle zip already exists: $ZipPath"
}

New-Item -ItemType Directory -Force -Path $BundlePath | Out-Null

Write-Text (Join-Path $BundlePath "README.txt") @"
Quan Ly Xuong support bundle
Created: $(Get-Date -Format "s")
Project: $ProjectRoot

This bundle is for troubleshooting. It should not include local credential BAT files or .env secrets.
"@

Run-Capture (Join-Path $BundlePath "healthcheck.txt") {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\Test-QuanLyXuongHealth.ps1")
}

Run-Capture (Join-Path $BundlePath "python-environment.txt") {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\Test-PythonEnvironment.ps1")
}

Run-Capture (Join-Path $BundlePath "git-status.txt") {
    git -C $ProjectRoot status --short --branch
    git -C $ProjectRoot log --oneline -5
}

Run-Capture (Join-Path $BundlePath "file-list.txt") {
    Get-ChildItem -LiteralPath $ProjectRoot -Force | Select-Object Mode, Length, LastWriteTime, Name | Format-Table -AutoSize
}

Run-Capture (Join-Path $BundlePath "data-list.txt") {
    Get-ChildItem -LiteralPath "C:\QuanLyXuong\Data" -Force -ErrorAction SilentlyContinue | Select-Object Mode, Length, LastWriteTime, Name | Format-Table -AutoSize
}

Copy-IfExists (Join-Path $ProjectRoot "CHANGELOG.md") (Join-Path $BundlePath "project\CHANGELOG.md")
Copy-IfExists (Join-Path $ProjectRoot "docs\MASTER_PLAN.md") (Join-Path $BundlePath "project\MASTER_PLAN.md")
Copy-IfExists (Join-Path $ProjectRoot ".env.example") (Join-Path $BundlePath "project\.env.example")

Copy-Tail "C:\QuanLyXuong\Server_Log.txt" (Join-Path $BundlePath "logs\Server_Log.tail.txt")
Copy-Tail "C:\QuanLyXuong\Dashboard_Log.txt" (Join-Path $BundlePath "logs\Dashboard_Log.tail.txt")
Copy-Tail "C:\QuanLyXuong\QCVL_Bridge_Log.txt" (Join-Path $BundlePath "logs\QCVL_Bridge_Log.tail.txt")
Copy-Tail "C:\QuanLyXuong\Data_Auto_CRM\Auto_CRM_Log.txt" (Join-Path $BundlePath "logs\Auto_CRM_Log.tail.txt")

Run-Capture (Join-Path $BundlePath "processes.txt") {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match "python|server|Dashboard|Auto_CRM|QuanLyXuong|powershell|cmd"
        } |
        Select-Object ProcessId, Name, CommandLine |
        Format-List
}

Compress-Archive -LiteralPath $BundlePath -DestinationPath $ZipPath -Force

Write-Host "Support bundle created:"
Write-Host $ZipPath
