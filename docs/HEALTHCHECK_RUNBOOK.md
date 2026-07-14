# Healthcheck runbook

Muc tieu: kiem tra nhanh he thong xuong co cac thanh phan co ban hay khong.

## Chay healthcheck

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1
```

Kiem tra rieng may server:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1 -Role Server
```

Kiem tra rieng may san xuat:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1 -Role Machine
```

Script kiem tra:

- Thu muc `C:\QuanLyXuong\Data`
- DB `InBat.db`, `InDecal.db`, `CNC.db`
- Port `8000` server cu
- Port `5000` dashboard cu
- Port `8001` Auto CRM neu legacy/Auto_CRM dang bat
- OpenClaw command neu Auto_CRM hoac Zalo server dang bat
- NAS dist path
- Process local neu dang chay

Trong V2, neu `QLX_ENABLE_AUTO_CRM=0` va `QLX_ENABLE_SERVER_ZALO=0`, healthcheck se khong bat buoc Auto_CRM/OpenClaw.

## Cach doc ket qua

```text
[OK]   Thanh phan co mat / dang mo
[WARN] Thanh phan khong thay
```

Healthcheck co `WARN` khong luon co nghia la loi. Vi du may con khong chay Dashboard thi port `5000` co the WARN.

## Khi nao chay

- Truoc deploy.
- Sau deploy.
- Sau rollback.
- Khi xuong bao phan mem khong cap nhat hoac khong gui du lieu.
