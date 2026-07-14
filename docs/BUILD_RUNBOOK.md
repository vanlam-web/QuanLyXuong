# Build runbook

Muc tieu: co danh sach dependency ro de build/chay lai may moi.

## Kiem tra moi truong Python

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-PythonEnvironment.ps1
```

Neu thieu package, cai:

```powershell
python -m pip install -r Z:\Tools\requirements.txt
```

## File dependency

```text
Z:\Tools\requirements.txt
```

Danh sach nay gom cac package dang can cho:

- `server.py`
- `Dashboard.py`
- `Auto_CRM.py`
- `QuanLyXuong.py`
- build exe bang PyInstaller

## Ghi chu

- `pillow` la optional cho thumbnail tren client, nhung nen co.
- `pyinstaller` can cho build exe.
- Script nay chi kiem tra moi truong, khong build va khong deploy.

## Build release exe

Xem [RELEASE_BUILD_RUNBOOK.md](./RELEASE_BUILD_RUNBOOK.md).
