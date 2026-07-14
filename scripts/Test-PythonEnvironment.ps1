param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Continue"

$requirementsPath = Join-Path $ProjectRoot "requirements.txt"
if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "requirements.txt not found: $requirementsPath"
}

Write-Host "Python:"
python --version

Write-Host ""
Write-Host "Required packages:"
$missing = @()
Get-Content -LiteralPath $requirementsPath | ForEach-Object {
    $name = $_.Trim()
    if ($name -eq "" -or $name.StartsWith("#")) {
        return
    }

    $result = python -m pip show $name 2>$null
    if ($LASTEXITCODE -eq 0) {
        $version = ($result | Select-String -Pattern "^Version:" | Select-Object -First 1).Line
        Write-Host "[OK] $name $version"
    } else {
        Write-Host "[MISSING] $name"
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Install missing packages:"
    Write-Host "python -m pip install -r $requirementsPath"
    exit 1
}

Write-Host ""
Write-Host "Python environment OK"
