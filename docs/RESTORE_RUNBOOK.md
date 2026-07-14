# Restore runbook

Muc tieu: khoi phuc database tu backup khi can, co backup nguoc truoc khi ghi de.

## Nguyen tac an toan

- Khong restore khi server/dashboard/Auto CRM dang dung DB.
- Mac dinh script tu choi restore neu port `8000`, `5000`, `8001` dang mo.
- Truoc khi restore, script tu backup du lieu hien tai vao `pre-restore-*`.

## Restore tu backup

Vi du:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Restore-QuanLyXuongData.ps1 -BackupPath Z:\Tools\backups\data\20260709-190000
```

Neu bat buoc restore khi service con dang mo:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Restore-QuanLyXuongData.ps1 -BackupPath Z:\Tools\backups\data\20260709-190000 -Force
```

Chi dung `-Force` khi hieu ro rui ro.

## Du lieu duoc restore

```text
C:\QuanLyXuong\Data\*.db
C:\QuanLyXuong\Data\*.json neu co trong backup
```

## Sau restore

1. Khoi dong lai server/dashboard/Auto CRM neu can.
2. Chay healthcheck.

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1
```
