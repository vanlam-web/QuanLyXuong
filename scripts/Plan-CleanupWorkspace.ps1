param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$archiveRoot = Join-Path $ProjectRoot "archive"
$oldBuilds = Join-Path $archiveRoot "old-builds"
$oldRootFiles = Join-Path $archiveRoot "old-root-files"

$moves = @()

Get-ChildItem -LiteralPath $ProjectRoot -Directory |
    Where-Object {
        $_.Name -like "build*" -or
        $_.Name -like "dist-*" -or
        $_.Name -eq "__pycache__"
    } |
    ForEach-Object {
        $moves += [PSCustomObject]@{
            Source = $_.FullName
            Target = Join-Path $oldBuilds $_.Name
            Reason = "temporary build/output folder"
        }
    }

@(
    "KhoiDongBot_CNC_Win7_py36.bat",
    "KhoiDongCNCWin7_py36_x86.bat",
    "KhoiDongCNCWin7_x86.bat",
    "TestCNCWin7_py36_Local_console.bat",
    "TestCNCWin7_py36_x86_console.bat",
    "TestCNCWin7_x86_console.bat",
    "CapNhatDashboardPreviewCNC.bat",
    "RestartQuanLyXuongService.bat"
) | ForEach-Object {
    $path = Join-Path $ProjectRoot $_
    if (Test-Path -LiteralPath $path) {
        $moves += [PSCustomObject]@{
            Source = $path
            Target = Join-Path $oldRootFiles $_
            Reason = "manual helper script; keep archived after moving to scripts"
        }
    }
}

$moves | Format-Table -AutoSize

Write-Host ""
Write-Host "Dry-run only. No files moved."
Write-Host "To apply later, create a separate Apply-CleanupWorkspace.ps1 after review."
