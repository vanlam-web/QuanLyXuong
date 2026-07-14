# Support bundle runbook

Muc tieu: khi he thong loi, gom thong tin can thiet vao mot file zip de AI/doc ky thuat xem nhanh.

## Tao support bundle

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\New-SupportBundle.ps1
```

Output:

```text
Z:\Tools\support-bundles\support-YYYYMMDD-HHMMSS.zip
```

## Noi dung

- Healthcheck output.
- Python environment output.
- Git status va 5 commit gan nhat.
- Danh sach file project.
- Danh sach file data.
- Tail log server/dashboard/Auto CRM/QCVL bridge.
- Mot so tai lieu du an: changelog, master plan, env example.
- Danh sach process lien quan.

## Bao mat

Script khong copy:

- `.env`
- `KhoiDongBot.bat`
- file credential local
- database `.db`

Neu can gui cho AI/nguoi khac, van nen xem nhanh zip truoc khi gui neu co du lieu nhay cam trong log.
