# Quality gate runbook

Muc tieu: kiem tra nhanh code va script truoc khi build/publish.

## Chay quality gate

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongCode.ps1
```

Script kiem tra:

- Python dependencies.
- Compile cac file Python chinh.
- Cu phap toan bo script PowerShell trong `scripts`.
- Import config.
- Bridge dry-run smoke voi state/log tam trong `%TEMP%`.

## Khi nao chay

- Truoc khi build exe.
- Truoc khi publish.
- Sau khi AI sua code.

## Neu loi

Khong build, khong publish. Sua loi tren working tree/staging truoc.
