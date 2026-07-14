param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Continue"

function Show-Header {
    Clear-Host
    Write-Host "========================================"
    Write-Host "  QUAN LY XUONG - ADMIN CONSOLE"
    Write-Host "========================================"
    Write-Host ""
    Write-Host "Project: $ProjectRoot"
    Write-Host ""
}

function Pause-Admin {
    Write-Host ""
    Read-Host "Nhan Enter de quay lai menu"
}

function Run-Script([string]$ScriptName, [string[]]$Arguments = @()) {
    $scriptPath = Join-Path $ProjectRoot "scripts\$ScriptName"
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        Write-Host "Khong tim thay script: $scriptPath"
        return
    }

    & powershell -ExecutionPolicy Bypass -File $scriptPath @Arguments
}

function Run-BridgeDryRun {
    $bridgePath = Join-Path $ProjectRoot "app\bridge_qcvl.py"
    if (-not (Test-Path -LiteralPath $bridgePath -PathType Leaf)) {
        Write-Host "Khong tim thay bridge: $bridgePath"
        return
    }

    python $bridgePath --dry-run
}

function Show-RecentLog([string]$Path, [int]$Lines = 80) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Host "Chua co log: $Path"
        return
    }

    Get-Content -LiteralPath $Path -Tail $Lines
}

function Publish-Release {
    $newDistPath = Read-Host "Nhap duong dan dist moi (mac dinh Z:\Tools\dist-new)"
    if ([string]::IsNullOrWhiteSpace($newDistPath)) {
        $newDistPath = Join-Path $ProjectRoot "dist-new"
    }

    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se backup DB, backup dist cu, roi copy ban moi vao dist."
    Write-Host "Chi chay khi ban da san sang deploy."
    $confirm = Read-Host "Go DEPLOY de xac nhan"
    if ($confirm -ne "DEPLOY") {
        Write-Host "Da huy deploy."
        return
    }

    Run-Script "Publish-Release.ps1" @("-NewDistPath", $newDistPath)
}

function Rollback-Release {
    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se dua dist ve ban rollback gan nhat."
    $confirm = Read-Host "Go ROLLBACK de xac nhan"
    if ($confirm -ne "ROLLBACK") {
        Write-Host "Da huy rollback."
        return
    }

    Run-Script "Rollback-Release.ps1"
}

function Restore-DataBackup {
    $backupPath = Read-Host "Nhap duong dan backup data can restore"
    if ([string]::IsNullOrWhiteSpace($backupPath)) {
        Write-Host "Da huy restore."
        return
    }

    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se ghi de DB trong C:\QuanLyXuong\Data."
    Write-Host "Script se backup du lieu hien tai truoc khi restore."
    $confirm = Read-Host "Go RESTORE de xac nhan"
    if ($confirm -ne "RESTORE") {
        Write-Host "Da huy restore."
        return
    }

    Run-Script "Restore-QuanLyXuongData.ps1" @("-BackupPath", $backupPath)
}

function Apply-V2Mode {
    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se dat env V2 cho user hien tai."
    Write-Host "Sau khi restart app, server se khong goi Auto_CRM va khong gui Zalo auto."
    $confirm = Read-Host "Go V2 de xac nhan"
    if ($confirm -ne "V2") {
        Write-Host "Da huy bat V2 mode."
        return
    }

    Run-Script "Set-V2Mode.ps1" @("-Apply")
}

function Apply-LegacyMode {
    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se dat env ve legacy cho user hien tai."
    $confirm = Read-Host "Go LEGACY de xac nhan"
    if ($confirm -ne "LEGACY") {
        Write-Host "Da huy ve legacy."
        return
    }

    Run-Script "Set-V2Mode.ps1" @("-Legacy", "-Apply")
}

function Start-V2Runtime {
    Write-Host ""
    Write-Host "CANH BAO: Lenh nay se restart server_Local va Dashboard_Local theo V2 mode."
    Write-Host "Auto_CRM se khong duoc start."
    $confirm = Read-Host "Go V2START de xac nhan"
    if ($confirm -ne "V2START") {
        Write-Host "Da huy start V2 runtime."
        return
    }

    Run-Script "Start-V2Runtime.ps1" @("-Restart")
}

while ($true) {
    Show-Header
    Write-Host "1. Healthcheck he thong"
    Write-Host "2. Backup database ngay"
    Write-Host "3. QCVL bridge dry-run"
    Write-Host "4. Xem log bridge QCVL"
    Write-Host "5. Xuat mau payload QCVL bridge"
    Write-Host "6. Kiem tra moi truong Python"
    Write-Host "7. Kiem tra code/script"
    Write-Host "8. Chay unit test"
    Write-Host "9. Preflight truoc deploy"
    Write-Host "10. Build ban moi vao dist-new"
    Write-Host "11. Publish ban moi (co backup + rollback)"
    Write-Host "12. Rollback ve ban cu"
    Write-Host "13. Restore database tu backup"
    Write-Host "14. Tao goi chan doan cho AI"
    Write-Host "15. Cai lich backup tu dong"
    Write-Host "16. Xem ke hoach tong"
    Write-Host "17. Xem ke hoach V2"
    Write-Host "18. Kiem tra san sang V2"
    Write-Host "19. Bat V2 mode (tat Auto_CRM/Zalo auto)"
    Write-Host "20. Ve legacy mode"
    Write-Host "21. V2 preflight truoc publish"
    Write-Host "22. Start V2 runtime (server + dashboard, khong Auto_CRM)"
    Write-Host "23. V2 cutover preflight thay V1"
    Write-Host "0. Thoat"
    Write-Host ""

    $choice = Read-Host "Chon"
    if ([string]::IsNullOrWhiteSpace($choice)) {
        break
    }
    Show-Header

    switch ($choice) {
        "1" { Run-Script "Test-QuanLyXuongHealth.ps1"; Pause-Admin }
        "2" { Run-Script "Backup-QuanLyXuongData.ps1"; Pause-Admin }
        "3" { Run-BridgeDryRun; Pause-Admin }
        "4" { Show-RecentLog "C:\QuanLyXuong\QCVL_Bridge_Log.txt"; Pause-Admin }
        "5" { Run-Script "Export-QcvlBridgeSample.ps1"; Pause-Admin }
        "6" { Run-Script "Test-PythonEnvironment.ps1"; Pause-Admin }
        "7" { Run-Script "Test-QuanLyXuongCode.ps1"; Pause-Admin }
        "8" { Run-Script "Run-UnitTests.ps1"; Pause-Admin }
        "9" { Run-Script "Invoke-PreDeployCheck.ps1"; Pause-Admin }
        "10" { Run-Script "Build-Release.ps1" @("-Clean"); Pause-Admin }
        "11" { Publish-Release; Pause-Admin }
        "12" { Rollback-Release; Pause-Admin }
        "13" { Restore-DataBackup; Pause-Admin }
        "14" { Run-Script "New-SupportBundle.ps1"; Pause-Admin }
        "15" { Run-Script "Install-QuanLyXuongBackupTask.ps1"; Pause-Admin }
        "16" { Get-Content -LiteralPath (Join-Path $ProjectRoot "docs\MASTER_PLAN.md"); Pause-Admin }
        "17" { Get-Content -LiteralPath (Join-Path $ProjectRoot "docs\V2_IMPLEMENTATION_PLAN.md"); Pause-Admin }
        "18" { Run-Script "Test-V2Readiness.ps1"; Pause-Admin }
        "19" { Apply-V2Mode; Pause-Admin }
        "20" { Apply-LegacyMode; Pause-Admin }
        "21" { Run-Script "Invoke-V2Preflight.ps1"; Pause-Admin }
        "22" { Start-V2Runtime; Pause-Admin }
        "23" { Run-Script "Invoke-V2CutoverPreflight.ps1"; Pause-Admin }
        "0" { break }
        default { Write-Host "Lua chon khong hop le."; Pause-Admin }
    }
}

