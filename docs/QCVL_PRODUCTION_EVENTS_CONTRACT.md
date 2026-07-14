# QCVL production events contract

Muc tieu: dinh nghia payload tu `Z:\Tools\bridge_qcvl.py` sang QCVL truoc khi tao endpoint that.

Endpoint muc tieu:

```text
POST /api/v1/production-events
```

## Nguyen tac

- Endpoint phai idempotent theo `legacy_event_hash`.
- Nhan trung cung `legacy_event_hash` thi tra success, khong tao ban ghi moi.
- Khong tu tao hoa don, khong tru kho, khong sua cong no.
- Chi ghi production event va cap nhat production queue.
- Neu parse loi, van luu event, queue item co `parse_status=error|pending`.

## Headers

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Giai doan bridge noi bo co the dung token service rieng sau.

## Request body

Vi du:

```json
{
  "legacy_event_hash": "9ffb298ed889fd0dd73cf0b4ba15912b8348864efc448e24581e63ab0c655c39",
  "source": "QuanLyXuong",
  "machine": {
    "legacy_name": "InBat",
    "code": "INBAT",
    "name": "In bat",
    "machine_type": "banner_print"
  },
  "raw_file_name": "ut_140x230.prt",
  "raw_file_path": "D:\\2026-07-09\\New Folder\\ut_140x230.prt",
  "event_type": "DONE",
  "job_type": "EXPORT",
  "status": "DONE",
  "received_at": "2026-07-09 08:17:50",
  "updated_at": "2026-07-09 09:03:57",
  "run_count": 1,
  "parse_status": "ok",
  "parse_error": null,
  "parsed": {
    "customer_code": "ut",
    "width_m": 1.4,
    "height_m": 2.3,
    "quantity": 1,
    "raw_name": "ut_140x230"
  },
  "legacy": {
    "file_hash": "c13812637b379ddf2baf79914b536707",
    "history": []
  }
}
```

## Field rules

| Field | Type | Required | Note |
|---|---:|---:|---|
| `legacy_event_hash` | string | yes | 64-char sha256, idempotency key |
| `source` | string | yes | `QuanLyXuong` |
| `machine.legacy_name` | string | yes | `InBat`, `InDecal`, `CNC` |
| `machine.code` | string | yes | `INBAT`, `INDECAL`, `CNC` |
| `machine.name` | string | yes | Display name |
| `machine.machine_type` | string | yes | `banner_print`, `decal_print`, `cnc_cut` |
| `raw_file_name` | string | yes | Basename |
| `raw_file_path` | string | yes | Legacy path |
| `event_type` | string | yes | `EXPORTED`, `RIP`, `PRINTING`, `CUTTING`, `DONE`, `DELETED` |
| `job_type` | string | no | Legacy job type |
| `status` | string | yes | Legacy status |
| `received_at` | string | yes | Legacy created time |
| `updated_at` | string | yes | Legacy updated time |
| `run_count` | number | yes | Legacy repeat count |
| `parse_status` | string | yes | `pending`, `ok`, `error` |
| `parse_error` | string/null | no | Reason when not ok |
| `parsed.customer_code` | string/null | no | Parsed from filename |
| `parsed.width_m` | number/null | no | Width in meters |
| `parsed.height_m` | number/null | no | Height in meters |
| `parsed.quantity` | number | yes | Defaults 1 |
| `parsed.raw_name` | string | yes | Filename without extension after cleanup |
| `legacy.file_hash` | string | yes | SQLite old key |
| `legacy.history` | array | no | Old timeline |

## Response

Created:

```json
{
  "success": true,
  "data": {
    "event_id": "uuid",
    "queue_item_id": "uuid",
    "deduped": false
  },
  "trace_id": "..."
}
```

Duplicate:

```json
{
  "success": true,
  "data": {
    "event_id": "uuid",
    "queue_item_id": "uuid",
    "deduped": true
  },
  "trace_id": "..."
}
```

Validation error:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid production event payload."
  },
  "trace_id": "..."
}
```

## Queue behavior

QCVL nen tao/cap nhat `production_queue_items` khi event co y nghia dua vao POS:

| Event | Queue behavior |
|---|---|
| `EXPORTED` | create/update queued item |
| `RIP` | update latest event/status |
| `PRINTING` | update latest event/status |
| `CUTTING` | update latest event/status |
| `DONE` | keep/update queued item; POS can add to draft |
| `DELETED` | mark dismissed/cancelled if not already added |

Trong MVP, POS production queue co the chi hien items status `queued` va event moi nhat la `DONE|EXPORTED|RIP`.

## Suggested PostgreSQL tables

```sql
create table production_machines (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  code text not null,
  name text not null,
  machine_type text not null check (machine_type in ('banner_print', 'decal_print', 'cnc_cut')),
  status text not null default 'active' check (status in ('active', 'inactive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, code)
);

create table production_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  production_machine_id uuid not null references production_machines(id) on delete cascade,
  legacy_event_hash text not null,
  source text not null,
  raw_file_name text not null,
  raw_file_path text not null,
  event_type text not null,
  job_type text,
  legacy_status text not null,
  received_at timestamptz not null,
  updated_at timestamptz not null,
  run_count integer not null default 1,
  parse_status text not null check (parse_status in ('pending', 'ok', 'error')),
  parse_error text,
  parsed_payload jsonb not null default '{}'::jsonb,
  legacy_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (organization_id, legacy_event_hash)
);

create table production_queue_items (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  production_machine_id uuid not null references production_machines(id) on delete cascade,
  source_event_id uuid references production_events(id) on delete set null,
  raw_file_name text not null,
  raw_file_path text not null,
  received_at timestamptz not null,
  latest_event_type text not null,
  status text not null check (status in ('queued', 'added_to_draft', 'dismissed')),
  parse_status text not null check (parse_status in ('pending', 'ok', 'error')),
  parse_error text,
  parsed_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

## Next QCVL tasks

1. Add DB schema/migration for production tables.
2. Add repository methods for upsert machine/event/queue.
3. Add `POST /api/v1/production-events`.
4. Change `GET /api/v1/production-queue` from mock RAM to DB.
5. Keep `add-to-draft` idempotent and permission-checked.
