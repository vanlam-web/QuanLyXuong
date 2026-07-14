param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DistPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist-new"),
    [string]$WorkPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "build-new"),
    [string]$SpecPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "build-specs"),
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$apps = @(
    @{ name = "server"; script = "app\server.py"; extra = @() },
    @{ name = "Dashboard"; script = "app\Dashboard.py"; extra = @() },
    @{ name = "QuanLyXuong"; script = "app\QuanLyXuong.py"; extra = @() },
    @{ name = "bridge_qcvl"; script = "app\bridge_qcvl.py"; extra = @() },
    @{ name = "cnc_legacy_bridge"; script = "app\cnc_legacy_bridge.py"; extra = @() },
    @{
        name = "Auto_CRM"
        script = "app\Auto_CRM.py"
        extra = @(
            "--hidden-import", "selenium.webdriver.chrome.options",
            "--hidden-import", "selenium.webdriver.chrome.service",
            "--hidden-import", "selenium.webdriver.chrome.webdriver"
        )
    }
)

function Run-Step([string]$Title, [scriptblock]$Step) {
    Write-Host ""
    Write-Host "== $Title =="
    & $Step
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$AppPath = Join-Path $ProjectRoot "app"

if ($Clean) {
    if (Test-Path -LiteralPath $DistPath) { Remove-Item -LiteralPath $DistPath -Recurse -Force }
    if (Test-Path -LiteralPath $WorkPath) { Remove-Item -LiteralPath $WorkPath -Recurse -Force }
    if (Test-Path -LiteralPath $SpecPath) { Remove-Item -LiteralPath $SpecPath -Recurse -Force }
}

New-Item -ItemType Directory -Force -Path $DistPath | Out-Null
New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null
New-Item -ItemType Directory -Force -Path $SpecPath | Out-Null

Run-Step "Check Python environment" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\Test-PythonEnvironment.ps1") -ProjectRoot $ProjectRoot
}

foreach ($app in $apps) {
    $scriptPath = Join-Path $ProjectRoot $app.script
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        throw "Missing app script: $scriptPath"
    }

    Run-Step "Build $($app.name)" {
        $args = @(
            "--onefile",
            "--name", $app.name,
            "--distpath", $DistPath,
            "--workpath", (Join-Path $WorkPath $app.name),
            "--specpath", $SpecPath,
            "--paths", $ProjectRoot
            "--paths", $AppPath
        ) + $app.extra + @($scriptPath)

        & pyinstaller @args
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed for $($app.name)"
        }
    }
}

$required = @("server.exe", "Dashboard.exe", "QuanLyXuong.exe", "bridge_qcvl.exe", "cnc_legacy_bridge.exe", "Auto_CRM.exe")
foreach ($exe in $required) {
    $path = Join-Path $DistPath $exe
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Build missing expected exe: $path"
    }
}

$manifest = [pscustomobject]@{
    createdAt = (Get-Date).ToString("s")
    projectRoot = $ProjectRoot
    distPath = $DistPath
    files = Get-ChildItem -LiteralPath $DistPath -File -Filter "*.exe" | Sort-Object Name | ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        [pscustomobject]@{
            name = $_.Name
            size = $_.Length
            sha256 = $hash.Hash
        }
    }
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $DistPath "BUILD_MANIFEST.json") -Encoding UTF8

Write-Host ""
Write-Host "Build complete: $DistPath"

