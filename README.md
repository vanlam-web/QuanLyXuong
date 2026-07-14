# Quan Ly Xuong

He thong noi bo quan ly luong san xuat, dashboard, Auto CRM va gui Zalo qua OpenClaw.

## Mo cong cu quan tri

Chay:

```text
Z:\Tools\KhoiDongAdminConsole.bat
```

Menu nay dung cho viec khong can code: healthcheck, backup, test, build, publish, rollback, restore va xuat goi chan doan cho AI.

## Viec nen chay hang ngay

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1
```

Neu muon backup ngay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Backup-QuanLyXuongData.ps1
```

## Chay V2 runtime

```text
Z:\Tools\KhoiDongV2Runtime.bat
```

V2 runtime start server + dashboard, khong start `Auto_CRM.exe`.

## Truoc khi deploy ban moi

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-PreDeployCheck.ps1
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-V2Readiness.ps1
```

Lenh dau chay quality gate, healthcheck, backup data va tao support bundle. Lenh sau kiem tra may da cau hinh theo V2 chua.

## Khi ban moi bi loi

Rollback ve ban cu:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Rollback-Release.ps1
```

Neu can khoi phuc database:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Restore-QuanLyXuongData.ps1 -BackupPath <backup-folder>
```

## QCVL bridge

Bridge hien mac dinh dry-run, khong gui that sang QCVL.

Xuat mau payload:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Export-QcvlBridgeSample.ps1
```

Hop dong API nam o:

```text
Z:\Tools\docs\QCVL_PRODUCTION_EVENTS_CONTRACT.md
Z:\Tools\docs\production-event.schema.json
```

## Cau hinh va secret

Khong commit mat khau, PIN, token, group Zalo that vao Git.

Mau cau hinh:

```text
Z:\Tools\.env.example
Z:\Tools\KhoiDongBot.example.bat
```

File that dang bi ignore:

```text
Z:\Tools\.env
Z:\Tools\KhoiDongBot.bat
```

## Tai lieu chinh

```text
Z:\Tools\docs\MASTER_PLAN.md
Z:\Tools\docs\V2_IMPLEMENTATION_PLAN.md
Z:\Tools\docs\V2_RUNBOOK.md
Z:\Tools\docs\ADMIN_CONSOLE_RUNBOOK.md
Z:\Tools\docs\PREDEPLOY_RUNBOOK.md
Z:\Tools\docs\ROLLBACK_DEPLOYMENT.md
Z:\Tools\CHANGELOG.md
```
