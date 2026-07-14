param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Run-Step([string]$Title, [scriptblock]$Step) {
    Write-Host ""
    Write-Host "== $Title =="
    & $Step
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$pythonFiles = @(
    "app\qlx_config.py",
    "app\qlx_outbox.py",
    "app\qlx_workstation_logic.py",
    "app\server.py",
    "app\Dashboard.py",
    "app\Auto_CRM.py",
    "app\QuanLyXuong.py",
    "app\bridge_qcvl.py"
) | ForEach-Object { Join-Path $ProjectRoot $_ }

$powerShellFiles = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "scripts") -File -Filter "*.ps1" | Sort-Object Name

Run-Step "Python environment" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\Test-PythonEnvironment.ps1") -ProjectRoot $ProjectRoot
}

Run-Step "Python compile" {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    python -B -m py_compile @pythonFiles
}

Run-Step "Unit tests" {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\Run-UnitTests.ps1") -ProjectRoot $ProjectRoot
}

Run-Step "PowerShell syntax" {
    foreach ($file in $powerShellFiles) {
        $tokens = $null
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) > $null
        if ($errors.Count -gt 0) {
            Write-Host "ERROR $($file.FullName)"
            $errors | Format-List *
            throw "PowerShell syntax failed: $($file.FullName)"
        }
        Write-Host "OK $($file.Name)"
    }
}

Run-Step "Config import" {
    $env:PYTHONIOENCODING = "utf-8"
    $appRoot = Join-Path $ProjectRoot "app"
    python -B -c "import sys; sys.path.insert(0, r'$appRoot'); import qlx_config; print(qlx_config.DB_DIR); print(qlx_config.API_SERVER_URL)"
}

Run-Step "JSON docs" {
    $jsonFiles = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "docs") -File -Filter "*.json" | Sort-Object Name
    foreach ($file in $jsonFiles) {
        Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json > $null
        Write-Host "OK $($file.Name)"
    }
}

Run-Step "Bridge dry-run smoke" {
    $state = Join-Path $env:TEMP "qcvl_bridge_quality_state.json"
    $log = Join-Path $env:TEMP "qcvl_bridge_quality_log.txt"
    Remove-Item -LiteralPath $state, $log -ErrorAction SilentlyContinue
    python (Join-Path $ProjectRoot "app\bridge_qcvl.py") --dry-run --state-file $state --log-file $log --since-minutes 10 --limit 1
}

Write-Host ""
Write-Host "Quality gate OK"


