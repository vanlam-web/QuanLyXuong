param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = $ProjectRoot

python -B -m unittest discover -s (Join-Path $ProjectRoot "tests") -p "test_*.py" -v
