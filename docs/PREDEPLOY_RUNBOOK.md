# Pre-deploy runbook

Muc tieu: truoc khi publish ban moi, chay mot lenh gom cac buoc an toan.

## Chay preflight

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-PreDeployCheck.ps1
```

Script se chay:

1. Quality gate.
2. Healthcheck.
3. Backup database.
4. Tao support bundle.

Neu buoc nao loi thi dung, khong deploy.

## Khi nao dung

- Truoc khi build/publish ban moi.
- Truoc khi bat bridge gui that sang QCVL.
- Khi muon gom trang thai he thong truoc luc sua lon.

## Tuy chon

Bo qua backup neu da backup rieng:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-PreDeployCheck.ps1 -SkipBackup
```

Bo qua support bundle:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-PreDeployCheck.ps1 -SkipSupportBundle
```
