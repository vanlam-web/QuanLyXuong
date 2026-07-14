# Test runbook

Muc tieu: co test nho cho logic quan trong truoc khi refactor va noi QCVL.

## Chay unit test

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Run-UnitTests.ps1
```

Hien co test cho:

- `bridge_qcvl.parse_filename`
- mapping payload bridge sang QCVL
- doc config tu environment variable

## Chay toan bo quality gate

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongCode.ps1
```

Quality gate se chay unit test kem compile va syntax check.
