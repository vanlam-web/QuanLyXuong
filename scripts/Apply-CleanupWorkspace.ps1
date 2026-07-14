param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$archiveRoot = Join-Path $ProjectRoot "archive"
$oldBuilds = Join-Path $archiveRoot "old-builds"
$oldRootFiles = Join-Path $archiveRoot "old-root-files"
$oldDocs = Join-Path $archiveRoot "old-root-docs"
$v1Backup = Join-Path $archiveRoot "v1-backup"
$manifestPath = Join-Path $archiveRoot ("cleanup_manifest_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Assert-UnderRoot([string]$Path, [string]$Root) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $full.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refuse path outside root: $full"
    }
    return $full
}

function Unique-Target([string]$Target) {
    if (-not (Test-Path -LiteralPath $Target)) { return $Target }
    $parent = Split-Path -Parent $Target
    $leaf = Split-Path -Leaf $Target
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    return (Join-Path $parent "$leaf.$stamp")
}

$moves = @()

Get-ChildItem -LiteralPath $ProjectRoot -Directory |
    Where-Object {
        $_.Name -like "build-*" -or
        $_.Name -eq "build" -or
        $_.Name -like "dist-*" -or
        $_.Name -eq "__pycache__"
    } |
    Where-Object {
        $_.Name -ne "build-specs"
    } |
    ForEach-Object {
        $moves += [PSCustomObject]@{
            Source = $_.FullName
            Target = Join-Path $oldBuilds $_.Name
            Reason = "temporary build/output folder"
        }
    }

@(
    "KhoiDongAdminConsole.bat",
    "KhoiDongBot.bat",
    "KhoiDongBot.example.bat",
    "KhoiDongV2Runtime.bat",
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
            Reason = "manual helper script moved out of root"
        }
    }
}

@(
    "BAO_CAO_LUONG_HE_THONG.md",
    "HD.txt",
    "KE_HOACH_NANG_CAP.md"
) | ForEach-Object {
    $path = Join-Path $ProjectRoot $_
    if (Test-Path -LiteralPath $path) {
        $moves += [PSCustomObject]@{
            Source = $path
            Target = Join-Path $oldDocs $_
            Reason = "legacy root document moved out of root"
        }
    }
}

@(
    "Auto_CRM.spec",
    "server.spec"
) | ForEach-Object {
    $path = Join-Path $ProjectRoot $_
    if (Test-Path -LiteralPath $path) {
        $moves += [PSCustomObject]@{
            Source = $path
            Target = Join-Path $oldRootFiles $_
            Reason = "old root spec; build-specs contains current specs"
        }
    }
}

$oldV1 = Join-Path $ProjectRoot "05062026-1632"
if (Test-Path -LiteralPath $oldV1 -PathType Container) {
    $moves += [PSCustomObject]@{
        Source = $oldV1
        Target = Join-Path $v1Backup "05062026-1632"
        Reason = "old V1 backup folder moved out of root"
    }
}

$moves = $moves | Sort-Object Source -Unique

if (-not $Apply) {
    $moves | Format-Table -AutoSize
    Write-Host ""
    Write-Host "Dry-run only. Add -Apply to move files."
    return
}

New-Item -ItemType Directory -Force -Path $oldBuilds, $oldRootFiles, $oldDocs, $v1Backup | Out-Null

$records = @()
foreach ($move in $moves) {
    if (-not (Test-Path -LiteralPath $move.Source)) { continue }
    $sourceFull = Assert-UnderRoot $move.Source $ProjectRoot
    $targetFull = Assert-UnderRoot (Unique-Target $move.Target) $archiveRoot
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetFull) | Out-Null

    Move-Item -LiteralPath $sourceFull -Destination $targetFull
    $records += [PSCustomObject]@{
        source = $sourceFull
        target = $targetFull
        reason = $move.Reason
        moved_at = (Get-Date).ToString("s")
    }
}

$records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Moved $($records.Count) item(s)."
Write-Host "Manifest: $manifestPath"
