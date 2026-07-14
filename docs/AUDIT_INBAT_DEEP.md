# Audit InBat deep - 2026-07-11

## Pham vi

Muc tieu: kiem tra sau may InBat khi may hien khong mo, khong truy cap duoc qua LAN.

Nguon da doc:

- `http://127.0.0.1:5000/api/v2_status`
- `C:\QuanLyXuong\Data\InBat.db`
- `C:\QuanLyXuong\Server_Log.txt`
- `Z:\Tools\app\QuanLyXuong.py`
- `Z:\Tools\app\qlx_workstation_logic.py`
- `Z:\Tools\app\qlx_outbox.py`
- `Z:\Tools\app\server.py`
- `Z:\Tools\tests\test_server_reprint_noise.py`
- `Z:\Tools\tests\test_qlx_workstation_logic.py`
- `Z:\Tools\tests\test_qlx_outbox.py`

## Trang thai hien tai

May InBat hien khong truy cap duoc:

- `Test-Connection InBat`: fail.
- `net view \\InBat`: `System error 53`, khong thay network path.

Dashboard status:

- `online=false`.
- `network_online=false`.
- `last_ping=2026-07-11 17:30:46`.
- `latest_machine_update=2026-07-11 17:30:21`.
- `version=V2.0.2_INDECAL_THUMB_FIX`.
- `done_today=7`.
- `active=0`.
- `old_active=1`.

Nhan dinh:

- Dashboard bao InBat chua mo la dung voi hien trang.
- Khong the doc live `PrintFile.ini`, outbox, log local tren InBat cho den khi may mo lai.
- Ban version dang dung chung ten voi fix InDecal, nen sau nay nen dat version theo nhom: `V2.x_INBAT_...`.

## Du lieu InBat hom nay

Trong `InBat.db`, ngay `2026-07-11` co 7 job DONE, khong co job dang chay hom nay:

| File | Trang thai | PRINTING | DONE | Thoi gian chay |
| --- | --- | --- | --- | --- |
| `KL_360X200.prt` | DONE | 08:58:18 | 09:08:39 | 10 phut 21 giay |
| `balong_162x120_Ngay10.prt` | DONE | 09:23:28 | 09:27:02 | 3 phut 34 giay |
| `an_15x8.prt` | DONE | 14:48:17 | 14:48:33 | 16 giay |
| `noithat_240x570.prt` | DONE | 15:20:53 | 15:40:02 | 19 phut 9 giay |
| `quochoang_270x240.prt` | DONE | 16:40:41 | 16:49:13 | 8 phut 32 giay |
| `quochoang_366x2544.prt` | DONE | 17:00:16 | 17:19:41 | 19 phut 25 giay |
| `hhhh_85x210.prt` | DONE | 17:25:33 | 17:30:21 | 4 phut 48 giay |

Ton cu:

- `balong_162x120.tif`
- `status=EXPORTED`
- `created_time=2026-07-10 17:25:48`
- Day la ton cu chua tinh hom nay, khong phai file dang chay hom nay.

## Truong hop `thanhnhan_450x60_bron_catdan2dau.prt`

DB dang co 2 dong:

1. Dong DONE:
   - `EXPORTED`: `2026-07-10 10:55:23`
   - `RIP`: `2026-07-10 15:06:39`
   - `PRINTING`: `2026-07-10 15:26:40`
   - `DONE`: `2026-07-10 15:27:57`
   - Thoi gian in: 1 phut 17 giay.

2. Dong DELETED:
   - `PRINTING`: `2026-07-10 15:29:33`
   - `DELETED`: `2026-07-10 15:48:14`
   - `cancel_type=production_cancel`
   - `progress_percent=null`

Nhan dinh:

- Theo nghiep vu da chot: DONE lan 1 sau do PRINTING lan 2 ma khong co `_x2/_xSL` thi la nghi van in lai.
- Neu lan 2 bi DELETE giua chung, can tinh % hỏng tu thoi gian/du lieu may in.
- Hien InBat chua co du lieu toc do/phan tram de tinh % hỏng, nen `progress_percent=null`.
- Thoi gian 1 phut 17 giay cho file 450x60 la bat thuong theo quan sat user, can co rule canh bao theo kich thuoc va lich su may, khong dung nguong co dinh.

## Dau hieu replay sau restart

`Server_Log.txt` co nhieu dong sau 18:47 ngay 2026-07-11:

- `[INBAT] EXPORTED: ntdq_800x310.tif`
- `[INBAT] DELETE: ntdq_800x310.tif`
- `[INBAT] PRINTING: thanhnhan_450x60_bron_catdan2dau.prt`
- `[INBAT] DONE: thanhnhan_450x60_bron_catdan2dau.prt`
- `[REPRINT-WAIT] ... nhan PRINTING moi luc 2026-07-10 15:29:33`

Nhung status ping InBat cuoi cung la `17:30:46`.

Nhan dinh:

- Cac log sau 18:47 khong khop voi viec may InBat dang tat.
- Kha nang cao day la replay tu event cu/outbox cu hoac server/process cu khi restart.
- DB khong tang them dong moi hom nay cho cac job nay, nhung log bi nhieu lam dashboard/audit de gay nham.

## Diem code chua chat che

### 1. Idempotency tren workstation con ngau nhien

`qlx_outbox.py`:

- Neu payload khong co `event_id`, outbox tao UUID moi.
- `idempotency_key` mac dinh bang UUID.

Rui ro:

- Cung mot tin hieu `PRINTING/DONE` neu bi enqueue lai sau restart se co UUID moi.
- Server khong biet day la cung event logic, chi biet la key moi.

Huong fix:

- Moi event tu workstation can co key xac dinh:
  - `machine`
  - `event_type`
  - normalized path/base id
  - source event time hoac source snapshot hash
  - source type: `scan`, `printmon`, `log`

### 2. Server tinh hash theo ngay hien tai

`server.py`:

- `today_str = datetime.now().strftime("%Y-%m-%d")`
- Hash file active/done dung `today_str`, khong dung ngay cua `event_time`.

Rui ro:

- Event cu ngay 10/07 replay vao ngay 11/07 co the bi map vao hash ngay 11/07.
- Truong hop DB hien chua bi phinh do logic khac chan bot, nhung day van la rui ro.

Huong fix:

- Hash logical job nen dung ngay cua `event_time` hoac ngay folder trong path.
- Neu event cu replay, no phai ve dung bucket ngay cu.

### 3. InBat PrintMon chi doc snapshot, khong co metadata

`worker_inbat_log()`:

- Doc `PrintFile.ini` / `PrintFile`.
- So sanh raw bytes voi `last_raw`.
- Parse path `.prt/.prn` va switch byte `1/2`.
- `1` = PRINTING, `2` = DONE.

Thieu:

- Khong gui `source_mtime`.
- Khong gui `source_size`.
- Khong gui `client_start_time`.
- Khong gui `printmon_path`.
- Khong gui raw hash de debug.

Rui ro:

- Khi may mo lai, neu PrintMon ghi lai snapshot cu hoac file bi chinh mtime, server kho phan biet cu/moi.

### 4. PRINTING sau DONE co xu ly nhung chua du chan replay

Server hien co logic:

- DONE roi nhan PRINTING moi -> tao reprint row/cho DONE lan 2.

Dung cho nghiep vu in lai that.

Rui ro:

- Neu PRINTING do replay, server co the hieu la in lai.
- Can them guard: neu event_time cu hon `last_ping/current_server_day` qua nguong, hoac source snapshot khong doi, thi danh dau `replay_suspect` thay vi tao san xuat moi.

### 5. DELETE sau DONE tu scan folder dang gay nhieu log phu

Sau DONE, file `.prt` co the bi xoa/move khoi `New Folder`, server log `DELETE`.

Hien server da giu DONE, khong doi sang DELETED neu khong co active hash phu hop. Nhung log van nhieu.

Huong fix:

- Neu DELETE cua `.prt/.prn` den sau DONE cung core trong khoang thoi gian ngan, ghi vao audit phu hoac bo qua log san xuat.
- Khong dua vao cot HUY/LOI neu file da DONE.

## Viec co the lam ngay khi InBat dang tat

1. Them deterministic event id cho workstation.
2. Sua server hash dung ngay `event_time`/ngay folder, khong dung `datetime.now()`.
3. Them replay guard cho event cu.
4. Them health payload cho InBat:
   - client start time
   - current PrintMon path
   - PrintMon mtime/size/hash
   - last parsed job/switch
   - outbox pending count
5. Sua dashboard de hien:
   - `May tinh InBat`: mo/tat.
   - `Client V2`: ping cuoi.
   - `PrintMon`: doc duoc/khong, update luc nao.
   - `Outbox`: con pending khong.
   - `Ton cu`: tach rieng, khong tinh vao dang chay hom nay.
6. Them tests cho replay:
   - Cung event logic, UUID khac, server van bo qua.
   - Event ngay cu replay sang ngay moi khong tao hash ngay moi.
   - PRINTING sau DONE voi event_time cu bi danh dau replay, khong tao reprint moi.

## Viec can cho InBat mo lai

1. Doc file live:
   - `C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile.ini`
   - `C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile`
2. Doc outbox local:
   - file `agent_outbox.db` neu co.
3. Xem log local:
   - `C:\QuanLyXuong\system_log.txt`
   - cac file log runtime neu co.
4. Test 1 job nho:
   - EXPORT -> RIP -> PRINTING -> DONE.
   - Restart client giua chung de xem co replay khong.
5. Test in lai:
   - DONE lan 1 -> PRINTING lan 2 -> DONE.
   - DONE lan 1 -> PRINTING lan 2 -> DELETE giua chung.

## Ket luan

InBat hien khong mo, nhung du lieu server cho thay:

- Khong co job InBat dang chay hom nay.
- Co 1 ton cu ngay 10/07 can tach khoi man hinh chinh.
- `thanhnhan_450x60...` la case nghi van in lai/replay can dung de test.
- Rui ro lon nhat khong nam o UI, ma nam o replay/idempotency va cach server dung ngay hien tai de tinh hash.

Uu tien fix tiep:

1. Chot idempotency logic theo event that.
2. Chot hash theo ngay event/path.
3. Them health/debug metadata cho InBat.
4. Sau khi InBat mo lai moi test live PrintMon va outbox.

## Da lam khi may InBat dang tat - 2026-07-11

Da sua trong source, chua restart runtime live:

- `Z:\Tools\app\qlx_workstation_logic.py`
  - Them `make_event_identity()`.
  - Key co dinh theo `machine + event_type + path/forced_base_id + event_time`.
  - Cung mot event logic se ra cung key, du restart/outbox retry.

- `Z:\Tools\app\QuanLyXuong.py`
  - `process_event()` tu gan:
    - `event_time`
    - `event_id`
    - `idempotency_key`
  - Outbox se luu key co dinh thay vi de UUID ngau nhien.

- `Z:\Tools\app\server.py`
  - Them `storage_day_for_event()`.
  - Hash job dung ngay cua `event_time` truoc, neu khong co moi doc ngay trong path, cuoi cung moi dung ngay server.
  - Them `logical_event_key()`.
  - Server check ca `idempotency_key` tu client va `logical:` key tu server.
  - Neu cung event logic nhung UUID khac, server van bo qua.

- Tests:
  - `test_same_logical_done_with_different_uuid_is_ignored`
  - `test_storage_day_uses_event_time_before_server_today`
  - `test_event_identity_is_stable_for_same_logical_event`

Muc dich:

- Giam rui ro file cu tu InBat nhay lai sau restart.
- Giam rui ro event ngay cu bi tinh vao bucket ngay moi.
- Giu duoc nghiep vu in lai that: neu DONE lan 2 co thoi gian khac, event logic khac, server van co the tinh lan in moi.

## Chua lam khi InBat dang tat

Can cho may InBat mo hoac can build/publish truoc:

- Chua doc duoc `PrintFile.ini` live.
- Chua doc duoc outbox local tren may InBat.
- Chua biet PrintMon co ghi snapshot cu khi may mo lai hay khong.
- Chua them day du health PrintMon len dashboard.
- Chua deploy ban source moi ra `C:\QuanLyXuong`/NAS runtime.

## Viec can lam ngay sau khi mo InBat

1. Kiem tra LAN:
   - `ping InBat`
   - `net view \\InBat`

2. Doc file PrintMon live:
   - `C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile.ini`
   - `C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile`

3. Doc outbox local:
   - `C:\QuanLyXuong\Data\agent_outbox_inbat.db`
   - Neu co pending cu, kiem tra truoc khi cho gui lai.

4. Test job nho:
   - EXPORT -> RIP -> PRINTING -> DONE.
   - Restart client giua chung.
   - Xac nhan khong replay file cu.

5. Test in lai:
   - DONE lan 1 -> PRINTING lan 2 -> DONE.
   - DONE lan 1 -> PRINTING lan 2 -> DELETE.
   - Xac nhan thong ke loi/hong khong dem sai.
