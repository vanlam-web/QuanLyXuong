# Ke hoach noi QuanLyXuong cu voi QCVL POS

Muc tieu: toi uu du an may san xuat hien tai de sau nay noi du lieu sang QCVL, khong lam gian doan xuong.

Quyet dinh hien tai: chuan hoa `Z:\Tools` thanh V2 truoc. QCVL chua sua trong giai doan nay; chi chuan bi contract, payload mau va checklist de gan sau.

## Hien trang

May san xuat dang chay `QuanLyXuong.py`.

Client gui event ve server cu:

```text
POST http://192.168.1.104:8000/api/log_event
```

Payload hien tai:

```json
{
  "machine": "inbat|indecal|cnc",
  "path": "duong_dan_file",
  "event_type": "EXPORT|RIP|PRINTING|CUTTING|DONE|DELETE",
  "forced_base_id": null,
  "forced_display_name": null,
  "thumbnail_b64": null
}
```

Server cu ghi SQLite:

```text
C:\QuanLyXuong\Data\InBat.db
C:\QuanLyXuong\Data\InDecal.db
C:\QuanLyXuong\Data\CNC.db
```

QCVL POS hien co UI `production-queue`, nhung backend hien tai moi co mock/demo data. Chua co endpoint nhan event that tu may san xuat.

Endpoint muc tieu cua QCVL:

```text
POST /api/v1/production-events
GET  /api/v1/production-queue
POST /api/v1/production-queue/{id}/add-to-draft
POST /api/v1/production-queue/{id}/dismiss
POST /api/v1/production-queue/{id}/restore
```

## Nguyen tac nang cap

- Khong sua client may san xuat truoc.
- Khong doi `/api/log_event` dang chay truoc.
- Khong bat may xuong gui truc tiep sang QCVL trong giai doan dau.
- Them bridge doc/bridge service doc lap, co the tat bat rieng.
- QCVL nhan du lieu san xuat nhu external integration, khong lam thay Source of Truth cu ngay lap tuc.
- V2 khong tu tao bill KiotViet.
- V2 khong tu gui tin Zalo cho khach.
- V2 chi day du lieu may sang POS QCVL de nhan vien xac nhan va tao bill.

## Huong noi an toan

Giai doan 1: Mirror tu server cu sang QCVL.

```text
QuanLyXuong client
  -> server.py cu /api/log_event
  -> SQLite cu
  -> QCVL bridge doc SQLite
  -> QCVL /api/v1/production-events
```

Giai doan nay neu QCVL loi thi xuong van chay binh thuong vi client khong phu thuoc QCVL.

Giai doan 2: QCVL co production tables that.

```text
production_machines
production_events
production_queue_items
production_heartbeats
```

QCVL POS doc `production_queue_items` that thay vi mock RAM.

Giai doan 3: Agent moi thay client cu tung may.

```text
May san xuat -> QCVL API -> PostgreSQL
```

Chi chuyen tung may sau khi co rollback.

## Mapping du lieu

| QuanLyXuong | QCVL |
|---|---|
| `machine=inbat` | `production_machine.code=INBAT` |
| `machine=indecal` | `production_machine.code=INDECAL` |
| `machine=cnc` | `production_machine.code=CNC` |
| `path` | `raw_file_path` |
| `basename(path)` | `raw_file_name` |
| `event_type` | `event_type` |
| `EXPORTED/RIP/PRINTING/CUTTING/DONE/DELETED` | `machine_status/job_status` |
| `thumbnail_b64` | `thumbnail_blob` hoac object storage sau |
| `created_time/updated_time/history` | `production_events.occurred_at`, `metadata` |

## De xuat schema QCVL toi thieu

```sql
create table production_machines (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  code text not null,
  name text not null,
  machine_type text not null check (machine_type in ('banner_print', 'decal_print', 'cnc_cut')),
  status text not null default 'active',
  unique (organization_id, code)
);

create table production_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  production_machine_id uuid not null references production_machines(id) on delete cascade,
  legacy_event_hash text not null,
  raw_file_name text not null,
  raw_file_path text not null,
  event_type text not null,
  occurred_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  unique (organization_id, legacy_event_hash)
);

create table production_queue_items (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  production_machine_id uuid not null references production_machines(id) on delete cascade,
  raw_file_name text not null,
  raw_file_path text not null,
  received_at timestamptz not null default now(),
  status text not null check (status in ('queued', 'added_to_draft', 'dismissed')),
  parse_status text not null check (parse_status in ('pending', 'ok', 'error')),
  parse_error text,
  parsed_payload jsonb not null default '{}'::jsonb,
  source_event_id uuid references production_events(id) on delete set null
);
```

## Viec nen lam tren `Z:\Tools`

1. Tach config `API_SERVER_URL` ra bien moi truong.
2. Them `QCVL_BRIDGE_ENABLED=false`.
3. Them `QCVL_API_BASE_URL` nhung mac dinh tat.
4. Viet bridge rieng doc SQLite cu, khong nam trong loop client may.
5. Them idempotency key de chong gui trung.
6. Log bridge ro: da gui, bi loi, se retry.

## Idempotency key de chong trung

Dung hash:

```text
machine + core_file_name + event_type + date + run_count
```

Khong dung timestamp thuan vi retry se sinh ban ghi trung.

## Uu tien tiep theo

1. Chuan hoa V2 trong `Z:\Tools`: config, log, test, build, backup, rollback.
2. Chay `bridge_qcvl.py` dry-run de xem payload doc tu SQLite cu.
3. Xuat payload mau va chot contract.
4. Chi sau khi QCVL san sang moi tao endpoint `POST /api/v1/production-events`.
5. Tao repository production trong QCVL PostgreSQL.
6. Doi `GET /api/v1/production-queue` tu mock sang DB.
7. Bat `QCVL_BRIDGE_DRY_RUN=0` khi QCVL endpoint san sang.

## Bridge dry-run da them

Chay mot lan:

```powershell
python Z:\Tools\bridge_qcvl.py --dry-run
```

Chay vong lap moi 30 giay:

```powershell
python Z:\Tools\bridge_qcvl.py --dry-run --loop --interval 30
```

Xuat mau payload JSONL de review contract QCVL:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Export-QcvlBridgeSample.ps1
```

Log:

```text
C:\QuanLyXuong\QCVL_Bridge_Log.txt
```

Checkpoint:

```text
C:\QuanLyXuong\Data\qcvl_bridge_state.json
```

Ghi chu: dry-run mac dinh co luu checkpoint de tranh in lai cung mot lo event. Neu muon xem lai, xoa file checkpoint hoac chay voi state-file khac.
