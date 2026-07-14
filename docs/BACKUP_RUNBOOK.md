# Backup runbook

Muc tieu: backup du lieu xuong truoc khi deploy, khong can tat server cu.

## Backup mac dinh

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Backup-QuanLyXuongData.ps1
```

Backup se nam o:

```text
Z:\Tools\backups\data\YYYYMMDD-HHMMSS
```

No backup cac SQLite database bang SQLite online backup API, tot hon copy thang file `.db` khi server dang chay.

## Backup kem log

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Backup-QuanLyXuongData.ps1 -IncludeLogs
```

## Noi dung backup

```text
db\
  InBat.db
  InDecal.db
  CNC.db
files\
  *.json
  *.txt
manifest.json
```

## Khi nao chay

- Truoc moi lan publish ban moi.
- Truoc khi sua schema/database.
- Truoc khi bat bridge gui that sang QCVL.

## Luu y

- Backup nay khong commit Git.
- Khong chua mat khau neu config nhay cam van nam ngoai `C:\QuanLyXuong\Data`.
- Neu backup loi, khong deploy.
