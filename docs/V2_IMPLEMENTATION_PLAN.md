# V2 implementation plan

Muc tieu: bien `Z:\Tools` thanh V2 an toan truoc khi gan that vao QCVL.

## Ket qua mong muon

```text
May san xuat
  -> QuanLyXuong V2 agent/server
  -> SQLite local buffer
  -> QCVL bridge dry-run/gui co kiem soat
  -> QCVL POS production queue
```

V2 khong tu tao bill, khong dung KiotViet, khong tu gui Zalo cho khach.

## Phase 1 - Dong bang va an toan release

Trang thai: da lam phan lon.

- Backup DB.
- Restore DB.
- Publish release co backup `dist` cu.
- Rollback release.
- Build vao `dist-new`.
- Admin console.
- Support bundle.
- Quality gate.
- Changelog.

Dieu kien xong:

- `Test-QuanLyXuongCode.ps1` OK.
- Build 5 exe OK.
- Publish/rollback script co canh bao va xac nhan.

## Phase 1.5 - Durable outbox may tram

Trang thai: da them nen tang.

Muc tieu: event tu may san xuat phai duoc ghi local truoc khi gui len server/QCVL, tranh mat event khi mat mang hoac restart.

Viec lam:

- Them `qlx_outbox.py` dung SQLite local.
- `QuanLyXuong.py` ghi event vao outbox truoc, worker nen gui sau.
- Moi event co `event_id` va `idempotency_key`.
- `server.py` luu `processed_event_keys` de retry khong ghi trung.
- Unit test outbox: enqueue, retry, mark sent, restart reload, duplicate event id.
- Healthcheck doc `agent_outbox_*.db` va canh bao pending event.
- Integration test folder scan bang temp dir, khong dung folder xuong that.
- `QuanLyXuong.py` co `run_universal_scan_once()` de test scanner khong can chay vong lap vo han.

Dieu kien xong:

- Mat mang khong block worker scan/log.
- Restart con thay event pending trong SQLite.
- Server nhan lai cung idempotency key thi bo qua an toan.
- Quality gate OK.
- `Test-QuanLyXuongHealth.ps1 -Role Machine` hien outbox pending count.
- `tests/test_quanlyxuong_scan.py` OK.
- One-cycle scan test bat duoc `EXPORT` va `DELETE`.
- One-cycle InDecal test bat duoc `RIP` sau rename `~meta`.
- One-cycle scanner ghi duoc event vao SQLite outbox tam.
- Dashboard `:5000` co tab `He thong` de xem DB may, outbox pending, version va log loi.
- `Invoke-V2CutoverPreflight.ps1` kiem tra cong cuoc thay V1 bang V2 truoc khi publish.

## Phase 2 - V2 runtime mode

Muc tieu: chay V2 ma khong kich hoat Auto_CRM/KiotViet/Zalo auto.

Viec lam:

- Them `QLX_RUNTIME_MODE=v2`.
- Them `QLX_ENABLE_AUTO_CRM=0`.
- Them `QLX_ENABLE_SERVER_ZALO=0`.
- `server.py` khong goi `/wake_up` Auto_CRM khi `DONE` neu flag tat.
- `server.py` khong gui Zalo server neu flag tat.
- Tao readiness check cho V2.

Dieu kien xong:

- V1 van giu default cu khi env chua set.
- V2 co env mau ro.
- Quality gate co test flag.

## Phase 3 - Bridge QCVL an toan

Muc tieu: bridge doc SQLite cu, xuat payload, chua gui that neu QCVL chua san sang.

Viec lam:

- Bridge mac dinh dry-run.
- Payload co `legacy_event_hash` chong trung.
- Export JSONL mau.
- Checkpoint rieng.
- Log rieng.
- Test JSONL sample.

Dieu kien xong:

- Bridge dry-run OK.
- Xuat sample OK.
- QCVL loi/khong co endpoint khong anh huong may san xuat.

## Phase 4 - Van hanh V2 tren PC/NAS

Muc tieu: de sau nay chuyen server trung tam len NAS.

Huong:

- May san xuat van chay agent local.
- NAS chay QCVL + PostgreSQL.
- V2 bridge/server co the chay tren PC tam thoi hoac NAS neu NAS doc/nhan du lieu on.
- Khong dua phan doc log local len NAS neu log chi nam tren may san xuat.

Dieu kien xong:

- Healthcheck thay ro DB, port, NAS path, process.
- Hostname may co the map bang `QLX_MACHINE_ALIASES`.
- Backup tu dong da co script cai.
- Restore co canh bao port dang chay.

## Phase 5 - Gan QCVL sau

Chua lam luc nay.

Chi lam khi V2 va contract on dinh:

- QCVL them `POST /api/v1/production-events`.
- QCVL them PostgreSQL `production_*`.
- QCVL doi `GET /api/v1/production-queue` tu mock sang DB.
- Bridge moi duoc bat `QCVL_BRIDGE_DRY_RUN=0`.

## Viec khong lam trong V2 hien tai

- Khong sua QCVL.
- Khong tu tao bill.
- Khong gui tin Zalo auto.
- Khong dung Selenium/KiotViet.
- Khong tu tru kho tu event may.
- Khong publish ban moi khi chua co lenh xac nhan.

## Checklist truoc khi thay ban cu

1. Quality gate OK.
2. Healthcheck OK.
3. Backup DB OK.
4. Build vao `dist-new` OK.
5. Bridge dry-run OK.
6. V2 readiness OK.
7. Outbox pending = 0 hoac biet ro ly do con pending.
8. `Invoke-V2CutoverPreflight.ps1` OK.
9. Publish trong luc xuong it viec.
10. Healthcheck sau publish OK.
11. Neu loi: rollback ngay.
