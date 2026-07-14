param(
    [string]$NasDistPath = "\\192.168.1.188\AI\Tools\dist",
    [string]$LocalDir = "C:\QuanLyXuong\Client",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

$sourceExe = Join-Path $NasDistPath "QuanLyXuong.exe"
$sourceManifest = Join-Path $NasDistPath "BUILD_MANIFEST.json"
$localExe = Join-Path $LocalDir "QuanLyXuong.exe"
$localManifest = Join-Path $LocalDir "BUILD_MANIFEST.json"
$logPath = Join-Path $LocalDir "client_launcher.log"

function Write-LauncherLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null

if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
    throw "NAS client exe not found: $sourceExe"
}

Copy-Item -LiteralPath $sourceExe -Destination $localExe -Force

if (Test-Path -LiteralPath $sourceManifest -PathType Leaf) {
    Copy-Item -LiteralPath $sourceManifest -Destination $localManifest -Force
    $manifest = Get-Content -LiteralPath $sourceManifest -Raw | ConvertFrom-Json
    $expected = ($manifest.files | Where-Object { $_.name -eq "QuanLyXuong.exe" } | Select-Object -First 1).sha256
    if ($expected) {
        $actual = (Get-FileHash -LiteralPath $localExe -Algorithm SHA256).Hash
        if ($actual -ne $expected) {
            throw "Local client hash mismatch. expected=$expected actual=$actual"
        }
        Write-LauncherLog "Hash OK $($actual.Substring(0, 12))"
    }
}

if ($NoStart) {
    Write-LauncherLog "Copied only: $localExe"
    exit 0
}

Write-LauncherLog "Start local client: $localExe"
Start-Process -FilePath $localExe -WorkingDirectory $LocalDir -WindowStyle Hidden
