param(
    [string]$NasDistPath = "\\192.168.1.188\AI\Tools\dist-auto-update",
    [string]$LocalRoot = "C:\QuanLyXuong",
    [string]$LocalDir = "",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

if ($LocalDir) {
    $LocalRoot = Split-Path -Parent $LocalDir
}

$localExe = Join-Path $LocalRoot "QuanLyXuong_Local.exe"
$clientDir = Join-Path $LocalRoot "Client"
$clientExe = Join-Path $clientDir "QuanLyXuong.exe"
$localManifest = Join-Path $LocalRoot "BUILD_MANIFEST.json"
$clientManifest = Join-Path $clientDir "BUILD_MANIFEST.json"
$logPath = Join-Path $LocalRoot "client_launcher.log"

function Write-LauncherLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Get-ManifestHash($Manifest, [string]$FileName) {
    $entry = $Manifest.files | Where-Object { $_.name -eq $FileName } | Select-Object -First 1
    if (-not $entry) { return "" }
    if (-not $entry.sha256) { return "" }
    return $entry.sha256.ToUpperInvariant()
}

function Read-UpdateSource([string]$Path) {
    $exe = Join-Path $Path "QuanLyXuong.exe"
    $manifestPath = Join-Path $Path "BUILD_MANIFEST.json"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "NAS client exe not found: $exe" }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "NAS manifest not found: $manifestPath" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $expected = Get-ManifestHash $manifest "QuanLyXuong.exe"
    if (-not $expected) { throw "QuanLyXuong.exe hash missing in BUILD_MANIFEST.json" }
    $actual = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToUpperInvariant()
    return [pscustomobject]@{
        Path = $Path
        Exe = $exe
        ManifestPath = $manifestPath
        Expected = $expected
        Actual = $actual
        IsMatch = ($actual -eq $expected)
    }
}

function Resolve-UpdateSource([string]$PreferredPath) {
    $source = Read-UpdateSource $PreferredPath
    if ($source.IsMatch) { return $source }

    $parent = Split-Path -Parent $PreferredPath
    $leaf = Split-Path -Leaf $PreferredPath
    if ($leaf -ne "dist") { return $source }

    $fallbackPath = Join-Path $parent "dist-auto-update"
    if (-not (Test-Path -LiteralPath $fallbackPath -PathType Container)) { return $source }
    $fallback = Read-UpdateSource $fallbackPath
    if ($fallback.IsMatch -and $fallback.Expected -eq $source.Expected) {
        Write-LauncherLog "SOURCE_SWITCH dist -> dist-auto-update $($fallback.Actual.Substring(0, 12))"
        return $fallback
    }
    return $source
}

New-Item -ItemType Directory -Force -Path $LocalRoot | Out-Null
New-Item -ItemType Directory -Force -Path $clientDir | Out-Null

$source = Resolve-UpdateSource $NasDistPath
$sourceExe = $source.Exe
$sourceManifest = $source.ManifestPath
$expected = $source.Expected

Stop-Process -Name QuanLyXuong -Force -ErrorAction SilentlyContinue
Stop-Process -Name QuanLyXuong_Local -Force -ErrorAction SilentlyContinue

Copy-Item -LiteralPath $sourceExe -Destination $localExe -Force
Copy-Item -LiteralPath $sourceExe -Destination $clientExe -Force

Copy-Item -LiteralPath $sourceManifest -Destination $localManifest -Force
Copy-Item -LiteralPath $sourceManifest -Destination $clientManifest -Force

$actual = (Get-FileHash -LiteralPath $localExe -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actual -ne $expected) {
    throw "Local client hash mismatch. expected=$expected actual=$actual"
}
Write-LauncherLog "Hash OK $($actual.Substring(0, 12))"

if ($NoStart) {
    Write-LauncherLog "Copied only: $localExe"
    exit 0
}

Write-LauncherLog "Start local client: $localExe"
Start-Process -FilePath $localExe -WorkingDirectory $LocalRoot -WindowStyle Hidden
