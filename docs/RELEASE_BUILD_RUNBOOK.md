# Release build runbook

Muc tieu: build ban exe moi vao `dist-new`, khong ghi de `dist` dang chay.

## Build ban moi

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Build-Release.ps1 -Clean
```

Output:

```text
Z:\Tools\dist-new
  server.exe
  Dashboard.exe
  QuanLyXuong.exe
  bridge_qcvl.exe
  Auto_CRM.exe
  BUILD_MANIFEST.json
```

Smoke test da xac nhan script build duoc exe vao thu muc tam:

```text
server.exe
Dashboard.exe
QuanLyXuong.exe
bridge_qcvl.exe
Auto_CRM.exe
```

## Publish sau khi build

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Publish-Release.ps1 -NewDistPath Z:\Tools\dist-new
```

Publish se backup DB va backup `dist` cu truoc khi thay file.

## Cach dung de an toan

1. Build vao `dist-new`.
2. Kiem tra file exe co mat.
3. Chon thoi diem xuong it viec.
4. Publish.
5. Healthcheck.
6. Neu loi, rollback.
