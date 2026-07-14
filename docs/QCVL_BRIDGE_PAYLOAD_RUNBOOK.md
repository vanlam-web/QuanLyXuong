# QCVL bridge payload runbook

Muc tieu: xuat mau payload ma bridge se gui sang QCVL, nhung khong gui that.

## Xuat mau payload

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Export-QcvlBridgeSample.ps1
```

Output nam trong:

```text
Z:\Tools\support-bundles\bridge-sample-YYYYMMDD-HHMMSS\production-events.jsonl
```

Moi dong la mot JSON payload cho endpoint QCVL tuong lai:

```text
POST /api/v1/production-events
```

## Ghi chu

- Script dung `--dry-run`.
- Script dung `--no-save-checkpoint`, nen khong anh huong checkpoint bridge that.
- Dung file JSONL nay de chot contract voi QCVL truoc khi bat gui that.
