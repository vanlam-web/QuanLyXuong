param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DistPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist-new"),
    [string]$DataDir = "C:\QuanLyXuong\Data",
    [string]$BackupRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "backups\data"),
    [int]$BackupMaxAgeHours = 24,
    [switch]$SkipQualityGate
)

$ErrorActionPreference = "Stop"

function Add-Check([System.Collections.Generic.List[object]]$Checks, [string]$Name, [bool]$Ok, [string]$Detail) {
    $Checks.Add([pscustomobject]@{
        ok = $Ok
        name = $Name
        detail = $Detail
    })
}

function Env-Value([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    }
    return $value
}

function Env-IsFalse([string]$Name) {
    $value = Env-Value $Name
    if ([string]::IsNullOrWhiteSpace($value)) { return $false }
    return $value.Trim().ToLowerInvariant() -in @("0", "false", "no", "off")
}

function Get-LatestBackupManifest([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $null }
    return Get-ChildItem -LiteralPath $Root -Recurse -File -Filter "manifest.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Test-OutboxReadable([string]$DbPath) {
    $script = "import sqlite3, sys; conn=sqlite3.connect(sys.argv[1]); conn.execute(sys.argv[2]).fetchone(); conn.close(); print('OK')"
    $sql = "SELECT COUNT(*) FROM outbox_events"
    try {
        $output = & python @("-c", $script, $DbPath, $sql) 2>$null
        return (($output | Select-Object -First 1) -eq "OK")
    } catch {
        return $false
    }
}

function Run-Step([string]$Title, [scriptblock]$Step) {
    Write-Host ""
    Write-Host "========================================"
    Write-Host $Title
    Write-Host "========================================"
    & $Step
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$scripts = Join-Path $ProjectRoot "scripts"
$checks = [System.Collections.Generic.List[object]]::new()

Run-Step "1. Quality gate" {
    if ($SkipQualityGate) {
        Write-Host "Skipped by -SkipQualityGate"
        Add-Check $checks "Quality gate" $true "Skipped"
    } else {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-QuanLyXuongCode.ps1") -ProjectRoot $ProjectRoot
        Add-Check $checks "Quality gate" ($LASTEXITCODE -eq 0) "Test-QuanLyXuongCode.ps1"
    }
}

Run-Step "2. Dist-new release files" {
    $required = @("server.exe", "Dashboard.exe", "QuanLyXuong.exe", "bridge_qcvl.exe", "cnc_legacy_bridge.exe", "Auto_CRM.exe", "BUILD_MANIFEST.json")
    Add-Check $checks "Dist path" (Test-Path -LiteralPath $DistPath -PathType Container) $DistPath
    foreach ($file in $required) {
        $path = Join-Path $DistPath $file
        Add-Check $checks "Dist file $file" (Test-Path -LiteralPath $path -PathType Leaf) $path
    }

    $manifestPath = Join-Path $DistPath "BUILD_MANIFEST.json"
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $names = @($manifest.files | ForEach-Object { $_.name })
            foreach ($exe in @("server.exe", "Dashboard.exe", "QuanLyXuong.exe", "bridge_qcvl.exe", "cnc_legacy_bridge.exe", "Auto_CRM.exe")) {
                $hasHash = $false
                foreach ($item in @($manifest.files)) {
                    if ($item.name -eq $exe -and -not [string]::IsNullOrWhiteSpace($item.sha256)) {
                        $hasHash = $true
                    }
                }
                Add-Check $checks "Manifest hash $exe" ($names -contains $exe -and $hasHash) $manifestPath
            }
        } catch {
            Add-Check $checks "Manifest parse" $false $_.Exception.Message
        }
    }
}

Run-Step "3. Backup and rollback readiness" {
    $latestBackup = Get-LatestBackupManifest $BackupRoot
    if ($null -eq $latestBackup) {
        Add-Check $checks "Recent data backup" $false "No manifest under $BackupRoot"
    } else {
        $ageHours = ((Get-Date) - $latestBackup.LastWriteTime).TotalHours
        Add-Check $checks "Recent data backup" ($ageHours -le $BackupMaxAgeHours) ("{0} age_hours={1:N1}" -f $latestBackup.FullName, $ageHours)
    }
    Add-Check $checks "Rollback script" (Test-Path -LiteralPath (Join-Path $scripts "Rollback-Release.ps1") -PathType Leaf) "Rollback-Release.ps1"
    Add-Check $checks "Publish script" (Test-Path -LiteralPath (Join-Path $scripts "Publish-Release.ps1") -PathType Leaf) "Publish-Release.ps1"
    Add-Check $checks "Backup script" (Test-Path -LiteralPath (Join-Path $scripts "Backup-QuanLyXuongData.ps1") -PathType Leaf) "Backup-QuanLyXuongData.ps1"
}

Run-Step "4. V2 environment" {
    Add-Check $checks "QLX_RUNTIME_MODE=v2" ((Env-Value "QLX_RUNTIME_MODE") -eq "v2") ("current=" + (Env-Value "QLX_RUNTIME_MODE"))
    Add-Check $checks "QLX_ENABLE_AUTO_CRM=0" (Env-IsFalse "QLX_ENABLE_AUTO_CRM") ("current=" + (Env-Value "QLX_ENABLE_AUTO_CRM"))
    Add-Check $checks "QLX_ENABLE_SERVER_ZALO=0" (Env-IsFalse "QLX_ENABLE_SERVER_ZALO") ("current=" + (Env-Value "QLX_ENABLE_SERVER_ZALO"))
    $bridgeDryRun = Env-Value "QCVL_BRIDGE_DRY_RUN"
    $bridgeOk = [string]::IsNullOrWhiteSpace($bridgeDryRun) -or ($bridgeDryRun.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on"))
    Add-Check $checks "QCVL bridge dry-run not disabled" $bridgeOk ("current=" + $bridgeDryRun)
}

Run-Step "5. Data, outbox, dashboard status" {
    Add-Check $checks "Data dir" (Test-Path -LiteralPath $DataDir -PathType Container) $DataDir
    if (Test-Path -LiteralPath $DataDir -PathType Container) {
        foreach ($dbName in @("InBat.db", "InDecal.db", "CNC.db")) {
            $dbPath = Join-Path $DataDir $dbName
            Add-Check $checks "Machine DB $dbName" (Test-Path -LiteralPath $dbPath -PathType Leaf) $dbPath
        }

        $outboxFiles = @(Get-ChildItem -LiteralPath $DataDir -File -Filter "agent_outbox_*.db" -ErrorAction SilentlyContinue)
        if ($outboxFiles.Count -eq 0) {
            Add-Check $checks "Outbox readable" $true "No outbox db yet; first V2 agent run will create it"
        } else {
            foreach ($outbox in $outboxFiles) {
                Add-Check $checks "Outbox readable $($outbox.Name)" (Test-OutboxReadable $outbox.FullName) $outbox.FullName
            }
        }
    }

    $dashboardCheck = & python @("-c", "import sys; sys.path.insert(0, r'$ProjectRoot'); import Dashboard; c=Dashboard.app.test_client(); print(c.get('/api/v2_status').status_code)") 2>$null
    Add-Check $checks "Dashboard /api/v2_status" (($dashboardCheck | Select-Object -First 1) -eq "200") "Flask test client"
}

Run-Step "6. Summary" {
    $failed = 0
    foreach ($check in $checks) {
        $status = if ($check.ok) { "OK" } else { "FAIL" }
        if (-not $check.ok) { $failed += 1 }
        Write-Host ("[{0}] {1} - {2}" -f $status, $check.name, $check.detail)
    }

    Write-Host ""
    Write-Host ("SUMMARY ok={0} fail={1}" -f ($checks.Count - $failed), $failed)

    if ($failed -gt 0) {
        throw "V2 cutover preflight failed. Do not publish V2 yet."
    }
}

Write-Host ""
Write-Host "V2 cutover preflight OK. Safe to proceed to controlled publish step."
