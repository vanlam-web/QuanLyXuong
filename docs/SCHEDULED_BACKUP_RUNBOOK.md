# Scheduled backup runbook

Muc tieu: tu dong backup du lieu xuong moi ngay.

## Cai lich backup hang ngay

Mac dinh chay luc `23:30`:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Install-QuanLyXuongBackupTask.ps1
```

Doi gio:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Install-QuanLyXuongBackupTask.ps1 -At 12:00
```

## Noi backup

```text
Z:\Tools\backups\data\scheduled-YYYYMMDD-HHMMSS
```

Log lich backup:

```text
Z:\Tools\backups\logs
```

## Dọn backup cũ

Task tu dong giu toi thieu 10 backup moi nhat va xoa backup cu hon 30 ngay.

Chay tay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Cleanup-QuanLyXuongBackups.ps1
```

## Go lich backup

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Uninstall-QuanLyXuongBackupTask.ps1
```

## Luu y

- Backup theo lich co `-IncludeLogs`.
- Backup dung SQLite online backup API.
- Thu muc `backups/` khong commit Git.
